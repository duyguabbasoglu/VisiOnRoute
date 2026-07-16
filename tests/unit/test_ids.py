"""UUIDv7 generator unit tests."""

import time
import uuid

from visionroute.domain.ids import uuid7


def test_uuid7_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_uuid7_timestamp_is_current() -> None:
    before_ms = time.time_ns() // 1_000_000
    value = uuid7()
    after_ms = time.time_ns() // 1_000_000
    embedded_ms = value.int >> 80
    assert before_ms <= embedded_ms <= after_ms


def test_uuid7_is_time_ordered_across_milliseconds() -> None:
    first = uuid7()
    time.sleep(0.002)
    second = uuid7()
    assert first.int < second.int


def test_uuid7_uniqueness() -> None:
    values = {uuid7() for _ in range(10_000)}
    assert len(values) == 10_000
