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
	dockercollector "github.com/cloudvigil/agent/internal/docker"
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
	conn, err := dialServer(cfg.ServerAddr)
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
	conn, err := dialServer(cfg.ServerAddr)
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

func dialServer(addr string) (*grpc.ClientConn, error) {
	return grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
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
