"""Ingestion pipeline: validate → dedup → persist → publish/quarantine.

Deterministic and side-effect-safe. Each envelope becomes exactly one
``ingest_events`` row (deduplicated); accepted rows emit an outbox event for
the worker to process into telemetry/trips/safety events (M5+).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.application.outbox import publish_event
from visionroute.domain.ingestion import (
    EventEnvelope,
    RejectionReason,
    TelemetryPayload,
    check_timestamp,
    is_schema_supported,
)
from visionroute.infrastructure.db.models.fleet import Vehicle
from visionroute.infrastructure.db.models.ingestion import DataSource, IngestEvent


@dataclass(frozen=True)
class IngestOutcome:
    event_id: str
    status: str  # accepted | duplicate | quarantined
    rejection_reason: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class BatchResult:
    accepted: int
    duplicates: int
    quarantined: int
    outcomes: list[IngestOutcome]


class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def ingest_batch(
        self,
        tenant_id: uuid.UUID,
        data_source: DataSource,
        raw_events: list[dict[str, object]],
        *,
        now: datetime | None = None,
    ) -> BatchResult:
        now = now or datetime.now(UTC)
        known_vehicles = await self._known_vehicle_ids(tenant_id)
        outcomes: list[IngestOutcome] = []
        accepted = duplicates = quarantined = 0

        for raw in raw_events:
            outcome = await self._ingest_one(tenant_id, data_source, raw, known_vehicles, now)
            outcomes.append(outcome)
            if outcome.status == "accepted":
                accepted += 1
            elif outcome.status == "duplicate":
                duplicates += 1
            else:
                quarantined += 1

        data_source.accepted_count += accepted
        data_source.rejected_count += quarantined
        data_source.duplicate_count += duplicates
        data_source.last_event_at = now
        if accepted:
            data_source.last_success_at = now
        return BatchResult(accepted, duplicates, quarantined, outcomes)

    async def _ingest_one(
        self,
        tenant_id: uuid.UUID,
        data_source: DataSource,
        raw: dict[str, object],
        known_vehicles: set[str],
        now: datetime,
    ) -> IngestOutcome:
        external_id = str(raw.get("event_id", "")) or "(bilinmiyor)"

        # 1. Schema version gate before full parse.
        schema_version = str(raw.get("schema_version", ""))
        if schema_version and not is_schema_supported(schema_version):
            return await self._store_quarantine(
                tenant_id,
                data_source,
                raw,
                external_id,
                None,
                RejectionReason.SCHEMA_VERSION_UNSUPPORTED,
                f"schema_version={schema_version}",
            )

        # 2. Structural validation.
        try:
            envelope = EventEnvelope.model_validate(raw)
        except ValidationError as exc:
            return await self._store_quarantine(
                tenant_id,
                data_source,
                raw,
                external_id,
                None,
                RejectionReason.INVALID_PAYLOAD,
                _summarize_errors(exc),
            )

        # 3. Telemetry payload validation (coordinates etc.).
        if envelope.event_type.value == "telemetry.position":
            try:
                TelemetryPayload.model_validate(envelope.payload)
            except ValidationError as exc:
                reason = (
                    RejectionReason.COORDINATES_OUT_OF_RANGE
                    if "latitude" in str(exc) or "longitude" in str(exc)
                    else RejectionReason.INVALID_PAYLOAD
                )
                return await self._store_quarantine(
                    tenant_id,
                    data_source,
                    envelope.model_dump(mode="json"),
                    envelope.event_id,
                    envelope,
                    reason,
                    _summarize_errors(exc),
                )

        # 4. Timestamp sanity.
        ts_reason = check_timestamp(envelope.occurred_at, now=now)
        if ts_reason is not None:
            return await self._store_quarantine(
                tenant_id,
                data_source,
                envelope.model_dump(mode="json"),
                envelope.event_id,
                envelope,
                ts_reason,
                str(envelope.occurred_at),
            )

        # 5. Tenant mapping validation.
        if envelope.vehicle_external_id not in known_vehicles:
            return await self._store_quarantine(
                tenant_id,
                data_source,
                envelope.model_dump(mode="json"),
                envelope.event_id,
                envelope,
                RejectionReason.UNKNOWN_VEHICLE,
                envelope.vehicle_external_id,
            )

        # 6. Accept with dedup: ON CONFLICT DO NOTHING on the natural key.
        return await self._store_accepted(tenant_id, data_source, envelope)

    async def _store_accepted(
        self, tenant_id: uuid.UUID, data_source: DataSource, envelope: EventEnvelope
    ) -> IngestOutcome:
        stmt = (
            pg_insert(IngestEvent)
            .values(
                id=uuid.uuid4(),
                organization_id=tenant_id,
                data_source_id=data_source.id,
                source=envelope.source,
                external_event_id=envelope.event_id,
                event_type=envelope.event_type.value,
                vehicle_external_id=envelope.vehicle_external_id,
                occurred_at=envelope.occurred_at,
                envelope=envelope.model_dump(mode="json"),
                status="accepted",
            )
            .on_conflict_do_nothing(
                index_elements=["organization_id", "source", "external_event_id"]
            )
            .returning(IngestEvent.id)
        )
        result = await self._db.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            return IngestOutcome(envelope.event_id, "duplicate")

        await publish_event(
            self._db,
            aggregate_type="ingest_event",
            aggregate_id=str(inserted_id),
            event_type="ingest.event_accepted",
            payload={
                "organization_id": str(tenant_id),
                "ingest_event_id": str(inserted_id),
                "event_type": envelope.event_type.value,
            },
        )
        return IngestOutcome(envelope.event_id, "accepted")

    async def _store_quarantine(
        self,
        tenant_id: uuid.UUID,
        data_source: DataSource,
        raw: dict[str, object],
        external_id: str,
        envelope: EventEnvelope | None,
        reason: RejectionReason,
        detail: str,
    ) -> IngestOutcome:
        stmt = (
            pg_insert(IngestEvent)
            .values(
                id=uuid.uuid4(),
                organization_id=tenant_id,
                data_source_id=data_source.id,
                source=envelope.source if envelope else data_source.source_key,
                external_event_id=external_id,
                event_type=envelope.event_type.value if envelope else "unknown",
                vehicle_external_id=envelope.vehicle_external_id if envelope else None,
                occurred_at=envelope.occurred_at if envelope else None,
                envelope=raw,
                status="quarantined",
                rejection_reason=reason.value,
                detail=detail[:2000],
            )
            .on_conflict_do_nothing(
                index_elements=["organization_id", "source", "external_event_id"]
            )
        )
        await self._db.execute(stmt)
        return IngestOutcome(external_id, "quarantined", reason.value, detail)

    async def _known_vehicle_ids(self, tenant_id: uuid.UUID) -> set[str]:
        result = await self._db.execute(
            select(Vehicle.external_id).where(Vehicle.organization_id == tenant_id)
        )
        return set(result.scalars())

    async def get_source_by_key(self, tenant_id: uuid.UUID, source_key: str) -> DataSource | None:
        result = await self._db.execute(
            select(DataSource).where(
                DataSource.organization_id == tenant_id,
                DataSource.source_key == source_key,
            )
        )
        return result.scalar_one_or_none()


def _summarize_errors(exc: ValidationError) -> str:
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['type']}" for e in exc.errors()[:5]]
    return "; ".join(parts)
