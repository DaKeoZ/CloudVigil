# CloudVigil

Outil de monitoring cloud en temps réel basé sur **gRPC** et **Protocol Buffers**.

```
┌─────────────────────────────────────────────────────────────┐
│                        CloudVigil                           │
│                                                             │
│   ┌─────────────┐   StreamMetrics (gRPC)  ┌─────────────┐  │
│   │  Agent (Go) │ ──────────────────────► │ Server (Py) │  │
│   │             │   MetricReport stream   │             │  │
│   │  Collecte : │                         │  Agrège et  │  │
│   │  • CPU      │                         │  stocke les │  │
│   │  • RAM      │                         │  métriques  │  │
│   │  • Disque   │                         │             │  │
│   └─────────────┘                         └─────────────┘  │
│                                                             │
│              proto/monitor.proto (source de vérité)         │
└─────────────────────────────────────────────────────────────┘
```

## Structure du dépôt

```
CloudVigil/
├── proto/
│   └── monitor.proto          # Définition gRPC (source de vérité)
├── agent/                     # Agent de collecte (Go)
│   ├── main.go
│   ├── go.mod
│   └── pb/
│       ├── monitor.pb.go      # Stubs protobuf générés
│       └── monitor_grpc.pb.go # Stubs gRPC générés
├── server/                    # Serveur de réception (Python)
│   ├── main.py
│   ├── requirements.txt
│   └── pb/
│       ├── monitor_pb2.py         # Stubs protobuf générés
│       └── monitor_pb2_grpc.py    # Stubs gRPC générés
└── Makefile                   # Automatisation
```

## Prérequis

| Outil | Version minimum |
|-------|----------------|
| Go | 1.22 |
| Python | 3.11 |
| protoc | 27.x |
| protoc-gen-go | latest |
| protoc-gen-go-grpc | latest |

## Démarrage rapide

```bash
# 1. Installer toutes les dépendances
make deps

# 2. (Re)générer les stubs gRPC depuis monitor.proto
make proto

# 3. Démarrer le serveur Python
make run-server

# 4. Dans un second terminal, démarrer l'agent Go
make run-agent
```

## Variables d'environnement

### Agent (Go)

| Variable | Défaut | Description |
|----------|--------|-------------|
| `CLOUDVIGIL_SERVER` | `localhost:50051` | Adresse du serveur gRPC |
| `CLOUDVIGIL_NODE_ID` | hostname | Identifiant du nœud |

### Serveur (Python)

| Variable | Défaut | Description |
|----------|--------|-------------|
| `CLOUDVIGIL_LISTEN` | `[::]:50051` | Adresse d'écoute |
| `CLOUDVIGIL_WORKERS` | `10` | Nombre de threads |

## Contrat gRPC (`proto/monitor.proto`)

```protobuf
service MonitoringService {
  rpc StreamMetrics(StreamRequest) returns (stream MetricReport);
}

message MetricReport {
  string node_id    = 1;
  float  cpu_usage  = 2;
  float  ram_usage  = 3;
  float  disk_usage = 4;
  google.protobuf.Timestamp timestamp = 5;
}
```

## Commandes utiles

```bash
make proto       # Régénère les stubs Go + Python
make build       # Compile le binaire agent
make lint        # Analyse statique Go + Python
make clean       # Supprime les artefacts générés
make help        # Affiche l'aide
```
