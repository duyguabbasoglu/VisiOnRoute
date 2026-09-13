"""In-memory mail adapter for automated tests (rejected in production-like
environments). Messages are kept in a process-wide list so the API and the
worker running in one test process observe the same mailbox."""

from __future__ import annotations

from visionroute.domain.mail import OutgoingEmail

SENT_MESSAGES: list[OutgoingEmail] = []


class MemoryMailSender:
    async def send(self, email: OutgoingEmail) -> str:
        SENT_MESSAGES.append(email)
        return email.message_id
