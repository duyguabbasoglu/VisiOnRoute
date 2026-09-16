# Sürüm Hazırlık Durumu / Release Readiness

Son değerlendirme: 2026-09-16 (UI tamamlama ve hobi dağıtım profili çalışması).

**Karar: READY FOR CONTROLLED PILOT — yerel ve konteyner düzeyinde doğrulandı;
staging dağıtımı kullanıcı kimlik bilgileriyle yapılmalı.**

`READY FOR PRODUCTION` **verilmedi** çünkü: gerçek AWS ortamında `terraform apply`
ve dağıtım yapılmadı, CI GitHub'da hiç koşmadı (uzak depo yok), DAST/sızma testi ve
yedekten geri yükleme tatbikatı yapılmadı, otomatik anonimleştirme ve zararlı
yazılım taraması yok (docs/HANDOVER.md).

✅ = kanıtla doğrulandı · ⚠️ = kısmi · ❌ = yapılmadı

## Ürün kabul kriterleri

| Kriter | Durum | Kanıt |
|--------|-------|-------|
| Kiracı kaydı, e-posta doğrulama, giriş, oturum yenileme | ✅ | test_auth_flow, test_account_security, E2E identity |
| Parola sıfırlama, MFA (TOTP + kurtarma) | ✅ | Entegrasyon + E2E team/identity |
| Kullanıcı davetleri (e-posta ile) | ✅ | test_invitations, E2E davet → analist rolü |
| API + UI seviyesinde RBAC | ✅ | RBAC katalog/seed testi, 403 testleri, E2E rol kısıtlı gezinme |
| Araç/sürücü/atama/veri kaynağı/API anahtarı | ✅ | test_fleet, test_api_token_listing, E2E operasyon |
| Telemetri alımı → güvenlik olayı | ✅ | test_telemetry_pipeline, test_safety_engine, E2E |
| Canlı operasyon (anlık akış + yedek yoklama) | ✅ | test_live_stream, E2E |
| Olay inceleme ve koçluk ataması/tamamlama | ✅ | test_coaching, E2E |
| Erişim kontrollü kanıt medyası | ✅ | test_evidence_media, MinIO sözleşme testi, E2E yükleme |
| Kanıtta otomatik anonimleştirme | ❌ | Kapsam dışı; arayüzde açıkça belirtilir |
| Filo yapısı, cihaz ve kamera ekranları | ✅ | E2E filo akışı (oluşturma, düzenleme, pasifleştirme, yetki sınırı) |
| Harita (MapLibre + OpenStreetMap, anahtarsız) | ✅ | Harita sayfası, sefer güzergâhı, olay konumu; E2E'de canvas boyutu doğrulanır |
| Raporlar (CSV, Türkçe PDF) | ✅ | test_notifications_reports, test_pdf_unicode, E2E indirme |
| Bildirim kuralları ve imzalı webhook'lar | ✅ | test_notifications_reports, E2E kural oluşturma |
| KVKK dışa aktarma/silme ve saklama | ✅ | test_privacy, E2E dışa aktarma |
| Abonelik limitleri, kullanım ölçümü, deneme bitişi | ✅ | test_saas, test_usage_metering, E2E abonelik |
| Kritik işlemlerde denetim kaydı | ✅ | Append-only trigger testi; akış testlerinde denetim kontrolleri |
| Türkçe UX bütünlüğü | ✅ | Tüm UI/hata/e-posta/rapor metinleri Türkçe; E2E Türkçe metinlerle çalışır |

## Mühendislik kabul kriterleri

| Kriter | Durum | Kanıt |
|--------|-------|-------|
| Birim + entegrasyon + güvenlik + sözleşme testleri | ✅ | 253 test + 1 atlanan (gerçek PostgreSQL/PostGIS, MinIO) |
| Frontend birim testleri | ✅ | Vitest 15 |
| Uçtan uca testler | ✅ | Playwright 21 akış (gerçek API + worker + üretim derlemesi); harita, filo, cihaz/kamera ve düşük yetki yolları dâhil |
| Migration'lar | ✅ | 17 revizyon, her biri up→down→up, `alembic check` temiz |
| Tip kontrolü / lint / import sınırları | ✅ | mypy strict, ruff, import-linter 2/2, tsc strict, eslint |
| Güvenlik taramaları | ✅ | bandit, pip-audit ve `pnpm audit --prod` temiz (CI'da engelleyici) |
| Üretim imajları | ✅ | API ve web imajları derlendi; compose duman testi |
| Terraform | ⚠️ | fmt + validate ✅; plan/apply ❌ (kimlik bilgisi yok) |
| CI/CD | ⚠️ | İş akışları yazıldı ve adımlar yerelde çalıştırıldı; GitHub'da koşmadı |
| Staging dağıtımı | ❌ | Kullanıcı eylemi (docs/operations/deployment.md) |

## Operasyon kriterleri

| Kriter | Durum |
|--------|-------|
| Yapısal log + redaksiyon | ✅ |
| Metrikler ve hazırlık kontrolü | ✅ Prometheus `/metrics` (token), migration başı kontrolü |
| Alarmlar | ⚠️ Eşikler runbook'ta; CloudWatch/Prometheus alarm kaynakları tanımlı değil |
| Yedekleme | ⚠️ RDS PITR 14 gün Terraform'da; geri yükleme tatbikatı yapılmadı |
| DLQ ve olay müdahale runbook'u | ✅ docs/operations/runbook.md |
| Anahtar rotasyonu | ✅ docs/operations/key-rotation.md (JWT tek anahtar sınırıyla) |
| Sırların dışsallaştırılması | ✅ Secrets Manager JSON anahtarları; depoda sır yok |
| Maliyet kontrolü | ✅ Bütçe alarmı; sıfır maliyetli yerel demo profili |
