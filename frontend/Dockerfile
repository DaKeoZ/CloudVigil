# ==============================================================================
# CloudVigil Frontend — Dockerfile multi-stage
# ==============================================================================
# Stage 1 (builder) : installe toutes les dépendances + build Next.js
# Stage 2 (runner)  : image minimale avec les artefacts de production uniquement
# ==============================================================================

# ── Stage 1 : Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copier les manifestes de dépendances en premier (cache layer)
COPY package.json package-lock.json* ./
RUN npm ci

# Copier le code source
COPY . .

# NEXT_PUBLIC_API_URL est injecté au moment du build (valeur statique dans le JS).
# En production derrière Nginx : /api (chemin relatif → même origine).
ARG  NEXT_PUBLIC_API_URL=/api
ENV  NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Build de production
RUN npm run build

# ── Stage 2 : Runner ──────────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Créer un utilisateur non-root pour la sécurité
RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# Copier les artefacts de build
COPY --from=builder /app/public          ./public
COPY --from=builder /app/.next           ./.next
COPY --from=builder /app/node_modules    ./node_modules
COPY --from=builder /app/package.json    ./

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node_modules/.bin/next", "start"]
