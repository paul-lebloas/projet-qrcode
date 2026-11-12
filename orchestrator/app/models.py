"""Contrats d'API exposés à l'IHM."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScanRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2048, description="EAN-13 ou contenu d'un QR Code")
    type: Literal["auto", "ean13", "qr"] = "auto"


class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    ean13: str | None = None
    qr_code: str | None = None
    name: str
    brand: str | None = None
    category: str | None = None
    description: str | None = None


class IdentifierOut(BaseModel):
    type: Literal["ean13", "qr"]
    value: str


class ScanResponse(BaseModel):
    identifier: IdentifierOut
    found: bool
    product: Product | None = None
    # Origine de la réponse côté cache Redis : HIT, MISS ou BYPASS (Redis indisponible).
    cache: str
    # "text" : code saisi ; "image" : code extrait d'une image par le service OCR.
    source: Literal["text", "image"]
    detected_by: Literal["barcode", "text"] | None = None


class SearchResponse(BaseModel):
    items: list[Product]
    cache: str


class CacheStatsResponse(BaseModel):
    hits: int
    misses: int
    hit_ratio: float
    redis: str
