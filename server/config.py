"""Configuration centralisée de CloudVigil Server via variables d'environnement."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLOUDVIGIL_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── gRPC ──────────────────────────────────────────────────────────────────
    grpc_listen: str = "[::]:50051"

    # ── HTTP / FastAPI ─────────────────────────────────────────────────────────
    http_host: str = "0.0.0.0"
    http_port: int = 8000

    # ── InfluxDB ───────────────────────────────────────────────────────────────
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = "cloudvigil-dev-token"
    influxdb_org: str = "cloudvigil"
    influxdb_bucket: str = "system_metrics"

    # ── Alertes ────────────────────────────────────────────────────────────────
    alerts_config_path: str = "config/alerts.yaml"

    # ── TLS / mTLS gRPC ────────────────────────────────────────────────────────
    # Laisser vide pour désactiver mTLS (mode développement non sécurisé).
    tls_ca_cert:     str = ""   # CLOUDVIGIL_TLS_CA_CERT     → certs/ca/ca.crt
    tls_server_cert: str = ""   # CLOUDVIGIL_TLS_SERVER_CERT → certs/server/server.crt
    tls_server_key:  str = ""   # CLOUDVIGIL_TLS_SERVER_KEY  → certs/server/server.key

    # ── JWT API ────────────────────────────────────────────────────────────────
    # IMPÉRATIF : changer jwt_secret en production (min. 32 caractères aléatoires).
    jwt_secret:         str = "changeme-use-a-long-random-secret-in-production"
    jwt_algorithm:      str = "HS256"
    jwt_expire_minutes: int = 480   # 8 heures

    # Identifiants de l'administrateur (surcharger via variables d'env en prod).
    api_username: str = "admin"
    api_password: str = "cloudvigil"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne l'instance unique des paramètres (mise en cache)."""
    return Settings()
