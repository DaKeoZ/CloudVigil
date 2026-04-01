# Build depuis la racine du dépôt :
#   docker build -f agent/Dockerfile -t cloudvigil-agent:latest ./agent
# Ou depuis agent/ :
#   docker build -t cloudvigil-agent:latest .

FROM golang:1.24-bookworm AS builder
WORKDIR /src

# go.mod exige Go 1.25 : télécharge la toolchain si besoin
ENV GOTOOLCHAIN=auto

# go.sum peut être absent (clone sans fichier) : go mod download complète le graphe.
COPY go.mod ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /cloudvigil-agent .

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /cloudvigil-agent /usr/local/bin/cloudvigil-agent

ENTRYPOINT ["/usr/local/bin/cloudvigil-agent"]
