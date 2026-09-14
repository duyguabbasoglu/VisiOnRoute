"""Executive PDF keeps Turkish characters (embedded DejaVu Sans).

Needs the DejaVu font files: CI installs ``fonts-dejavu-core`` and sets
VISIONROUTE_TEST_PDF_FONT_DIR; locally point it at any directory containing
DejaVuSans.ttf and DejaVuSans-Bold.ttf.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from tests.helpers import auth_headers, create_org_and_login
from visionroute.config.fonts import find_unicode_font_dir

_CONFIGURED = os.environ.get("VISIONROUTE_TEST_PDF_FONT_DIR")

pytestmark = pytest.mark.skipif(
    _CONFIGURED is None or find_unicode_font_dir(Path(_CONFIGURED)) is None,
    reason="DejaVu Sans yazı tipi dizini ayarlanmadı (VISIONROUTE_TEST_PDF_FONT_DIR)",
)


def test_executive_pdf_renders_turkish_text(client: TestClient) -> None:
    owner = create_org_and_login(client, "pdf-tr", "o@pdf-tr.example")
    renamed = client.patch(
        "/api/v1/organizations/current",
        json={"name": "Işıklı Şoför Güvenliği Ağı"},
        headers=auth_headers(owner),
    )
    assert renamed.status_code == 200, renamed.text

    response = client.get("/api/v1/reports/executive.pdf", headers=auth_headers(owner))
    assert response.status_code == 200
    reader = PdfReader(io.BytesIO(response.content))
    text = "\n".join(page.extract_text() for page in reader.pages)

    for expected in (
        "Yönetici Güvenlik Raporu",
        "Işıklı Şoför Güvenliği Ağı",
        "Şiddet dağılımı",
        "Üretim zamanı",
        "Sınırlamalar",
    ):
        assert expected in text, expected
    fonts = reader.pages[0]["/Resources"]["/Font"]
    assert any("DejaVu" in str(font.get_object()["/BaseFont"]) for font in fonts.values())
