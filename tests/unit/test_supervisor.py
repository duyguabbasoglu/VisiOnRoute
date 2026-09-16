"""Hobby-profile process supervisor: fail-fast, signal forwarding, one-shot steps."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time

from visionroute.cli.hobby import build_specs
from visionroute.cli.supervisor import ProcessSpec, Supervisor, run_step

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def test_crashing_child_stops_siblings_and_propagates_status() -> None:
    supervisor = Supervisor(
        [
            ProcessSpec("long", SLEEPER),
            ProcessSpec(
                "crash", [sys.executable, "-c", "import sys, time; time.sleep(0.3); sys.exit(3)"]
            ),
        ],
        grace_seconds=5,
    )
    started = time.monotonic()
    assert supervisor.run() == 3
    assert time.monotonic() - started < 15
    assert all(child.poll() is not None for child in supervisor._children.values())


def test_sigterm_is_forwarded_and_exit_is_clean() -> None:
    supervisor = Supervisor([ProcessSpec("a", SLEEPER), ProcessSpec("b", SLEEPER)], grace_seconds=5)
    timer = threading.Timer(0.8, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()
    try:
        assert supervisor.run() == 0
    finally:
        timer.cancel()
    assert all(child.returncode is not None for child in supervisor._children.values())


def test_failed_one_shot_step_reports_status() -> None:
    assert run_step(ProcessSpec("migrate", [sys.executable, "-c", "raise SystemExit(2)"])) == 2
    assert run_step(ProcessSpec("migrate", [sys.executable, "-c", "pass"])) == 0


def test_hobby_specs_bind_platform_port_with_all_processes() -> None:
    specs = build_specs(10000, scheduler_interval=120)
    assert [spec.name for spec in specs] == ["worker", "scheduler", "api"]
    api = list(specs[2].argv)
    assert api[api.index("--port") + 1] == "10000"
    assert api[api.index("--host") + 1] == "0.0.0.0"
    assert "--proxy-headers" in api
