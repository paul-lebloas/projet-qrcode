from __future__ import annotations


class ApiError(Exception):
    """Erreur renvoyée à l'IHM sous la forme {"error": message, "code": code}."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
