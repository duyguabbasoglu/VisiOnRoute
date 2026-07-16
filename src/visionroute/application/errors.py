"""Application-level errors, mapped to the API error envelope in api/errors.py."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base for expected, user-attributable failures."""


class ValidationFailedError(ApplicationError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class DomainConflictError(ApplicationError):
    pass


class DomainNotFoundError(ApplicationError):
    pass


class InvalidCredentialsError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("E-posta veya parola hatalı.")


class AccountLockedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "Hesap art arda başarısız girişler nedeniyle geçici olarak kilitlendi. "
            "Lütfen 15 dakika sonra tekrar deneyin."
        )


class PermissionDeniedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("Bu işlem için yetkiniz yok.")
