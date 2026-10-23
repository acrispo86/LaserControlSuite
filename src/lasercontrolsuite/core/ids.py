"""Generazione di ID univoci."""

from __future__ import annotations

import uuid


def new_id() -> str:
    """Restituisce un UUID4 come stringa."""
    return str(uuid.uuid4())