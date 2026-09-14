# Sıfır maliyetli demo profili

Amaç: VISiOnRoute'u bulut hesabı veya ücretli kaynak olmadan uçtan uca göstermek.
Profil tamamen yerelde, Docker Compose ile çalışır. **Tüm demo telemetrisi
sentetiktir** (`data_origin=synthetic`, `environment=demo`) ve gerçek kanıt olarak
kullanılamaz.

Doğrulama (2026-09-14, Apple Silicon + Docker Desktop): `migrate` başarıyla
bitti, `/health/ready` veritabanı + migration + Redis için `ok` döndü, kayıt 201,
web `/giris` 200, doğrulama e-postası worker tarafından SMTP ile Mailpit'e ulaştı.

## Bileşenler

| Servis | Rol | Varsayılan port |
|---|---|---|
| postgres (PostGIS 17) | Veritabanı | 5433 |
| redis | Hız sınırlama | 6379 |
| minio | S3 uyumlu kanıt/dışa aktarma deposu | 9000 (konsol 9001) |
| mailpit | SMTP yakalayıcı + web arayüzü | 1025 / 8025 |
| migrate | `alembic upgrade head` (tek seferlik) | — |
| api | FastAPI | 8000 |
| worker | outbox, e-posta, webhook, KVKK | — |
| scheduler | saklama, kullanım ölçümü, bakım | — |
| web | Next.js | 3000 |

Portlar doluysa `VR_PG_PORT`, `VR_REDIS_PORT`, `VR_MINIO_PORT`, `VR_MINIO_CONSOLE_PORT`,
`VR_SMTP_PORT`, `VR_MAILPIT_PORT`, `VR_API_PORT`, `VR_WEB_PORT` ile değiştirin; web
imajı API adresini derleme sırasında aldığı için `VR_API_PORT` değiştiğinde
`--build` ile yeniden derleyin.

## Kurulum

```bash
poetry install
poetry run visionroute keys generate --out .dev/keys
poetry run visionroute keys generate-field-key >> .env
docker compose --profile full up -d --build
```

Apple Silicon: resmî PostGIS imajı yalnızca `linux/amd64` yayımlandığı için Docker
Desktop emülasyonuyla çalışır (compose dosyasında `platform: linux/amd64`); ilk
başlatma birkaç dakika sürebilir.

## Demo akışı

1. <http://localhost:3000/kayit> — organizasyon oluşturun.
2. <http://localhost:8025> (Mailpit) — doğrulama e-postasındaki bağlantıyı açın.
3. Panelde **Araçlar** → araç ekleyin (dış kimlik ör. `34ABC123`);
   **Entegrasyonlar** → veri kaynağı (ör. `telematik-1`) ve `Telemetri gönderimi`
   kapsamlı API anahtarı üretin.
4. Sentetik telemetri gönderin (bir sert fren olayı içerir):
   ```bash
   make seed-demo API_KEY=vrk_... SOURCE_KEY=telematik-1 VEHICLE=34ABC123
   ```
5. **Güvenlik Olayları** → olayı inceleyin, koçluk atayın; **Canlı Operasyon**
   anlık bağlantı durumunu gösterir; **Gizlilik (KVKK)** → sürücü verisini dışa
   aktarın; **Abonelik** → deneme süresi ve kullanım.
6. Kapatma: `docker compose --profile full down -v` (verileri siler).

## Sınırlar

- Yerel profil `environment=local` ile çalışır: HTTPS, gerçek SMTP sağlayıcısı ve
  AWS gerekmez; üretim benzeri doğrulamalar (TLS, S3 zorunluluğu) uygulanmaz.
- Otomatik yüz/plaka anonimleştirme, zararlı yazılım taraması ve ödeme sağlayıcısı
  bu profilde de yoktur (docs/HANDOVER.md).
- Bulut üzerinde "ücretsiz" bir dağıtım profili doğrulanmadı: Terraform staging
  yığını (RDS, NAT Gateway, ALB, ElastiCache) ücretlidir; bütçe alarmı ile birlikte
  kullanın (docs/operations/deployment.md).
