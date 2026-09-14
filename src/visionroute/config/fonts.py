"""Unicode font discovery for generated PDF reports.

The PDF core fonts (Helvetica) only cover Latin-1, so Turkish letters such as
ğ, ş, ı and İ need an embedded TrueType font. DejaVu Sans is used (Bitstream
Vera / public-domain licence, freely redistributable) and is provided by the
operating system package ``fonts-dejavu-core`` in the API image and in CI;
the font files are not vendored into the repository.
"""

from __future__ import annotations

from pathlib import Path

REGULAR_FONT = "DejaVuSans.ttf"
BOLD_FONT = "DejaVuSans-Bold.ttf"

_SYSTEM_FONT_DIRS = (
    Path("/usr/share/fonts/truetype/dejavu"),  # Debian / Ubuntu
    Path("/usr/share/fonts/dejavu-sans-fonts"),  # Fedora / RHEL
    Path("/usr/share/fonts/TTF"),  # Arch
    Path("/opt/homebrew/share/fonts"),  # Homebrew (macOS)
)


def find_unicode_font_dir(configured: Path | None = None) -> Path | None:
    """Directory containing DejaVu Sans regular and bold, or None.

    An explicitly configured directory is authoritative: if it lacks the fonts
    the result is None rather than silently falling back to another location.
    """
    candidates = (configured,) if configured is not None else _SYSTEM_FONT_DIRS
    for directory in candidates:
        if (directory / REGULAR_FONT).is_file() and (directory / BOLD_FONT).is_file():
            return directory
    return None
