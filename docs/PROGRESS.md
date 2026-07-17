# İlerleme Kaydı / Progress Log

Her kilometre taşı kapanışında güncellenir. Tarihler UTC.

## 2026-07-16 — Oturum başlangıcı

- Depo boş bulundu; `git init` yapıldı.
- Ortam envanteri: Python 3.13.9, Poetry 2.3.2, Node 23, pnpm 9.15,
  PostgreSQL 17 (yerel, PostGIS Homebrew ile kuruluyor), Docker **yok**,
  Redis Homebrew ile kuruluyor, Terraform CLI yok.
- M1 başlatıldı.

## 2026-07-16 — M1 (Temel) tamamlandı

- Depo yapısı, `AGENTS.md`, `CLAUDE.md`, planlama/güvenlik dokümanları oluşturuldu.
- Poetry + pnpm çalışma alanları; Ruff, mypy (strict), import-linter, bandit,
  pip-audit, pre-commit, gitleaks yapılandırıldı.
- FastAPI uygulama fabrikası: Türkçe hata zarfı, korelasyon kimliği, güvenlik
  başlıkları, liveness/readiness uçları (yapılandırma sızdırmaz).
- `docker-compose.yml` + üretim Dockerfile'ları; Docker yoksa yerel PostgreSQL 17
  (+PostGIS) / Redis'e düşen `make db-up`.
- CI iş akışı (backend + frontend + gizli tarama + terraform validate), üçüncü
  taraf eylemleri SHA ile sabitlendi.
- **Kalite kapısı**: ruff ✓ mypy ✓ import-linter (2/2) ✓ 13 birim testi ✓
- Frontend: Next.js 15 strict TS, Tailwind v4; `pnpm typecheck/lint/build` ✓

## 2026-07-16 — M2 (Kimlik & kiracılık) tamamlandı

- Tablolar: organizations, organization_settings, users, roles, permissions,
  role_permissions, memberships, invitations, sessions, api_clients, api_tokens,
  audit_logs, outbox_events, idempotency_keys, background_jobs. İlk Alembic
  revizyonu; up→down→up doğrulandı.
- RBAC: 28 izin, 10 kiracı rolü; katalog `visionroute.domain.permissions`'ta
  tek doğruluk kaynağı, migration'a seed edildi, entegrasyon testi eşleşmeyi doğrular.
- Kimlik doğrulama: Argon2id parola, RS256 JWT (kısa ömürlü), refresh token
  rotasyonu + yeniden kullanım tespiti (aile iptali), hesap kilitleme,
  HttpOnly+SameSite çerez.
- Çok kiracılılık: uygulama katmanı + PostgreSQL RLS (`app.tenant_id`),
  çapraz kiracı ve WHERE'siz sorgu testleriyle doğrulandı.
- Denetim kaydı: append-only, DB trigger'ı UPDATE/DELETE reddeder (test edildi).
- `visionroute admin bootstrap`: tek seferlik, mevcut yöneticiyi ezmeyi reddeder,
  parolayı yazdırmaz (uçtan uca test edildi).
- **Kalite kapısı**: ruff ✓ mypy ✓ import-linter ✓ bandit (0 yüksek/orta) ✓
  39 test (birim + entegrasyon + güvenlik) ✓
- Güvenlik testleri: JWT algoritma karmaşası (elle üretilmiş HS256), alg=none,
  süresi dolmuş/yanlış audience/eksik claim, IDOR, SQL enjeksiyon dizeleri,
  aşırı büyük gövde.

## 2026-07-17 — M3 (Filo alanı) tamamlandı

- Tablolar: fleets, vehicle_groups, vehicles, drivers, driver_assignments,
  devices, cameras. RLS tüm filo tablolarına uygulandı; migration up→down→up
  doğrulandı. İkinci Alembic revizyonu.
- `external_id` her kaynakta kiracı içinde benzersiz (ingestion eşlemesi için).
- Sürücü-araç ataması zaman sınırlı; araç başına en fazla bir açık atama
  (kısmi benzersiz indeks) — testle doğrulandı.
- Filo servisi kiracı-bağlı; benzersizlik ihlalleri Türkçe çakışma hatasına
  çevrilir; çapraz kiracı erişim 404 döner (RLS + açık kontrol).
- CRUD uçları: /vehicles, /drivers, /devices, /cameras, /fleets, /assignments;
  RBAC (FLEET_READ / FLEET_MANAGE) ile korunur.
- **Kalite kapısı**: ruff ✓ mypy ✓ bandit (0 yüksek/orta) ✓ 46 test ✓
  (yeni: 7 filo entegrasyon testi, 6 izin birim testi, RBAC katalog seed testi)

## 2026-07-17 — M4 (Veri alımı) tamamlandı

- Kanonik olay zarfı (`visionroute.domain.ingestion`, sürüm 1.0): katı Pydantic
  doğrulama, saat dilimi zorunluluğu, koordinat/hız aralıkları, sentetik veri
  işaretleri (`data_origin`, `environment`).
- Tablolar: data_sources, data_source_credentials_metadata, ingest_events
  (RLS'li). Dedup doğal anahtarı (organizasyon, source, event_id). Üçüncü
  Alembic revizyonu (up→down→up doğrulandı).
- REST alım API'si (`X-API-Key`, `ingest:write` kapsamı): tek/çoklu olay,
  CSV toplu içe aktarma (10 MiB sınırı, dekompresyon bombası koruması).
- İşlem hattı: şema sürümü → yapı doğrulama → telemetri yükü → zaman damgası
  mantığı → kiracı eşleme → dedup'lu kabul. Reddedilenler karantinaya alınır,
  Türkçe nedenle saklanır (kaybolmaz).
- Idempotency: `ON CONFLICT DO NOTHING`; kabul edilen her olay outbox'a yazılır
  (worker M5+ işleyecek).
- API istemci/anahtar yönetimi: hash'li saklama, kapsam, süre, iptal,
  son kullanım; ihraç anında bir kez gösterim.
- SSRF-güvenli URL doğrulayıcı (`urlguard`): şema allowlist, kimlik-bilgisi
  reddi, özel/loopback/link-local/metadata adresleri engellenir.
- Referans simülatör CLI: aynı genel sözleşme üzerinden sentetik veri;
  `data_origin=synthetic`. **Uçtan uca canlı doğrulama yapıldı**: onboarding →
  veri kaynağı → API anahtarı → simülatör → 10 olay kabul, outbox'ta 10 kayıt,
  RLS ham sorguları tenant bağlamı olmadan engelledi.
- **Kalite kapısı**: ruff ✓ mypy ✓ bandit (0 yüksek/orta) ✓ 71 test ✓
  (yeni: 7 ingest entegrasyon, 8 urlguard, 7 sözleşme birim, 4 contract testi)
