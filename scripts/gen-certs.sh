#!/usr/bin/env bash
# ==============================================================================
# CloudVigil — Génération des certificats TLS / mTLS
# ==============================================================================
# Produit :
#   certs/ca/        — Autorité de Certification commune (validité 10 ans)
#   certs/server/    — Certificat serveur gRPC (validité 2 ans)
#   certs/agent/     — Certificat client mTLS pour les agents (validité 2 ans)
#   certs/nginx/     — Certificat auto-signé pour le reverse-proxy HTTPS
#
# Usage :
#   bash scripts/gen-certs.sh
# ==============================================================================

set -euo pipefail

CERTS_DIR="certs"
mkdir -p "$CERTS_DIR"/{ca,server,agent,nginx}

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  CloudVigil — Génération des certificats TLS/mTLS   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Autorité de Certification (CA) ────────────────────────────────────────
echo "▶  [1/4] Génération de la CA (10 ans)..."

openssl genrsa -out "$CERTS_DIR/ca/ca.key" 4096 2>/dev/null

openssl req -new -x509 -days 3650 \
  -key    "$CERTS_DIR/ca/ca.key" \
  -out    "$CERTS_DIR/ca/ca.crt" \
  -subj   "/C=FR/ST=Paris/O=CloudVigil/OU=PKI/CN=CloudVigil-Root-CA" \
  2>/dev/null

echo "   ✓  CA : $CERTS_DIR/ca/ca.crt"

# ── 2. Certificat serveur gRPC ────────────────────────────────────────────────
echo "▶  [2/4] Génération du certificat serveur gRPC (2 ans)..."

openssl genrsa -out "$CERTS_DIR/server/server.key" 2048 2>/dev/null

openssl req -new \
  -key  "$CERTS_DIR/server/server.key" \
  -out  "$CERTS_DIR/server/server.csr" \
  -subj "/C=FR/O=CloudVigil/CN=cloudvigil-server" \
  2>/dev/null

# SAN : autoriser localhost + nom du service Docker + IP Docker Bridge
cat > "$CERTS_DIR/server/server.ext" <<EOF
subjectAltName=DNS:localhost,DNS:server,DNS:cloudvigil-server,IP:127.0.0.1
EOF

openssl x509 -req -days 730 \
  -in      "$CERTS_DIR/server/server.csr" \
  -CA      "$CERTS_DIR/ca/ca.crt" \
  -CAkey   "$CERTS_DIR/ca/ca.key" \
  -CAcreateserial \
  -out     "$CERTS_DIR/server/server.crt" \
  -extfile "$CERTS_DIR/server/server.ext" \
  2>/dev/null

echo "   ✓  Serveur : $CERTS_DIR/server/server.{crt,key}"

# ── 3. Certificat agent (client mTLS) ────────────────────────────────────────
echo "▶  [3/4] Génération du certificat agent / client mTLS (2 ans)..."

openssl genrsa -out "$CERTS_DIR/agent/agent.key" 2048 2>/dev/null

openssl req -new \
  -key  "$CERTS_DIR/agent/agent.key" \
  -out  "$CERTS_DIR/agent/agent.csr" \
  -subj "/C=FR/O=CloudVigil/CN=cloudvigil-agent" \
  2>/dev/null

openssl x509 -req -days 730 \
  -in    "$CERTS_DIR/agent/agent.csr" \
  -CA    "$CERTS_DIR/ca/ca.crt" \
  -CAkey "$CERTS_DIR/ca/ca.key" \
  -CAcreateserial \
  -out   "$CERTS_DIR/agent/agent.crt" \
  2>/dev/null

echo "   ✓  Agent : $CERTS_DIR/agent/agent.{crt,key}"

# ── 4. Certificat Nginx HTTPS (auto-signé, sans CA intermédiaire) ─────────────
echo "▶  [4/4] Génération du certificat Nginx HTTPS (2 ans)..."

openssl req -x509 -newkey rsa:2048 -nodes -days 730 \
  -keyout "$CERTS_DIR/nginx/nginx.key" \
  -out    "$CERTS_DIR/nginx/nginx.crt" \
  -subj   "/C=FR/O=CloudVigil/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
  2>/dev/null

echo "   ✓  Nginx : $CERTS_DIR/nginx/nginx.{crt,key}"

# ── Nettoyage des fichiers intermédiaires ─────────────────────────────────────
rm -f "$CERTS_DIR/server/server.csr" \
      "$CERTS_DIR/server/server.ext" \
      "$CERTS_DIR/agent/agent.csr"   \
      "$CERTS_DIR/ca/ca.srl"

# ── Résumé ────────────────────────────────────────────────────────────────────
echo ""
echo "┌──────────────────────────────────────────────────────┐"
echo "│  ✅  Tous les certificats ont été générés avec succès │"
echo "└──────────────────────────────────────────────────────┘"
echo ""
echo "  Répertoire        : $CERTS_DIR/"
echo "  CA                : $CERTS_DIR/ca/ca.crt"
echo "  Serveur gRPC      : $CERTS_DIR/server/server.{crt,key}"
echo "  Agent (client)    : $CERTS_DIR/agent/agent.{crt,key}"
echo "  Nginx HTTPS       : $CERTS_DIR/nginx/nginx.{crt,key}"
echo ""
echo "  ⚠️   Ces certificats sont destinés au développement."
echo "  ⚠️   En production, utilisez Let's Encrypt ou une PKI d'entreprise."
echo ""
