"""Prometheus metrics.

One registry per process. The API exposes it at ``/metrics`` (bearer token,
disabled unless ``VISIONROUTE_METRICS_TOKEN`` is set); the worker and scheduler
can serve it on an internal port (``--metrics-port``). Label values are bounded
(route templates, never raw paths; no tenant or user identifiers).
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "visionroute_http_requests_total",
    "HTTP requests by method, route template and status code.",
    ["method", "route", "status"],
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "visionroute_http_request_duration_seconds",
    "Time to response headers by method and route template.",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
QUEUE_DEPTH = Gauge(
    "visionroute_queue_depth",
    "Items in background queues by state (sampled at scrape time).",
    ["queue", "state"],
    registry=REGISTRY,
)
QUEUE_OLDEST_PENDING = Gauge(
    "visionroute_queue_oldest_pending_seconds",
    "Age of the oldest pending item per queue (0 when empty).",
    ["queue"],
    registry=REGISTRY,
)
LIVE_STREAM_SUBSCRIBERS = Gauge(
    "visionroute_live_stream_subscribers",
    "Open live-operation event streams in this API process.",
    registry=REGISTRY,
)
LIVE_HUB_CONNECTED = Gauge(
    "visionroute_live_hub_connected",
    "1 when this API process listens for live notifications.",
    registry=REGISTRY,
)
WORKER_ITEMS = Counter(
    "visionroute_worker_items_total",
    "Items handled by the worker by source.",
    ["source"],
    registry=REGISTRY,
)
SCHEDULER_TICKS = Counter(
    "visionroute_scheduler_ticks_total",
    "Scheduler ticks by result (ran, skipped, failed).",
    ["result"],
    registry=REGISTRY,
)
RETENTION_PURGED = Counter(
    "visionroute_retention_purged_total",
    "Records or objects removed by retention maintenance.",
    ["category"],
    registry=REGISTRY,
)
USAGE_SNAPSHOT_RECORDS = Counter(
    "visionroute_usage_snapshot_records_total",
    "Usage records written by daily metering snapshots.",
    registry=REGISTRY,
)
TRIALS_EXPIRED = Counter(
    "visionroute_trials_expired_total",
    "Trial subscriptions moved to past_due.",
    registry=REGISTRY,
)


def observe_http_request(method: str, route: str, status: int, seconds: float) -> None:
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_DURATION.labels(method, route).observe(seconds)


def render_latest() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def serve_metrics(port: int, host: str) -> None:
    """Expose the registry on an internal port (worker/scheduler processes)."""
    start_http_server(port, addr=host, registry=REGISTRY)
