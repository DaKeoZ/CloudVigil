"""
Modèles de données et chargement de la configuration d'alertes depuis le YAML.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

log = logging.getLogger(__name__)

Operator  = Literal[">", ">=", "<", "<="]
Severity  = Literal["info", "warning", "critical"]
MetricKey = Literal["cpu_usage", "ram_usage", "disk_usage"]

# Mapping opérateur texte → lambda Python
_OPS: dict[str, object] = {
    ">":  lambda v, t: v > t,
    ">=": lambda v, t: v >= t,
    "<":  lambda v, t: v < t,
    "<=": lambda v, t: v <= t,
}


@dataclass(frozen=True)
class AlertRule:
    name:             str
    metric:           MetricKey
    operator:         Operator
    threshold:        float
    duration_minutes: int      = 5
    cooldown_minutes: int      = 30
    severity:         Severity = "warning"

    def evaluate(self, value: float) -> bool:
        """Retourne True si la valeur franchit le seuil dans le sens défini."""
        fn = _OPS.get(self.operator)
        return bool(fn(value, self.threshold)) if fn else False

    def to_dict(self) -> dict:
        return {
            "name":             self.name,
            "metric":           self.metric,
            "operator":         self.operator,
            "threshold":        self.threshold,
            "duration_minutes": self.duration_minutes,
            "cooldown_minutes": self.cooldown_minutes,
            "severity":         self.severity,
        }


@dataclass(frozen=True)
class WebhookTarget:
    enabled: bool = False
    url:     str  = ""

    @property
    def is_active(self) -> bool:
        return self.enabled and bool(self.url) and "CHANGE_ME" not in self.url


# ── Auto-réparation ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AutoRepairRule:
    """
    Identifie un conteneur critique par sous-chaîne (insensible à la casse).
    Ex: name_pattern="nginx" correspond à "nginx", "my-nginx-proxy", "/nginx-1"…
    """
    name_pattern: str

    def matches(self, container_name: str) -> bool:
        return self.name_pattern.lower() in container_name.lower()

    def to_dict(self) -> dict:
        return {"name_pattern": self.name_pattern}


@dataclass(frozen=True)
class AutoRepairConfig:
    enabled:           bool             = True
    cooldown_minutes:  int              = 10
    restart_timeout_s: int              = 10
    rules:             tuple[AutoRepairRule, ...]  = field(default_factory=tuple)

    @property
    def is_active(self) -> bool:
        return self.enabled and bool(self.rules)


# ── Config globale ────────────────────────────────────────────────────────────

@dataclass
class AlertConfig:
    rules:       list[AlertRule]  = field(default_factory=list)
    slack:       WebhookTarget    = field(default_factory=WebhookTarget)
    discord:     WebhookTarget    = field(default_factory=WebhookTarget)
    auto_repair: AutoRepairConfig = field(default_factory=AutoRepairConfig)

    @property
    def has_active_webhook(self) -> bool:
        return self.slack.is_active or self.discord.is_active


def load_alert_config(path: Path | str) -> AlertConfig:
    """
    Charge `config/alerts.yaml` et retourne un AlertConfig.
    Retourne une configuration vide (sans règles) si le fichier est absent.
    """
    p = Path(path)
    if not p.exists():
        log.warning("[alerts] Fichier de configuration introuvable : %s — alertes désactivées.", p)
        return AlertConfig()

    try:
        with p.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        log.error("[alerts] Erreur de parsing YAML (%s) : %s", p, exc)
        return AlertConfig()

    # ── Règles ────────────────────────────────────────────────────────────────
    rules: list[AlertRule] = []
    for r in raw.get("rules", []):
        try:
            rules.append(
                AlertRule(
                    name=str(r["name"]),
                    metric=r["metric"],
                    operator=r["operator"],
                    threshold=float(r["threshold"]),
                    duration_minutes=int(r.get("duration_minutes", 5)),
                    cooldown_minutes=int(r.get("cooldown_minutes", 30)),
                    severity=r.get("severity", "warning"),
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            log.warning("[alerts] Règle ignorée (données invalides) : %s — %s", r, exc)

    # ── Webhooks ──────────────────────────────────────────────────────────────
    wh = raw.get("webhooks", {})
    slack_raw   = wh.get("slack",   {})
    discord_raw = wh.get("discord", {})

    # ── Auto-réparation ───────────────────────────────────────────────────────
    ar_raw = raw.get("auto_repair", {})
    repair_rules: list[AutoRepairRule] = []
    for c in ar_raw.get("containers", []):
        pat = c.get("name_pattern", "").strip()
        if pat:
            repair_rules.append(AutoRepairRule(name_pattern=pat))

    auto_repair = AutoRepairConfig(
        enabled=bool(ar_raw.get("enabled", True)),
        cooldown_minutes=int(ar_raw.get("cooldown_minutes", 10)),
        restart_timeout_s=int(ar_raw.get("restart_timeout_s", 10)),
        rules=tuple(repair_rules),
    )

    cfg = AlertConfig(
        rules=rules,
        slack=WebhookTarget(
            enabled=bool(slack_raw.get("enabled", False)),
            url=str(slack_raw.get("url", "")),
        ),
        discord=WebhookTarget(
            enabled=bool(discord_raw.get("enabled", False)),
            url=str(discord_raw.get("url", "")),
        ),
        auto_repair=auto_repair,
    )

    log.info(
        "[alerts] Config chargée : %d règle(s), %d conteneur(s) surveillé(s), Slack=%s, Discord=%s",
        len(rules),
        len(repair_rules),
        "✓" if cfg.slack.is_active  else "✗",
        "✓" if cfg.discord.is_active else "✗",
    )
    return cfg
