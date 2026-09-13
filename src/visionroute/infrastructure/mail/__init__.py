"""Mail sender adapters (SMTP, local .eml files, in-memory for tests)."""

from __future__ import annotations

from visionroute.config.settings import Settings
from visionroute.infrastructure.mail.file import FileMailSender
from visionroute.infrastructure.mail.memory import MemoryMailSender
from visionroute.infrastructure.mail.smtp import SmtpMailSender


def build_mail_sender(settings: Settings) -> SmtpMailSender | FileMailSender | MemoryMailSender:
    if settings.mail_backend == "smtp":
        return SmtpMailSender.from_settings(settings)
    if settings.mail_backend == "file":
        return FileMailSender(settings.mail_file_dir)
    return MemoryMailSender()
