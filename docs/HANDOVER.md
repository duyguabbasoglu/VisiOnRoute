# Devir Kaydı / Handover Log

Son güncelleme: 2026-07-17 (M12 kapanışı). Bu belge tamamlanamayan işleri,
nedenlerini ve tamamlanma kriterlerini açıkça kaydeder.

## Ortam kısıtlarından doğan kalıcı notlar

- **Docker bu makinede yok**: `docker-compose.yml` ve Dockerfile'lar yazıldı
  ancak yerelde derlenmedi/doğrulanmadı. Entegrasyon testleri Homebrew
  PostgreSQL 17 + PostGIS 3.6.4 (port 5433) ile koşuyor ve geçiyor.
  *Tamamlanma kriteri*: Docker'lı bir makinede `docker compose up` + imaj
  derlemeleri + compose profillerinin doğrulanması.
- **Terraform CLI yerelde yok**: HCL yazıldı; `terraform validate` ci.yml'de
  tanımlı ama henüz hiç koşmadı (depo GitHub'a itilmedi).
  *Tamamlanma kriteri*: CI'da terraform job'ının yeşil olması; ardından
  staging'e gerçek `terraform apply`.
- **Gerçek AWS hesabı yok**: canlı dağıtım, RDS PostGIS uzantısı, Secrets
  Manager doldurma, OIDC rolü, ACM sertifikası uygulanamadı. Prosedürlerin
  tamamı `docs/operations/deployment.md`'de adım adım mevcut.

## Eksik / kısmi kalan işler (spesifikasyona göre)

| Konu | Durum | Neden | Önerilen sonraki adım |
|------|-------|-------|----------------------|
| MQTT / Kafka / S3 batch alım adaptörleri | Yapılmadı | REST + CSV yolları tam; broker altyapısı yerelde yok | `DataSource.kind` alanı hazır; worker'a tüketici ekleyin |
| E-posta gönderimi (davet/rapor) | Yapılmadı | SMTP kimlik bilgisi yok; davetler token'ı API yanıtında döndürüyor (bilinçli, test edilebilir yol) | Mailpit ile adaptör + outbox handler |
| MFA/TOTP, parola sıfırlama, e-posta doğrulama | Yapılmadı | Alan modeli hazır (`mfa_totp_secret_enc`, `email_verified_at`); alan şifreleme anahtarı yapılandırması gerekiyordu | Fernet alan şifrelemesi + TOTP uçları |
| Video kanıt depolama (S3 imzalı URL, bulanıklaştırma) | Kısmi | `event_evidence.storage_key` + Terraform bucket hazır; MinIO yerelde kurulamadı (Docker yok) | boto3 adaptörü + kısa ömürlü imzalı URL ucu + erişim logu |
| Koçluk iş akışı | Yapılmadı | Kapsam/zaman dengesi; inceleme `resolution=kocluk_atandi` alanı var | coaching_actions tablosu + CRUD + rapor |
| Stripe adaptörü | Yapılmadı | Kimlik bilgisi yok; manuel fatura modu varsayılan (ADR-0009) | BillingProvider protokolü üzerinden ekleyin |
| WebSocket/SSE canlı güncelleme | Yapılmadı | Canlı harita 10 sn poll ile çalışıyor | SSE ucu + frontend aboneliği |
| Playwright E2E | Yapılmadı | Zaman; kritik akışlar TestClient entegrasyon testleriyle + canlı tarayıcı doğrulamasıyla kapsandı | 13 akışlık E2E paketi (spec 20.4) |
| PDF'te tam Türkçe glif | Kısmi | fpdf2 çekirdek fontu; Türkçe karakterler ASCII'ye katlanıyor | DejaVuSans.ttf gömün |
| Webhook secret'ının KMS/alan şifrelemesi | Kısmi | İmzalama için düz erişim gerekli; at-rest koruma DB şifrelemesine dayanıyor | Fernet alan şifrelemesi (anahtar Secrets Manager'dan) |
| Prometheus/OTel metrikleri | Kısmi | Yapısal JSON log + sağlık uçları + platform sağlık sayaçları var; metrik exporter yok | `prometheus-fastapi-instrumentator` + OTel collector |
| Kullanım ölçümü (usage_records doldurma) | Kısmi | Tablo + RLS hazır | scheduler'a günlük snapshot job'ı |
| Veri silme/dışa aktarma (KVKK) uçları | Yapılmadı | retention alanları ve plan bazlı retention_days hazır | deletion_jobs + export uçları |
| Bilinen uyarılar | Açık | fastapi ORJSONResponse deprecation, starlette httpx uyarısı (testlerde görünür, davranış etkisi yok) | FastAPI yeni sürüme geçişte temizlenir |

## Güvenlik notları (bilinçli kararlar)

- Refresh token rotasyonunda aile iptali **commit-before-raise** ile kalıcı
  (rollback yutmasın diye) — `identity/service.py` yorumlarında gerekçe.
- Simülatör verisi her zaman `data_origin=synthetic`; üretim benzeri URL'lere
  karşı çalışmayı reddeder.
- Bandit B311 (random) yalnızca simülatör için global skip'te — gerekçe
  pyproject'te.

## NEXT AGENT PROMPT INPUT

VISiOnRoute: Türkçe ulaşım güvenliği SaaS'ı. Modüler monolit:
`src/visionroute/{domain,application,infrastructure,api,worker,scheduler,cli}`
(sınırlar import-linter ile zorlanır; domain framework-içermez) + `apps/web`
(Next.js 15, strict TS, Türkçe UI) + `infra/terraform` (staging/production).

**Çalışır durum**: 114 test (birim+entegrasyon+güvenlik+contract) yeşil;
ruff/mypy strict/bandit temiz; 8 Alembic migration'ı boş DB'den head'e
up→down→up doğrulanmış. Uçtan uca kanıtlanmış akış: kayıt → filo → veri
kaynağı → API anahtarı → simülatör telemetrisi → outbox worker → sefer +
partisyonlu telemetri → deterministik güvenlik olayı (Türkçe açıklamalı) →
inceleme → bildirim + imzalı webhook → CSV/PDF rapor → analitik. RLS tüm
kiracı tablolarında FORCE modda; auth/worker `app.rls_bypass`, istek yolları
`app.tenant_id` kullanır.

**Yerel ortam**: Docker YOK. `make db-up` Homebrew PostgreSQL 17+PostGIS'i
5433'te başlatır (LC_ALL=C şart). Testler `visionroute_test` DB'sini kendisi
kurar: `poetry run pytest`. Python 3.13 (Poetry otomatik seçer). Frontend:
`pnpm --dir apps/web dev --port 3001` (3000'de başka süreç var olabilir);
API CORS'una 3001 eklenmeli (bkz. VISIONROUTE_CORS_ORIGINS).

**İlk yapılacaklar**: (1) GitHub'a push → CI'ın terraform validate dahil
yeşil olduğunu görün; (2) yukarıdaki eksikler tablosundan önceliklendirin —
önerilen sıra: e-posta adaptörü → KVKK silme/dışa aktarma → koçluk →
Playwright E2E → S3 kanıt adaptörü → MFA. Kurallar: AGENTS.md (Türkçe müşteri
metni, migration zorunlu, testleri zayıflatma, sahte veri yok).
