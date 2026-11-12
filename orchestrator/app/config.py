"""Configuration de l'orchestrateur, lue depuis les variables d'environnement."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    dataaccess_url: str = "http://dataaccess:8000"
    ocr_url: str = "http://ocr:8000"
    # Taille maximale d'une image envoyée par l'utilisateur (octets).
    max_upload_bytes: int = 5_000_000
    dataaccess_timeout: float = 5.0
    ocr_timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            dataaccess_url=os.environ.get("DATAACCESS_URL", cls.dataaccess_url).rstrip("/"),
            ocr_url=os.environ.get("OCR_URL", cls.ocr_url).rstrip("/"),
            max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", cls.max_upload_bytes)),
        )
