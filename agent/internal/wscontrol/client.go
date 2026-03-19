// Package wscontrol implémente le canal de contrôle WebSocket entre l'agent
// et le serveur Master.
//
// Protocole :
//
//	Server → Agent  {"action":"start_logs","container_id":"…","session_id":"…","tail":"50"}
//	Server → Agent  {"action":"stop_logs","session_id":"…"}
//	Agent  → Server {"type":"log","session_id":"…","container_id":"…","stream":"stdout","line":"…"}
//	Agent  → Server {"type":"eof","session_id":"…","container_id":"…"}
//	Agent  → Server {"type":"error","session_id":"…","container_id":"…","line":"…"}
//
// Seul un goroutine écrit sur la connexion WebSocket (writePump) — gorilla/websocket
// n'autorise pas les écritures concurrentes.
package wscontrol

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"
	"time"

	dockerclient "github.com/docker/docker/client"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/gorilla/websocket"
)

// ── Types de messages ─────────────────────────────────────────────────────────

// Command est reçue depuis le serveur.
type Command struct {
	Action      string `json:"action"`       // "start_logs" | "stop_logs"
	ContainerID string `json:"container_id"`
	SessionID   string `json:"session_id"`
	Tail        string `json:"tail"` // "50", "100", "all" — vide = "50"
}

// LogLine est envoyée vers le serveur.
type LogLine struct {
	Type        string `json:"type"`         // "log" | "eof" | "error"
	SessionID   string `json:"session_id"`
	ContainerID string `json:"container_id"`
	Stream      string `json:"stream,omitempty"` // "stdout" | "stderr"
	Line        string `json:"line,omitempty"`
}

// ── Client ────────────────────────────────────────────────────────────────────

const (
	sendBufSize    = 256              // taille du canal de sortie
	pingInterval   = 30 * time.Second
	writeTimeout   = 10 * time.Second
	handshakeTimeout = 10 * time.Second
)

// Client gère la connexion WebSocket persistante vers le Master et
// orchestre les sessions de streaming de logs Docker.
type Client struct {
	masterURL string              // ex. ws://localhost:8000
	nodeID    string
	docker    *dockerclient.Client

	sendCh  chan []byte            // canal sérialisé unique (writePump est l'unique writer)
	sessions map[string]context.CancelFunc
	mu       sync.Mutex
}

// New crée un Client. docker peut être nil si Docker n'est pas disponible
// (le client détecte les erreurs au moment de la requête de logs).
func New(masterURL, nodeID string, docker *dockerclient.Client) *Client {
	return &Client{
		masterURL: masterURL,
		nodeID:    nodeID,
		docker:    docker,
		sendCh:    make(chan []byte, sendBufSize),
		sessions:  make(map[string]context.CancelFunc),
	}
}

// DockerProvider est satisfait par *docker.Collector pour découpler les packages.
type DockerProvider interface {
	DockerClient() *dockerclient.Client
}

// NewFromCollector est un raccourci qui extrait le client Docker depuis un Collector.
// Si provider est nil (Docker absent), docker est également nil — le wscontrol
// répondra avec une erreur explicite au frontend lors des demandes de logs.
func NewFromCollector(masterURL, nodeID string, provider DockerProvider) *Client {
	var docker *dockerclient.Client
	if provider != nil {
		docker = provider.DockerClient()
	}
	return New(masterURL, nodeID, docker)
}

// Run établit (et maintient) la connexion WebSocket vers le Master.
// Retourne une erreur lorsque la connexion est perdue (runWithBackoff reconnecte).
func (c *Client) Run(ctx context.Context) error {
	// Contexte de connexion : annulé quand Run retourne (nettoie toutes les sessions)
	connCtx, cancelConn := context.WithCancel(ctx)
	defer cancelConn()

	url := fmt.Sprintf("%s/ws/agent/%s", c.masterURL, c.nodeID)

	dialer := websocket.Dialer{
		HandshakeTimeout: handshakeTimeout,
		// En production derrière Nginx wss:// la validation TLS est gérée par net/http
	}

	conn, resp, err := dialer.DialContext(ctx, url, http.Header{})
	if err != nil {
		if resp != nil {
			return fmt.Errorf("WS dial %s (HTTP %d): %w", url, resp.StatusCode, err)
		}
		return fmt.Errorf("WS dial %s: %w", url, err)
	}
	defer conn.Close()

	log.Printf("[wscontrol] connecté au Master (%s)", url)

	// Vider le canal de sortie pour éviter les fuites de l'ancienne connexion
	c.drainSendCh()

	// Unique goroutine d'écriture WebSocket
	go c.writePump(conn, connCtx)

	// Boucle de lecture des commandes
	for {
		var cmd Command
		if err := conn.ReadJSON(&cmd); err != nil {
			return fmt.Errorf("WS read: %w", err)
		}
		switch cmd.Action {
		case "start_logs":
			c.handleStartLogs(connCtx, cmd)
		case "stop_logs":
			c.handleStopLogs(cmd.SessionID)
		default:
			log.Printf("[wscontrol] commande inconnue : %q", cmd.Action)
		}
	}
}

// ── Write pump ────────────────────────────────────────────────────────────────

func (c *Client) writePump(conn *websocket.Conn, ctx context.Context) {
	ticker := time.NewTicker(pingInterval)
	defer ticker.Stop()

	for {
		select {

		case data, ok := <-c.sendCh:
			if !ok {
				return
			}
			conn.SetWriteDeadline(time.Now().Add(writeTimeout))
			if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
				log.Printf("[wscontrol] writePump erreur : %v", err)
				return
			}

		case <-ticker.C:
			conn.SetWriteDeadline(time.Now().Add(writeTimeout))
			if err := conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}

		case <-ctx.Done():
			conn.SetWriteDeadline(time.Now().Add(writeTimeout))
			conn.WriteMessage(websocket.CloseMessage,
				websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
			return
		}
	}
}

func (c *Client) send(msg LogLine) {
	data, err := json.Marshal(msg)
	if err != nil {
		return
	}
	select {
	case c.sendCh <- data:
	default:
		// Canal plein : message abandonné (backpressure)
		log.Printf("[wscontrol] canal plein, log abandonné (session=%s)", msg.SessionID)
	}
}

func (c *Client) drainSendCh() {
	for {
		select {
		case <-c.sendCh:
		default:
			return
		}
	}
}

// ── Gestion des sessions de logs ──────────────────────────────────────────────

func (c *Client) handleStartLogs(ctx context.Context, cmd Command) {
	// Annuler une éventuelle session précédente avec le même ID
	c.handleStopLogs(cmd.SessionID)

	sessionCtx, cancel := context.WithCancel(ctx)
	c.mu.Lock()
	c.sessions[cmd.SessionID] = cancel
	c.mu.Unlock()

	log.Printf("[wscontrol] démarrage logs — session=%s conteneur=%s", cmd.SessionID, cmd.ContainerID)
	go c.streamDockerLogs(sessionCtx, cmd)
}

func (c *Client) handleStopLogs(sessionID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if cancel, ok := c.sessions[sessionID]; ok {
		cancel()
		delete(c.sessions, sessionID)
		log.Printf("[wscontrol] session logs arrêtée — session=%s", sessionID)
	}
}

// ── Streaming Docker ──────────────────────────────────────────────────────────

func (c *Client) streamDockerLogs(ctx context.Context, cmd Command) {
	defer func() {
		c.send(LogLine{Type: "eof", SessionID: cmd.SessionID, ContainerID: cmd.ContainerID})
		c.mu.Lock()
		delete(c.sessions, cmd.SessionID)
		c.mu.Unlock()
	}()

	if c.docker == nil {
		c.send(LogLine{
			Type: "error", SessionID: cmd.SessionID,
			ContainerID: cmd.ContainerID,
			Line:        "Docker non disponible sur cet agent.",
		})
		return
	}

	// Inspecter le conteneur pour détecter le mode TTY
	info, err := c.docker.ContainerInspect(ctx, cmd.ContainerID)
	if err != nil {
		c.send(LogLine{
			Type: "error", SessionID: cmd.SessionID,
			ContainerID: cmd.ContainerID,
			Line:        fmt.Sprintf("ContainerInspect: %v", err),
		})
		return
	}
	hasTTY := info.Config != nil && info.Config.Tty

	tail := cmd.Tail
	if tail == "" {
		tail = "50"
	}

	rc, err := c.docker.ContainerLogs(ctx, cmd.ContainerID, container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Follow:     true,
		Timestamps: true,
		Tail:       tail,
	})
	if err != nil {
		c.send(LogLine{
			Type: "error", SessionID: cmd.SessionID,
			ContainerID: cmd.ContainerID,
			Line:        fmt.Sprintf("ContainerLogs: %v", err),
		})
		return
	}
	defer rc.Close()

	if hasTTY {
		// Pas de header de multiplexage : lecture directe
		c.scanLines(ctx, rc, cmd, "stdout")
	} else {
		// Démultiplexer stdout et stderr via des pipes
		stdoutPR, stdoutPW := io.Pipe()
		stderrPR, stderrPW := io.Pipe()

		go func() {
			defer stdoutPW.Close()
			defer stderrPW.Close()
			if _, err := stdcopy.StdCopy(stdoutPW, stderrPW, rc); err != nil {
				// Erreur normale à l'arrêt du contexte
				_ = err
			}
		}()

		var wg sync.WaitGroup
		wg.Add(2)
		go func() { defer wg.Done(); c.scanLines(ctx, stdoutPR, cmd, "stdout") }()
		go func() { defer wg.Done(); c.scanLines(ctx, stderrPR, cmd, "stderr") }()
		wg.Wait()
	}
}

// scanLines lit un flux ligne par ligne et l'envoie au Master.
func (c *Client) scanLines(ctx context.Context, r io.Reader, cmd Command, stream string) {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 64*1024), 64*1024) // lignes jusqu'à 64 Ko

	for scanner.Scan() {
		select {
		case <-ctx.Done():
			return
		default:
		}
		c.send(LogLine{
			Type:        "log",
			SessionID:   cmd.SessionID,
			ContainerID: cmd.ContainerID,
			Stream:      stream,
			Line:        scanner.Text(),
		})
	}
}
