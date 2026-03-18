// Package docker collecte l'état et les ressources des conteneurs via le SDK Docker.
package docker

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	dockertypes "github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
)

// ContainerSnapshot représente l'état et les ressources d'un conteneur à un instant donné.
type ContainerSnapshot struct {
	ID         string
	Name       string
	Image      string
	State      string  // "running" | "exited" | "paused" | ...
	CPUPercent float32 // % CPU (toutes cœurs confondus)
	MemUsageMB float32 // Mémoire résidente (Mo, hors cache)
	MemLimitMB float32 // Limite mémoire configurée (Mo)
}

// statsJSON est un sous-ensemble du JSON retourné par l'API Docker Stats.
// On définit le struct localement pour éviter les dépendances sur les types internes de Docker.
type statsJSON struct {
	CPUStats struct {
		CPUUsage struct {
			TotalUsage  uint64   `json:"total_usage"`
			PercpuUsage []uint64 `json:"percpu_usage"`
		} `json:"cpu_usage"`
		SystemUsage uint64 `json:"system_cpu_usage"`
		OnlineCPUs  uint32 `json:"online_cpus"`
	} `json:"cpu_stats"`
	PreCPUStats struct {
		CPUUsage struct {
			TotalUsage uint64 `json:"total_usage"`
		} `json:"cpu_usage"`
		SystemUsage uint64 `json:"system_cpu_usage"`
	} `json:"precpu_stats"`
	MemoryStats struct {
		Usage uint64            `json:"usage"`
		Limit uint64            `json:"limit"`
		Stats map[string]uint64 `json:"stats"`
	} `json:"memory_stats"`
}

// Collector interroge le daemon Docker.
type Collector struct {
	cli *client.Client
}

// NewCollector tente de créer un client Docker et vérifie sa disponibilité.
// Retourne une erreur si Docker n'est pas installé ou si le daemon est inaccessible.
func NewCollector() (*Collector, error) {
	cli, err := client.NewClientWithOpts(
		client.FromEnv,
		client.WithAPIVersionNegotiation(),
	)
	if err != nil {
		return nil, fmt.Errorf("création du client Docker : %w", err)
	}

	// Ping rapide pour confirmer que le daemon est opérationnel.
	if _, err := cli.Ping(context.Background()); err != nil {
		_ = cli.Close()
		return nil, fmt.Errorf("daemon Docker inaccessible : %w", err)
	}

	return &Collector{cli: cli}, nil
}

// Close libère le client Docker.
func (c *Collector) Close() {
	_ = c.cli.Close()
}

// Collect retourne un snapshot de tous les conteneurs (running et stopped).
func (c *Collector) Collect(ctx context.Context) ([]ContainerSnapshot, error) {
	list, err := c.cli.ContainerList(ctx, dockertypes.ListOptions{All: true})
	if err != nil {
		return nil, fmt.Errorf("ContainerList : %w", err)
	}

	snapshots := make([]ContainerSnapshot, 0, len(list))
	for _, ctr := range list {
		snap := ContainerSnapshot{
			ID:    shortID(ctr.ID),
			Name:  firstName(ctr.Names),
			Image: ctr.Image,
			State: ctr.State,
		}

		if ctr.State == "running" {
			cpu, memU, memL, err := fetchStats(ctx, c.cli, ctr.ID)
			if err != nil {
				log.Printf("[docker] stats(%s) : %v", snap.ID, err)
			} else {
				snap.CPUPercent = float32(cpu)
				snap.MemUsageMB = memU
				snap.MemLimitMB = memL
			}
		}

		snapshots = append(snapshots, snap)
	}

	return snapshots, nil
}

// fetchStats interroge l'API Stats Docker pour un conteneur en cours d'exécution.
func fetchStats(ctx context.Context, cli *client.Client, id string) (cpuPct float64, memUsedMB, memLimitMB float32, err error) {
	resp, err := cli.ContainerStats(ctx, id, false)
	if err != nil {
		return 0, 0, 0, err
	}
	defer func() { _ = resp.Body.Close() }()

	var s statsJSON
	if err := json.NewDecoder(resp.Body).Decode(&s); err != nil {
		return 0, 0, 0, fmt.Errorf("décodage stats JSON : %w", err)
	}

	cpuPct = calcCPUPercent(&s)

	// Docker rapporte la mémoire "cache" dans stats.memory_stats.stats["cache"].
	// On la soustrait pour obtenir la mémoire réellement utilisée par le processus.
	cache := s.MemoryStats.Stats["cache"]
	used := s.MemoryStats.Usage
	if used > cache {
		used -= cache
	}
	memUsedMB = float32(used) / 1024 / 1024
	memLimitMB = float32(s.MemoryStats.Limit) / 1024 / 1024

	return
}

// calcCPUPercent dérive le % CPU depuis les deux snapshots successifs fournis par Docker.
func calcCPUPercent(s *statsJSON) float64 {
	cpuDelta := float64(s.CPUStats.CPUUsage.TotalUsage - s.PreCPUStats.CPUUsage.TotalUsage)
	sysDelta := float64(s.CPUStats.SystemUsage - s.PreCPUStats.SystemUsage)
	numCPU := float64(s.CPUStats.OnlineCPUs)
	if numCPU == 0 {
		numCPU = float64(len(s.CPUStats.CPUUsage.PercpuUsage))
	}
	if sysDelta > 0 && cpuDelta > 0 && numCPU > 0 {
		return (cpuDelta / sysDelta) * numCPU * 100.0
	}
	return 0
}

// shortID retourne les 12 premiers caractères d'un ID Docker.
func shortID(id string) string {
	if len(id) > 12 {
		return id[:12]
	}
	return id
}

// firstName extrait le premier nom Docker (qui est préfixé d'un "/").
func firstName(names []string) string {
	if len(names) == 0 {
		return "unknown"
	}
	name := names[0]
	if len(name) > 0 && name[0] == '/' {
		return name[1:]
	}
	return name
}
