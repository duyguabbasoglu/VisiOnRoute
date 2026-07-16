# Tehdit Modeli / Threat Model

Kapsam: VISiOnRoute API, web uygulaması, worker, veri alım hattı, nesne depolama,
AWS altyapısı. Yöntem: STRIDE + veri akışı bazlı. Bu belge yaşayan bir belgedir;
her yeni yüzey eklendiğinde güncellenir.

## Varlıklar (koruma öncelik sırasıyla)

1. Video/görüntü kanıtları ve konum geçmişi (kişisel veri, KVKK kapsamı)
2. Kiracı verileri (olaylar, sürücü profilleri, telemetri)
3. Kimlik bilgileri: parolalar, refresh token'lar, API anahtarları, imzalama anahtarları
4. Platform bütünlüğü (kural/model sürümleri, denetim kayıtları)

## Tehditler ve kontroller

| Tehdit | Vektör | Kontroller |
|--------|--------|------------|
| Çapraz kiracı veri erişimi | IDOR, sorgu hatası | Kiracı-bağlı repository'ler, PostgreSQL RLS, deny-by-default yetkilendirme, çapraz kiracı regresyon testleri |
| Çalınan oturum/token | XSS, cihaz hırsızlığı | HttpOnly+SameSite çerezler, kısa ömürlü access token, refresh rotasyonu + yeniden kullanım tespiti, oturum iptali |
| API anahtarı sızıntısı | Depo sızıntısı, log | Anahtarlar hash'lenerek saklanır, scope + kiracı bağlama, son kullanım izleme, iptal, secret scanning |
| Kanıt medyasının ifşası | Public bucket, uzun ömürlü URL | Private bucket, kısa ömürlü imzalı URL, ayrı ham-medya izni, erişim logu |
| Sahte telemetri | Zayıf ingest auth | Kaynak başına API anahtarı, zaman damgası mantık kontrolü, koordinat doğrulama, hız sınırlama, karantina |
| Webhook sahteciliği | İmzasız çağrı | HMAC imza + zaman damgası + nonce; replay penceresi reddi |
| SSRF | Kullanıcı URL'leri (webhook, RTSP) | URL şema/host doğrulama, özel IP blokları reddi, egress kısıtları |
| SQL enjeksiyonu | Girdi | Parametrik sorgular (SQLAlchemy), girişte Pydantic doğrulama, güvenlik testleri |
| XSS | Kullanıcı içeriği, LLM çıktısı | Çıktı kodlama, CSP, LLM çıktısı asla güvenilir HTML olarak render edilmez |
| CSRF | Çerez tabanlı oturum | SameSite=Lax + CSRF token (durum değiştiren isteklerde) |
| Mass assignment | Geniş modeller | Ayrı istek/yanıt şemaları; ORM modeline doğrudan bind yok |
| Yetki yükseltme | Rol kontrolü eksikliği | Merkezî permission kontrolü, UI'da değil API'de zorlanır, testler |
| Prompt injection | Operatör notları → LLM | LLM'e giden içerik sınırlanır; çıktı şema doğrulamalı; LLM kritik kayıtları değiştiremez |
| Kötü amaçlı dosya yükleme | CSV/medya import | MIME + magic-byte doğrulama, boyut limiti, zararlı yazılım tarama adaptörü, ayrıştırıcı izolasyonu |
| Decompression bomb | Sıkıştırılmış yükler | Boyut/oran limitleri, akış tabanlı ayrıştırma |
| DoS | Yük | Hız sınırlama, istek boyutu limitleri, WAF, autoscaling |
| Bağımlılık ele geçirme | Tedarik zinciri | Sürüm sabitleme, pip-audit/pnpm audit, SBOM, imzalanmış CI eylemleri (SHA pin) |
| Bulut IAM aşırı yetki | Yanlış yapılandırma | Görev başına ayrı IAM rolü, en az yetki, Terraform incelemesi |
| Log sızıntısı | PII/secret loglama | structlog işlemcisiyle redaksiyon, PII-güvenli log politikası |
| İçeriden kötüye kullanım | Destek erişimi | Impersonation yalnızca gerekçe + süre + görünür banner + değişmez denetim kaydı ile |
| JWT algoritma karmaşası | `alg` manipülasyonu | Algoritma allowlist (yalnızca RS256), `kid` doğrulaması |
| Kaba kuvvet | Login | Oran sınırlama, hesap bazlı yavaşlatma, MFA, şüpheli giriş denetimi |

## Kabul edilen riskler (şimdilik)

- Zararlı yazılım tarama adaptörü arayüz olarak mevcut; gerçek tarayıcı (ör. ClamAV)
  dağıtımı altyapı aşamasında yapılandırılmalı.
- DAST taraması CI temel hattında; tam kapsam staging ortamı gerektirir.
