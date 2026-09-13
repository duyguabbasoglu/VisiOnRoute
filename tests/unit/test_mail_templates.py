"""Turkish e-mail templates: links, escaping, header safety, time zone."""

from __future__ import annotations

import pytest

from visionroute.application.mail.templates import (
    SECURITY_EVENT_LABELS_TR,
    TemplateRenderError,
    render,
    render_subject,
)

APP_URL = "https://app.visionroute.test/"


def _invitation(**overrides: str) -> dict[str, str]:
    context = {
        "organization_name": "Akyol Lojistik",
        "inviter_name": "Ayşe Yılmaz",
        "role_label": "Analist",
        "expires_at": "2026-09-20T09:00:00+00:00",
    }
    context.update(overrides)
    return context


def test_invitation_link_carries_token_in_fragment_only() -> None:
    rendered = render("invitation", _invitation(), {"token": "vri_abc-DEF_123"}, app_url=APP_URL)
    assert "https://app.visionroute.test/davet#token=vri_abc-DEF_123" in rendered.text
    assert "https://app.visionroute.test/davet#token=vri_abc-DEF_123" in rendered.html
    assert "?token=" not in rendered.text + rendered.html
    assert "Akyol Lojistik" in rendered.subject
    # 09:00 UTC is 12:00 in Europe/Istanbul.
    assert "20.09.2026 12:00" in rendered.text


def test_html_escapes_tenant_controlled_values() -> None:
    rendered = render(
        "invitation",
        _invitation(organization_name="<script>alert(1)</script>"),
        {"token": "vri_" + "x" * 20},
        app_url=APP_URL,
    )
    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html


def test_subject_cannot_carry_extra_headers() -> None:
    subject = render_subject(
        "invitation", _invitation(organization_name="Kötü\r\nBcc: x@y.example")
    )
    assert "\r" not in subject
    assert "\n" not in subject


def test_subjects_render_without_secrets() -> None:
    assert render_subject("invitation", _invitation())
    assert render_subject("password_reset", {"full_name": "A B", "ttl_minutes": "30"})
    assert render_subject("email_verification", {"full_name": "A B", "ttl_hours": "48"})
    assert render_subject(
        "security_notice",
        {
            "full_name": "A B",
            "event": "password_changed",
            "occurred_at": "2026-09-01T00:00:00+00:00",
        },
    )


def test_missing_values_and_unknown_templates_raise() -> None:
    with pytest.raises(TemplateRenderError):
        render("password_reset", {"full_name": "A", "ttl_minutes": "30"}, {}, app_url=APP_URL)
    with pytest.raises(TemplateRenderError):
        render("invitation", {}, {"token": "t" * 20}, app_url=APP_URL)
    with pytest.raises(TemplateRenderError):
        render("bilinmeyen", {}, {}, app_url=APP_URL)
    with pytest.raises(TemplateRenderError):
        render(
            "security_notice",
            {"full_name": "A", "event": "uydurma", "occurred_at": "2026-09-01T00:00:00+00:00"},
            {},
            app_url=APP_URL,
        )


def test_turkish_characters_are_preserved() -> None:
    rendered = render(
        "security_notice",
        {
            "full_name": "Çağrı Işık Öztürk Şüheda İnce",
            "event": "mfa_enabled",
            "occurred_at": "2026-09-01T21:30:00+00:00",
        },
        {},
        app_url=APP_URL,
    )
    for ch in "çÇğıIİöÖşŞüÜ":
        if ch in "Çağrı Işık Öztürk Şüheda İnce":
            assert ch in rendered.text
    assert SECURITY_EVENT_LABELS_TR["mfa_enabled"] in rendered.subject
    assert "02.09.2026 00:30" in rendered.text


def test_reset_and_verification_links() -> None:
    reset = render(
        "password_reset",
        {"full_name": "A B", "ttl_minutes": "30"},
        {"token": "vra_r"},
        app_url=APP_URL,
    )
    assert "/sifre-sifirla#token=vra_r" in reset.text
    assert "30 dakika" in reset.text
    verify = render(
        "email_verification",
        {"full_name": "A B", "ttl_hours": "48"},
        {"token": "vra_v"},
        app_url=APP_URL,
    )
    assert "/eposta-dogrula#token=vra_v" in verify.text
