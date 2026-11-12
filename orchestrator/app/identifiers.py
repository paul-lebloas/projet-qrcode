"""Détermination du type d'identifiant fourni : EAN-13 ou QR Code (cadrage §2)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IdentifierType = Literal["ean13", "qr"]

MAX_QR_LENGTH = 2048

_DIGITS_13 = re.compile(r"^\d{13}$")
_EAN_SEPARATORS = re.compile(r"[\s\-]")


class InvalidIdentifier(ValueError):
    """L'identifiant est inutilisable (vide, trop long, clé EAN-13 incorrecte…)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Identifier:
    type: IdentifierType
    value: str


def ean13_check_digit(first12: str) -> int:
    """Clé de contrôle EAN-13 : poids 1,3,1,3… sur les 12 premiers chiffres."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return (10 - total % 10) % 10


def is_valid_ean13(value: str) -> bool:
    return bool(_DIGITS_13.match(value)) and ean13_check_digit(value[:12]) == int(value[12])


def classify(raw: str, hint: str = "auto") -> Identifier:
    """Retourne l'identifiant normalisé et son type.

    - 13 chiffres (espaces et tirets tolérés) : EAN-13, clé de contrôle exigée ;
    - toute autre chaîne non vide : contenu d'un QR Code.
    `hint` ("ean13" ou "qr") force le type quand l'appelant le connaît déjà
    (par exemple lorsqu'un lecteur de codes l'a déjà identifié).
    """
    text = raw.strip()
    if not text:
        raise InvalidIdentifier("empty_code", "Le code est vide.")

    compact = _EAN_SEPARATORS.sub("", text)
    looks_like_ean = bool(_DIGITS_13.match(compact))

    if hint == "ean13" or (hint == "auto" and looks_like_ean):
        if not is_valid_ean13(compact):
            raise InvalidIdentifier(
                "invalid_ean13",
                "EAN-13 invalide : 13 chiffres avec une clé de contrôle correcte sont attendus.",
            )
        return Identifier("ean13", compact)

    if len(text) > MAX_QR_LENGTH:
        raise InvalidIdentifier(
            "qr_too_long", f"Le contenu du QR Code dépasse {MAX_QR_LENGTH} caractères."
        )
    return Identifier("qr", text)
