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

## 2026-07-17 — M5 (Seferler & telemetri) tamamlandı

- Tablolar: trips, trip_segments, telemetry_aggregates ve **zaman-partisyonlu**
  telemetry_points (aylık RANGE partisyonları + DEFAULT partisyon, elle DDL).
  Dördüncü Alembic revizyonu (up→down→up doğrulandı, 5 partisyon).
- **Worker** (ADR-0002): outbox tüketicisi `FOR UPDATE SKIP LOCKED`, üstel
  geri çekilme, `dead_letter` eşiği. `ingest.event_accepted` olaylarını
  telemetri noktalarına ve seferlere dönüştürür.
- Sefer yaşam döngüsü: aktif sefer takibi, 15 dk boşluk → sefer kapatma,
  denormalize sefer başı (son konum, mesafe, nokta sayısı, azami hız).
- Deterministik telemetri kuralları: haversine mesafe, veri-kalite skoru
  (HDOP/uydu/hız), fiziksel olarak imkânsız sıçrama (GPS anomalisi) tespiti.
- Scheduler: partisyon önden oluşturma, bayat sefer kapatma.
- API: canlı operasyon (bayat besleme uyarısı), sefer listesi/detay, iz (trail).
- **Uçtan uca test**: ingest → worker → telemetri → sefer → canlı harita/iz;
  kiracı izolasyonu tüm hat boyunca doğrulandı.
- **Kalite kapısı**: ruff ✓ mypy ✓ bandit ✓ 80 test ✓
  (yeni: 6 telemetri kuralı birim, 3 boru hattı entegrasyon testi)

## 2026-07-17 — M6 (Güvenlik motoru) tamamlandı

- Deterministik kural motoru (`visionroute.domain.safety`, sürüm 2): sert fren,
  sert hızlanma, sert viraj, hız aşımı. **LLM sayısal telemetriyi sınıflandırmaz.**
- Sürümlü şiddet çerçevesi (eşiğe uzaklık → düşük/orta/yüksek/kritik); güven
  seviyesi veri kalitesini yansıtır, düşük kalite insan incelemesi bayrağı kaldırır.
- Kiracı bazlı eşik geçersiz kılma (organization_settings.risk_thresholds).
- Tablolar: safety_events (dedup doğal anahtarı, inceleme yaşam döngüsü),
  event_evidence (telemetri penceresi + medya için storage_key). RLS'li.
  Beşinci Alembic revizyonu (up→down→up doğrulandı).
- Tekilleştirme: aynı (araç, tip, 30 sn kova) çakışır, occurrence_count artar.
- Açıklanabilirlik: her olay "Ne oldu / Ne zaman / Nerede / Hangi veri / Hangi
  kural / Eşik / Ölçülen / Güven / Veri kalitesi / İnceleme gerekli" yanıtlar.
- Worker entegrasyonu: telemetri noktası oluşturulduktan sonra güvenlik motoru
  çalışır; kanıt bağlanır, outbox olayı yayınlanır.
- Güvenlik olayları API: filtrelenebilir liste + detay (açıklama + kanıt).
- **Uçtan uca test**: sert fren telemetrisi → açıklamalı güvenlik olayı,
  dedup, kiracı izolasyonu, normal sürüşte olay üretilmemesi.
- **Kalite kapısı**: ruff ✓ mypy ✓ bandit ✓ 92 test ✓
  (yeni: 8 kural birim, 4 motor entegrasyon testi)

## 2026-07-17 — M7 (Olay inceleme, yol riski, sürücü skoru) tamamlandı

- Olay inceleme akışı: onayla/reddet/belirsiz + not + kök neden + çözüm;
  her işlem değişmez denetim kaydına yazılır. EVENTS_REVIEW izni zorunlu.
- Yol riski kümeleme: tekrarlanan sert olayları konuma göre gruplar
  (deterministik açgözlü kümeleme); gözlenen kanıt / çıkarılan risk / güven /
  kaynak güvenilirliği ayrı tutulur. `road_risks` tablosu.
- Coğrafi çitler (geofences): dairesel yüksek-risk bölgeleri. Altıncı Alembic
  revizyonu (up→down→up doğrulandı, RLS'li).
- **Şeffaf sürücü risk skoru** (`domain.driver_score`, sürüm 1): maruziyete
  göre normalize (100 km başına), yapılandırılabilir şiddet ağırlıkları,
  tazelik yarı-ömrü, güven & veri-kalitesi ağırlıklandırma, minimum maruziyet
  eşiği (50 km altında skor yok), tam açıklanabilir, gizli/demografik değişken
  yok. Reddedilen olaylar hariç tutulur.
- **Kalite kapısı**: ruff ✓ mypy ✓ bandit ✓ 103 test ✓
  (yeni: 7 sürücü skoru birim, 4 inceleme/risk entegrasyon testi)
