# VISiOnRoute

**VISiOnRoute, sürücü davranışlarını ve yol koşullarını gerçek zamanlı analiz ederek
riskleri oluşmadan görünür kılan, tamamen Türkçe bir ulaşım güvenliği platformudur.**

VISiOnRoute kazaları önlediğini iddia etmez; hukuki, tıbbi, iş güvenliği, otomotiv
veya insan kararlarının yerine geçmez. Amaç: riskleri veriye dayalı, açıklanabilir
biçimde görünür kılmak.

## Hızlı başlangıç (yerel geliştirme)

Gereksinimler: Python 3.13, Poetry, Node 20+, pnpm ve Docker **veya**
Homebrew PostgreSQL 17 + PostGIS.

```bash
make bootstrap   # bağımlılıkları kurar, .env oluşturur
make dev         # veritabanı + API (8000) + web (3000) + worker
```

İlk platform yöneticisini oluşturmak için (tek seferlik, güvenli):

```bash
poetry run visionroute admin bootstrap
```

Demo verisi (yalnızca yerel/demo; tüm kayıtlar `data_origin=synthetic` işaretlenir):

```bash
make seed-demo
poetry run visionroute simulate telemetry --help
```

## Depo haritası

| Yol | İçerik |
|-----|--------|
| `src/visionroute/` | Modüler monolit backend (FastAPI, domain, worker, CLI) |
| `apps/web/` | Türkçe Next.js ön yüz |
| `infra/terraform/` | AWS altyapısı (IaC) |
| `infra/docker/` | Üretim imaj tanımları |
| `docs/` | Mimari, operasyon, güvenlik, ürün dokümantasyonu |
| `tests/` | unit / integration / contract / security / e2e |
| `scripts/` | Yardımcı geliştirme betikleri |

## Kalite kapısı

```bash
make check   # format + lint + import sınırları + mypy + testler + güvenlik taramaları
```

## Dokümantasyon

- Uygulama planı: [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
- Mimari kararlar: [`docs/DECISIONS.md`](docs/DECISIONS.md) ve `docs/adr/`
- Tehdit modeli: [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)
- Veri kaynağı kaydı: [`docs/DATA_SOURCE_REGISTER.md`](docs/DATA_SOURCE_REGISTER.md)
- Sürüm hazırlık durumu: [`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md)
- Devir kaydı: [`docs/HANDOVER.md`](docs/HANDOVER.md)

## Lisans

Tescilli (proprietary). Tüm hakları saklıdır.
