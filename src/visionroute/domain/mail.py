"""E-mail value objects exchanged between the application layer and mail adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    # Stable per queued message, so a retried delivery carries the same
    # Message-ID and receiving systems can de-duplicate it.
    message_id: str
    from_address: str
    from_name: str
    to_address: str
    subject: str
    text_body: str
    html_body: str
    attachments: tuple[EmailAttachment, ...] = ()


class MailDeliveryError(Exception):
    """Delivery failed. ``permanent`` failures (e.g. 5xx recipient rejected)
    are not retried; transient ones (network, 4xx) are."""

    def __init__(self, reason: str, *, permanent: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.permanent = permanent
