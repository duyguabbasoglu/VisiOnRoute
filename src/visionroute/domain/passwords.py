"""Password policy (domain rule, framework-free)."""

from __future__ import annotations

MIN_LENGTH = 12

# Deliberately small blocklist of catastrophic choices; a breached-password
# service adapter can extend this in production.
_BLOCKLIST = {
    "123456789012",
    "password1234",
    "visionroute1",
    "qwertyuiop12",
}


def password_problems(password: str) -> list[str]:
    """Return Turkish, user-facing problems; empty list means acceptable."""
    problems: list[str] = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Parola en az {MIN_LENGTH} karakter olmalıdır.")
    if password.lower() in _BLOCKLIST:
        problems.append("Bu parola çok yaygın; lütfen farklı bir parola seçin.")
    if password.isdigit() or password.isalpha():
        problems.append("Parola harf ve rakam (veya sembol) karışımı içermelidir.")
    return problems
