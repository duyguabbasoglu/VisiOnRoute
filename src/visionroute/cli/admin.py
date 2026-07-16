"""One-time platform administrator bootstrap.

Security properties (spec 9.4):
- interactive secure input or VISIONROUTE_BOOTSTRAP_ADMIN_* env variables,
- password strength validated,
- refuses to run when a platform admin already exists,
- action is audit-logged, password never printed.
"""

from __future__ import annotations

import asyncio

import typer
from sqlalchemy import select

from visionroute.application.audit import record_audit
from visionroute.application.context import SYSTEM_CONTEXT
from visionroute.config.settings import get_settings
from visionroute.domain.passwords import password_problems
from visionroute.infrastructure.db.engine import (
    build_engine,
    build_session_factory,
    session_scope,
)
from visionroute.infrastructure.db.models.identity import User
from visionroute.infrastructure.db.tenancy import set_rls_bypass
from visionroute.infrastructure.security.passwords import hash_password

app = typer.Typer(no_args_is_help=True, help="Platform yöneticisi işlemleri.")


async def _bootstrap(email: str, full_name: str, password: str) -> str:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    try:
        async with session_scope(factory) as db:
            await set_rls_bypass(db)
            existing = await db.execute(
                select(User).where(User.platform_role == "super_admin").limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                return "exists"
            user = User(
                email=email.strip().lower(),
                password_hash=hash_password(password),
                full_name=full_name,
                platform_role="super_admin",
            )
            db.add(user)
            await db.flush()
            await record_audit(
                db,
                SYSTEM_CONTEXT,
                action="platform.admin_bootstrapped",
                resource_type="user",
                resource_id=str(user.id),
                data={"email": user.email},
            )
            return "created"
    finally:
        await engine.dispose()


@app.command("bootstrap")
def bootstrap(
    email: str = typer.Option(None, help="Yönetici e-postası (boşsa sorulur)."),
    full_name: str = typer.Option(None, help="Ad soyad (boşsa sorulur)."),
) -> None:
    """İlk platform yöneticisini güvenli biçimde oluşturur (tek seferlik)."""
    settings = get_settings()

    resolved_email = email or settings.bootstrap_admin_email
    password = settings.bootstrap_admin_password
    if resolved_email is None:
        resolved_email = typer.prompt("Yönetici e-postası")
    resolved_name = full_name or typer.prompt("Ad soyad", default="Platform Yöneticisi")
    if password is None:
        password = typer.prompt("Parola", hide_input=True, confirmation_prompt=True)

    problems = password_problems(password)
    if problems:
        for problem in problems:
            typer.secho(f"HATA: {problem}", fg=typer.colors.RED)
        raise typer.Exit(1)

    outcome = asyncio.run(_bootstrap(resolved_email, resolved_name, password))
    if outcome == "exists":
        typer.secho(
            "Bir platform yöneticisi zaten mevcut; bootstrap yeniden çalıştırılamaz.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    typer.secho(f"Platform yöneticisi oluşturuldu: {resolved_email}", fg=typer.colors.GREEN)
    if settings.bootstrap_admin_password is not None:
        typer.secho(
            "UYARI: VISIONROUTE_BOOTSTRAP_ADMIN_PASSWORD ortam değişkenini şimdi silin.",
            fg=typer.colors.YELLOW,
        )
