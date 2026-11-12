"""Clients HTTP vers les services internes (Data Access C# et OCR Python)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .errors import ApiError
from .identifiers import Identifier


def _unavailable(service: str) -> ApiError:
    return ApiError(503, f"{service}_unavailable", "Un service interne est momentanément indisponible.")


def _bad_gateway(service: str) -> ApiError:
    return ApiError(502, f"{service}_bad_response", "Réponse inattendue d'un service interne.")


def _json(resp: httpx.Response, service: str) -> Any:
    try:
        return resp.json()
    except ValueError:
        raise _bad_gateway(service) from None


class DataAccessClient:
    """Seul chemin vers les données : l'orchestrateur n'accède ni à Redis ni à PostgreSQL."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._http = client

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        try:
            return await self._http.get(path, params=params)
        except httpx.HTTPError:
            raise _unavailable("dataaccess") from None

    async def lookup(self, identifier: Identifier) -> tuple[dict[str, Any] | None, str]:
        key = "ean13" if identifier.type == "ean13" else "qr"
        resp = await self._get("/products/lookup", {key: identifier.value})
        cache = resp.headers.get("X-Cache", "BYPASS")
        if resp.status_code == 404:
            return None, cache
        if resp.status_code != 200:
            raise _bad_gateway("dataaccess")
        return _json(resp, "dataaccess"), cache

    async def search(self, q: str, limit: int) -> tuple[list[dict[str, Any]], str]:
        resp = await self._get("/products/search", {"q": q, "limit": limit})
        if resp.status_code != 200:
            raise _bad_gateway("dataaccess")
        body = _json(resp, "dataaccess")
        return body.get("items", []), resp.headers.get("X-Cache", "BYPASS")

    async def cache_stats(self) -> dict[str, Any]:
        resp = await self._get("/cache/stats")
        if resp.status_code != 200:
            raise _bad_gateway("dataaccess")
        return _json(resp, "dataaccess")


@dataclass(frozen=True)
class OcrCandidate:
    type: str  # "ean13" ou "qr"
    value: str
    source: str  # "barcode" (lecture de code) ou "text" (OCR du texte imprimé)


class OcrClient:
    """Service d'extraction de codes depuis une image, remplaçable indépendamment."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._http = client

    async def decode(self, content: bytes, content_type: str) -> list[OcrCandidate]:
        # Le nom de fichier de l'utilisateur n'est volontairement pas transmis.
        files = {"file": ("image", content, content_type)}
        try:
            resp = await self._http.post("/decode", files=files)
        except httpx.HTTPError:
            raise _unavailable("ocr") from None

        if resp.status_code in (400, 413, 415, 422):
            raise ApiError(422, "invalid_image", "L'image n'a pas pu être lue.")
        if resp.status_code != 200:
            raise _bad_gateway("ocr")

        body = _json(resp, "ocr")
        try:
            return [
                OcrCandidate(str(c["type"]), str(c["value"]), str(c.get("source", "barcode")))
                for c in body.get("candidates", [])
            ]
        except (KeyError, TypeError, AttributeError):
            raise _bad_gateway("ocr") from None
