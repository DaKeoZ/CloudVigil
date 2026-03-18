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
