"""Report generation (M9): CSV and PDF with mandatory metadata.

Every generated report carries: tenant, generation timestamp, selected
filters, data freshness/coverage, methodology and limitations (spec 2.8).
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from visionroute.config.fonts import BOLD_FONT, REGULAR_FONT, find_unicode_font_dir
from visionroute.domain.safety import (
    EVENT_LABELS_TR,
    SEVERITY_LABELS_TR,
    SafetyEventType,
    Severity,
)
from visionroute.infrastructure.db.models.identity import Organization
from visionroute.infrastructure.db.models.safety import SafetyEvent
from visionroute.infrastructure.db.models.telemetry import Trip

_METHODOLOGY_TR = (
    "Olaylar deterministik kurallarla üretilir; şiddet ve güven ayrı hesaplanır. "
    "Bu rapor kazaların önleneceğini garanti etmez; riskleri veriye dayalı "
    "görünür kılar."
)
_LIMITATIONS_TR = (
    "Veri kapsamı cihaz bağlantısına ve veri kalitesine bağlıdır. Düşük kaliteli "
    "veriden üretilen olaylar insan incelemesi gerektirir."
)


_MAX_REPORT_ROWS = 5000

# Spreadsheet applications evaluate cells starting with these characters as
# formulas (CSV/formula injection, OWASP). Tenant-controlled text is prefixed
# with an apostrophe so it is always rendered as literal text.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: str) -> str:
    if value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


@dataclass(frozen=True)
class ReportMeta:
    organization_name: str
    generated_at: datetime
    window_days: int
    event_count: int
    total_distance_km: float
    latest_event_at: datetime | None


class ReportService:
    def __init__(self, session: AsyncSession, *, pdf_font_dir: Path | None = None) -> None:
        self._db = session
        self._pdf_font_dir = pdf_font_dir

    async def _load(
        self, tenant_id: uuid.UUID, window_days: int
    ) -> tuple[ReportMeta, list[SafetyEvent]]:
        organization = await self._db.get(Organization, tenant_id)
        since = datetime.now(UTC) - timedelta(days=window_days)
        events_result = await self._db.execute(
            select(SafetyEvent)
            .where(SafetyEvent.organization_id == tenant_id, SafetyEvent.occurred_at >= since)
            .order_by(SafetyEvent.occurred_at.desc())
            .limit(_MAX_REPORT_ROWS)
        )
        events = list(events_result.scalars())
        distance = await self._db.execute(
            select(func.coalesce(func.sum(Trip.distance_km), 0.0)).where(
                Trip.organization_id == tenant_id, Trip.started_at >= since
            )
        )
        meta = ReportMeta(
            organization_name=organization.name if organization else str(tenant_id),
            generated_at=datetime.now(UTC),
            window_days=window_days,
            event_count=len(events),
            total_distance_km=round(float(distance.scalar_one()), 1),
            latest_event_at=events[0].occurred_at if events else None,
        )
        return meta, events

    async def safety_events_csv(self, tenant_id: uuid.UUID, *, window_days: int = 90) -> str:
        meta, events = await self._load(tenant_id, window_days)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        # Metadata block (as comment-style rows) before the header.
        writer.writerow(["# Rapor", "Güvenlik Olayları"])
        writer.writerow(["# Organizasyon", csv_safe(meta.organization_name)])
        writer.writerow(["# Üretim zamanı (UTC)", meta.generated_at.isoformat()])
        writer.writerow(["# Kapsam", f"Son {window_days} gün"])
        writer.writerow(["# Kapsanan toplam mesafe (km)", meta.total_distance_km])
        writer.writerow(["# Olay sayısı", meta.event_count])
        if meta.event_count >= _MAX_REPORT_ROWS:
            writer.writerow(["# Uyarı", f"Rapor en yeni {_MAX_REPORT_ROWS} olayla sınırlandı."])
        writer.writerow(["# Metodoloji", _METHODOLOGY_TR])
        writer.writerow(["# Sınırlamalar", _LIMITATIONS_TR])
        writer.writerow([])
        writer.writerow(
            [
                "olay_id",
                "olay_tipi",
                "olay_etiketi",
                "siddet",
                "guven",
                "zaman_utc",
                "enlem",
                "boylam",
                "olculen_deger",
                "esik",
                "inceleme_durumu",
                "tekrar_sayisi",
            ]
        )
        for event in events:
            writer.writerow(
                [
                    str(event.id),
                    csv_safe(event.event_type),
                    csv_safe(_label(event.event_type)),
                    event.severity,
                    event.confidence,
                    event.occurred_at.isoformat(),
                    event.latitude,
                    event.longitude,
                    event.measured_value,
                    event.threshold,
                    event.review_status,
                    event.occurrence_count,
                ]
            )
        return buffer.getvalue()

    async def executive_pdf(self, tenant_id: uuid.UUID, *, window_days: int = 90) -> bytes:
        meta, events = await self._load(tenant_id, window_days)
        by_severity = {s.value: 0 for s in Severity}
        for event in events:
            by_severity[event.severity] = by_severity.get(event.severity, 0) + 1
        confirmed = sum(1 for e in events if e.review_status == "confirmed")

        pdf = FPDF()
        pdf.set_title("VisiOnRoute Yönetici Güvenlik Raporu")
        pdf.set_creator("VisiOnRoute")
        font_dir = find_unicode_font_dir(self._pdf_font_dir)
        if font_dir is not None:
            pdf.add_font("DejaVu", "", str(font_dir / REGULAR_FONT))
            pdf.add_font("DejaVu", "B", str(font_dir / BOLD_FONT))
            family = "DejaVu"
            text = _identity
        else:
            # Development without the font package only: production-like
            # startup refuses to run without it (Settings.validate_for_runtime).
            family = "Helvetica"
            text = _ascii
        pdf.add_page()

        def line(value: str, *, size: int = 10, bold: bool = False, height: int = 6) -> None:
            pdf.set_font(family, "B" if bold else "", size)
            pdf.cell(0, height, text(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        def paragraph(value: str) -> None:
            pdf.set_font(family, "", 9)
            pdf.multi_cell(0, 5, text(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        line("VisiOnRoute — Yönetici Güvenlik Raporu", size=16, bold=True, height=10)
        line(f"Organizasyon: {meta.organization_name}")
        line(f"Üretim zamanı (UTC): {meta.generated_at.strftime('%Y-%m-%d %H:%M')}")
        line(f"Dönem: son {window_days} gün")
        line(f"Toplam mesafe: {meta.total_distance_km} km")
        line(f"Olay sayısı: {meta.event_count}")
        pdf.ln(4)

        line("Şiddet dağılımı", size=12, bold=True, height=8)
        for severity in Severity:
            line(f"{SEVERITY_LABELS_TR[severity]}: {by_severity[severity.value]}")
        rate = round(confirmed / meta.event_count * 100) if meta.event_count else 0
        line(f"İnceleme sonucu onaylanan olay oranı: %{rate}")
        pdf.ln(4)

        line("Metodoloji", size=12, bold=True, height=8)
        paragraph(_METHODOLOGY_TR)
        line("Sınırlamalar", size=12, bold=True, height=8)
        paragraph(_LIMITATIONS_TR)
        return bytes(pdf.output())

    async def coaching_csv(self, tenant_id: uuid.UUID, *, window_days: int = 90) -> str:
        """Coaching actions created in the window, with status and outcome."""
        from visionroute.domain.coaching import (
            OUTCOME_LABELS_TR,
            STATUS_LABELS_TR,
            CoachingOutcome,
            CoachingStatus,
            is_overdue,
        )
        from visionroute.infrastructure.db.models.coaching import CoachingAction
        from visionroute.infrastructure.db.models.fleet import Driver

        organization = await self._db.get(Organization, tenant_id)
        now = datetime.now(UTC)
        rows = await self._db.execute(
            select(CoachingAction, Driver.full_name)
            .outerjoin(Driver, Driver.id == CoachingAction.driver_id)
            .where(
                CoachingAction.organization_id == tenant_id,
                CoachingAction.created_at >= now - timedelta(days=window_days),
            )
            .order_by(CoachingAction.created_at.desc())
            .limit(_MAX_REPORT_ROWS)
        )
        records = rows.all()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["# Rapor", "Koçluk Görevleri"])
        writer.writerow(["# Organizasyon", csv_safe(organization.name if organization else "")])
        writer.writerow(["# Üretim zamanı (UTC)", now.isoformat()])
        writer.writerow(["# Kapsam", f"Son {window_days} günde oluşturulan görevler"])
        writer.writerow(["# Kayıt sayısı", len(records)])
        writer.writerow([])
        writer.writerow(
            [
                "gorev_id",
                "baslik",
                "durum",
                "gecikme",
                "surucu",
                "guvenlik_olayi_id",
                "termin_utc",
                "olusturma_utc",
                "tamamlanma_utc",
                "sonuc",
            ]
        )
        for action, driver_name in records:
            status = CoachingStatus(action.status)
            writer.writerow(
                [
                    str(action.id),
                    csv_safe(action.title),
                    STATUS_LABELS_TR[status],
                    "Gecikmiş" if is_overdue(status, action.due_at, now) else "",
                    csv_safe(driver_name or ""),
                    str(action.safety_event_id) if action.safety_event_id else "",
                    action.due_at.isoformat() if action.due_at else "",
                    action.created_at.isoformat(),
                    action.completed_at.isoformat() if action.completed_at else "",
                    OUTCOME_LABELS_TR[CoachingOutcome(action.outcome)] if action.outcome else "",
                ]
            )
        return buffer.getvalue()


def _label(event_type: str) -> str:
    try:
        return EVENT_LABELS_TR[SafetyEventType(event_type)]
    except ValueError:
        return event_type


def _identity(text: str) -> str:
    return text


def _ascii(text: str) -> str:
    """Fold Turkish characters for the Latin-1 core font (fallback only)."""
    table = str.maketrans("çÇğĞıİöÖşŞüÜ—", "cCgGiIoOsSuU-")
    return text.translate(table)
