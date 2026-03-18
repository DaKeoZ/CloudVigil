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
    # Chemin vers le fichier YAML de configuration des alertes.
    # Relatif au répertoire de travail courant (racine du projet).
    alerts_config_path: str = "config/alerts.yaml"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne l'instance unique des paramètres (mise en cache)."""
    return Settings()
