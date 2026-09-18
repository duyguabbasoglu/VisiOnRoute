"""The product name is written exactly "VisiOnRoute" wherever people read it.

Technical identifiers keep their own casing (``visionroute`` package and CLI,
``VISIONROUTE_*`` environment variables), so only mixed-case spellings of the
name are checked here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = "VisiOnRoute"
_NAME = re.compile(r"visionroute", re.IGNORECASE)
_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".tf",
    ".html",
    ".css",
    ".sh",
    ".example",
}


# Generated, vendored or local-only trees are not source.
_SKIP_DIRS = {
    ".git",
    ".next",
    ".venv",
    ".localdata",
    ".terraform",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "playwright-report",
    "test-results",
}


def _source_text_files() -> list[Path]:
    files = []
    for directory, subdirs, names in os.walk(ROOT):
        subdirs[:] = [d for d in subdirs if d not in _SKIP_DIRS]
        for name in names:
            path = Path(directory) / name
            if path.suffix in _TEXT_SUFFIXES or name == "Makefile":
                files.append(path)
    return files


def test_product_name_casing_is_canonical() -> None:
    offenders = []
    for path in _source_text_files():
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            for match in _NAME.finditer(line):
                word = match.group(0)
                # All-lower and all-upper spellings are technical identifiers.
                if word not in (CANONICAL, word.lower(), word.upper()):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {word}")
    assert not offenders, "Ürün adı tam olarak 'VisiOnRoute' yazılmalı:\n" + "\n".join(offenders)
