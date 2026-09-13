"""SMTP mail adapter (Mailpit locally, a transactional e-mail provider in production).

Uses the standard library ``smtplib`` in a worker thread; no extra dependency.
Failure classification:
- 5xx recipient/sender/data rejections → permanent (not retried);
- authentication failures, 4xx, timeouts, connection errors → transient
  (retried with backoff, so an operator can fix credentials without losing mail).
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from visionroute.config.settings import Settings
from visionroute.domain.mail import MailDeliveryError, OutgoingEmail
from visionroute.infrastructure.mail.mime import build_mime


class SmtpMailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        starttls: bool = False,
        use_ssl: bool = False,
        timeout: float = 15.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._starttls = starttls
        self._use_ssl = use_ssl
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> SmtpMailSender:
        return cls(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
            starttls=settings.smtp_starttls,
            use_ssl=settings.smtp_use_ssl,
            timeout=settings.smtp_timeout_seconds,
        )

    async def send(self, email: OutgoingEmail) -> str:
        message = build_mime(email)
        await asyncio.to_thread(self._send_sync, message, email.to_address)
        return email.message_id

    def _send_sync(self, message: EmailMessage, recipient: str) -> None:
        try:
            client: smtplib.SMTP
            if self._use_ssl:
                client = smtplib.SMTP_SSL(
                    self._host,
                    self._port,
                    timeout=self._timeout,
                    context=ssl.create_default_context(),
                )
            else:
                client = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
            with client:
                client.ehlo()
                if self._starttls:
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
                if self._username:
                    client.login(self._username, self._password or "")
                refused = client.send_message(message, to_addrs=[recipient])
            if refused:
                msg = "Alıcı adresi sunucu tarafından reddedildi."
                raise MailDeliveryError(msg, permanent=True)
        except MailDeliveryError:
            raise
        except smtplib.SMTPAuthenticationError as exc:
            msg = f"SMTP kimlik doğrulaması başarısız ({exc.smtp_code})."
            raise MailDeliveryError(msg, permanent=False) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            codes = [code for code, _ in exc.recipients.values()]
            permanent = bool(codes) and all(500 <= code < 600 for code in codes)
            msg = f"Alıcı reddedildi ({', '.join(str(c) for c in codes)})."
            raise MailDeliveryError(msg, permanent=permanent) from exc
        except smtplib.SMTPResponseException as exc:
            permanent = 500 <= exc.smtp_code < 600
            msg = f"SMTP sunucusu isteği reddetti ({exc.smtp_code})."
            raise MailDeliveryError(msg, permanent=permanent) from exc
        except (smtplib.SMTPException, OSError) as exc:
            msg = f"SMTP bağlantı hatası ({type(exc).__name__})."
            raise MailDeliveryError(msg, permanent=False) from exc
