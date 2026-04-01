# CloudVigil

Outil de monitoring cloud open-source : métriques système (CPU, RAM, disque), conteneurs Docker, supervision réseau (latence + SSL), alertes webhook, auto-réparation des services.

```
[Agent Go] ──mTLS gRPC──▶ [Serveur Python] ──▶ [InfluxDB]
    │ Docker metrics            │ FastAPI REST + JWT
    └── WebSocket logs          └──▶ [Nginx HTTPS] ──▶ [Dashboard Next.js]
```

---

## Ports utilisés

| Port | Service | Modifiable | Description |
|------|---------|------------|-------------|
| **443** | Nginx | ✅ `CV_HTTPS_PORT` | Dashboard + API (HTTPS) |
| **80** | Nginx | ✅ `CV_HTTP_PORT` | Redirection automatique vers 443 |
| **50051** | Serveur gRPC | ✅ `CV_GRPC_PORT` | Agents distants → Master |
| 8000 | FastAPI | ✗ interne | API interne, non exposé |
| 8086 | InfluxDB | ✗ interne | Base de données, non exposé |
| 3000 | Next.js | ✗ interne | Frontend, non exposé |

> **Si des ports sont déjà utilisés sur votre VPS**, ajoutez simplement ces lignes dans votre fichier `.env` :
> ```
> CV_HTTP_PORT=8080
> CV_HTTPS_PORT=8443
> CV_GRPC_PORT=50052
> ```
> Aucune modification de fichier de configuration nécessaire.

---

## Guide de déploiement — étape par étape

Ce guide couvre l'installation complète de CloudVigil sur un VPS/serveur, depuis zéro jusqu'au dashboard accessible en HTTPS.

### Prérequis

Votre serveur doit avoir :

```bash
# Vérifier les versions
docker --version          # Docker ≥ 24
docker compose version    # Docker Compose v2 ≥ 2.20
git --version             # Git (n'importe quelle version récente)
openssl version           # OpenSSL ≥ 1.1
```

> **Docker Compose v2** : la commande est `docker compose` (avec espace), pas `docker-compose`.

---

### Étape 1 — Récupérer le code

```bash
git clone https://github.com/votre-org/cloudvigil.git
cd cloudvigil
```

---

### Étape 2 — Choisir vos ports

Vérifiez quels ports sont déjà utilisés sur votre serveur :

```bash
ss -tlnp | grep -E '80|443|50051'
```

Créez ensuite le fichier `.env` à la racine du projet. Ce fichier centralise **toute** la configuration sensible et les ports :

```bash
# Créer le fichier .env (ne jamais le versionner — déjà dans .gitignore)
cat > .env << 'EOF'
# ── Ports ─────────────────────────────────────────────────────────────────────
# Modifier uniquement si ces ports sont déjà pris sur votre machine.
# Laisser vide = valeur par défaut (80, 443, 50051).
CV_HTTP_PORT=80
CV_HTTPS_PORT=443
CV_GRPC_PORT=50051

# ── Sécurité (OBLIGATOIRE en production) ──────────────────────────────────────
# Générer une clé JWT aléatoire :
#   openssl rand -hex 32
CLOUDVIGIL_JWT_SECRET=REMPLACER_PAR_UNE_CHAINE_ALEATOIRE_64_CHARS

# Identifiants du dashboard (page de connexion)
CLOUDVIGIL_API_USERNAME=admin
CLOUDVIGIL_API_PASSWORD=REMPLACER_PAR_UN_MOT_DE_PASSE_FORT

# ── InfluxDB ──────────────────────────────────────────────────────────────────
INFLUXDB_ADMIN_PASSWORD=REMPLACER_PAR_UN_MOT_DE_PASSE_INFLUX
INFLUXDB_ADMIN_TOKEN=REMPLACER_PAR_UN_TOKEN_INFLUX_SECRET
EOF
```

> **Important** : remplacez chaque valeur `REMPLACER_PAR_...` par de vraies valeurs.  
> Pour générer une clé aléatoire : `openssl rand -hex 32`

---

### Étape 3 — Générer les certificats TLS

CloudVigil utilise des certificats pour :
- **Nginx** : chiffrer l'accès HTTPS au dashboard
- **gRPC mTLS** : authentifier mutuellement le serveur et les agents

```bash
bash scripts/gen-certs.sh
```

Cela crée automatiquement dans `certs/` :

```
certs/
├── ca/          ← Autorité de certification (à garder précieusement)
│   ├── ca.crt
│   └── ca.key
├── server/      ← Certificat du serveur gRPC
│   ├── server.crt
│   └── server.key
├── agent/       ← Certificat de l'agent (à copier sur chaque machine distante)
│   ├── agent.crt
│   └── agent.key
└── nginx/       ← Certificat HTTPS auto-signé pour le dashboard
    ├── nginx.crt
    └── nginx.key
```

> Ces fichiers sont dans `.gitignore` — ils ne seront jamais versionnés.

---

### Étape 4 — Configurer les alertes (optionnel)

Éditez `config/alerts.yaml` pour adapter les seuils à votre infrastructure et activer les webhooks :

```yaml
# Exemple : alerte si CPU > 90% pendant 5 minutes
rules:
  - name: "CPU critique"
    metric: cpu_usage
    operator: ">"
    threshold: 90.0
    duration_minutes: 5
    cooldown_minutes: 30
    severity: critical

# Surveillance réseau (sites web / APIs externes)
network_checks:
  enabled: true
  targets:
    - url: "https://monsite.com"
      name: "Mon Site"

# Auto-restart des conteneurs critiques si down
auto_repair:
  enabled: true
  containers:
    - name_pattern: "mon-api"

# Notifications (décommenter et renseigner l'URL)
webhooks:
  slack:
    enabled: false
    url: "https://hooks.slack.com/services/..."
```

---

### Étape 4b — Cas particulier : Nginx déjà installé sur le VPS

Si votre VPS fait déjà tourner un Nginx sur les ports 80 et 443 (ce qui est fréquent si vous hébergez d'autres sites), le Nginx intégré à CloudVigil entrerait en conflit. Voici la marche à suivre.

**Dans votre `.env`**, ajoutez les ports internes (ne seront accessibles que depuis `127.0.0.1`) :

```bash
# Ports internes CloudVigil (accessible seulement depuis le VPS lui-même)
# Vérifiez que ces ports sont libres sur votre machine : ss -tlnp | grep -E '8001|3003'
CV_API_PORT=8001       # Port local pour FastAPI (API + WebSocket)
CV_FRONTEND_PORT=3003  # Port local pour le Dashboard Next.js
CV_GRPC_PORT=50051     # Port public pour les agents Go (inchangé)
```

**Lancez CloudVigil SANS le profil `with-nginx`** (pas de Nginx CloudVigil) :

```bash
# Sans --profile with-nginx → le service nginx de CloudVigil ne démarre PAS
docker compose up -d
```

**Ajoutez un virtual host à votre Nginx existant** :

```bash
# Copier le fichier modèle fourni
sudo cp nginx/cloudvigil-vhost.conf /etc/nginx/sites-available/cloudvigil

# Éditer le fichier : remplacer VOTRE_DOMAINE, adapter les ports si besoin
sudo nano /etc/nginx/sites-available/cloudvigil

# Activer le site
sudo ln -s /etc/nginx/sites-available/cloudvigil /etc/nginx/sites-enabled/cloudvigil

# Tester la configuration
sudo nginx -t

# Recharger Nginx (sans coupure de service)
sudo systemctl reload nginx
```

Le fichier `nginx/cloudvigil-vhost.conf` contient une configuration complète avec :
- Redirection HTTP → HTTPS
- Proxy vers FastAPI (`127.0.0.1:8001`) pour l'API REST et les WebSockets
- Proxy vers Next.js (`127.0.0.1:3003`) pour le dashboard
- En-têtes de sécurité

> **Note sur les ports 8001 et 3003** : ces ports sont uniquement liés à `127.0.0.1`
> (réseau de loopback) — ils ne sont jamais accessibles depuis Internet, uniquement
> depuis le VPS lui-même via le Nginx local.

---

### Étape 5 — Lancer la stack

```bash
docker compose up -d
```

Docker va construire les images et démarrer les 4 services. La première fois prend 3 à 5 minutes.

Vérifier que tout est démarré et sain :

```bash
docker compose ps
```

Le résultat attendu (colonne `STATUS`) :

```
NAME                    STATUS
cloudvigil-influxdb     Up X minutes (healthy)
cloudvigil-server       Up X minutes (healthy)
cloudvigil-frontend     Up X minutes
cloudvigil-nginx        Up X minutes (healthy)
```

> Si un service est en `Restarting`, consultez ses logs :
> ```bash
> docker compose logs server --tail 50
> ```

---

### Étape 6 — Accéder au dashboard

Ouvrez votre navigateur :

```
https://ADRESSE_IP_DU_SERVEUR
# ou si vous avez changé le port HTTPS :
https://ADRESSE_IP_DU_SERVEUR:8443
```

> Le navigateur affichera un avertissement "certificat non approuvé" car le certificat est auto-signé. C'est normal — cliquez sur "Avancé" puis "Accéder au site". Pour supprimer cet avertissement, utilisez un vrai certificat (voir [Étape 9](#étape-9--let-s-encrypt-production)).

Identifiants par défaut :
- Utilisateur : valeur de `CLOUDVIGIL_API_USERNAME` (défaut : `admin`)
- Mot de passe : valeur de `CLOUDVIGIL_API_PASSWORD` (défaut : `cloudvigil`)

---

### Étape 7 — Installer un agent sur une machine distante

L'agent Go collecte les métriques d'un serveur et les envoie au Master. Vous en installez un **sur chaque machine que vous voulez surveiller**.

#### 7a. Copier les certificats sur la machine distante

Depuis votre serveur Master (là où tourne CloudVigil) :

```bash
# Créer le dossier de certificats sur la machine distante
ssh user@IP_MACHINE_DISTANTE "mkdir -p /etc/cloudvigil/certs"

# Copier les 3 fichiers nécessaires
scp certs/ca/ca.crt       user@IP_MACHINE_DISTANTE:/etc/cloudvigil/certs/
scp certs/agent/agent.crt user@IP_MACHINE_DISTANTE:/etc/cloudvigil/certs/
scp certs/agent/agent.key user@IP_MACHINE_DISTANTE:/etc/cloudvigil/certs/
```

#### 7b. Lancer l'agent sur la machine distante

Connectez-vous en SSH sur la machine distante, puis :

```bash
docker run -d \
  --name cloudvigil-agent \
  --restart unless-stopped \
  --net host \
  -v /etc/cloudvigil/certs:/certs:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e CLOUDVIGIL_SERVER=IP_DU_MASTER:50051 \
  -e CLOUDVIGIL_NODE_ID=$(hostname) \
  -e CLOUDVIGIL_TLS_CA_CERT=/certs/ca.crt \
  -e CLOUDVIGIL_TLS_AGENT_CERT=/certs/agent.crt \
  -e CLOUDVIGIL_TLS_AGENT_KEY=/certs/agent.key \
  ghcr.io/votre-org/cloudvigil-agent:latest
```

> Remplacez `IP_DU_MASTER` par l'adresse IP publique de votre serveur CloudVigil.  
> Si vous avez changé le port gRPC (`CV_GRPC_PORT=50052`), utilisez ce port ici aussi.

Vérifier que l'agent est connecté :

```bash
docker logs cloudvigil-agent --tail 20
```

Vous devriez voir :
```
[grpc] connecté au Master (IP_DU_MASTER:50051)
[wscontrol] connecté au Master (ws://IP_DU_MASTER:50051)
```

Dans le dashboard, le serveur apparaît dans la grille après quelques secondes.

#### Variables d'environnement de l'agent

| Variable | Défaut | Description |
|----------|--------|-------------|
| `CLOUDVIGIL_SERVER` | `localhost:50051` | Adresse IP:port du serveur gRPC |
| `CLOUDVIGIL_NODE_ID` | `hostname` | Nom affiché dans le dashboard |
| `CLOUDVIGIL_INTERVAL` | `2s` | Fréquence de collecte |
| `CLOUDVIGIL_DISK_PATH` | `/` | Partition à surveiller |
| `CLOUDVIGIL_TLS_CA_CERT` | _(vide)_ | Chemin vers `ca.crt` (activer mTLS) |
| `CLOUDVIGIL_TLS_AGENT_CERT` | _(vide)_ | Chemin vers `agent.crt` |
| `CLOUDVIGIL_TLS_AGENT_KEY` | _(vide)_ | Chemin vers `agent.key` |
| `CLOUDVIGIL_WS_SERVER` | _(vide)_ | `ws://IP_MASTER:PORT` (Log Viewer) |

> **Sans certificats** (si `CLOUDVIGIL_TLS_CA_CERT` est vide), la connexion gRPC est non chiffrée.  
> Acceptable uniquement sur un réseau local privé.

---

### Étape 8 — Pare-feu

Ouvrez uniquement les ports nécessaires sur votre VPS :

```bash
# UFW (Ubuntu/Debian)
ufw allow 80/tcp      # HTTP (redirection → HTTPS)
ufw allow 443/tcp     # Dashboard HTTPS
ufw allow 50051/tcp   # Agents distants (gRPC)
# Si vous avez changé les ports :
# ufw allow CV_HTTP_PORT/tcp
# ufw allow CV_HTTPS_PORT/tcp
# ufw allow CV_GRPC_PORT/tcp
```

> **InfluxDB (8086), FastAPI (8000) et Next.js (3000) ne doivent PAS être ouverts** : ils restent en réseau interne Docker.

---

### Étape 9 — Let's Encrypt (production)

Pour supprimer l'avertissement de certificat dans le navigateur, remplacez le certificat auto-signé par Let's Encrypt.

Prérequis : votre serveur doit avoir un **nom de domaine** pointant vers son IP.

```bash
# Installer certbot (si absent)
apt install certbot -y   # Debian/Ubuntu

# Obtenir le certificat (stopper Nginx le temps de la validation)
docker compose stop nginx
certbot certonly --standalone -d votre-domaine.com
docker compose start nginx

# Les certificats sont dans :
# /etc/letsencrypt/live/votre-domaine.com/fullchain.pem
# /etc/letsencrypt/live/votre-domaine.com/privkey.pem
```

Mettre à jour `nginx/nginx.conf` pour pointer vers les nouveaux certificats :

```nginx
ssl_certificate     /etc/nginx/certs/fullchain.pem;
ssl_certificate_key /etc/nginx/certs/privkey.pem;
```

Mettre à jour `docker-compose.yml` pour monter les certificats Let's Encrypt :

```yaml
nginx:
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - /etc/letsencrypt/live/votre-domaine.com:/etc/nginx/certs:ro
```

Redémarrer Nginx :

```bash
docker compose restart nginx
```

---

## Commandes de maintenance

```bash
# Voir les logs en temps réel
docker compose logs -f

# Voir les logs d'un service spécifique
docker compose logs server --tail 100
docker compose logs nginx  --tail 50

# Redémarrer un service
docker compose restart server

# Arrêter toute la stack (données conservées)
docker compose stop

# Arrêter ET supprimer les conteneurs (données conservées dans les volumes)
docker compose down

# Mise à jour de la stack
git pull
docker compose build
docker compose up -d

# Renouveler les certificats agent (sans toucher à la CA)
openssl genrsa -out certs/agent/agent.key 2048
openssl req -new -key certs/agent/agent.key \
  -out /tmp/agent.csr -subj "/C=FR/O=CloudVigil/CN=cloudvigil-agent"
openssl x509 -req -days 730 -in /tmp/agent.csr \
  -CA certs/ca/ca.crt -CAkey certs/ca/ca.key -CAcreateserial \
  -out certs/agent/agent.crt
# Redéployer l'agent sur les machines distantes
```

---

## API REST

Documentation interactive : `https://VOTRE_DOMAINE/api/docs`

```bash
# Obtenir un token JWT
TOKEN=$(curl -sk -X POST https://localhost/api/auth/token \
  -d "username=admin&password=VOTRE_MOT_DE_PASSE" | jq -r .access_token)

# Exemples d'appels
curl -sk https://localhost/api/dashboard       -H "Authorization: Bearer $TOKEN" | jq
curl -sk https://localhost/api/network         -H "Authorization: Bearer $TOKEN" | jq
curl -sk https://localhost/api/repairs         -H "Authorization: Bearer $TOKEN" | jq
curl -sk https://localhost/api/alerts/status   -H "Authorization: Bearer $TOKEN" | jq

# Tester les webhooks
curl -sk -X POST https://localhost/api/alerts/test -H "Authorization: Bearer $TOKEN"
```

| Méthode | Endpoint | Auth | Description |
|---------|----------|------|-------------|
| `POST` | `/auth/token` | Non | Obtenir un Bearer JWT |
| `GET` | `/health` | Non | Healthcheck global |
| `GET` | `/dashboard` | JWT | Nœuds + historique + Docker |
| `GET` | `/nodes` | JWT | Liste des nœuds actifs |
| `GET` | `/nodes/{id}/containers` | JWT | Conteneurs Docker d'un nœud |
| `GET` | `/network` | JWT | État des services réseau surveillés |
| `GET` | `/repairs` | JWT | Historique des auto-réparations |
| `GET` | `/alerts/status` | JWT | État du moteur d'alertes |
| `POST` | `/alerts/test` | JWT | Notification de test webhook |
| `DELETE` | `/alerts/cooldown/{node}/{rule}` | JWT | Réinitialiser un cooldown |

---

## Structure du projet

```
cloudvigil/
├── agent/                  # Agent Go
│   ├── internal/
│   │   ├── connect/        # Backoff exponentiel (reconnexion)
│   │   ├── docker/         # Collecteur Docker SDK
│   │   ├── metrics/        # Collecteur CPU/RAM/Disque (gopsutil)
│   │   └── wscontrol/      # Canal WebSocket (logs + auto-réparation)
│   ├── pb/                 # Stubs gRPC générés (Go)
│   └── main.go
├── server/                 # Serveur Python
│   ├── alerts/             # Moteur d'alertes (YAML + webhook + auto-réparation)
│   ├── network/            # Sonde réseau HTTP + SSL
│   ├── pb/                 # Stubs gRPC générés (Python)
│   ├── auth.py             # JWT
│   ├── config.py           # Settings (pydantic-settings)
│   ├── database.py         # Client InfluxDB async
│   ├── grpc_server.py      # Servicer gRPC
│   ├── main.py             # FastAPI app + lifespan
│   ├── store.py            # Cache mémoire Docker
│   ├── ws_hub.py           # Hub WebSocket (logs + auto-réparation)
│   └── Dockerfile
├── frontend/               # Dashboard Next.js 15
│   ├── src/
│   │   ├── app/            # Pages (/, /login)
│   │   ├── components/     # NodeCard, NetworkHealth, RepairHistory…
│   │   ├── hooks/          # useDashboard, useAuth, useNetwork, useRepairs
│   │   └── types/          # Interfaces TypeScript
│   └── Dockerfile
├── proto/
│   └── monitor.proto       # Définition gRPC/Protobuf
├── config/
│   └── alerts.yaml         # Alertes + auto-réparation + supervision réseau
├── certs/                  # Certificats TLS (gitignorés)
├── nginx/
│   └── nginx.conf          # Reverse proxy HTTPS
├── scripts/
│   └── gen-certs.sh        # Générateur de certificats OpenSSL
├── .env                    # Secrets et ports (gitignorés — À CRÉER)
├── docker-compose.yml
└── Makefile
```

---

## Checklist de sécurité avant la mise en production

- [ ] `CLOUDVIGIL_JWT_SECRET` → chaîne aléatoire de 64+ caractères (`openssl rand -hex 32`)
- [ ] `CLOUDVIGIL_API_PASSWORD` → mot de passe fort
- [ ] `INFLUXDB_ADMIN_PASSWORD` et `INFLUXDB_ADMIN_TOKEN` → valeurs uniques
- [ ] Certificats auto-signés remplacés par Let's Encrypt (si domaine public)
- [ ] Pare-feu configuré (seuls 80, 443, 50051 ouverts)
- [ ] Fichier `.env` avec permissions restrictives : `chmod 600 .env`

---

## Licence

MIT
