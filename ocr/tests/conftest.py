"""Images de test générées à la volée (aucun fichier binaire dans le dépôt)."""
import io

import barcode
import pytest
import qrcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def ean_png() -> bytes:
    """EAN-13 3760000000017 avec le numéro imprimé dessous."""
    buf = io.BytesIO()
    barcode.get("ean13", "376000000001", writer=ImageWriter()).write(buf)
    return buf.getvalue()


@pytest.fixture
def qr_png() -> bytes:
    return to_png(qrcode.make("https://produits.example/p/1001").get_image())


@pytest.fixture
def printed_number_png() -> bytes:
    """Numéro imprimé seul, sans code-barres : seule la voie OCR peut le lire."""
    font = ImageFont.load_default(size=56)
    img = Image.new("L", (900, 140), 255)
    ImageDraw.Draw(img).text((30, 30), "3 760000 000017", fill=0, font=font)
    return to_png(img)


@pytest.fixture
def blank_png() -> bytes:
    return to_png(Image.new("L", (300, 200), 255))
