# CloudVigil

Outil de monitoring cloud open-source : collecte des métriques système (CPU, RAM, disque) et Docker en temps réel, stockage dans InfluxDB, visualisation dans un dashboard Next.js, alertes via Webhook.

```
┌──────────────────────────────────────────────────────────────────┐
│                        CloudVigil Stack                          │
│                                                                  │
│  [Agent Go]──mTLS gRPC──▶[Serveur Python]──▶[InfluxDB]         │
│      │                        │                                  │
│      └── Docker metrics       └──▶[FastAPI REST + JWT]          │
│                                        │                         │
│                                  [Nginx HTTPS]                   │
│                                        │                         │
│                                  [Dashboard Next.js]             │
└──────────────────────────────────────────────────────────────────┘
```

## Architecture

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| **Agent** | Go + gopsutil + Docker SDK | Collecte métriques système & conteneurs |
| **Serveur** | Python + FastAPI + gRPC | Réception gRPC, persistance InfluxDB, API REST |
| **Base de données** | InfluxDB v2 | Stockage time-series (rétention 30 jours) |
| **Frontend** | Next.js 15 + Tremor | Dashboard temps réel |
| **Proxy** | Nginx | TLS termination, rate limiting, reverse proxy |

### Sécurité

- **gRPC mTLS** : l'agent et le serveur s'authentifient mutuellement par certificats X.509
- **JWT** : tous les endpoints de l'API REST sont protégés par un Bearer token
- **HTTPS** : Nginx termine TLS avec un certificat auto-signé (dev) ou Let's Encrypt (prod)
- **Rate limiting** : Nginx limite les appels API (120 req/min) et les tentatives de login (10 req/min)
- **Réseau isolé** : InfluxDB n'est accessible qu'en réseau interne Docker

---

## Prérequis

| Outil | Version minimale |
|-------|-----------------|
| Go | 1.22 |
| Python | 3.11 |
| Node.js | 20 |
| Docker | 24 |
| Docker Compose | v2.20 |
| OpenSSL | 1.1+ |
| protoc | 3.x |

---

## Démarrage rapide (stack complète)

```bash
# 1. Cloner le dépôt
git clone https://github.com/votre-org/cloudvigil.git
cd cloudvigil

# 2. Générer les certificats TLS/mTLS (nécessite OpenSSL)
bash scripts/gen-certs.sh

# 3. Configurer les variables secrètes (optionnel — des valeurs par défaut existent)
cat > .env <<'EOF'
CLOUDVIGIL_JWT_SECRET=remplacer-par-une-chaine-aleatoire-de-32-chars-minimum
CLOUDVIGIL_API_USERNAME=admin
CLOUDVIGIL_API_PASSWORD=votre-mot-de-passe-securise
INFLUXDB_ADMIN_PASSWORD=influx-mot-de-passe
INFLUXDB_ADMIN_TOKEN=cloudvigil-token-secret
EOF

# 4. Lancer toute la stack
docker compose up -d

# 5. Vérifier que tous les services sont sains
docker compose ps

# 6. Ouvrir le dashboard
# → https://localhost  (certificat auto-signé — accepter l'avertissement navigateur)
```

**Identifiants par défaut** (à changer impérativement en production) :
- Utilisateur : `admin`
- Mot de passe : `cloudvigil`

---

## Déployer un agent sur un serveur distant

### En une seule commande Docker

Copiez d'abord le certificat CA et le certificat agent sur le serveur distant :

```bash
# Sur la machine hébergeant CloudVigil
scp certs/ca/ca.crt      user@serveur-distant:/etc/cloudvigil/certs/ca.crt
scp certs/agent/agent.crt user@serveur-distant:/etc/cloudvigil/certs/agent.crt
scp certs/agent/agent.key user@serveur-distant:/etc/cloudvigil/certs/agent.key
```

Puis sur le **serveur distant**, lancez l'agent avec Docker :

```bash
docker run -d \
  --name cloudvigil-agent \
  --restart unless-stopped \
  --net host \
  -v /etc/cloudvigil/certs:/certs:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e CLOUDVIGIL_SERVER=IP_DU_SERVEUR_MAITRE:50051 \
  -e CLOUDVIGIL_NODE_ID=$(hostname) \
  -e CLOUDVIGIL_TLS_CA_CERT=/certs/ca.crt \
  -e CLOUDVIGIL_TLS_AGENT_CERT=/certs/agent.crt \
  -e CLOUDVIGIL_TLS_AGENT_KEY=/certs/agent.key \
  ghcr.io/votre-org/cloudvigil-agent:latest
```

> Remplacez `IP_DU_SERVEUR_MAITRE` par l'adresse IP ou le nom DNS du serveur CloudVigil.
> Le port `50051` doit être accessible depuis le réseau du serveur distant.

### Variables d'environnement de l'agent

| Variable | Défaut | Description |
|----------|--------|-------------|
| `CLOUDVIGIL_SERVER` | `localhost:50051` | Adresse du serveur gRPC |
| `CLOUDVIGIL_NODE_ID` | `hostname` | Identifiant unique du nœud |
| `CLOUDVIGIL_INTERVAL` | `2s` | Intervalle de collecte |
| `CLOUDVIGIL_DISK_PATH` | `/` (Linux) | Partition à monitorer |
| `CLOUDVIGIL_TLS_CA_CERT` | _(vide)_ | Chemin vers `ca.crt` (activer mTLS) |
| `CLOUDVIGIL_TLS_AGENT_CERT` | _(vide)_ | Chemin vers `agent.crt` |
| `CLOUDVIGIL_TLS_AGENT_KEY` | _(vide)_ | Chemin vers `agent.key` |
| `CLOUDVIGIL_TLS_SERVER_NAME` | `cloudvigil-server` | SNI — CN du certificat serveur |

> **Sans certificats** (`TLS_CA_CERT` vide), l'agent se connecte en clair.
> Uniquement acceptable en développement local.

---

## Développement local

### Structure du projet

```
cloudvigil/
├── agent/              # Agent Go (métriques système + Docker)
│   ├── internal/
│   │   ├── metrics/    # Collecteur CPU/RAM/Disque (gopsutil)
│   │   ├── docker/     # Collecteur Docker SDK
│   │   └── connect/    # Backoff exponentiel reconnexion
│   ├── pb/             # Stubs gRPC générés
│   └── main.go
├── server/             # Serveur Python
│   ├── alerts/         # Moteur d'alertes (YAML + Webhook)
│   ├── pb/             # Stubs gRPC générés
│   ├── auth.py         # JWT authentication
│   ├── config.py       # Settings (pydantic-settings)
│   ├── database.py     # Client InfluxDB async
│   ├── grpc_server.py  # Servicer gRPC
│   ├── main.py         # FastAPI app + lifespan
│   ├── store.py        # Cache mémoire Docker
│   └── Dockerfile
├── frontend/           # Dashboard Next.js 15
│   ├── src/
│   │   ├── app/        # Pages (/, /login)
│   │   ├── components/ # NodeCard, MetricGauge, Sparkline…
│   │   ├── hooks/      # useDashboard, useAuth
│   │   └── types/      # Interfaces TypeScript
│   └── Dockerfile
├── proto/
│   └── monitor.proto   # Définition gRPC/Protobuf
├── config/
│   └── alerts.yaml     # Seuils d'alerte configurables
├── certs/              # Certificats TLS (gitignorés)
├── nginx/
│   └── nginx.conf      # Reverse proxy HTTPS
├── scripts/
│   └── gen-certs.sh    # Générateur de certificats
├── docker-compose.yml
└── Makefile
```

### Commandes utiles

```bash
# Générer les certificats (à faire une seule fois)
make gen-certs

# Installer toutes les dépendances
make deps

# Générer les stubs gRPC (après modification de proto/monitor.proto)
make proto

# Démarrer InfluxDB seul (développement)
docker compose up influxdb -d

# Démarrer le serveur Python
make run-server

# Compiler et démarrer l'agent Go
make run-agent

# Démarrer le frontend
make run-frontend    # → http://localhost:3000

# Build de l'agent pour la production
make build
```

### Développement sans TLS (mode local)

Omettre les variables `CLOUDVIGIL_TLS_*` dans le serveur et l'agent :

```bash
# Terminal 1 — Serveur (sans mTLS)
PYTHONPATH=. python server/main.py

# Terminal 2 — Agent (sans mTLS)
./agent/bin/cloudvigil-agent
```

Le serveur affichera un avertissement `⚠️ non chiffré` dans les logs.

---

## Configuration des alertes

Éditez `config/alerts.yaml` pour définir vos seuils :

```yaml
rules:
  - name: "CPU critique"
    metric: cpu_usage      # cpu_usage | ram_usage | disk_usage
    operator: ">"
    threshold: 90.0        # Valeur en pourcentage
    duration_minutes: 5    # Durée minimale de dépassement
    cooldown_minutes: 30   # Délai avant la prochaine alerte
    severity: critical     # info | warning | critical

webhooks:
  slack:
    enabled: true
    url: "https://hooks.slack.com/services/T.../B.../..."
  discord:
    enabled: false
    url: "https://discord.com/api/webhooks/..."
```

**Tester les webhooks** :
```bash
curl -X POST https://localhost/api/alerts/test \
  -H "Authorization: Bearer $TOKEN"
```

**Consulter l'état du moteur** :
```bash
curl https://localhost/api/alerts/status \
  -H "Authorization: Bearer $TOKEN"
```

---

## API REST

Documentation interactive disponible sur `https://localhost/api/docs`

| Méthode | Endpoint | Auth | Description |
|---------|----------|------|-------------|
| `POST` | `/auth/token` | Non | Obtenir un Bearer JWT |
| `GET` | `/health` | Non | Healthcheck global |
| `GET` | `/dashboard` | JWT | Données complètes (nœuds + historique + Docker) |
| `GET` | `/nodes` | JWT | Liste des nœuds |
| `GET` | `/nodes/{id}/containers` | JWT | Conteneurs Docker d'un nœud |
| `GET` | `/alerts/status` | JWT | État du moteur d'alertes |
| `POST` | `/alerts/test` | JWT | Notification de test |
| `DELETE` | `/alerts/cooldown/{node}/{rule}` | JWT | Réinitialiser un cooldown |

**Obtenir un token JWT** :
```bash
TOKEN=$(curl -s -X POST https://localhost/api/auth/token \
  -d "username=admin&password=cloudvigil" \
  --insecure | jq -r .access_token)

# Appel authentifié
curl https://localhost/api/dashboard \
  -H "Authorization: Bearer $TOKEN" \
  --insecure
```

---

## Production

### Checklist de sécurité

- [ ] Remplacer `CLOUDVIGIL_JWT_SECRET` par une chaîne aléatoire de 64+ caractères
- [ ] Changer `CLOUDVIGIL_API_PASSWORD` et `INFLUXDB_ADMIN_PASSWORD`
- [ ] Remplacer les certificats auto-signés par Let's Encrypt ou une PKI d'entreprise
- [ ] Configurer un pare-feu pour n'exposer que les ports 80, 443, et 50051
- [ ] Activer HTTPS sur InfluxDB
- [ ] Restreindre le token InfluxDB au seul bucket `system_metrics`
- [ ] Activer les alertes (Slack / Discord) dans `config/alerts.yaml`

### Renouvellement des certificats agent

```bash
# Générer un nouveau certificat agent (sans toucher à la CA)
openssl genrsa -out certs/agent/agent.key 2048
openssl req -new -key certs/agent/agent.key -out /tmp/agent.csr -subj "/C=FR/O=CloudVigil/CN=cloudvigil-agent"
openssl x509 -req -days 730 -in /tmp/agent.csr \
  -CA certs/ca/ca.crt -CAkey certs/ca/ca.key -CAcreateserial \
  -out certs/agent/agent.crt

# Redistribuer agent.crt et agent.key sur les serveurs distants
# Redémarrer les agents
```

### Let's Encrypt (production)

Remplacez le certificat Nginx auto-signé par un certificat Let's Encrypt :

```bash
# Avec certbot
certbot certonly --standalone -d votre-domaine.com

# Mettre à jour nginx.conf
ssl_certificate     /etc/letsencrypt/live/votre-domaine.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/votre-domaine.com/privkey.pem;
```

---

## Licence

MIT
