"""Orchestrateur / modèle ambassadeur : point central de coordination (cadrage §4).

Reçoit les demandes de l'IHM, détermine le type d'identifiant, sollicite le
service OCR quand une image est fournie, interroge Data Access (qui gère
Redis et PostgreSQL) et assemble une réponse cohérente.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .clients import DataAccessClient, OcrClient
from .config import Settings
from .errors import ApiError
from .identifiers import Identifier, InvalidIdentifier, classify
from .models import (
    CacheStatsResponse,
    IdentifierOut,
    Product,
    ScanRequest,
    ScanResponse,
    SearchResponse,
)

_CHUNK = 64 * 1024


def create_app(
    settings: Settings | None = None,
    data_transport: httpx.AsyncBaseTransport | None = None,
    ocr_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Fabrique de l'application ; les transports permettent de simuler les services dans les tests."""
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with (
            httpx.AsyncClient(
                base_url=cfg.dataaccess_url, timeout=cfg.dataaccess_timeout, transport=data_transport
            ) as data_http,
            httpx.AsyncClient(
                base_url=cfg.ocr_url, timeout=cfg.ocr_timeout, transport=ocr_transport
            ) as ocr_http,
        ):
            app.state.data = DataAccessClient(data_http)
            app.state.ocr = OcrClient(ocr_http)
            yield

    # La documentation interactive n'est pas exposée : le port 8080 ne publie que l'API utile.
    app = FastAPI(
        title="Orchestrateur",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------ erreurs
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"error": exc.message, "code": exc.code}, status_code=exc.status_code)

    @app.exception_handler(InvalidIdentifier)
    async def _invalid_identifier(_: Request, exc: InvalidIdentifier) -> JSONResponse:
        return JSONResponse({"error": exc.message, "code": exc.code}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Les valeurs saisies ne sont pas renvoyées : seuls le champ et le motif le sont.
        details = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            {"error": "Requête invalide.", "code": "invalid_request", "details": details},
            status_code=422,
        )

    # ------------------------------------------------------------ outils
    async def _lookup(
        request: Request, identifier: Identifier, source: str, detected_by: str | None = None
    ) -> ScanResponse:
        raw, cache = await request.app.state.data.lookup(identifier)
        return ScanResponse(
            identifier=IdentifierOut(type=identifier.type, value=identifier.value),
            found=raw is not None,
            product=Product.model_validate(raw) if raw is not None else None,
            cache=cache,
            source=source,  # type: ignore[arg-type]
            detected_by=detected_by,  # type: ignore[arg-type]
        )

    async def _read_limited(file: UploadFile, limit: int) -> bytes:
        data = bytearray()
        while chunk := await file.read(_CHUNK):
            data.extend(chunk)
            if len(data) > limit:
                raise ApiError(413, "image_too_large", f"L'image dépasse {limit // 1_000_000} Mo.")
        return bytes(data)

    # ------------------------------------------------------------ routes
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/scan", response_model=ScanResponse)
    async def scan(body: ScanRequest, request: Request) -> ScanResponse:
        """Identifiant saisi ou lu par l'IHM (EAN-13 ou contenu de QR Code)."""
        identifier = classify(body.code, body.type)
        return await _lookup(request, identifier, source="text")

    @app.post("/api/scan/image", response_model=ScanResponse)
    async def scan_image(request: Request, file: UploadFile = File(...)) -> ScanResponse:
        """Image d'un code : le service OCR en extrait l'identifiant avant la recherche."""
        content_type = file.content_type or ""
        if not content_type.startswith("image/"):
            raise ApiError(415, "unsupported_media_type", "Un fichier image est attendu.")

        content = await _read_limited(file, cfg.max_upload_bytes)
        if not content:
            raise ApiError(422, "empty_file", "Le fichier est vide.")

        candidates = await request.app.state.ocr.decode(content, content_type)
        for candidate in candidates:
            try:
                identifier = classify(candidate.value, candidate.type if candidate.type in ("ean13", "qr") else "auto")
            except InvalidIdentifier:
                continue
            detected_by = "text" if candidate.source == "text" else "barcode"
            return await _lookup(request, identifier, source="image", detected_by=detected_by)

        raise ApiError(422, "no_code_found", "Aucun QR Code ni EAN-13 détecté dans l'image.")

    @app.get("/api/products/search", response_model=SearchResponse)
    async def search(
        request: Request,
        q: str = Query("", max_length=100),
        limit: int = Query(20, ge=1, le=50),
    ) -> SearchResponse:
        items, cache = await request.app.state.data.search(q.strip(), limit)
        return SearchResponse(items=[Product.model_validate(i) for i in items], cache=cache)

    @app.get("/api/cache/stats", response_model=CacheStatsResponse)
    async def cache_stats(request: Request) -> CacheStatsResponse:
        return CacheStatsResponse.model_validate(await request.app.state.data.cache_stats())

    return app


app = create_app()
