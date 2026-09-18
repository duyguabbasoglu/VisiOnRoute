"""Turkish transactional e-mail templates.

Rendering rules:
- every interpolated value is HTML-escaped in the HTML part;
- the subject is forced onto a single line (header injection);
- links are built only from the configured application URL, and one-time
  tokens are placed in the URL *fragment* (``#token=``). Browsers never send
  fragments to servers, so tokens cannot leak into web or proxy access logs;
- secret values come from ``secret_context``, which is stored encrypted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from html import escape
from urllib.parse import quote
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Istanbul")
_FOOTER = "Bu e-posta VisiOnRoute tarafından otomatik olarak gönderildi; lütfen yanıtlamayın."

TEMPLATES = frozenset(
    {
        "invitation",
        "password_reset",
        "email_verification",
        "security_notice",
        "coaching_assigned",
        "privacy_export_ready",
    }
)

SECURITY_EVENT_LABELS_TR: dict[str, str] = {
    "password_changed": "Parolanız değiştirildi",  # nosec B105 - UI label, not a secret
    "mfa_enabled": "İki adımlı doğrulama etkinleştirildi",
    "mfa_disabled": "İki adımlı doğrulama kapatıldı",
    "mfa_reset": "İki adımlı doğrulamanız bir yönetici tarafından sıfırlandı",
    "mfa_recovery_code_used": "Bir kurtarma kodu kullanıldı",
    "recovery_codes_regenerated": "Kurtarma kodlarınız yenilendi",
}


class TemplateRenderError(ValueError):
    """Unknown template or incomplete context (a permanent delivery failure)."""


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


@dataclass(frozen=True, slots=True)
class _Content:
    subject: str
    title: str
    paragraphs: list[str]
    action: tuple[str, str] | None
    note: str


def format_local(iso_timestamp: str) -> str:
    """Format a UTC ISO timestamp for Turkish readers (Europe/Istanbul)."""
    return datetime.fromisoformat(iso_timestamp).astimezone(_TZ).strftime("%d.%m.%Y %H:%M")


def render_subject(template: str, context: Mapping[str, str]) -> str:
    """Subject without secrets; safe to store for delivery-status listings."""
    return _content(template, context, {}, app_url="", with_secrets=False).subject


def render(
    template: str,
    context: Mapping[str, str],
    secret_context: Mapping[str, str],
    *,
    app_url: str,
) -> RenderedEmail:
    content = _content(template, context, secret_context, app_url=app_url, with_secrets=True)
    text_parts = [*content.paragraphs]
    if content.action is not None:
        text_parts.append(f"{content.action[0]}: {content.action[1]}")
    text_parts.extend([content.note, _FOOTER])
    return RenderedEmail(
        subject=content.subject,
        text="\n\n".join(text_parts) + "\n",
        html=_html(content),
    )


def _content(
    template: str,
    context: Mapping[str, str],
    secret_context: Mapping[str, str],
    *,
    app_url: str,
    with_secrets: bool,
) -> _Content:
    def link(path: str) -> tuple[str, str] | None:
        if not with_secrets:
            return None
        return _link(app_url, path, _require(secret_context, "token"))

    if template == "coaching_assigned":
        title = _require(context, "title")
        due_at = context.get("due_at")
        paragraphs = [
            f"Merhaba {_require(context, 'full_name')},",
            f"{_require(context, 'organization_name')} organizasyonunda size bir sürücü koçluğu "
            f"görevi atandı: {title}.",
        ]
        if due_at:
            paragraphs.append(f"Termin: {format_local(due_at)}.")
        action_id = quote(_require(context, "action_id"), safe="")
        return _Content(
            subject=_single_line(f"Size koçluk görevi atandı: {title}"),
            title="Yeni koçluk görevi",
            paragraphs=paragraphs,
            action=(
                ("Görevi görüntüle", f"{app_url.rstrip('/')}/panel/kocluk/{action_id}")
                if with_secrets
                else None
            ),
            note=("Sürücü ve olay ayrıntıları yalnızca panelde, yetkili kullanıcılara gösterilir."),
        )
    if template == "privacy_export_ready":
        return _Content(
            subject="Kişisel veri dışa aktarma dosyanız hazır",
            title="Veri dışa aktarma hazır",
            paragraphs=[
                f"Merhaba {_require(context, 'full_name')},",
                f"{_require(context, 'organization_name')} organizasyonundaki kişisel "
                "verilerinizin dışa aktarma dosyası hazırlandı.",
                f"Dosya {format_local(_require(context, 'expires_at'))} tarihine kadar panelden "
                "indirilebilir; sonrasında otomatik olarak silinir.",
            ],
            action=(
                ("Hesabıma git", f"{app_url.rstrip('/')}/panel/hesap") if with_secrets else None
            ),
            note=(
                "Güvenliğiniz için dosya e-postaya eklenmez; indirmek için oturum açmanız gerekir."
            ),
        )
    if template == "invitation":
        organization = _require(context, "organization_name")
        action = link("/davet")
        return _Content(
            subject=_single_line(f"{organization} sizi VisiOnRoute'a davet etti"),
            title="VisiOnRoute daveti",
            paragraphs=[
                "Merhaba,",
                f"{_require(context, 'inviter_name')} sizi {organization} organizasyonuna "
                f"{_require(context, 'role_label')} rolüyle davet etti.",
                "VisiOnRoute; sürücü davranışlarını ve yol koşullarını analiz ederek "
                "riskleri görünür kılan bir ulaşım güvenliği platformudur.",
            ],
            action=("Daveti kabul et", action[1]) if action else None,
            note=(
                f"Bu bağlantı {format_local(_require(context, 'expires_at'))} tarihine kadar "
                "geçerlidir ve yalnızca bir kez kullanılabilir. Bu daveti beklemiyorsanız "
                "e-postayı yok sayabilirsiniz."
            ),
        )
    if template == "password_reset":
        action = link("/sifre-sifirla")
        return _Content(
            subject="VisiOnRoute parola sıfırlama",
            title="Parola sıfırlama isteği",
            paragraphs=[
                f"Merhaba {_require(context, 'full_name')},",
                "Hesabınız için bir parola sıfırlama isteği aldık.",
            ],
            action=("Yeni parola belirle", action[1]) if action else None,
            note=(
                f"Bağlantı {_require(context, 'ttl_minutes')} dakika geçerlidir ve yalnızca bir "
                "kez kullanılabilir. Bu isteği siz yapmadıysanız parolanız değişmez; "
                "e-postayı yok sayabilirsiniz."
            ),
        )
    if template == "email_verification":
        action = link("/eposta-dogrula")
        return _Content(
            subject="VisiOnRoute e-posta adresinizi doğrulayın",
            title="E-posta doğrulama",
            paragraphs=[
                f"Merhaba {_require(context, 'full_name')},",
                "VisiOnRoute hesabınızı güvenle kullanabilmek için e-posta adresinizi doğrulayın.",
            ],
            action=("E-postamı doğrula", action[1]) if action else None,
            note=(
                f"Bağlantı {_require(context, 'ttl_hours')} saat geçerlidir. Bu hesabı siz "
                "oluşturmadıysanız e-postayı yok sayabilirsiniz."
            ),
        )
    if template == "security_notice":
        event = _require(context, "event")
        label = SECURITY_EVENT_LABELS_TR.get(event)
        if label is None:
            raise TemplateRenderError(f"Bilinmeyen güvenlik olayı: {event}")
        return _Content(
            subject=f"VisiOnRoute güvenlik bildirimi: {label}",
            title="Hesap güvenliği bildirimi",
            paragraphs=[
                f"Merhaba {_require(context, 'full_name')},",
                f"Hesabınızda şu işlem yapıldı: {label} "
                f"({format_local(_require(context, 'occurred_at'))}).",
            ],
            action=None,
            note=(
                "Bu işlemi siz yapmadıysanız hemen parolanızı sıfırlayın ve organizasyon "
                "yöneticinizle iletişime geçin."
            ),
        )
    raise TemplateRenderError(f"Bilinmeyen e-posta şablonu: {template}")


def _require(context: Mapping[str, str], key: str) -> str:
    value = context.get(key)
    if not value:
        raise TemplateRenderError(f"Şablon bağlamında eksik alan: {key}")
    return value


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _link(app_url: str, path: str, token: str) -> tuple[str, str]:
    return path, f"{app_url.rstrip('/')}{path}#token={quote(token, safe='')}"


def _html(content: _Content) -> str:
    body = "".join(f'<p style="margin:0 0 16px">{escape(p)}</p>' for p in content.paragraphs)
    if content.action is not None:
        label, url = content.action
        safe_url = escape(url, quote=True)
        body += (
            f'<p style="margin:24px 0"><a href="{safe_url}" style="background:#1d4ed8;'
            "color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;"
            f'display:inline-block">{escape(label)}</a></p>'
            '<p style="margin:0 0 16px;font-size:12px;color:#64748b">Düğme çalışmazsa bu '
            f"bağlantıyı tarayıcınıza yapıştırın:<br>{safe_url}</p>"
        )
    return (
        '<!doctype html><html lang="tr"><body style="font-family:Segoe UI,Arial,sans-serif;'
        'color:#0b1220;background:#f8fafc;padding:24px">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid '
        '#e2e8f0;border-radius:12px;padding:32px">'
        f'<h1 style="font-size:20px;margin:0 0 24px">{escape(content.title)}</h1>{body}'
        f'<p style="margin:24px 0 0;font-size:12px;color:#64748b">{escape(content.note)}</p>'
        f'<p style="margin:8px 0 0;font-size:12px;color:#94a3b8">{escape(_FOOTER)}</p>'
        "</div></body></html>"
    )
