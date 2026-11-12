"""Extraction d'identifiants produit depuis une image.

Deux stratégies, dans cet ordre :
  1. lecture directe des codes (QR Code et EAN-13) avec ZBar, sur plusieurs
     variantes de l'image (contraste, taille, rotation) ;
  2. à défaut, OCR (Tesseract) du numéro imprimé sous le code-barres ; un
     nombre n'est retenu que si c'est un EAN-13 à clé de contrôle valide.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Iterator

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError
from pyzbar.pyzbar import ZBarSymbol
from pyzbar.pyzbar import decode as zbar_decode

MAX_PIXELS = 30_000_000
MAX_CANDIDATES = 10
TESSERACT_TIMEOUT_SECONDS = 7

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InvalidImage(ValueError):
    """Le fichier n'est pas une image exploitable."""


@dataclass(frozen=True)
class Candidate:
    type: str  # "ean13" ou "qr"
    value: str
    source: str  # "barcode" ou "text"


def ean13_check_digit(first12: str) -> int:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return (10 - total % 10) % 10


def is_valid_ean13(value: str) -> bool:
    return bool(re.fullmatch(r"\d{13}", value)) and ean13_check_digit(value[:12]) == int(value[12])


def load_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise InvalidImage("Image trop grande.")
        img.load()
    except InvalidImage:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise InvalidImage("Fichier image illisible.") from None

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        # Fond blanc sous la transparence : un code noir sur fond transparent reste lisible.
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, rgba)
    return img.convert("L")


def _variants(img: Image.Image) -> Iterator[Image.Image]:
    yield img
    yield ImageOps.autocontrast(img)

    longest = max(img.size)
    if longest < 800:
        yield img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    elif longest > 1600:
        ratio = 1600 / longest
        yield img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.LANCZOS)

    yield img.point(lambda p: 255 if p > 128 else 0)
    for angle in (90, 180, 270):
        yield img.rotate(angle, expand=True, fillcolor=255)


def _read_barcodes(img: Image.Image) -> list[Candidate]:
    for variant in _variants(img):
        found: list[Candidate] = []
        for symbol in zbar_decode(variant, symbols=[ZBarSymbol.EAN13, ZBarSymbol.QRCODE]):
            value = symbol.data.decode("utf-8", errors="replace").strip()
            if not value:
                continue
            if symbol.type == "EAN13":
                if is_valid_ean13(value):
                    found.append(Candidate("ean13", value, "barcode"))
            else:
                found.append(Candidate("qr", value, "barcode"))
        if found:
            return found
    return []


# 13 chiffres, éventuellement séparés par des espaces simples (« 3 760000 000017 »),
# non précédés ni suivis d'autres chiffres.
_EAN_IN_TEXT = re.compile(r"(?<!\d)(?<!\d )\d(?: ?\d){12}(?! ?\d)")


def _read_printed_number(img: Image.Image) -> list[Candidate]:
    prepared = ImageOps.autocontrast(img)
    if max(prepared.size) < 1000:
        prepared = prepared.resize((prepared.width * 2, prepared.height * 2), Image.LANCZOS)

    found: list[Candidate] = []
    for psm in (6, 11):
        try:
            text = pytesseract.image_to_string(
                prepared,
                config=f"--psm {psm} -c tessedit_char_whitelist=0123456789",
                timeout=TESSERACT_TIMEOUT_SECONDS,
            )
        except (RuntimeError, pytesseract.TesseractError, pytesseract.TesseractNotFoundError):
            continue  # délai dépassé ou Tesseract indisponible : on renonce à cette passe

        for line in text.splitlines():
            for match in _EAN_IN_TEXT.finditer(line):
                digits = match.group().replace(" ", "")
                if is_valid_ean13(digits):
                    found.append(Candidate("ean13", digits, "text"))
        if found:
            break
    return found


def extract_candidates(data: bytes) -> list[Candidate]:
    """Retourne les identifiants trouvés (codes lus d'abord, puis numéro imprimé), sans doublon."""
    img = load_image(data)

    candidates = _read_barcodes(img)
    if not candidates:
        candidates = _read_printed_number(img)

    unique: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for c in candidates:
        if (c.type, c.value) not in seen:
            seen.add((c.type, c.value))
            unique.append(c)
    return unique[:MAX_CANDIDATES]
