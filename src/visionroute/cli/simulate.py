"""Telemetry simulator — sends contract-compliant events to the public
ingestion API. SYNTHETIC/DEMO ONLY.

Every generated event is flagged so it can never masquerade as production data:
the payload carries ``data_origin="synthetic"`` and ``environment="demo"``, and
the CLI refuses to run against a production-like base URL without --force.
"""

from __future__ import annotations

import itertools
import math
import random
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import typer

from visionroute.domain.ingestion import SCHEMA_VERSION

app = typer.Typer(no_args_is_help=True, help="Telemetri simülatörü (yalnızca demo).")

# A short synthetic route in Ankara (WGS84). The vehicle drives along it and
# back again, so consecutive samples stay physically plausible.
_ROUTE = [
    (39.9208, 32.8541),
    (39.9250, 32.8600),
    (39.9300, 32.8660),
    (39.9360, 32.8700),
    (39.9420, 32.8745),
    (39.9480, 32.8790),
]
# Seconds between consecutive samples (typical telematics reporting interval).
SAMPLE_SECONDS = 5.0
_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _route_position(distance_m: float) -> tuple[float, float]:
    segments = list(itertools.pairwise(_ROUTE))
    lengths = [haversine_m(a, b) for a, b in segments]
    total = sum(lengths)
    remaining = distance_m % (2 * total)
    if remaining > total:  # driving back towards the start
        remaining = 2 * total - remaining
    for (start, end), length in zip(segments, lengths, strict=True):
        if remaining <= length:
            fraction = remaining / length if length else 0.0
            return (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
        remaining -= length
    return _ROUTE[-1]


@app.command("telemetry")
def telemetry(
    base_url: str = typer.Option("http://localhost:8000", help="API taban adresi."),
    api_key: str = typer.Option(..., help="Ingest kapsamı olan API anahtarı."),
    source_key: str = typer.Option(..., help="Hedef veri kaynağı anahtarı."),
    vehicle_external_id: str = typer.Option("34ABC123", help="Araç dış kimliği."),
    driver_external_id: str = typer.Option("SUR-001", help="Sürücü dış kimliği."),
    count: int = typer.Option(20, min=1, max=1000, help="Gönderilecek olay sayısı."),
    interval: float = typer.Option(0.5, min=0.0, help="Olaylar arası bekleme (sn)."),
    inject_harsh_brake: bool = typer.Option(
        True, help="Örnek olarak bir sert fren olayı enjekte et."
    ),
) -> None:
    """Sözleşmeye uygun sentetik telemetri üretir ve /api/v1/ingest/events'e gönderir."""
    if any(env in base_url for env in ("prod", "production")) is True:
        typer.secho("Simülatör üretim benzeri adreslere karşı çalıştırılamaz.", fg="red")
        raise typer.Exit(1)

    typer.secho(
        "UYARI: Bu araç YALNIZCA sentetik demo verisi üretir "
        "(data_origin=synthetic, environment=demo).",
        fg="yellow",
    )

    events = _build_events(
        vehicle_external_id,
        driver_external_id,
        source_key,
        count,
        inject_harsh_brake=inject_harsh_brake,
    )

    sent = 0
    with httpx.Client(base_url=base_url, headers={"X-API-Key": api_key}, timeout=10.0) as client:
        for event in events:
            response = client.post(
                "/api/v1/ingest/events",
                json={"source_key": source_key, "events": [event]},
            )
            if response.status_code != 200:
                typer.secho(f"HATA {response.status_code}: {response.text}", fg="red")
                raise typer.Exit(1)
            body = response.json()
            sent += 1
            typer.echo(
                f"[{sent}/{count}] kabul={body['accepted']} "
                f"yinelenen={body['duplicates']} karantina={body['quarantined']}"
            )
            if interval:
                time.sleep(interval)

    typer.secho(f"Tamamlandı: {sent} olay gönderildi.", fg="green")


def _build_events(
    vehicle: str,
    driver: str,
    source_key: str,
    count: int,
    *,
    inject_harsh_brake: bool,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Samples ``SAMPLE_SECONDS`` apart, ending now, moving along the route."""
    events: list[dict[str, object]] = []
    start = (now or datetime.now(UTC)) - timedelta(seconds=SAMPLE_SECONDS * (count - 1))
    speed = 50.0
    travelled_m = 0.0
    for i in range(count):
        accel = random.uniform(-1.5, 1.5)  # noqa: S311 — not cryptographic
        if inject_harsh_brake and i == count // 2:
            accel = -6.5  # clear harsh-braking sample
            speed = 70.0
        speed = max(0.0, min(120.0, speed + accel * 2))
        if i > 0:
            travelled_m += speed / 3.6 * SAMPLE_SECONDS
        lat, lon = _route_position(travelled_m)
        occurred_at = start + timedelta(seconds=SAMPLE_SECONDS * i)
        events.append(
            {
                "schema_version": SCHEMA_VERSION,
                "source": source_key,
                "event_id": f"sim-{uuid.uuid4()}",
                "event_type": "telemetry.position",
                "occurred_at": occurred_at.isoformat(),
                "vehicle_external_id": vehicle,
                "driver_external_id": driver,
                "payload": {
                    # ~3 m of GPS jitter; never enough to fake movement.
                    "latitude": round(lat + random.uniform(-0.00003, 0.00003), 6),  # noqa: S311
                    "longitude": round(lon + random.uniform(-0.00003, 0.00003), 6),  # noqa: S311
                    "speed_kph": round(speed, 1),
                    "acceleration_ms2": round(accel, 2),
                    "heading_deg": round(random.uniform(0, 360), 1),  # noqa: S311
                    "data_origin": "synthetic",
                    "environment": "demo",
                },
            }
        )
    return events
