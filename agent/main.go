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

		err := runStreamSession(ctx, cfg, collector)
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

// runStreamSession ouvre une connexion gRPC, démarre le flux et envoie les
// métriques jusqu'à ce qu'une erreur survienne ou que le contexte soit annulé.
func runStreamSession(ctx context.Context, cfg config, collector *metrics.Collector) error {
	conn, err := grpc.NewClient(
		cfg.ServerAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return err
	}
	defer conn.Close()

	client := pb.NewMonitoringServiceClient(conn)

	stream, err := client.StreamMetrics(ctx, &pb.StreamRequest{
		NodeId:          cfg.NodeID,
		IntervalSeconds: uint32(cfg.CollectInterval.Seconds()),
	})
	if err != nil {
		return err
	}

	log.Printf("[agent] flux ouvert vers %s", cfg.ServerAddr)

	// Réinitialiser le backoff dès que la connexion est établie.
	backoff := &connect.Policy{}
	backoff.Reset()

	ticker := time.NewTicker(cfg.CollectInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
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

			// En mode server-streaming le client ne peut pas envoyer après
			// l'envoi initial du StreamRequest. On utilise le flux pour
			// démontrer la réception côté serveur ; l'envoi réel de rapports
			// nécessiterait un flux bidirectionnel (prévu dans la v2).
			// Pour l'instant on logue localement et on vérifie que le flux est vivant.
			log.Printf("[agent] métrique — cpu=%.1f%% ram=%.1f%% disk=%.1f%%",
				report.CpuUsage, report.RamUsage, report.DiskUsage)

			// Vérification de la santé du flux (le serveur peut l'avoir fermé).
			_, recvErr := stream.Recv()
			if recvErr != nil {
				if errors.Is(recvErr, io.EOF) {
					log.Println("[agent] serveur a fermé le flux proprement.")
					return nil
				}
				return recvErr
			}
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
