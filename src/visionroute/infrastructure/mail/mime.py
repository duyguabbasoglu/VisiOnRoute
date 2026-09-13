"""MIME message construction shared by the SMTP and file adapters."""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr, formatdate

from visionroute.domain.mail import MailDeliveryError, OutgoingEmail


def build_mime(email: OutgoingEmail) -> EmailMessage:
    message = EmailMessage()
    try:
        message["From"] = formataddr((email.from_name, email.from_address))
        message["To"] = email.to_address
        message["Subject"] = email.subject
        message["Message-ID"] = email.message_id
        message["Date"] = formatdate(localtime=False)
        # RFC 3834: suppress auto-replies and vacation responders.
        message["Auto-Submitted"] = "auto-generated"
    except ValueError as exc:
        # The e-mail package rejects CR/LF in header values (header injection).
        msg = "Geçersiz e-posta başlığı."
        raise MailDeliveryError(msg, permanent=True) from exc
    message.set_content(email.text_body)
    message.add_alternative(email.html_body, subtype="html")
    for attachment in email.attachments:
        maintype, _, subtype = attachment.content_type.partition("/")
        message.add_attachment(
            attachment.content,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=attachment.filename,
        )
    return message
