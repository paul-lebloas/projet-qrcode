"""Service OCR : indépendant du reste de l'application (cadrage §5).

Contrat : POST /decode (multipart, champ `file`) -> {"candidates": [{type, value, source}]}.
Tant que ce contrat est respecté, ce service peut être remplacé ou amélioré
sans toucher à l'orchestrateur.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from .decoder import InvalidImage, extract_candidates

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 5_000_000))

app = FastAPI(title="OCR", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Fonction synchrone : FastAPI l'exécute dans un thread, la boucle d'événements reste libre
# pendant le décodage (ZBar) et l'appel à Tesseract.
@app.post("/decode")
def decode(file: UploadFile = File(...)):
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": "Image trop volumineuse."}, status_code=413)
    if not data:
        return JSONResponse({"error": "Fichier vide."}, status_code=422)

    try:
        candidates = extract_candidates(data)
    except InvalidImage as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    return {"candidates": [{"type": c.type, "value": c.value, "source": c.source} for c in candidates]}
