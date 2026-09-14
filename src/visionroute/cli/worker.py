"""Worker and scheduler CLI entrypoints."""

from __future__ import annotations

import asyncio

import typer

from visionroute.config.settings import get_settings

worker_app = typer.Typer(no_args_is_help=True, help="Outbox/iş kuyruğu tüketicisi.")
scheduler_app = typer.Typer(no_args_is_help=True, help="Zamanlanmış işler.")


@worker_app.command("run")
def worker_run(
    poll_interval: float = typer.Option(1.0, help="Boşta bekleme aralığı (sn)."),
    once: bool = typer.Option(False, help="Tek partiyi işle ve çık (test/CI)."),
    metrics_port: int | None = typer.Option(None, help="Prometheus metrik portu (iç ağ)."),
    metrics_host: str = typer.Option("127.0.0.1", help="Metrik sunucusunun dinleyeceği adres."),
) -> None:
    """Outbox olaylarını işleyen worker'ı başlatır."""
    from visionroute.worker.runner import Worker

    _serve_metrics(metrics_port, metrics_host)

    worker = Worker(get_settings())

    async def _run() -> None:
        if once:
            count = await worker.run_once()
            typer.echo(f"{count} olay işlendi.")
            await worker._engine.dispose()
        else:
            await worker.run_forever(poll_interval=poll_interval)

    asyncio.run(_run())


@scheduler_app.command("run")
def scheduler_run(
    once: bool = typer.Option(False, help="Bir tur çalış ve çık."),
    interval: float = typer.Option(300.0, help="Turlar arası bekleme (sn)."),
    metrics_port: int | None = typer.Option(None, help="Prometheus metrik portu (iç ağ)."),
    metrics_host: str = typer.Option("127.0.0.1", help="Metrik sunucusunun dinleyeceği adres."),
) -> None:
    """Partisyon bakımı, saklama temizliği, kullanım ölçümü gibi periyodik işleri çalıştırır."""
    from visionroute.scheduler.runner import Scheduler

    _serve_metrics(metrics_port, metrics_host)

    scheduler = Scheduler(get_settings())

    async def _run() -> None:
        if once:
            await scheduler.run_once()
        else:
            await scheduler.run_forever(interval=interval)

    asyncio.run(_run())


def _serve_metrics(port: int | None, host: str) -> None:
    if port is None:
        return
    from visionroute.observability.metrics import serve_metrics

    serve_metrics(port, host)
    typer.echo(f"Metrikler {host}:{port} adresinde yayınlanıyor.")
