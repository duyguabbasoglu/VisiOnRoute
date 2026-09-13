"""Mail adapters against a real SMTP conversation (local socket server) and
the local .eml file adapter."""

from __future__ import annotations

import email
import email.policy
import socket
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from visionroute.domain.mail import MailDeliveryError, OutgoingEmail
from visionroute.infrastructure.mail.file import FileMailSender
from visionroute.infrastructure.mail.mime import build_mime
from visionroute.infrastructure.mail.smtp import SmtpMailSender


class _FakeSmtpServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _SmtpHandler)
        self.messages: list[bytes] = []
        self.rcpt_reply = "250 2.1.5 OK"


class _SmtpHandler(socketserver.StreamRequestHandler):
    server: _FakeSmtpServer

    def _reply(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode())

    def handle(self) -> None:
        self._reply("220 fake.smtp ESMTP")
        in_data = False
        lines: list[bytes] = []
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            if in_data:
                body_line = raw.rstrip(b"\r\n")
                if body_line == b".":
                    in_data = False
                    self.server.messages.append(b"\r\n".join(lines))
                    lines = []
                    self._reply("250 2.0.0 queued")
                else:
                    lines.append(body_line[1:] if body_line.startswith(b"..") else body_line)
                continue
            line = raw.decode("ascii", "replace").rstrip("\r\n")
            command = line.upper()
            if command.startswith(("EHLO", "HELO")):
                self._reply("250-fake.smtp")
                self._reply("250 8BITMIME")
            elif command.startswith("RCPT TO"):
                self._reply(self.server.rcpt_reply)
            elif command == "DATA":
                in_data = True
                self._reply("354 end with <CRLF>.<CRLF>")
            elif command == "QUIT":
                self._reply("221 bye")
                return
            else:
                self._reply("250 OK")


@pytest.fixture
def smtp_server() -> Iterator[_FakeSmtpServer]:
    server = _FakeSmtpServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _message(**overrides: str) -> OutgoingEmail:
    values = {
        "message_id": "<ornek-id@visionroute>",
        "from_address": "no-reply@visionroute.test",
        "from_name": "VISiOnRoute",
        "to_address": "alici@ornek.example",
        "subject": "Güvenlik bildirimi: parolanız değiştirildi",
        "text_body": "Merhaba Çağrı,\nparolanız değiştirildi.\n",
        "html_body": "<p>Merhaba Çağrı</p>",
    }
    values.update(overrides)
    return OutgoingEmail(**values)


def _sender(server: _FakeSmtpServer) -> SmtpMailSender:
    return SmtpMailSender(host="127.0.0.1", port=server.server_address[1], timeout=5)


async def test_smtp_delivers_multipart_turkish_message(smtp_server: _FakeSmtpServer) -> None:
    await _sender(smtp_server).send(_message())
    assert len(smtp_server.messages) == 1
    parsed = email.message_from_bytes(smtp_server.messages[0], policy=email.policy.default)
    assert parsed["Message-ID"] == "<ornek-id@visionroute>"
    assert parsed["Subject"] == "Güvenlik bildirimi: parolanız değiştirildi"
    assert parsed["Auto-Submitted"] == "auto-generated"
    plain = parsed.get_body(("plain",))
    html = parsed.get_body(("html",))
    assert plain is not None and "Merhaba Çağrı" in plain.get_content()
    assert html is not None and "<p>Merhaba Çağrı</p>" in html.get_content()


async def test_smtp_permanent_rejection_is_not_retried(smtp_server: _FakeSmtpServer) -> None:
    smtp_server.rcpt_reply = "550 5.1.1 no such user"
    with pytest.raises(MailDeliveryError) as excinfo:
        await _sender(smtp_server).send(_message())
    assert excinfo.value.permanent is True


async def test_smtp_temporary_rejection_is_transient(smtp_server: _FakeSmtpServer) -> None:
    smtp_server.rcpt_reply = "450 4.2.1 mailbox busy, try later"
    with pytest.raises(MailDeliveryError) as excinfo:
        await _sender(smtp_server).send(_message())
    assert excinfo.value.permanent is False


async def test_unreachable_server_is_transient() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(MailDeliveryError) as excinfo:
        await SmtpMailSender(host="127.0.0.1", port=port, timeout=2).send(_message())
    assert excinfo.value.permanent is False


def test_header_injection_is_rejected_permanently() -> None:
    with pytest.raises(MailDeliveryError) as excinfo:
        build_mime(_message(subject="Merhaba\r\nBcc: saldirgan@ornek.example"))
    assert excinfo.value.permanent is True


async def test_file_sender_writes_owner_only_eml(tmp_path: Path) -> None:
    location = await FileMailSender(tmp_path / "mail").send(_message())
    path = Path(location)
    assert path.suffix == ".eml"
    assert path.stat().st_mode & 0o777 == 0o600
    parsed = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    assert parsed["To"] == "alici@ornek.example"
