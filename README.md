# VISiOnRoute

**VISiOnRoute, sürücü davranışlarını ve yol koşullarını gerçek zamanlı analiz ederek
riskleri oluşmadan görünür kılan, tamamen Türkçe bir ulaşım güvenliği platformudur.**

VISiOnRoute kazaları önlediğini iddia etmez; hukuki, tıbbi, iş güvenliği, otomotiv
veya insan kararlarının yerine geçmez. Amaç: riskleri veriye dayalı, açıklanabilir
biçimde görünür kılmak.

## Hızlı başlangıç

Gereksinimler: Python 3.13, Poetry 2, Node 22, pnpm 9 ve Docker **veya**
Homebrew PostgreSQL 17 + PostGIS ve Redis.

### Docker Compose (tam yığın, sıfır maliyet)

```bash
poetry install
poetry run visionroute keys generate --out .dev/keys
poetry run visionroute keys generate-field-key >> .env
docker compose --profile full up -d --build
```

Web <http://localhost:3000>, API <http://localhost:8000>, e-postalar
<http://localhost:8025> (Mailpit). Ayrıntı ve demo akışı:
[`docs/operations/demo-profile.md`](docs/operations/demo-profile.md).

### Yerel süreçler

```bash
make bootstrap   # bağımlılıklar, .env
make dev         # veritabanı + migration + API (8000) + web (3000) + worker
make scheduler   # ayrı terminalde: saklama, kullanım ölçümü, bakım
```

İlk platform yöneticisi (tek seferlik): `poetry run visionroute admin bootstrap`.
Sentetik demo telemetrisi: `make seed-demo API_KEY=... SOURCE_KEY=...`
(tüm kayıtlar `data_origin=synthetic`).

## Depo haritası

| Yol | İçerik |
|-----|--------|
| `src/visionroute/` | Modüler monolit backend: domain, application, infrastructure, api, worker, scheduler, cli |
| `apps/web/` | Türkçe Next.js ön yüzü; `e2e/` Playwright uçtan uca testleri |
| `infra/terraform/` | AWS altyapısı (staging, production) |
| `infra/docker/` | Üretim imajları (API/worker/scheduler, web) |
| `docs/` | Kararlar, ADR'ler, operasyon, tehdit modeli, sürüm durumu |
| `tests/` | unit / integration / contract / security |
| `scripts/e2e/` | Uçtan uca test ortamı hazırlığı |

## Kalite kapısı

```bash
make check                      # format, lint, import sınırları, mypy, testler, bandit
cd apps/web && pnpm typecheck && pnpm lint && pnpm test && pnpm build
make e2e                        # Playwright: gerçek API + worker + web (PostgreSQL :5433)
```

S3 sözleşme testleri için `VISIONROUTE_TEST_S3_ENDPOINT`, Türkçe PDF testi için
`VISIONROUTE_TEST_PDF_FONT_DIR` tanımlayın (CI ikisini de sağlar).

## Dokümantasyon

- Sürüm hazırlık durumu: [`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md)
- Devir kaydı ve bilinen eksikler: [`docs/HANDOVER.md`](docs/HANDOVER.md)
- Kararlar: [`docs/DECISIONS.md`](docs/DECISIONS.md), ADR'ler: [`docs/adr/`](docs/adr/)
- Tehdit modeli: [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)
- Dağıtım: [`docs/operations/deployment.md`](docs/operations/deployment.md),
  runbook: [`docs/operations/runbook.md`](docs/operations/runbook.md),
  anahtar rotasyonu: [`docs/operations/key-rotation.md`](docs/operations/key-rotation.md)
- Veri alım sözleşmesi: [`docs/api/ingestion.md`](docs/api/ingestion.md);
  canlı OpenAPI: `/api/openapi.json` (üretimde belge arayüzü kapalı)
- Veri kaynağı kaydı: [`docs/DATA_SOURCE_REGISTER.md`](docs/DATA_SOURCE_REGISTER.md)

## Lisans

Tescilli (proprietary). Tüm hakları saklıdır.
