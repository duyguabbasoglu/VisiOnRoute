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
