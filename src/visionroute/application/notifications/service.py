"""Notification pipeline (M9).

Rule evaluation runs in the worker when a safety event is created:
matching rules produce in-app notifications and queue signed webhook
deliveries. Deliveries are sent with HMAC-SHA256 signatures, retried with
exponential backoff, and dead-lettered after repeated failure.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.domain.safety import (
    EVENT_LABELS_TR,
    SEVERITY_LABELS_TR,
    SafetyEventType,
    Severity,
)
from visionroute.infrastructure.db.models.notifications import (
    Notification,
    NotificationRule,
    WebhookDelivery,
    WebhookEndpoint,
)
from visionroute.infrastructure.security.urlguard import UnsafeUrlError, UrlPolicy, validate_url
from visionroute.observability.logging import get_logger

logger = get_logger(__name__)

_SEVERITY_RANK = {s.value: i for i, s in enumerate(Severity)}
_MAX_DELIVERY_ATTEMPTS = 6
_DELIVERY_TIMEOUT_SECONDS = 10.0

# Local development often uses plain-http endpoints; production policy is
# https-only. The policy is chosen by the caller based on environment.
DEV_URL_POLICY = UrlPolicy(allow_http=True)
PROD_URL_POLICY = UrlPolicy()


def sign_payload(secret: str, body: bytes, timestamp: int) -> str:
    """Return the delivery signature header value: ``t=<ts>,v1=<hex>``.

    Receivers recompute HMAC-SHA256 over ``b"{ts}.{body}"`` and must reject
    stale timestamps (replay defense)."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ------------------------------------------------------------- evaluation

    async def on_safety_event(
        self,
        *,
        organization_id: uuid.UUID,
        safety_event_id: uuid.UUID,
        event_type: str,
        severity: str,
    ) -> int:
        """Evaluate active rules for a new safety event. Returns the number of
        notifications produced (in-app + queued webhooks)."""
        rules = await self._db.execute(
            select(NotificationRule).where(
                NotificationRule.organization_id == organization_id,
                NotificationRule.active.is_(True),
                NotificationRule.kind == "severity_threshold",
            )
        )
        produced = 0
        try:
            label = EVENT_LABELS_TR[SafetyEventType(event_type)]
        except ValueError:
            label = event_type
        severity_label = SEVERITY_LABELS_TR.get(Severity(severity), severity)

        for rule in rules.scalars():
            if _SEVERITY_RANK.get(severity, 0) < _SEVERITY_RANK.get(rule.min_severity, 99):
                continue
            channels = list(rule.channels)
            if "in_app" in channels:
                self._db.add(
                    Notification(
                        organization_id=organization_id,
                        rule_id=rule.id,
                        safety_event_id=safety_event_id,
                        level="critical" if severity == "critical" else "warning",
                        title_tr=f"{severity_label} şiddette güvenlik olayı: {label}",
                        body_tr=(
                            f"{label} olayı tespit edildi (şiddet: {severity_label}). "
                            "Ayrıntılar için olay inceleme ekranına gidin."
                        ),
                    )
                )
                produced += 1
            if "webhook" in channels:
                produced += await self._queue_webhooks(
                    organization_id,
                    event_type="safety.event_created",
                    payload={
                        "safety_event_id": str(safety_event_id),
                        "event_type": event_type,
                        "severity": severity,
                    },
                )
        return produced

    async def _queue_webhooks(
        self, organization_id: uuid.UUID, *, event_type: str, payload: dict[str, object]
    ) -> int:
        endpoints = await self._db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.organization_id == organization_id,
                WebhookEndpoint.active.is_(True),
            )
        )
        queued = 0
        for endpoint in endpoints.scalars():
            self._db.add(
                WebhookDelivery(
                    organization_id=organization_id,
                    endpoint_id=endpoint.id,
                    event_type=event_type,
                    payload=payload,
                )
            )
            queued += 1
        return queued

    # ------------------------------------------------------------- delivery

    async def deliver_pending(self, *, url_policy: UrlPolicy, limit: int = 20) -> tuple[int, int]:
        """Send due webhook deliveries. Returns (delivered, failed)."""
        now = datetime.now(UTC)
        rows = await self._db.execute(
            select(WebhookDelivery, WebhookEndpoint)
            .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
            .where(
                WebhookDelivery.status == "pending",
                WebhookDelivery.next_attempt_at <= now,
            )
            .limit(limit)
            .with_for_update(skip_locked=True, of=WebhookDelivery)
        )
        delivered = failed = 0
        for delivery, endpoint in rows.all():
            ok = await self._send_one(delivery, endpoint, url_policy)
            if ok:
                delivered += 1
            else:
                failed += 1
        return delivered, failed

    async def _send_one(
        self, delivery: WebhookDelivery, endpoint: WebhookEndpoint, policy: UrlPolicy
    ) -> bool:
        now = datetime.now(UTC)
        body = json.dumps(
            {
                "event_type": delivery.event_type,
                "delivery_id": str(delivery.id),
                "created_at": delivery.created_at.isoformat(),
                "data": delivery.payload,
            },
            ensure_ascii=False,
        ).encode()

        try:
            # SSRF re-validation right before send (DNS may have changed).
            validate_url(endpoint.url, policy=policy)
            timestamp = int(time.time())
            signature = sign_payload(endpoint.secret, body, timestamp)
            async with httpx.AsyncClient(timeout=_DELIVERY_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    endpoint.url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "VISiOnRoute-Webhook/1.0",
                        "X-VisiOnRoute-Signature": signature,
                        "X-VisiOnRoute-Delivery": str(delivery.id),
                    },
                )
            delivery.response_status = response.status_code
            if 200 <= response.status_code < 300:
                delivery.status = "delivered"
                delivery.delivered_at = now
                endpoint.last_success_at = now
                return True
            raise RuntimeError(f"HTTP {response.status_code}")
        except (httpx.HTTPError, UnsafeUrlError, RuntimeError) as exc:
            delivery.attempts += 1
            delivery.last_error = str(exc)[:1000]
            endpoint.last_failure_at = now
            if delivery.attempts >= _MAX_DELIVERY_ATTEMPTS:
                delivery.status = "dead_letter"
            else:
                backoff = min(2**delivery.attempts * 5, 900)
                delivery.next_attempt_at = now + timedelta(seconds=backoff)
            logger.warning(
                "webhook_delivery_failed",
                delivery_id=str(delivery.id),
                attempts=delivery.attempts,
                error=str(exc),
            )
            return False
