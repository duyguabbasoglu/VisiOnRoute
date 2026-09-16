# Devir Kaydı / Handover Log

Son güncelleme: 2026-09-16 (UI tamamlama, harita ve ücretsiz hobi dağıtım profili çalışması). Bu belge
tamamlanamayan işleri, nedenlerini ve tamamlanma kriterlerini açıkça kaydeder.

## Doğrulanmış ortam gerçekleri

- **Yerel doğrulama**: backend testleri gerçek PostgreSQL 17 + PostGIS (5433),
  Redis ve MinIO'ya karşı; Playwright gerçek API + worker + üretim web derlemesiyle.
- **Docker**: API ve web imajları bu makinede derlendi; `docker compose --profile full`
  ile migrate → API hazır (DB + migration + Redis) → kayıt 201 → web 200 → doğrulama
  e-postası Mailpit'e SMTP ile ulaştı (bkz. docs/operations/demo-profile.md).
- **Terraform**: `terraform fmt -check` ve `validate` (1.10.5, Docker imajı) staging ve
  production için başarılı. **`plan`/`apply` hiç çalıştırılmadı** (AWS kimlik bilgisi yok).
- **GitHub**: uzak depo `duyguabbasoglu/VisiOnRoute` (public) tanımlı. Bu çalışmanın
  itilmesinden önce CI GitHub üzerinde koşmamıştı; CI adımlarının yerel eşdeğerleri
  çalıştırıldı.
- **Ücretsiz hobi dağıtımı**: profil, `render.yaml` blueprint'i ve adım adım belge
  hazır (docs/operations/hobby-deployment.md). **Hiçbir sağlayıcıda kaynak
  oluşturulmadı**: Render/Neon/Upstash/Backblaze/Brevo hesap girişleri kullanıcıya ait.

## Yetenek durumu

| Konu | Durum | Kanıt / not |
|------|-------|-------------|
| Kimlik: kayıt, giriş, oturum yenileme (tek uçuş), e-posta doğrulama, parola sıfırlama, davet | Tamam | Entegrasyon + E2E; token'lar API yanıtında dönmez, e-postada URL fragmanında |
| TOTP MFA, kurtarma kodları, org MFA politikası, yönetici MFA sıfırlama | Tamam | test_account_security + E2E (TOTP test içinde üretilir) |
| İşlemsel e-posta (SMTP/file/memory, outbox, yeniden deneme) | Tamam | Sahte SMTP sunucusu testleri + compose Mailpit teslimi |
| Alan şifreleme (Fernet anahtar halkası, yeniden şifreleme) | Tamam | test_field_crypto, migration testleri |
| Koçluk iş akışı | Tamam | test_coaching + E2E |
| Kanıt medyası (S3/MinIO, imzalı URL, sihirli bayt, denetim) | Tamam | test_evidence_media + MinIO sözleşme testi + E2E yükleme |
| Otomatik yüz/plaka anonimleştirme | **Yapılmadı** | Harici bilgisayarlı görü servisi + hukuki eşik kararı gerekir; medya `not_processed` olarak dürüstçe işaretlenir |
| KVKK dışa aktarma/silme, saklama temizliği, hız sınırları | Tamam | test_privacy + E2E dışa aktarma |
| Canlı operasyon (SSE + LISTEN/NOTIFY, yoklama yedeği) | Tamam | test_live_stream + E2E |
| Prometheus metrikleri, katı hazırlık kontrolü, runbook | Tamam | test_observability; runbook alarm eşikleri öneri düzeyinde |
| Kullanım ölçümü, deneme bitişi (manuel faturalama) | Tamam | test_usage_metering; ödeme sağlayıcısı **yok** (ADR-0009) |
| Türkçe PDF (DejaVu Sans) | Tamam | pypdf metin çıkarma testi (yazı tipi dizini gerekli) |
| Raporlar, bildirimler/kurallar/webhook'lar, API anahtarı iptali, araç ataması, platform yönetimi ekranları | Tamam | Frontend build + E2E (rapor indirme, kural, iptal, atama) |
| MQTT / Kafka / S3 toplu alım adaptörleri | **Kapsam dışı** | Spesifikasyon gerektirmiyor; REST + CSV alımı tam. `DataSource.kind` bu türleri kabul eder; tüketici eklemek broker altyapısı ve sözleşme testleri gerektirir |
| Cihaz, kamera ve filo grupları için ekran | Tamam | Filolar ve Cihazlar/Kameralar ekranları; cihaz/kamera güncelleme uçları eklendi (test_fleet), E2E filo akışı |
| Harita görünümü | Tamam | MapLibre GL + OpenStreetMap (anahtarsız): harita sayfası, canlı operasyon, sefer güzergâhı, olay konumu; listeler erişilebilir alternatif olarak korunur |
| Zararlı yazılım taraması, WAF, ECS otomatik ölçekleme | **Yapılmadı** | THREAT_MODEL kabul edilen riskler |
| JWT çoklu anahtar rotasyonu | **Yapılmadı** | Tek imzalama anahtarı; değişimde kullanıcılar refresh ile yeni token alır |
| AI yardımı | **Yapılmadı (bilinçli)** | ADR-0008 |

## Kullanıcının yapması gerekenler (kimlik bilgisi/karar gerektiren)

1. Ücretsiz hobi dağıtımı için sağlayıcı hesapları ve kimlik doğrulama:
   Render, Neon, Upstash, Backblaze B2 ve Brevo (Vercel CLI bu makinede giriş
   yapmış durumda). Adımlar: docs/operations/hobby-deployment.md.
2. AWS: Terraform durum bucket'ı + kilit tablosu, Terraform rolü, ACM sertifikası,
   alan adı, SMTP sağlayıcısı; ardından staging `terraform apply` ve secret
   değerlerinin yazılması (docs/operations/deployment.md).
3. Hukuk: saklama süreleri, KVKK aydınlatma metni, veri işleme sözleşmeleri, AWS
   bölgesi (eu-central-1 varsayıldı) teyidi.
4. Staging'de DAST/sızma testi, yedekten geri yükleme tatbikatı.

## Güvenlik notları (bilinçli kararlar)

- Refresh token yeniden kullanımında aile iptali; yalnızca yanıtı kaybolmuş, halefi
  kullanılmamış, aynı cihazdan gelen döndürme 10 sn içinde yeniden denenebilir.
- Tüm kiracı tabloları FORCE RLS (istisnalar testte gerekçeli).
- Simülatör verisi her zaman `data_origin=synthetic`.

## NEXT AGENT PROMPT INPUT

VISiOnRoute: Türkçe ulaşım güvenliği SaaS'ı. Modüler monolit
`src/visionroute/{domain,application,infrastructure,api,worker,scheduler,cli}`
(import-linter sınırları) + `apps/web` (Next.js 15.5, strict TS, Zod) +
`infra/terraform` + `infra/docker`.

**Durum**: 253 backend testi + 1 atlanan (S3 sözleşme ve Türkçe PDF testleri ortam
değişkenleriyle), 15 Vitest, 21 Playwright akışı; ruff/mypy strict/bandit/
pip-audit/pnpm audit temiz; 17 Alembic revizyonu up→down→up ve `alembic check`;
Docker imajları ve compose yığını doğrulandı; Terraform validate başarılı.
Harita, filo/cihaz/kamera ekranları, sefer ayrıntısı, coğrafi alan oluşturma,
sürücü risk skoru ve "sunucu uyanıyor" deneyimi eklendi.

**Yerel**: PostgreSQL 17+PostGIS :5433 (`make db-up`), Redis, isteğe bağlı MinIO
(`VISIONROUTE_TEST_S3_ENDPOINT`), DejaVu yazı tipi dizini
(`VISIONROUTE_TEST_PDF_FONT_DIR`). `poetry run pytest`, `make e2e`.

**Önerilen sıra**: hobi dağıtımı (sağlayıcı girişleri) → pilot müşteriyle
anonimleştirme ve saklama kararları → AWS staging. Kurallar:
AGENTS.md (Türkçe müşteri metni, migration zorunlu, testleri zayıflatma, sahte
veri/entegrasyon yok).
