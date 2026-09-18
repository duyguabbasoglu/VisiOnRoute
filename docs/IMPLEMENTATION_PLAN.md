# VisiOnRoute — Uygulama Planı / Implementation Plan

> Durum takibi için `docs/PROGRESS.md`, kararlar için `docs/DECISIONS.md`,
> tamamlanamayan işler için `docs/HANDOVER.md` dosyalarına bakın.

## Ürün özeti

VisiOnRoute, sürücü davranışlarını ve yol koşullarını gerçek zamanlı analiz ederek
riskleri oluşmadan görünür kılan, tamamen Türkçe bir ulaşım güvenliği platformudur.
Platform kazaları önlediğini iddia etmez; hukuki, tıbbi, iş güvenliği, otomotiv veya
insan kararlarının yerine geçmez.

## Mimari strateji

- **Modüler monolit**: tek Python paketi (`src/visionroute/`), katı iç sınırlar
  (import-linter ile doğrulanır). Bağımsız ölçeklenen dağıtım birimleri:
  `api`, `worker`, `scheduler`, `web`.
- **PostgreSQL + PostGIS** tek doğruluk kaynağı. Büyük telemetri tabloları zaman
  bazlı partisyonlanır.
- **Outbox deseni**: domain olayları `outbox_events` tablosuna yazılır; worker
  `FOR UPDATE SKIP LOCKED` ile tüketir (ADR-0002).
- **Deterministik kurallar** güvenlik olaylarının temelidir; LLM hiçbir sayısal
  telemetri sınıflandırması yapmaz.
- **Çok kiracılılık**: istek bağlamı → uygulama yetkilendirmesi → kiracıya bağlı
  repository → PostgreSQL Row-Level Security → çapraz kiracı testleri.

## Kilometre taşları

| # | Kapsam | Durum |
|---|--------|-------|
| M1 | Depo yapısı, araç zinciri, dokümantasyon, CI temeli | devam ediyor |
| M2 | Kimlik & kiracılık: kullanıcılar, organizasyonlar, RBAC, oturumlar, JWT, bootstrap, denetim kaydı | bekliyor |
| M3 | Filo alanı: sürücüler, araçlar, cihazlar, atamalar | bekliyor |
| M4 | Veri alımı: kanonik zarf, REST ingest, idempotency, karantina, simülatör | bekliyor |
| M5 | Seferler & telemetri: yaşam döngüsü, partisyonlu depolama, agregasyon | bekliyor |
| M6 | Güvenlik motoru: deterministik kurallar, şiddet, tekilleştirme, Türkçe açıklamalar | bekliyor |
| M7 | Olay inceleme, yol riski, sürücü risk skoru | bekliyor |
| M8 | Türkçe Next.js ön yüz | bekliyor |
| M9 | Bildirimler, raporlar, analitik | bekliyor |
| M10 | SaaS planları, yetkilendirmeler, platform yönetimi | bekliyor |
| M11 | Terraform AWS altyapısı, CI/CD | bekliyor |
| M12 | Son doğrulama, HANDOVER, mühendislik raporu | bekliyor |

Her kilometre taşı sonunda: format → lint → tip kontrolü → birim testleri →
ilgili entegrasyon testleri → güvenlik kontrolleri → dokümantasyon güncellemesi.

## Ortam kısıtları (bu oturumda tespit edilen gerçekler)

- Docker bu makinede **yok**. `docker-compose.yml` geliştiriciler için sağlanır;
  bu oturumdaki entegrasyon testleri yerel PostgreSQL 17 (+ PostGIS, Homebrew) ile koşar.
- Terraform CLI yerelde yok; `terraform validate` CI'da koşacak şekilde yazılır.
- Gerçek AWS hesabı, SMTP, kamera, telematik sağlayıcı kimlik bilgileri yok —
  adaptörler sözleşme testleriyle doğrulanır, eksik kimlik bilgileri
  `docs/HANDOVER.md`'de listelenir.
