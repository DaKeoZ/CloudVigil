// Package metrics fournit la collecte des métriques système via gopsutil.
package metrics

import (
	"context"
	"fmt"
	"time"

	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/disk"
	"github.com/shirou/gopsutil/v3/mem"
)

// Snapshot contient une mesure ponctuelle des ressources système.
type Snapshot struct {
	CPUUsage  float32
	RAMUsage  float32
	DiskUsage float32
	CollectedAt time.Time
}

// Collector mesure les ressources système en temps réel.
type Collector struct {
	diskPath string // point de montage surveillé (ex: "/" ou "C:\\")
}

// New crée un Collector. diskPath est le point de montage à surveiller.
func New(diskPath string) *Collector {
	return &Collector{diskPath: diskPath}
}

// Collect effectue une mesure instantanée.
// La mesure CPU nécessite un intervalle de 100 ms (imposé par gopsutil).
func (c *Collector) Collect(ctx context.Context) (Snapshot, error) {
	cpuPercents, err := cpu.PercentWithContext(ctx, 100*time.Millisecond, false)
	if err != nil {
		return Snapshot{}, fmt.Errorf("cpu: %w", err)
	}

	vmStat, err := mem.VirtualMemoryWithContext(ctx)
	if err != nil {
		return Snapshot{}, fmt.Errorf("ram: %w", err)
	}

	diskStat, err := disk.UsageWithContext(ctx, c.diskPath)
	if err != nil {
		return Snapshot{}, fmt.Errorf("disk(%s): %w", c.diskPath, err)
	}

	return Snapshot{
		CPUUsage:    float32(cpuPercents[0]),
		RAMUsage:    float32(vmStat.UsedPercent),
		DiskUsage:   float32(diskStat.UsedPercent),
		CollectedAt: time.Now().UTC(),
	}, nil
}
