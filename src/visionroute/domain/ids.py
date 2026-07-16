"""UUIDv7 generation (RFC 9562).

Python 3.13's stdlib has no uuid7; this implementation produces
millisecond-ordered identifiers that index well in PostgreSQL (ADR-0005).
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Generate a UUIDv7: 48-bit unix-ms timestamp, version/variant bits, randomness."""
    timestamp_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10))  # 80 random bits

    rand_a = (rand >> 68) & 0xFFF  # 12 bits
    rand_b = rand & ((1 << 62) - 1)  # 62 bits

    value = (
        ((timestamp_ms & ((1 << 48) - 1)) << 80)
        | (0x7 << 76)  # version 7
        | (rand_a << 64)
        | (0b10 << 62)  # RFC 4122 variant
        | rand_b
    )
    return uuid.UUID(int=value)
