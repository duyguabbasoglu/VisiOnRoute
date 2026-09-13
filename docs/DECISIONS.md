# Mimari Kararlar / Architecture Decisions

Ayrıntılı ADR'ler `docs/adr/` altındadır. Bu dosya özet dizindir.

| ADR | Karar | Gerekçe özeti |
|-----|-------|----------------|
| 0001 | Tek Poetry paketi (`src/visionroute/`) içinde modüler monolit; `apps/packages` çoklu-paket düzeni yerine import-linter ile sınır zorlaması | Tek ekip, tek dağıtım hattı; paketleme yükünü azaltır, sınırlar statik analizle korunur |
| 0002 | Worker sistemi: Celery/Dramatiq yerine PostgreSQL outbox + `FOR UPDATE SKIP LOCKED` tüketici | Daha az hareketli parça; outbox zaten zorunlu; Redis broker tek hata noktası olmaktan çıkar; Redis önbellek/hız sınırlama için kalır |
| 0003 | JWT imzalama: RS256 (asimetrik), kısa ömürlü access token + veritabanında hash'lenmiş refresh token, sunucu tarafı iptal | Simetrik anahtar sızıntı riskini azaltır; iptal edilebilirlik zorunlu |
| 0004 | Parola: Argon2id (argon2-cffi) | Modern bellek-sert KDF |
| 0005 | Kimlik ID'leri: UUIDv7 (uuid_extension yok; uygulama tarafında üretim, `uuid6` kütüphanesi yerine stdlib tabanlı üretici) | Sıralanabilir, indeks dostu |
| 0006 | Konum verisi: çekirdek kolonlar `latitude/longitude double precision` + PostGIS `geography` kolonu ve GIST indeksi migration'da `CREATE EXTENSION postgis` ile | PostGIS prod'da zorunlu; çekirdek sorgular PostGIS'siz de çalışır |
| 0007 | Frontend: Next.js (App Router) + TypeScript strict + Tailwind + TanStack Query + Zod + MapLibre GL | Spesifikasyon gereksinimi; MapLibre lisans açısından güvenli |
| 0008 | LLM kullanımı varsayılan **kapalı**; yalnızca şema doğrulamalı, kanıt-temelli, sınırlandırılmış görevler | Spesifikasyon 5.3 |
| 0009 | Faturalama: sağlayıcı soyutlaması + manuel fatura modu varsayılan; Stripe adaptörü yalnızca yapılandırıldığında | Türk kurumsal satış gerçeği; kart verisi saklanmaz |
| 0010 | Kiracı izolasyonu: uygulama katmanı + PostgreSQL RLS (oturum değişkeni `app.tenant_id`) çift katman | Derinlemesine savunma |

## 2026-09 tamamlama geçişi kararları

| Karar | Gerekçe |
|-------|---------|
| import-linter katmanları: `cli` en üstte, `api \| worker \| scheduler` altında | CLI süreçlerin kompozisyon köküdür (worker ve scheduler'ı başlatır). Önceki sözleşme `cli`'yi bu modüllerle kardeş katmana koyduğu için temel hatta zaten KIRIKTI; kural gevşetilmedi, gerçek bağımlılık yönü tanımlandı |
| Her kimlik doğrulamalı istekte üyelik/rol veritabanından yeniden doğrulanır | Access token 15 dk yaşar; üyelikten çıkarılan, rolü düşürülen veya devre dışı bırakılan kullanıcı eski yetkisini token süresi dolana kadar koruyordu. İstek başına tek indeksli sorgu maliyeti kabul edildi |
| Worker her outbox olayını kendi SAVEPOINT'inde işler; webhook teslimatı ayrı işlemde | Tek bir veritabanı hatası tüm partiyi geri alıyor ve `attempts` hiç artmadığı için dead-letter'a ulaşılamıyordu (sonsuz zehirli döngü). Ağ çağrıları outbox kilitlerini tutmamalı |
| Scheduler turu `pg_try_advisory_xact_lock` ile tekilleştirilir | Rolling deploy veya yanlışlıkla çoklu replika çift çalıştırma üretmemeli |
| Güvenlik olayı tekilleştirme: sabit 30 sn saat kovası yerine ±30 sn kayan pencere + araç/tip bazlı advisory lock | Sabit kova 5 sn arayla gelen iki sert freni kova sınırında iki olaya bölüyordu (test ~1/6 oranında kırmızıydı) |
| Kanıt yükü `events.evidence.read` izni ister | `events.read` (ör. analist) kanıtı görmemeli; izin kataloğu bunu zaten ayırıyordu ancak uç nokta zorlamıyordu |
| CSV raporlarında kiracı kontrollü metin formül enjeksiyonuna karşı `'` ile öneklenir | OWASP CSV injection |
| İstek gövdesi boyut sınırı (varsayılan 12 MiB) ASGI katmanında | Uvicorn varsayılan olarak sınır uygulamaz; chunked gövdeler dahil |
| `X-Request-ID` yalnızca `[A-Za-z0-9._:-]{1,64}` ise kabul edilir | İstemci değeri loglara ve yanıta yansıtılıyordu (log enjeksiyonu) |
| Alan şifreleme: `cryptography` Fernet + sürümlü anahtar halkası (`enc1:<kid>:<token>`), anahtarlar yapılandırmadan (Secrets Manager) | Yeni bağımlılık yok; doğrulanmış, kimlik doğrulamalı şifreleme; kesintisiz rotasyon (`visionroute security reencrypt`). KMS envelope çağrısı her şifre çözmede ağ gecikmesi ve maliyet getirirdi; anahtar zaten KMS şifreli Secrets Manager'da tutuluyor |
| Webhook sırrı şifreleme geçişi üç revizyonda: şema ekle → veri doldur → düz metni kaldır | AGENTS.md kural 9 (veri doldurma şemadan ayrı). Veri adımı `app.rls_bypass` açar: FORCE RLS nedeniyle aksi halde 0 satır görüp düz metin sütununu şifrelemeden silecekti. Anahtar yoksa ve satır varsa migration durur |
| Hız sınırlama: Redis sabit pencere (üretim), bellek içi (yalnızca yerel/test); Redis kesintisinde fail-open + log | CLAUDE.md: Redis yalnızca önbellek/hız sınırlama. Kimlik doğrulamanın önbellek kesintisiyle çökmesi kabul edilmez; hesap kilitleme ayrıca korur. Anahtarlar SHA-256 ile hash'lenir (Redis'te e-posta/IP yok) |
| Giriş sınırı iki katmanlı: (IP, e-posta) başına 10/dk + IP başına 100/dk | Tek NAT arkasındaki ofis kullanıcılarını engellemeden kaba kuvveti yavaşlatır |
