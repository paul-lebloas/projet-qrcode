import pytest

from app.identifiers import Identifier, InvalidIdentifier, classify, ean13_check_digit, is_valid_ean13


@pytest.mark.parametrize(
    "value",
    ["3760000000017", "4006381333931", "5901234123457", "9780201379624"],
)
def test_valid_ean13(value):
    assert is_valid_ean13(value)


@pytest.mark.parametrize(
    "value",
    ["3760000000018", "376000000001", "37600000000170", "376000000001x", "", " 3760000000017"],
)
def test_invalid_ean13(value):
    assert not is_valid_ean13(value)


def test_check_digit():
    assert ean13_check_digit("376000000001") == 7
    assert ean13_check_digit("400638133393") == 1


def test_auto_detects_ean13():
    assert classify("3760000000017") == Identifier("ean13", "3760000000017")


def test_ean13_tolerates_spaces_and_hyphens():
    assert classify(" 3 760000 000017 ") == Identifier("ean13", "3760000000017")
    assert classify("376-0000-000017") == Identifier("ean13", "3760000000017")


def test_auto_detects_qr_for_urls_and_text():
    assert classify("https://produits.example/p/1001") == Identifier("qr", "https://produits.example/p/1001")
    assert classify("PRODUIT-42") == Identifier("qr", "PRODUIT-42")


def test_thirteen_digits_with_bad_check_digit_is_rejected_not_treated_as_qr():
    with pytest.raises(InvalidIdentifier) as exc:
        classify("3760000000018")
    assert exc.value.code == "invalid_ean13"


def test_hint_qr_forces_qr_even_for_13_digits():
    assert classify("3760000000018", hint="qr") == Identifier("qr", "3760000000018")


def test_hint_ean13_rejects_non_ean():
    with pytest.raises(InvalidIdentifier) as exc:
        classify("hello", hint="ean13")
    assert exc.value.code == "invalid_ean13"


def test_empty_and_too_long():
    with pytest.raises(InvalidIdentifier) as exc:
        classify("   ")
    assert exc.value.code == "empty_code"
    with pytest.raises(InvalidIdentifier) as exc:
        classify("a" * 2049)
    assert exc.value.code == "qr_too_long"
    assert classify("a" * 2048).type == "qr"
