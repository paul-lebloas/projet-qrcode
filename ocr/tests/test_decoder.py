import io

import pytest
from PIL import Image

from app.decoder import (
    Candidate,
    InvalidImage,
    extract_candidates,
    is_valid_ean13,
    _EAN_IN_TEXT,
)
from conftest import to_png


def test_reads_ean13_barcode(ean_png):
    assert extract_candidates(ean_png) == [Candidate("ean13", "3760000000017", "barcode")]


def test_reads_qr_code(qr_png):
    assert extract_candidates(qr_png) == [Candidate("qr", "https://produits.example/p/1001", "barcode")]


def test_reads_printed_number_when_there_is_no_barcode(printed_number_png):
    assert extract_candidates(printed_number_png) == [Candidate("ean13", "3760000000017", "text")]


def test_reads_rotated_barcode(ean_png):
    rotated = Image.open(io.BytesIO(ean_png)).rotate(90, expand=True, fillcolor="white")
    assert extract_candidates(to_png(rotated)) == [Candidate("ean13", "3760000000017", "barcode")]


def test_reads_downscaled_barcode(ean_png):
    img = Image.open(io.BytesIO(ean_png))
    small = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    assert Candidate("ean13", "3760000000017", "barcode") in extract_candidates(to_png(small))


def test_reads_barcode_with_transparent_background(ean_png):
    rgba = Image.open(io.BytesIO(ean_png)).convert("RGBA")
    pixels = [(255, 255, 255, 0) if p[:3] == (255, 255, 255) else p for p in rgba.get_flattened_data()]
    rgba.putdata(pixels)
    assert Candidate("ean13", "3760000000017", "barcode") in extract_candidates(to_png(rgba))


def test_blank_image_gives_no_candidate(blank_png):
    assert extract_candidates(blank_png) == []


@pytest.mark.parametrize("data", [b"", b"not an image", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20])
def test_garbage_is_rejected(data):
    with pytest.raises(InvalidImage):
        extract_candidates(data)


@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
def test_huge_image_is_rejected_before_decoding():
    huge = to_png(Image.new("L", (6000, 6000), 255))  # 36 Mpx, très compressible
    assert len(huge) < 200_000
    with pytest.raises(InvalidImage):
        extract_candidates(huge)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3 760000 000017", ["3 760000 000017"]),
        ("3760000000017", ["3760000000017"]),
        ("ref 3760000000017 fin", ["3760000000017"]),
        ("37600000000170", []),  # 14 chiffres : pas un EAN-13
        ("2 3760000000017", []),  # chiffre isolé collé devant
        ("376000000001", []),  # 12 chiffres
    ],
)
def test_ean_pattern(text, expected):
    assert [m.group() for m in _EAN_IN_TEXT.finditer(text)] == expected


def test_printed_number_with_wrong_check_digit_is_ignored(monkeypatch):
    import app.decoder as d

    monkeypatch.setattr(d.pytesseract, "image_to_string", lambda *a, **k: "3 760000 000018\n")
    assert d._read_printed_number(Image.new("L", (100, 50), 255)) == []
    assert not is_valid_ean13("3760000000018")


def test_tesseract_timeout_or_absence_is_survivable(monkeypatch):
    import app.decoder as d

    def boom(*a, **k):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(d.pytesseract, "image_to_string", boom)
    assert d._read_printed_number(Image.new("L", (100, 50), 255)) == []
