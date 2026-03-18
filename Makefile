# ==============================================================================
# CloudVigil — Makefile
# ==============================================================================
# Cibles principales :
#   make proto      — génère les stubs gRPC pour Go et Python
#   make deps       — installe toutes les dépendances (Go + Python)
#   make deps-go    — installe uniquement les dépendances Go
#   make deps-py    — installe uniquement les dépendances Python
#   make run-server — démarre le serveur Python
#   make run-agent  — compile et démarre l'agent Go
#   make build      — compile le binaire de l'agent Go
#   make lint       — vérifie le code (Go vet + Python ruff)
#   make clean      — supprime les artefacts générés
# ==============================================================================

PROTO_DIR   := proto
PROTO_FILE  := $(PROTO_DIR)/monitor.proto

GO_OUT_DIR  := agent/pb
PY_OUT_DIR  := server/pb

AGENT_BIN   := agent/bin/cloudvigil-agent

VENV        := server/.venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip

.PHONY: all proto deps deps-go deps-py run-server run-agent build lint clean help

all: deps proto build

# ------------------------------------------------------------------------------
# Génération des stubs Protocol Buffers
# ------------------------------------------------------------------------------
proto: proto-go proto-py

proto-go:
	@echo "==> Génération des stubs gRPC Go..."
	protoc \
		--proto_path=$(PROTO_DIR) \
		--go_out=$(GO_OUT_DIR) \
		--go_opt=paths=source_relative \
		--go-grpc_out=$(GO_OUT_DIR) \
		--go-grpc_opt=paths=source_relative \
		$(PROTO_FILE)
	@echo "    Stubs Go générés dans $(GO_OUT_DIR)/"

proto-py:
	@echo "==> Génération des stubs gRPC Python..."
	$(PYTHON) -m grpc_tools.protoc \
		--proto_path=$(PROTO_DIR) \
		--python_out=$(PY_OUT_DIR) \
		--grpc_python_out=$(PY_OUT_DIR) \
		$(PROTO_FILE)
	@echo "    Stubs Python générés dans $(PY_OUT_DIR)/"

# ------------------------------------------------------------------------------
# Installation des dépendances
# ------------------------------------------------------------------------------
deps: deps-go deps-py

deps-go:
	@echo "==> Installation des dépendances Go..."
	cd agent && go mod tidy
	@echo "==> Installation de protoc-gen-go et protoc-gen-go-grpc..."
	go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
	go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

deps-py:
	@echo "==> Création de l'environnement virtuel Python..."
	python3 -m venv $(VENV)
	@echo "==> Installation des dépendances Python..."
	$(PIP) install --upgrade pip
	$(PIP) install -r server/requirements.txt

# ------------------------------------------------------------------------------
# Exécution
# ------------------------------------------------------------------------------
run-server:
	@echo "==> Démarrage du serveur CloudVigil..."
	PYTHONPATH=. $(PYTHON) server/main.py

run-agent: build
	@echo "==> Démarrage de l'agent CloudVigil..."
	./$(AGENT_BIN)

# ------------------------------------------------------------------------------
# Build
# ------------------------------------------------------------------------------
build:
	@echo "==> Compilation de l'agent Go..."
	mkdir -p agent/bin
	cd agent && go build -o bin/cloudvigil-agent ./...

# ------------------------------------------------------------------------------
# Lint / Qualité de code
# ------------------------------------------------------------------------------
lint: lint-go lint-py

lint-go:
	@echo "==> Analyse statique Go..."
	cd agent && go vet ./...

lint-py:
	@echo "==> Analyse statique Python..."
	$(PYTHON) -m py_compile server/main.py server/pb/monitor_pb2.py server/pb/monitor_pb2_grpc.py
	@echo "    Syntaxe Python OK."

# ------------------------------------------------------------------------------
# Nettoyage
# ------------------------------------------------------------------------------
clean:
	@echo "==> Nettoyage des artefacts..."
	rm -f $(GO_OUT_DIR)/monitor.pb.go $(GO_OUT_DIR)/monitor_grpc.pb.go
	rm -f $(PY_OUT_DIR)/monitor_pb2.py $(PY_OUT_DIR)/monitor_pb2_grpc.py
	rm -rf agent/bin
	@echo "    Nettoyage terminé."

# ------------------------------------------------------------------------------
# Aide
# ------------------------------------------------------------------------------
help:
	@echo ""
	@echo "CloudVigil — Cibles disponibles :"
	@echo ""
	@echo "  make proto       Génère les stubs gRPC Go + Python depuis proto/"
	@echo "  make deps        Installe toutes les dépendances"
	@echo "  make deps-go     Installe les dépendances Go uniquement"
	@echo "  make deps-py     Installe les dépendances Python uniquement"
	@echo "  make build       Compile le binaire de l'agent Go"
	@echo "  make run-server  Démarre le serveur Python"
	@echo "  make run-agent   Compile et démarre l'agent Go"
	@echo "  make lint        Analyse statique (Go vet + Python)"
	@echo "  make clean       Supprime les artefacts générés"
	@echo ""
