# ADR-0003: RS256 erişim token'ları, opak refresh token'ları ve API anahtarları

## Durum
Kabul edildi — 2026-07-16; `kid` doğrulaması ve oturum iptal damgası eklendi — 2026-09-14

## Bağlam
API hem tarayıcıdan hem entegrasyonlardan çağrılır. Erişim kontrolü her istekte hızlı
olmalı; çalınan kimlik bilgilerinin etkisi sınırlı kalmalı ve iptal edilebilmelidir.

## Karar
- **Erişim token'ı**: JWT, yalnızca **RS256** (algoritma allowlist'i; `none`/HS256
  karmaşası reddedilir), 15 dk ömür. `iss`, `aud`, `exp`, `nbf`, `iat`, `jti`, `sub`
  zorunlu; başlıktaki `kid` beklenen anahtar kimliğiyle eşleşmezse token reddedilir.
  `iat` saniye altı hassasiyettedir.
- Token taşıyıcı başlıkta (`Authorization: Bearer`) gönderilir, tarayıcıda yalnızca
  bellekte tutulur; durum değiştiren istekler çerezle kimlik doğrulamadığı için CSRF
  token'ı gerekmez.
- Her istekte kullanıcı durumu, üyelik/rol ve `users.sessions_revoked_at` damgası
  veritabanından doğrulanır: çıkarılan üye, düşürülen rol, parola/MFA sıfırlaması
  token ömrünü beklemeden etkili olur.
- **Refresh token**: 256 bit opak değer, yalnızca SHA-256 özeti saklanır, HttpOnly +
  Secure + SameSite=Lax çerezde; her kullanımda döndürülür, yeniden kullanım tespit
  edilirse aile iptal edilir. Tek istisna: yanıtı kaybolan bir döndürme, halefi hiç kullanılmadıysa aynı user-agent'tan en fazla 10 sn içinde yeniden denenebilir (halef iptal edilir, alarm üretilmez). Tarayıcı istemcisi eşzamanlı yenilemeleri tek uçuşta birleştirir.
- **API anahtarı**: `vrk_` önekli opak değer, yalnızca özeti saklanır, kapsamlarla
  (`ingest:write`, `evidence:write`) sınırlıdır, son kullanım zamanı izlenir, iptal edilebilir.
- İmzalama anahtarları ortamdan/secret'tan PEM olarak veya dosya yolundan okunur.

## Sonuçlar
- (+) Algoritma karmaşası ve token sahteciliği kapalı; iptal gecikmesi pratikte sıfır
  (istek başına bir veritabanı sorgusu karşılığında).
- (−) Tek imzalama anahtarı: anahtar değişiminde mevcut erişim token'ları geçersizleşir,
  kullanıcılar refresh ile yeni token alır. Birden çok doğrulama anahtarını (`kid` başına)
  kabul eden rotasyon henüz yok.
