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

## 2026-07-17 — M9 (Bildirimler, raporlar, analitik) tamamlandı

- Tablolar: notification_rules, notifications, webhook_endpoints,
  webhook_deliveries (RLS'li). Yedinci Alembic revizyonu (geri alınabilir).
- Kural değerlendirme worker'da: `safety.event_created` → şiddet eşiği kuralları
  → uygulama içi bildirim + imzalı webhook teslimatı kuyruğu.
- Webhook teslimatı: HMAC-SHA256 imza (`t=<ts>,v1=<hex>`, replay savunması),
  gönderim öncesi SSRF yeniden doğrulaması, üstel geri çekilme, dead-letter.
  İmza yerel alıcıya gerçek teslimatla testte doğrulandı.
- Raporlar: CSV (BOM'lu, metadata bloğu: organizasyon/zaman/kapsam/metodoloji/
  sınırlamalar) ve yönetici PDF'i (fpdf2). PDF'te tam Türkçe glif desteği için
  gömülü font gerekiyor (HANDOVER).
- Analitik özeti: şiddet dağılımı, onay oranı, 100 km başına olay (payda yoksa
  null — asla uydurma oran), Türkçe veri notu.
- **Kalite kapısı**: ruff ✓ mypy ✓ bandit ✓ 110 test ✓

## 2026-07-17 — M10 (SaaS & platform yönetimi) tamamlandı

- Tablolar: plans (katalog seed: Başlangıç 10 araç/5 kullanıcı, Profesyonel
  100/25, Kurumsal sınırsız), subscriptions (org başına tek, deneme/aktif/
  gecikmiş/iptal), usage_records. Sekizinci Alembic revizyonu, RLS'li.
- Kayıt anında otomatik 30 günlük deneme aboneliği (Başlangıç planı).
- **Limit zorlaması uygulama katmanında**: araç limiti (create_vehicle) ve
  kullanıcı limiti (davet) aşımında Türkçe 409; -1 = sınırsız. Testlerle
  doğrulandı (10 araç sonrası red, 5 üyelik sonrası red).
- Faturalama soyutlaması: varsayılan manuel fatura modu (ADR-0009); Stripe
  adaptörü kimlik bilgisi sağlanana dek devre dışı (HANDOVER).
- Platform yönetimi (yalnızca süper admin): organizasyon listesi + plan
  değiştirme (denetim kayıtlı) + plan kataloğu + sistem sağlığı (outbox/
  karantina/webhook DLQ sayaçları). Kiracı sahibi 403 alır (testle doğrulandı).
- Kiracıya abonelik görünümü: /subscription (plan, limitler, deneme bitişi).
- **Kalite kapısı**: ruff ✓ mypy ✓ bandit ✓ 114 test ✓

## 2026-07-17 — M11 (AWS altyapısı & CD) tamamlandı

- Terraform: yeniden kullanılabilir `stack` modülü (VPC + özel alt ağlar + NAT,
  RDS PostgreSQL 17 [KMS, PITR 14 gün, public erişim kapalı], ElastiCache
  Redis, özel S3 kanıt bucket'ı [versiyonlu, SSE-KMS, public block],
  ECR [immutable + push tarama], ECS Fargate [api+worker], ALB [TLS 1.3
  politikası, /api/* yönlendirme], en az yetkili IAM görev rolleri, Secrets
  Manager [DB parolası + JWT anahtar kabı], bütçe alarmı).
- Ortamlar: staging (ucuz profil, tek AZ) ve production (multi-AZ, silme
  koruması, zorunlu ACM sertifikası, GitHub environment onay kapısı).
- CD iş akışı: OIDC federasyonu (uzun ömürlü AWS anahtarı yok), SBOM (syft) +
  imaj taraması (grype --fail-on high), migration ayrı tek seferlik ECS görevi,
  smoke test. Tüm eylemler SHA-sabitli.
- Operasyon dokümanları: deployment.md (ilk kurulum + olağan dağıtım +
  rollback), runbook.md (sağlık, karantina, DLQ yeniden kuyruğa alma, anahtar
  rotasyonu, olay müdahalesi), backup-restore.md (PITR tatbikat prosedürü).
- **Sınırlama**: Terraform CLI bu makinede yok; `terraform validate` CI
  işinde tanımlı (ci.yml terraform job'ı). AWS hesabı olmadan canlı doğrulama
  yapılamadı (HANDOVER'da).

## 2026-07-17 — M12 (Son doğrulama & devir) tamamlandı

- Tam kalite paketi son kez koşuldu: fmt ✓ lint ✓ import sınırları ✓ mypy
  strict (97 dosya) ✓ 114 test ✓ bandit ✓ boş DB'den 8 migration ✓
  frontend typecheck/lint/build ✓.
- `docs/HANDOVER.md` eksikler tablosu + NEXT AGENT PROMPT INPUT ile güncellendi.
- `docs/RELEASE_READINESS.md` kanıt bazlı değerlendirme: **READY FOR STAGING**.

## 2026-09-14 — Kontrollü pilot tamamlama çalışması

Başlangıç (M12 sonrası denetim): 114 test, 8 migration, import-linter kırık,
2 bilinen CVE (cryptography, pytest), birçok spesifikasyon özelliği eksik.

- Temel hatalar: katman ihlalleri, DB-yetkili rol kontrolü, worker savepoint'leri,
  scheduler kilidi, tekilleştirme yarışı, CSV enjeksiyonu, gövde boyutu sınırı.
- Güvenlik: alan şifreleme, hız sınırlama (sonra kayan pencere), şifreli webhook
  sırları, JWT `kid`, refresh yeniden deneme penceresi, KVKK hız sınırları,
  kanıta dayalı tehdit modeli, eksik ADR'ler.
- Kimlik: işlemsel e-posta outbox'ı, parola sıfırlama, e-posta doğrulama, TOTP MFA;
  web tarafında tüm kimlik ekranları ve tek uçuşlu oturum yenileme.
- Ürün: koçluk, kanıt medyası (S3/MinIO), KVKK dışa aktarma/silme + saklama,
  SSE canlı akış, Türkçe PDF, Prometheus metrikleri, kullanım ölçümü, deneme bitişi,
  raporlar/bildirimler/webhook/API anahtarı/atama/platform ekranları.
- Altyapı: dağıtılabilir imajlar (API imajı hiç derlenmiyordu), compose tam yığın,
  Terraform worker/scheduler/web servisleri ve sırlar, sıralı CD, engelleyici denetimler,
  Playwright CI işi; web bağımlılıklarındaki kritik açıklar giderildi.
- Kalite kapısı: 247 backend testi, 12 Vitest, 16 Playwright akışı, 17 migration;
  Docker derleme + compose duman testi, Terraform validate.
- Yapılmayanlar ve kullanıcı eylemleri: docs/HANDOVER.md.

## 2026-09-16 — UI tamamlama, harita ve ücretsiz hobi dağıtım profili

Başlangıç durumu: 247 test, 16 Playwright akışı; cihaz/kamera/filo ekranları ve
harita eksikti; README depoda tek satıra inmişti.

- **Yerel çalışma zamanı**: makinedeki port çakışmaları teşhis edildi (3000/3001 ve
  9000/9001 başka bir projenin konteynerlerinde, 6379 Homebrew Redis, 5433 Homebrew
  PostgreSQL). `.env` sanitize edildi (yinelenen anahtarlar birleştirildi; alan
  şifreleme anahtar halkası korunarak tek satıra indirildi), compose host portları
  3002/6380/5434/9010/9011 olarak ayarlandı. Dokuz servisin tamamı sağlıklı;
  `/health/ready` ok, web 200.
- **Yeni ekranlar**: Filolar, Cihazlar ve Kameralar, Harita, Sefer ayrıntısı
  (güzergâh + sefere ait olaylar); araç düzenleme, coğrafi alan oluşturma
  (haritadan nokta seçme), sürücü risk skoru, olay listesinde araç/sürücü sütunu ve
  sayfalama, entegrasyon bağlantı rehberi, Türkçe 404 ve panel hata sınırı.
- **Harita**: MapLibre GL + OpenStreetMap (anahtarsız). Bulunan hata: MapLibre
  konteynere `position: relative` uyguladığı için Tailwind `absolute inset-0` ezildi
  ve tuval 0 px yüksekliğe düştü; konteyner `h-full w-full` ile boyutlandırıldı,
  E2E'de tuval görünürlüğü regresyon testi olarak eklendi.
- **Backend**: cihaz/kamera güncelleme uçları (PATCH, yalnızca `active`/`inactive`;
  `offline`/`obstructed` platforma ait), güvenlik olayları için `trip_id` filtresi,
  `Environment.DEMO` (üretim düzeyinde doğrulama, sentetik veri).
- **Simülatör hatası düzeltildi**: tüm noktalar aynı `occurred_at` ile üretiliyor ve
  4 noktalı döngüde zıplıyordu (40 nokta → 41,5 km "anlık" mesafe). Artık 5 sn
  aralıklı, rota üzerinde ilerleyen, fiziksel olarak tutarlı örnekler üretiyor.
- **Uyanma deneyimi**: ücretsiz sunucu uykudayken GET'ler sınırlı sayıda yeniden
  denenir ve kullanıcıya Türkçe "sunucu uyanıyor" bildirimi gösterilir.
- **Kalite kapısı**: 253 backend testi + 1 atlanan, 15 Vitest, 21 Playwright akışı,
  17 migration (up→down→up + `alembic check`), ruff/mypy strict/import-linter/
  bandit/pip-audit/pnpm audit temiz.
- **Hobi dağıtımı**: `visionroute hobby serve` süreç yöneticisi (migration → worker +
  scheduler + API, sinyal iletimi, çocuk süreç ölürse konteyner çıkar), `render.yaml`,
  Vercel `/api` proxy'si (çerez birinci taraf kalsın diye) ve belgeler.
  Cloudflare R2 ücretsiz katmanı bile kart istediği için nesne depolama tercihi
  Backblaze B2 olarak belirlendi. Sağlayıcı hesapları kullanıcı girişi bekliyor.

### CI'ın hiç yeşil olmadığının tespiti ve düzeltilmesi

Depo GitHub'a itildiğinde CI'ın **dört kez de başarısız** olduğu (sürüm commit'i
dâhil) görüldü; devir kaydı "CI hiç koşmadı" diyordu. Hata her seferinde
"Integration & security tests" adımındaydı ve yerelde tekrarlanamıyordu.

Kök neden: CI'ın kullandığı Postgres servis imajı bootstrap rolünü **superuser**
yapar; PostgreSQL'de superuser rolleri satır düzeyi güvenliği (RLS) atlar. Bu
nedenle `test_rls_blocks_unfiltered_cross_tenant_query` beklenen 0 yerine 183
satır gördü ve e-posta kuyruğu testi başka kiracının satırını okudu. Yerel
Homebrew rolü superuser olmadığı için aynı testler yerelde geçiyordu: suite
CI'da yerelde olduğundan daha azını kanıtlıyordu.

Düzeltme: testler artık üretim çalışma rolüne benzeyen, sahip rolünün nesne
yetkilerini devralan ama rol niteliklerini almayan (NOSUPERUSER, NOBYPASSRLS)
en az yetkili bir rolle bağlanır. Rol oluşturulamayan ortamlarda, mevcut rolün
RLS'i atlamadığı doğrulanırsa ona düşülür; atlıyorsa test açıkça hata verir.
Linux konteynerinde superuser sahipli veritabanına karşı doğrulandı: önce 2
başarısız, sonra 139 başarılı.

Ayrıca CI backend işine Redis servisi eklendi (hız sınırlama testi gerçek
Redis'e karşı çalışır) ve gitleaks yapılandırmasıyla e-posta şablonu testindeki
sahte davet belirteci beyaz listeye alındı.

