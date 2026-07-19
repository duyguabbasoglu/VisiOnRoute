# Sürüm Hazırlık Durumu / Release Readiness

Son değerlendirme: 2026-07-17 (M12). **Karar: READY FOR STAGING.**

`READY FOR CONTROLLED PRODUCTION` **verilmedi** çünkü: gerçek AWS ortamında
hiç dağıtım yapılmadı, Docker imajları derlenmedi, Playwright E2E paketi ve
KVKK silme/dışa aktarma uçları eksik (docs/HANDOVER.md).

✅ = kanıtla doğrulandı · ⚠️ = kısmi · ❌ = yapılmadı

## Ürün kabul kriterleri

| Kriter | Durum | Kanıt |
|--------|-------|-------|
| Kiracı kaydı/tedariki | ✅ | `POST /auth/register` + test_auth_flow; tarayıcıda canlı doğrulama |
| Güvenli admin bootstrap + giriş | ✅ | `visionroute admin bootstrap` CLI canlı test; test_saas platform admin girişi |
| Kullanıcı davetleri | ✅ | test_rbac_and_tenancy (davet→kabul→rol); e-posta gönderimi yerine token dönüşü (HANDOVER) |
| API + UI seviyesinde RBAC | ✅ | 28 izin/10 rol; analist 403 testleri; UI rol koşullu (Ayarlar) |
| Araç/sürücü/cihaz/veri kaynağı yapılandırma | ✅ | test_fleet, test_ingestion; panel ekranları canlı doğrulandı |
| Sözleşmeye uygun telemetri gönderimi | ✅ | Simülatör → public API canlı akış (M4) |
| Üretim ingest hattından veri akışı | ✅ | ingest→karantina/dedup→outbox→worker testleri |
| Gerçek kurallarla güvenlik olayı üretimi | ✅ | Deterministik motor v2; test_safety_engine; canlı tarayıcı doğrulaması |
| Canlı operasyon + olay inceleme ekranları | ✅ | /panel/canli (10 sn poll), /panel/olaylar/[id] canlı doğrulandı |
| Erişim kontrollü kanıt | ⚠️ | Telemetri kanıtı izinli uçta; medya (S3 imzalı URL) adaptörü eksik |
| Olay inceleme/çözümleme akışı | ✅ | Onay/red/belirsiz + denetim kaydı; UI'dan canlı doğrulandı |
| Koçluk ataması | ❌ | HANDOVER — resolution alanı var, akış yok |
| Rapor üretimi ve indirme | ✅ | CSV (metodolojili) + yönetici PDF testleri |
| Bildirim testi ve teslimi | ✅ | Kural→uygulama içi bildirim; imzalı webhook canlı yerel alıcıya teslim testi |
| Abonelik limiti zorlaması | ✅ | 10 araç / 5 kullanıcı sınırı 409 testleri; plan yükseltme testi |
| Kritik işlemlerde denetim kaydı | ✅ | Append-only + DB trigger testi; tüm kritik uçlarda record_audit |
| Türkçe UX bütünlüğü | ✅ | Tüm UI/hata/rapor metinleri Türkçe; tarayıcı ekran görüntüleriyle doğrulandı |

## Mühendislik kabul kriterleri

| Kriter | Durum | Kanıt |
|--------|-------|-------|
| Temiz kurulum | ✅ | `make bootstrap` (poetry install + pnpm install) bu oturumda sıfırdan |
| Yerel başlatma | ✅ | API + web + worker canlı koştu (tarayıcı doğrulaması) |
| Migration head'e | ✅ | Boş DB → 8 revizyon; her revizyon up→down→up |
| Birim testleri | ✅ | 114 testin birim bölümü |
| Entegrasyon testleri | ✅ | Gerçek PostgreSQL 17+PostGIS'e karşı |
| E2E testleri | ⚠️ | Playwright yok; kritik akışlar TestClient + canlı tarayıcıyla kapsandı |
| Güvenlik testleri | ✅ | JWT confusion/alg=none, IDOR, RLS, SSRF, SQLi, lockout, replay-korumalı imza |
| Tip kontrolü | ✅ | mypy strict, 97 dosya, 0 hata |
| Lint | ✅ | ruff + import-linter (2 sözleşme) |
| Üretim imajları | ⚠️ | Dockerfile'lar yazıldı; Docker yok, derlenmedi |
| Terraform validate | ⚠️ | CI'da tanımlı; henüz koşmadı |
| Staging dağıtım talimatları | ✅ | docs/operations/deployment.md adım adım |
| Smoke testleri | ✅ | cd.yml /health/ready döngüsü |

## Operasyon kriterleri

| Kriter | Durum |
|--------|-------|
| Log/metrik/izleme | ⚠️ Yapısal JSON log + sağlık uçları + platform sayaçları; Prometheus/OTel exporter yok |
| Alarmlar | ⚠️ Bütçe alarmı Terraform'da; CloudWatch alarm tanımları runbook'ta öneri düzeyinde |
| Yedekleme | ✅ Terraform PITR 14 gün; tatbikat prosedürü yazılı (henüz koşulmadı) |
| DLQ yeniden oynatma | ✅ runbook.md SQL prosedürleri |
| Olay müdahale runbook'u | ✅ runbook.md |
| Anahtar rotasyonu | ✅ runbook.md (JWT/API/webhook/DB) |
| Üretim sırları dışsallaştırılmış | ✅ Secrets Manager + pydantic-settings; depoda sır yok (gitleaks CI) |
| Maliyet kontrolü | ✅ Bütçe kaynağı + ucuz staging profili |
