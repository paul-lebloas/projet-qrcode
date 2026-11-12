import pytest
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)


def post(data: bytes, name="x.png", ctype="image/png"):
    return client.post("/decode", files={"file": (name, data, ctype)})


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_decode_ean(ean_png):
    r = post(ean_png)
    assert r.status_code == 200
    assert r.json() == {"candidates": [{"type": "ean13", "value": "3760000000017", "source": "barcode"}]}


def test_decode_qr(qr_png):
    assert post(qr_png).json()["candidates"][0] == {
        "type": "qr",
        "value": "https://produits.example/p/1001",
        "source": "barcode",
    }


def test_decode_blank_returns_empty_list(blank_png):
    r = post(blank_png)
    assert r.status_code == 200
    assert r.json() == {"candidates": []}


def test_decode_not_an_image():
    r = post(b"hello world", "a.png")
    assert r.status_code == 422


def test_decode_empty_file():
    assert post(b"").status_code == 422


def test_decode_too_large(monkeypatch, blank_png):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 100)
    assert post(blank_png).status_code == 413


def test_no_public_docs():
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
