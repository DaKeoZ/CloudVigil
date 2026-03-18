package main

import (
	"context"
	"errors"
	"io"
	"log"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/cloudvigil/agent/internal/connect"
	"github.com/cloudvigil/agent/internal/metrics"
	"github.com/cloudvigil/agent/pb"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// config regroupe tous les paramètres de l'agent issus des variables d'environnement.
type config struct {
	ServerAddr      string
	NodeID          string
	CollectInterval time.Duration
	DiskPath        string
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
	}
}

func main() {
	cfg := loadConfig()
	collector := metrics.New(cfg.DiskPath)
	backoff := &connect.Policy{}

	// Contexte racine annulé par SIGINT / SIGTERM pour un arrêt gracieux.
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	log.Printf("[agent] démarrage — node_id=%s server=%s interval=%s",
		cfg.NodeID, cfg.ServerAddr, cfg.CollectInterval)

	for {
		if ctx.Err() != nil {
			log.Println("[agent] arrêt demandé, bye.")
			return
		}

		err := runStreamSession(ctx, cfg, collector, backoff)
		if err == nil || errors.Is(err, context.Canceled) {
			return
		}

		log.Printf("[agent] session perdue : %v", err)
		if !backoff.Wait(ctx) {
			log.Println("[agent] contexte annulé pendant le backoff, bye.")
			return
		}
	}
}

// runStreamSession ouvre une connexion gRPC, envoie les métriques en client-streaming
// jusqu'à ce qu'une erreur survienne ou que le contexte soit annulé.
func runStreamSession(ctx context.Context, cfg config, collector *metrics.Collector, backoff *connect.Policy) error {
	conn, err := grpc.NewClient(
		cfg.ServerAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return err
	}
	defer conn.Close()

	client := pb.NewMonitoringServiceClient(conn)

	stream, err := client.StreamMetrics(ctx)
	if err != nil {
		return err
	}

	log.Printf("[agent] flux ouvert vers %s", cfg.ServerAddr)
	backoff.Reset()

	ticker := time.NewTicker(cfg.CollectInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			// Clôture propre : on prévient le serveur et on attend sa réponse.
			resp, closeErr := stream.CloseAndRecv()
			if closeErr != nil && !errors.Is(closeErr, io.EOF) {
				log.Printf("[agent] erreur à la clôture : %v", closeErr)
			} else if resp != nil {
				log.Printf("[agent] serveur a répondu : %s", resp.GetStatus())
			}
			return ctx.Err()

		case <-ticker.C:
			snap, err := collector.Collect(ctx)
			if err != nil {
				log.Printf("[agent] collecte échouée : %v", err)
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
				return err // déclenche une reconnexion avec backoff
			}

			log.Printf("[agent] envoyé — cpu=%.1f%% ram=%.1f%% disk=%.1f%%",
				report.CpuUsage, report.RamUsage, report.DiskUsage)
		}
	}
}

// ── helpers ──────────────────────────────────────────────────────────────────

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
