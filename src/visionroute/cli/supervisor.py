"""Minimal process supervisor for the single-container hobby profile.

Free hosting tiers (e.g. one Render free web service) offer no separate
background workers, so the hobby profile runs API, outbox worker and
scheduler side by side in one container. They stay separate OS processes so
a crash in one is visible and the production topology (independent services)
is unchanged. Rules:

* a one-shot step (migrations) must succeed before anything starts;
* SIGTERM/SIGINT are forwarded to every child, then the supervisor waits;
* if any long-running child exits, the others are stopped and the supervisor
  exits with that child's status, so the platform restarts the container
  instead of silently running without a worker or scheduler.

NOT used by the production deployment (docs/operations/deployment.md).
"""

from __future__ import annotations

import signal
import subprocess  # nosec B404 — fixed internal argv lists only, never a shell
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from types import FrameType

POLL_SECONDS = 0.5


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    argv: Sequence[str]


def _log(message: str) -> None:
    print(f"[supervisor] {message}", file=sys.stderr, flush=True)


def run_step(spec: ProcessSpec) -> int:
    """Run a one-shot command to completion and return its exit status."""
    _log(f"{spec.name} başlatılıyor")
    code = subprocess.call(list(spec.argv))  # noqa: S603  # nosec B603 — argv built in code
    _log(f"{spec.name} bitti (çıkış kodu {code})")
    return code


class Supervisor:
    def __init__(self, specs: Sequence[ProcessSpec], *, grace_seconds: float = 20.0) -> None:
        self._specs = list(specs)
        self._grace = grace_seconds
        self._children: dict[str, subprocess.Popen[bytes]] = {}
        self._stopping = False

    def _handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        _log(f"sinyal alındı ({signal.Signals(signum).name}); süreçler durduruluyor")
        self._stopping = True

    def run(self) -> int:
        previous = {
            sig: signal.signal(sig, self._handle_signal) for sig in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            for spec in self._specs:
                # argv comes from build_specs(), never from user input.
                self._children[spec.name] = subprocess.Popen(list(spec.argv))  # noqa: S603  # nosec B603
                _log(f"{spec.name} başlatıldı (pid {self._children[spec.name].pid})")
            exit_code = 0
            while not self._stopping:
                for name, child in self._children.items():
                    code = child.poll()
                    if code is not None:
                        _log(f"{name} beklenmedik şekilde durdu (çıkış kodu {code})")
                        exit_code = code or 1
                        self._stopping = True
                        break
                time.sleep(POLL_SECONDS)
            self._terminate_all()
            return exit_code
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    def _terminate_all(self) -> None:
        for child in self._children.values():
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
        deadline = time.monotonic() + self._grace
        for name, child in self._children.items():
            remaining = max(0.0, deadline - time.monotonic())
            try:
                child.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                _log(f"{name} süre içinde kapanmadı; zorla sonlandırılıyor")
                child.kill()
                child.wait()
