"""
Authentification JWT pour l'API FastAPI CloudVigil.

Flux :
  1. POST /auth/token  (form OAuth2 : username + password)
     → retourne { access_token, token_type, expires_in }

  2. Endpoints protégés utilisent Depends(get_current_user) :
     → valide le Bearer token JWT dans l'en-tête Authorization.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from server.config import get_settings

log = logging.getLogger(__name__)

# Schéma OAuth2 Bearer — indique à FastAPI/Swagger où chercher le token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


# ── Modèles de réponse ────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int           # durée de validité en secondes


# ── Fonctions utilitaires ─────────────────────────────────────────────────────

def verify_credentials(username: str, password: str) -> bool:
    """Vérifie les identifiants contre ceux configurés (env vars ou défauts)."""
    settings = get_settings()
    return username == settings.api_username and password == settings.api_password


def create_access_token(subject: str) -> tuple[str, int]:
    """
    Génère un JWT signé avec le secret configuré.

    Retourne (encoded_token, expires_in_seconds).
    """
    settings = get_settings()
    expire_seconds = settings.jwt_expire_minutes * 60
    expire_at      = datetime.now(tz=timezone.utc) + timedelta(seconds=expire_seconds)

    payload = {
        "sub": subject,
        "exp": expire_at,
        "iat": datetime.now(tz=timezone.utc),
        "iss": "cloudvigil",
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expire_seconds


# ── Dépendance FastAPI ────────────────────────────────────────────────────────

async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> str:
    """
    Dépendance FastAPI : valide le Bearer JWT et retourne le subject (username).

    Lève HTTP 401 si le token est absent, invalide ou expiré.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise. Obtenez un token via POST /auth/token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        sub: str | None = payload.get("sub")
        if not sub:
            raise ValueError("Payload JWT sans 'sub'.")
    except (JWTError, ValueError) as exc:
        log.warning("[auth] Token invalide : %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'accès invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return sub


# Type annoté réutilisable dans les signatures de route
CurrentUser = Annotated[str, Depends(get_current_user)]
