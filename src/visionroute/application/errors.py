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


class InvalidAccountTokenError(ApplicationError):
    """Reset/verification link is unknown, used, or expired (no detail given)."""

    def __init__(self) -> None:
        super().__init__(
            "Bağlantı geçersiz, daha önce kullanılmış veya süresi dolmuş. "
            "Lütfen yeni bir bağlantı isteyin."
        )


class InvalidMfaCodeError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("Doğrulama kodu geçersiz veya süresi dolmuş.")


class ReauthenticationFailedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("Parola doğrulanamadı.")


class ServiceNotConfiguredError(ApplicationError):
    """A required server-side dependency (e.g. encryption keys) is missing."""
