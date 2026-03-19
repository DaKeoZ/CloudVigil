package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/cloudvigil/agent/internal/connect"
	dockercollector "github.com/cloudvigil/agent/internal/docker"
	"github.com/cloudvigil/agent/internal/metrics"
	"github.com/cloudvigil/agent/internal/wscontrol"
	"github.com/cloudvigil/agent/pb"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// config regroupe tous les paramètres de l'agent issus des variables d'environnement.
type config struct {
	ServerAddr      string
	NodeID          string
	CollectInterval time.Duration
	DiskPath        string

	// mTLS — si TLSCACert est vide, la connexion est non chiffrée (dev uniquement).
	TLSCACert     string // CLOUDVIGIL_TLS_CA_CERT   → certs/ca/ca.crt
	TLSClientCert string // CLOUDVIGIL_TLS_AGENT_CERT → certs/agent/agent.crt
	TLSClientKey  string // CLOUDVIGIL_TLS_AGENT_KEY  → certs/agent/agent.key
	TLSServerName string // CLOUDVIGIL_TLS_SERVER_NAME → "cloudvigil-server"

	// WebSocket Log Viewer
	// CLOUDVIGIL_WS_SERVER : adresse HTTP du Master pour le canal de contrôle WS.
	// Exemples : ws://localhost:8000  |  wss://monitoring.example.com
	WSServer string
}

func loadConfig() config {
	diskPath := os.Getenv("CLOUDVIGIL_DISK_PATH")
	if diskPath == "" {
		if runtime.GOOS == "windows" {
			diskPath = "C:\\"
		} else {
			diskPath = "/"
		}
	}
	return config{
		ServerAddr:      envOrDefault("CLOUDVIGIL_SERVER", "localhost:50051"),
		NodeID:          envOrDefault("CLOUDVIGIL_NODE_ID", mustHostname()),
		CollectInterval: envDuration("CLOUDVIGIL_INTERVAL", 2*time.Second),
		DiskPath:        diskPath,
		TLSCACert:       os.Getenv("CLOUDVIGIL_TLS_CA_CERT"),
		TLSClientCert:   os.Getenv("CLOUDVIGIL_TLS_AGENT_CERT"),
		TLSClientKey:    os.Getenv("CLOUDVIGIL_TLS_AGENT_KEY"),
		TLSServerName:   envOrDefault("CLOUDVIGIL_TLS_SERVER_NAME", "cloudvigil-server"),
		WSServer:        envOrDefault("CLOUDVIGIL_WS_SERVER", "ws://localhost:8000"),
	}
}

func main() {
	cfg := loadConfig()
	sysCollector := metrics.New(cfg.DiskPath)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	log.Printf("[agent] démarrage — node_id=%s server=%s interval=%s",
		cfg.NodeID, cfg.ServerAddr, cfg.CollectInterval)

	// ── Flux 1 : métriques système (toujours actif) ───────────────────────────
	go runWithBackoff(ctx, "metrics", func(c context.Context) error {
		return runMetricsSession(c, cfg, sysCollector)
	})

	// ── Flux 2 : Docker (activé uniquement si le daemon est détecté) ──────────
	dkr, err := dockercollector.NewCollector()
	if err != nil {
		log.Printf("[agent] Docker non détecté, monitoring des conteneurs désactivé : %v", err)
	} else {
		defer dkr.Close()
		log.Println("[agent] Docker détecté — démarrage du flux de conteneurs")
		go runWithBackoff(ctx, "docker", func(c context.Context) error {
			return runDockerSession(c, cfg, dkr)
		})
	}

	// ── Flux 3 : canal de contrôle WebSocket (Log Viewer) ─────────────────────
	// Se connecte au Master en WS pour recevoir les commandes de streaming de logs.
	// dkr peut être nil (Docker absent) — wscontrol renvoie alors une erreur explicite.
	wsClient := wscontrol.NewFromCollector(cfg.WSServer, cfg.NodeID, dkr)
	go runWithBackoff(ctx, "wscontrol", func(c context.Context) error {
		return wsClient.Run(c)
	})

	// Attendre le signal d'arrêt.
	<-ctx.Done()
	log.Println("[agent] signal reçu, arrêt en cours…")
}

// runWithBackoff boucle avec un backoff exponentiel jusqu'à l'annulation du contexte.
func runWithBackoff(ctx context.Context, label string, fn func(context.Context) error) {
	bp := &connect.Policy{}
	for {
		if ctx.Err() != nil {
			return
		}
		err := fn(ctx)
		if err == nil || errors.Is(err, context.Canceled) {
			return
		}
		log.Printf("[%s] session perdue : %v", label, err)
		if !bp.Wait(ctx) {
			return
		}
	}
}

// ── Session métriques système ─────────────────────────────────────────────────

func runMetricsSession(ctx context.Context, cfg config, collector *metrics.Collector) error {
	conn, err := dialServer(cfg)
	if err != nil {
		return err
	}
	defer conn.Close()

	stream, err := pb.NewMonitoringServiceClient(conn).StreamMetrics(ctx)
	if err != nil {
		return err
	}
	log.Printf("[metrics] flux ouvert vers %s", cfg.ServerAddr)

	ticker := time.NewTicker(cfg.CollectInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return closeStream(stream)
		case <-ticker.C:
			snap, err := collector.Collect(ctx)
			if err != nil {
				log.Printf("[metrics] collecte échouée : %v", err)
				continue
			}
			report := &pb.MetricReport{
				NodeId:    cfg.NodeID,
				CpuUsage:  snap.CPUUsage,
				RamUsage:  snap.RAMUsage,
				DiskUsage: snap.DiskUsage,
				Timestamp: timestamppb.New(snap.CollectedAt),
			}
			if err := stream.Send(report); err != nil {
				return err
			}
			log.Printf("[metrics] envoyé — cpu=%.1f%% ram=%.1f%% disk=%.1f%%",
				report.CpuUsage, report.RamUsage, report.DiskUsage)
		}
	}
}

// ── Session Docker ────────────────────────────────────────────────────────────

func runDockerSession(ctx context.Context, cfg config, collector *dockercollector.Collector) error {
	conn, err := dialServer(cfg)
	if err != nil {
		return err
	}
	defer conn.Close()

	stream, err := pb.NewMonitoringServiceClient(conn).StreamDockerStatus(ctx)
	if err != nil {
		return err
	}
	log.Printf("[docker] flux ouvert vers %s", cfg.ServerAddr)

	ticker := time.NewTicker(cfg.CollectInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return closeDockerStream(stream)
		case <-ticker.C:
			snapshots, err := collector.Collect(ctx)
			if err != nil {
				log.Printf("[docker] collecte échouée : %v", err)
				continue
			}

			containers := make([]*pb.ContainerInfo, 0, len(snapshots))
			for _, s := range snapshots {
				containers = append(containers, &pb.ContainerInfo{
					Id:         s.ID,
					Name:       s.Name,
					Image:      s.Image,
					State:      s.State,
					CpuPercent: s.CPUPercent,
					MemUsageMb: s.MemUsageMB,
					MemLimitMb: s.MemLimitMB,
				})
			}

			report := &pb.DockerReport{
				NodeId:     cfg.NodeID,
				Containers: containers,
				Timestamp:  timestamppb.Now(),
			}
			if err := stream.Send(report); err != nil {
				return err
			}
			log.Printf("[docker] envoyé — %d conteneurs", len(containers))
		}
	}
}

// ── helpers ──────────────────────────────────────────────────────────────────

// dialServer ouvre une connexion gRPC vers le serveur.
// Si les variables TLS sont renseignées, active le mTLS ; sinon utilise
// une connexion non chiffrée (pratique pour le développement local).
func dialServer(cfg config) (*grpc.ClientConn, error) {
	opt, err := buildDialOption(cfg)
	if err != nil {
		return nil, fmt.Errorf("TLS: %w", err)
	}
	return grpc.NewClient(cfg.ServerAddr, opt)
}

// buildDialOption construit l'option de transport gRPC (mTLS ou insecure).
func buildDialOption(cfg config) (grpc.DialOption, error) {
	if cfg.TLSCACert == "" {
		log.Println("[tls] ⚠️  Connexion non chiffrée — définissez CLOUDVIGIL_TLS_CA_CERT pour activer mTLS")
		return grpc.WithTransportCredentials(insecure.NewCredentials()), nil
	}

	// Charger le certificat de l'autorité de certification (CA)
	caPEM, err := os.ReadFile(cfg.TLSCACert)
	if err != nil {
		return nil, fmt.Errorf("lecture CA cert %q: %w", cfg.TLSCACert, err)
	}
	certPool := x509.NewCertPool()
	if !certPool.AppendCertsFromPEM(caPEM) {
		return nil, errors.New("impossible de parser le certificat CA")
	}

	// Charger le certificat client + clé privée (mTLS)
	clientCert, err := tls.LoadX509KeyPair(cfg.TLSClientCert, cfg.TLSClientKey)
	if err != nil {
		return nil, fmt.Errorf("cert/clé agent %q/%q: %w", cfg.TLSClientCert, cfg.TLSClientKey, err)
	}

	tlsCfg := &tls.Config{
		Certificates: []tls.Certificate{clientCert},
		RootCAs:      certPool,
		ServerName:   cfg.TLSServerName, // SNI — doit correspondre au CN/SAN du serveur
		MinVersion:   tls.VersionTLS13,
	}

	log.Printf("[tls] mTLS activé — CA=%s cert=%s serveur=%s",
		cfg.TLSCACert, cfg.TLSClientCert, cfg.TLSServerName)
	return grpc.WithTransportCredentials(credentials.NewTLS(tlsCfg)), nil
}

func closeStream(stream pb.MonitoringService_StreamMetricsClient) error {
	resp, err := stream.CloseAndRecv()
	if err != nil && !errors.Is(err, io.EOF) {
		return err
	}
	if resp != nil {
		log.Printf("[metrics] serveur a répondu : %s", resp.GetStatus())
	}
	return context.Canceled
}

func closeDockerStream(stream pb.MonitoringService_StreamDockerStatusClient) error {
	resp, err := stream.CloseAndRecv()
	if err != nil && !errors.Is(err, io.EOF) {
		return err
	}
	if resp != nil {
		log.Printf("[docker] serveur a répondu : %s", resp.GetStatus())
	}
	return context.Canceled
}

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envDuration(key string, def time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		log.Printf("[config] %s invalide (%q), valeur par défaut %s utilisée", key, v, def)
		return def
	}
	return d
}

func mustHostname() string {
	h, err := os.Hostname()
	if err != nil {
		return "unknown-node"
	}
	return h
}
