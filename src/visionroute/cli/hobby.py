"""Hobby/free-demo entrypoint: migrations + worker + scheduler + API in one container.

Only for the zero-cost public demo (docs/operations/hobby-deployment.md).
Production keeps API, worker and scheduler as independently scaled services.
"""

from __future__ import annotations

import os
import sys

import typer

from visionroute.cli.supervisor import ProcessSpec, Supervisor, run_step

hobby_app = typer.Typer(
    no_args_is_help=True, help="Ücretsiz hobi demo profili (üretim için değil)."
)


def build_specs(port: int, *, scheduler_interval: float) -> list[ProcessSpec]:
    exe = sys.executable
    return [
        ProcessSpec("worker", [exe, "-m", "visionroute.cli.main", "worker", "run"]),
        ProcessSpec(
            "scheduler",
            [
                exe,
                "-m",
                "visionroute.cli.main",
                "scheduler",
                "run",
                "--interval",
                str(scheduler_interval),
            ],
        ),
        ProcessSpec(
            "api",
            [
                exe,
                "-m",
                "uvicorn",
                "visionroute.api.main:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
                "--proxy-headers",
                "--timeout-keep-alive",
                "75",
            ],
        ),
    ]


@hobby_app.command("serve")
def serve(
    port: int = typer.Option(
        int(os.environ.get("PORT", "8000")), help="API portu (Render PORT değişkenini verir)."
    ),
    migrate: bool = typer.Option(True, help="Başlamadan önce alembic upgrade head çalıştır."),
    scheduler_interval: float = typer.Option(300.0, help="Zamanlayıcı turları arası (sn)."),
) -> None:
    """Migration'ları uygular, ardından worker, zamanlayıcı ve API'yi birlikte çalıştırır."""
    if migrate:
        code = run_step(
            ProcessSpec("migrate", [sys.executable, "-m", "alembic", "upgrade", "head"])
        )
        if code != 0:
            raise typer.Exit(code)
    raise typer.Exit(Supervisor(build_specs(port, scheduler_interval=scheduler_interval)).run())
