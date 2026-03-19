export interface MetricPoint {
  timestamp: string;
  cpu_usage: number;
  ram_usage: number;
  disk_usage: number;
}

export interface ContainerSummary {
  id: string;
  name: string;
  image: string;
  state: string;
  cpu_percent: number;
  mem_usage_mb: number;
  mem_limit_mb: number;
}

export interface NodeSummary {
  node_id: string;
  status: "online" | "offline";
  latest: MetricPoint | null;
  history: MetricPoint[];
  containers: ContainerSummary[];
  container_count: number;
  updated_at: string | null;
}

export interface DashboardData {
  nodes: NodeSummary[];
  total: number;
}

// ── Network Health ────────────────────────────────────────────────────────────

export type NetworkStatus  = "up" | "down" | "pending";
export type SslStatus      = "ok" | "warning" | "critical" | "expired" | "na";

export interface LatencyPoint {
  t:          string;   // ISO timestamp
  latency_ms: number | null;
  up:         boolean;
}

export interface NetworkTarget {
  name:               string;
  url:                string;
  status:             NetworkStatus;
  reachable:          boolean | null;
  status_code:        number | null;
  latency_ms:         number | null;
  ssl_days_remaining: number | null;
  ssl_status:         SslStatus;
  error:              string | null;
  last_checked:       string | null;
  history:            LatencyPoint[];
}

export interface NetworkData {
  targets:     NetworkTarget[];
  total:       number;
  up:          number;
  down:        number;
  configured:  boolean;
  probe_stats: {
    total_probes:  number;
    total_alerts:  number;
    interval_s:    number;
    started_at:    string | null;
    running:       boolean;
  };
}

// ── Réparations ───────────────────────────────────────────────────────────────

export interface RepairEvent {
  timestamp: string;
  node_id: string;
  container_id: string;
  container_name: string;
  action: string;
  status: "success" | "failed";
  success: boolean;
  message: string;
}

export interface RepairsData {
  events: RepairEvent[];
  total: number;
  window_minutes: number;
}
