"""Tests de l'orchestrateur avec Data Access et OCR simulés (httpx.MockTransport)."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PRODUCT = {
    "id": 1,
    "ean13": "3760000000017",
    "qr_code": "https://produits.example/p/1001",
    "name": "Biscuits sablés pur beurre 200 g",
    "brand": "Maison Démo",
    "category": "Épicerie sucrée",
    "description": "Sablés au beurre doux.",
    "created_at": "2026-10-08T10:00:00+00:00",
    "updated_at": "2026-10-08T10:00:00+00:00",
}


class FakeDataAccess:
    """Simule Data Access, y compris l'en-tête X-Cache (MISS à la 1re lecture, puis HIT)."""

    def __init__(self):
        self.down = False
        self.seen: set[str] = set()
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("data access down")
        self.requests.append(request)
        path, params = request.url.path, dict(request.url.params)

        if path == "/products/lookup":
            key = params.get("ean13") or params.get("qr")
            found = key in (PRODUCT["ean13"], PRODUCT["qr_code"])
            cache = "HIT" if key in self.seen else "MISS"
            self.seen.add(key)
            if not found:
                return httpx.Response(404, json={"error": "Produit inconnu."}, headers={"X-Cache": cache})
            return httpx.Response(200, json=PRODUCT, headers={"X-Cache": cache})
        if path == "/products/search":
            return httpx.Response(200, json={"items": [PRODUCT]}, headers={"X-Cache": "MISS"})
        if path == "/cache/stats":
            return httpx.Response(200, json={"hits": 3, "misses": 1, "hit_ratio": 0.75, "redis": "up"})
        return httpx.Response(500)


class FakeOcr:
    """Le contenu de l'image pilote la réponse, pour des tests déterministes."""

    def __init__(self):
        self.down = False
        self.received: list[bytes] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("ocr down")
        body = request.content
        self.received.append(body)
        if b"MODE-EAN" in body:
            c = [{"type": "ean13", "value": "3760000000017", "source": "barcode"}]
        elif b"MODE-QR" in body:
            c = [{"type": "qr", "value": "https://produits.example/p/1001", "source": "barcode"}]
        elif b"MODE-TEXT" in body:
            c = [{"type": "ean13", "value": "3760000000017", "source": "text"}]
        elif b"MODE-BADFIRST" in body:
            c = [
                {"type": "ean13", "value": "3760000000018", "source": "barcode"},
                {"type": "qr", "value": "https://produits.example/p/1001", "source": "barcode"},
            ]
        elif b"MODE-INVALID" in body:
            return httpx.Response(422, json={"detail": "image illisible"})
        elif b"MODE-BROKEN" in body:
            return httpx.Response(200, text="pas du json")
        else:
            c = []
        return httpx.Response(200, json={"candidates": c})


@pytest.fixture
def data():
    return FakeDataAccess()


@pytest.fixture
def ocr():
    return FakeOcr()


@pytest.fixture
def client(data, ocr):
    app = create_app(
        Settings(max_upload_bytes=1000),
        data_transport=httpx.MockTransport(data),
        ocr_transport=httpx.MockTransport(ocr),
    )
    with TestClient(app) as c:
        yield c


def png(mode: str, size: int = 0) -> dict:
    return {"file": ("scan.png", (mode.encode() + b"\x00" * size), "image/png")}


# ------------------------------------------------------------------ texte
def test_scan_ean13_found_and_cache_miss_then_hit(client):
    first = client.post("/api/scan", json={"code": "3760000000017"})
    assert first.status_code == 200
    body = first.json()
    assert body["identifier"] == {"type": "ean13", "value": "3760000000017"}
    assert body["found"] is True
    assert body["product"]["name"].startswith("Biscuits")
    assert body["cache"] == "MISS"
    assert body["source"] == "text"
    assert "created_at" not in body["product"]

    second = client.post("/api/scan", json={"code": "3760000000017"})
    assert second.json()["cache"] == "HIT"


def test_scan_ean13_with_spaces_is_normalised(client, data):
    r = client.post("/api/scan", json={"code": " 3 760000 000017 "})
    assert r.status_code == 200
    assert r.json()["identifier"]["value"] == "3760000000017"
    assert data.requests[0].url.params["ean13"] == "3760000000017"


def test_scan_invalid_ean13_is_rejected_before_reaching_data_access(client, data):
    r = client.post("/api/scan", json={"code": "3760000000018"})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_ean13"
    assert data.requests == []


def test_scan_qr_found(client, data):
    r = client.post("/api/scan", json={"code": "https://produits.example/p/1001"})
    body = r.json()
    assert body["identifier"]["type"] == "qr"
    assert body["found"] is True
    assert data.requests[0].url.params["qr"] == "https://produits.example/p/1001"


def test_scan_unknown_product_is_a_normal_answer(client):
    r = client.post("/api/scan", json={"code": "https://autre.example/x"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is False
    assert body["product"] is None
    assert body["cache"] == "MISS"


def test_scan_type_hint_forces_qr(client):
    r = client.post("/api/scan", json={"code": "3760000000018", "type": "qr"})
    assert r.status_code == 200
    assert r.json()["identifier"]["type"] == "qr"


@pytest.mark.parametrize("payload", [{}, {"code": ""}, {"code": "x" * 2049}, {"code": "x", "type": "autre"}])
def test_scan_request_validation(client, payload):
    r = client.post("/api/scan", json=payload)
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"


def test_validation_errors_do_not_echo_input(client):
    r = client.post("/api/scan", json={"code": "x" * 2049})
    assert "xxxx" not in r.text


# ------------------------------------------------------------------ image
def test_image_with_barcode_goes_through_ocr(client, ocr):
    r = client.post("/api/scan/image", files=png("MODE-EAN"))
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "image"
    assert body["detected_by"] == "barcode"
    assert body["identifier"] == {"type": "ean13", "value": "3760000000017"}
    assert body["found"] is True
    assert len(ocr.received) == 1


def test_image_with_qr(client):
    body = client.post("/api/scan/image", files=png("MODE-QR")).json()
    assert body["identifier"]["type"] == "qr"
    assert body["found"] is True


def test_image_number_read_by_text_ocr(client):
    body = client.post("/api/scan/image", files=png("MODE-TEXT")).json()
    assert body["detected_by"] == "text"


def test_image_skips_invalid_candidate_and_uses_next(client):
    body = client.post("/api/scan/image", files=png("MODE-BADFIRST")).json()
    assert body["identifier"]["type"] == "qr"


def test_image_without_code(client):
    r = client.post("/api/scan/image", files=png("MODE-NONE"))
    assert r.status_code == 422
    assert r.json()["code"] == "no_code_found"


def test_image_unreadable(client):
    r = client.post("/api/scan/image", files=png("MODE-INVALID"))
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_image"


def test_image_wrong_content_type_never_reaches_ocr(client, ocr):
    r = client.post("/api/scan/image", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    assert ocr.received == []


def test_image_too_large(client, ocr):
    r = client.post("/api/scan/image", files=png("MODE-EAN", size=5000))
    assert r.status_code == 413
    assert r.json()["code"] == "image_too_large"
    assert ocr.received == []


def test_image_empty(client):
    r = client.post("/api/scan/image", files={"file": ("a.png", b"", "image/png")})
    assert r.status_code == 422
    assert r.json()["code"] == "empty_file"


def test_image_missing_file(client):
    assert client.post("/api/scan/image").status_code == 422


def test_ocr_garbage_response_is_a_502(client):
    r = client.post("/api/scan/image", files=png("MODE-BROKEN"))
    assert r.status_code == 502
    assert r.json()["code"] == "ocr_bad_response"


# ------------------------------------------------------------------ pannes
def test_data_access_down_gives_503_without_leaking_details(client, data):
    data.down = True
    r = client.post("/api/scan", json={"code": "3760000000017"})
    assert r.status_code == 503
    assert r.json() == {"error": "Un service interne est momentanément indisponible.", "code": "dataaccess_unavailable"}
    assert "data access down" not in r.text


def test_ocr_down_gives_503(client, ocr):
    ocr.down = True
    r = client.post("/api/scan/image", files=png("MODE-EAN"))
    assert r.status_code == 503
    assert r.json()["code"] == "ocr_unavailable"


# ------------------------------------------------------------------ autres routes
def test_search_and_stats(client):
    r = client.get("/api/products/search", params={"q": "biscuit", "limit": 5})
    assert r.status_code == 200
    assert r.json()["items"][0]["name"].startswith("Biscuits")

    stats = client.get("/api/cache/stats").json()
    assert stats == {"hits": 3, "misses": 1, "hit_ratio": 0.75, "redis": "up"}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"q": "x" * 101}])
def test_search_validation(client, params):
    assert client.get("/api/products/search", params=params).status_code == 422


def test_health_and_no_public_docs(client):
    assert client.get("/health").json() == {"status": "ok"}
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
