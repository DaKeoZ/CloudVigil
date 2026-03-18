package main

import (
	"context"
	"log"
	"math/rand"
	"os"
	"time"

	"github.com/cloudvigil/agent/pb"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/timestamppb"
)

func main() {
	serverAddr := envOrDefault("CLOUDVIGIL_SERVER", "localhost:50051")
	nodeID := envOrDefault("CLOUDVIGIL_NODE_ID", mustHostname())
	intervalSec := uint32(5)

	conn, err := grpc.NewClient(serverAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("impossible de se connecter au serveur : %v", err)
	}
	defer conn.Close()

	client := pb.NewMonitoringServiceClient(conn)

	ctx := context.Background()
	req := &pb.StreamRequest{
		NodeId:          nodeID,
		IntervalSeconds: intervalSec,
	}

	stream, err := client.StreamMetrics(ctx, req)
	if err != nil {
		log.Fatalf("erreur lors de l'ouverture du flux : %v", err)
	}

	log.Printf("[agent] connecté au serveur %s — node_id=%s", serverAddr, nodeID)

	ticker := time.NewTicker(time.Duration(intervalSec) * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		report := &pb.MetricReport{
			NodeId:    nodeID,
			CpuUsage:  collectCPU(),
			RamUsage:  collectRAM(),
			DiskUsage: collectDisk(),
			Timestamp: timestamppb.Now(),
		}

		log.Printf("[agent] envoi — cpu=%.1f%% ram=%.1f%% disk=%.1f%%",
			report.CpuUsage, report.RamUsage, report.DiskUsage)

		_ = stream
		_ = report
	}
}

// collectCPU retourne un pourcentage simulé ; remplacer par gopsutil en production.
func collectCPU() float32 {
	return rand.Float32() * 100
}

func collectRAM() float32 {
	return rand.Float32() * 100
}

func collectDisk() float32 {
	return rand.Float32() * 100
}

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func mustHostname() string {
	h, err := os.Hostname()
	if err != nil {
		return "unknown-node"
	}
	return h
}
