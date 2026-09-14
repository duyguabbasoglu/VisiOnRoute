# Tehdit Modeli / Threat Model

Kapsam: VISiOnRoute API, web uygulaması, worker, scheduler, veri alım hattı, nesne
depolama, e-posta, canlı akış, AWS altyapısı. Yöntem: STRIDE + veri akışı bazlı.
Yaşayan bir belgedir; her yeni yüzeyde güncellenir. **Yalnızca kodda veya altyapıda
gerçekten bulunan kontroller "kontrol" olarak listelenir**; eksikler "kabul edilen
riskler" bölümündedir.

Son gözden geçirme: 2026-09-14.

## Varlıklar (koruma öncelik sırasıyla)

1. Kanıt medyası (görüntü/video) ve konum geçmişi — kişisel veri, KVKK kapsamı
2. Kiracı verileri (olaylar, sürücü profilleri, telemetri, koçluk notları)
3. Kimlik bilgileri: parolalar, refresh token'lar, API anahtarları, JWT imzalama
   anahtarı, alan şifreleme anahtarları, TOTP sırları, tek kullanımlık bağlantılar
4. Platform bütünlüğü (kural sürümleri, denetim kayıtları, abonelik durumu)

## Tehditler ve kontroller

| Tehdit | Vektör | Kontroller (uygulanmış) |
|--------|--------|------------------------|
| Çapraz kiracı veri erişimi | IDOR, eksik filtre | Uygulama katmanında kiracı filtresi + FORCE RLS; `test_rls_coverage` tüm kiracı tablolarını denetler; çapraz kiracı API/E2E testleri (olay, kanıt, KVKK talebi, kullanım) |
| Çalınan erişim token'ı | XSS, cihaz hırsızlığı | Token yalnızca bellekte; 15 dk ömür; her istekte kullanıcı/üyelik/rol ve oturum iptal damgası DB'den doğrulanır |
| Çalınan refresh token | Çerez hırsızlığı | HttpOnly + Secure + SameSite=Lax çerez; rotasyon + yeniden kullanımda aile iptali; yalnızca SHA-256 özeti saklanır |
| CSRF | Çerez tabanlı oturum | Durum değiştiren uçlar `Authorization: Bearer` ister (tarayıcı otomatik eklemez); refresh çerezi SameSite=Lax. Ayrı CSRF token'ı yoktur (gerekmez) |
| JWT sahteciliği | `alg` manipülasyonu, yabancı anahtar | Yalnızca RS256 allowlist; `iss/aud/exp/nbf/iat/jti/sub` zorunlu; `kid` eşleşmesi zorunlu |
| Kaba kuvvet / hesap numaralandırma | Giriş, parola sıfırlama | Kayan pencere hız sınırı (IP+e-posta ve IP), hesap kilitleme, TOTP MFA ve org MFA politikası, bilinmeyen hesapta sahte Argon2 doğrulaması, sıfırlama yanıtları hesabın varlığını ele vermez |
| Tek kullanımlık bağlantı sızıntısı | Proxy/erişim logları, API yanıtı | Davet/sıfırlama/doğrulama token'ları API yanıtında dönmez; e-postada URL fragmanında (`#token=`, sunucuya gitmez); outbox'ta şifreli, gönderimden sonra silinir |
| API anahtarı sızıntısı/kötüye kullanımı | Depo sızıntısı, log | Yalnızca özet saklanır; kapsam (`ingest:write`, `evidence:write`) ve kiracıya bağlı; bilinmeyen kapsam reddedilir; iptal; hız sınırı; gitleaks CI |
| Kanıt medyasının ifşası | Açık bucket, uzun ömürlü URL | Özel bucket (public access block, TLS-only politika, KMS); 5 dk imzalı `attachment` URL'leri; ham medya için ayrı izin; her erişim denetime yazılır, URL yazılmaz; yerel geliştirmede HMAC imzalı, işleme ve anahtara bağlı bağlantılar |
| Kötü amaçlı/yanlış dosya yükleme | Medya yükleme | Tür allowlist'i (JPEG/PNG/MP4), bildirilen boyut imzalı POST koşuluyla zorlanır, `complete` adımında boyut + sihirli bayt kontrolü, uyuşmazlıkta nesne silinir; CSV içe aktarmada boyut sınırı |
| KVKK taleplerinin kötüye kullanımı | Yetkisiz dışa aktarma/silme | Yönetici talepleri `org.retention.manage`; silmede gerekçe zorunlu, sahip ve kendi hesabı silinemez; self servis yalnızca kendi verisi; dışa aktarma 7 gün, imzalı kısa ömürlü indirme; tüm adımlar denetimde |
| Sahte telemetri | Zayıf ingest kimlik doğrulaması | İstemci başına kapsamlı API anahtarı, şema/zaman damgası/koordinat doğrulaması, idempotency, karantina, hız sınırı |
| Webhook sahteciliği | İmzasız çağrı | HMAC-SHA256 imza (`t=<ts>,v1=<hex>`), zaman damgası imzaya dahil; alıcı 5 dk'dan eski damgayı reddetmeli. Sır alan şifrelemesiyle saklanır |
| SSRF | Webhook URL'leri | Şema/host doğrulaması, özel/yerel IP blokları ve DNS çözümlemesi sonrası kontrol (`urlguard`) |
| SQL enjeksiyonu | Girdi | Parametrik sorgular (SQLAlchemy), Pydantic doğrulaması, DDL için `format()` ile tırnaklama |
| CSV formül enjeksiyonu | Rapor dışa aktarma | Kiracı kontrollü metin `'` ile öneklenir |
| XSS | Kullanıcı içeriği | React çıktı kodlaması, `dangerouslySetInnerHTML` yok; API yanıtlarında `default-src 'none'` CSP; e-posta HTML'i kaçışlı |
| DoS | Büyük gövde, uzun akışlar | ASGI gövde boyutu sınırı (chunked dahil), hız sınırları, canlı akış boşta DB bağlantısı tutmaz ve en fazla 600 sn sürer, sorgu sınırları |
| Canlı akışta yetki kalıntısı | Açık SSE bağlantısı | Akış 60 sn'de bir token ve üyelik durumunu yeniden doğrular, iptalde sonlanır; bildirim yükü yalnızca organizasyon kimliği |
| İstemci IP sahteciliği | `X-Forwarded-For` | Uvicorn yalnızca `FORWARDED_ALLOW_IPS` içindeki kaynaklardan başlığa güvenir; ECS'te görevlere yalnızca ALB güvenlik grubu erişir |
| Metrik ucunun ifşası | `/metrics` | Token tanımlı değilse 404; Bearer sabit zamanlı karşılaştırma; ALB'ye yönlendirilmez; etiketlerde kiracı/kullanıcı kimliği yok |
| Hassas alanların at-rest ifşası | DB/yedek sızıntısı | Fernet alan şifrelemesi (webhook sırları, TOTP sırları, e-posta outbox sırları, ehliyet no), sürümlü anahtar halkası ve yeniden şifreleme komutu; RDS/S3 KMS |
| Log sızıntısı | PII/secret loglama | structlog redaksiyon işlemcisi (hassas anahtar adları), token/URL loglanmaz, erişim logunda sorgu dizesi yok |
| Yetki yükseltme | Rol kontrolü eksikliği | Merkezî izin kataloğu (DB seed'iyle eşleşmesi testli), API'de zorlanır; UI yalnızca yansıtır |
| Denetim izinin değiştirilmesi | İçeriden kötüye kullanım | `audit_logs` append-only (DB trigger UPDATE/DELETE reddeder) |
| Bağımlılık ele geçirme | Tedarik zinciri | Kilit dosyaları, SHA ile sabitlenmiş CI eylemleri, sürümü sabit tarayıcılar (Syft/Grype), pip-audit, doğrulanmış imaj etiketleri |
| Bulut IAM aşırı yetki | Yanlış yapılandırma | Görev rolleri ayrı (web görev rolü yok), API/worker yalnızca kanıt bucket'ı; dar kapsamlı OIDC dağıtım rolü |

## Kabul edilen riskler / bilinen eksikler

- **Zararlı yazılım taraması yok**: yüklenen medya tür/boyut/sihirli bayt ile
  doğrulanır ancak antivirüs taramasından geçmez; medya yalnızca indirme olarak sunulur.
- **Otomatik yüz/plaka anonimleştirme yok**: ham medya `not_processed` olarak
  işaretlenir ve ayrı izinle sınırlıdır.
- **WAF ve otomatik ölçekleme tanımlı değil**: DoS koruması uygulama hız sınırları ve
  ALB ile sınırlı; üretimden önce AWS WAF ve ECS autoscaling değerlendirilmeli.
- **Webhook replay koruması alıcıya bağlı**: nonce yok; zaman damgası kontrolü alıcı
  tarafında yapılmalıdır.
- **Tek JWT imzalama anahtarı**: çoklu doğrulama anahtarıyla kesintisiz rotasyon yok.
- **Redis aktarım şifrelemesi yok** (tek düğüm ElastiCache); yalnızca VPC içi hız
  sınırlama sayaçları taşır.
- **Silinen nesneler 7 gün sürümlü kalır** (kazara silmeye karşı); KVKK silmesi bu süre
  sonunda tamamlanır.
- **Destek erişimi/impersonation özelliği yoktur**; eklenirse gerekçe, süre sınırı,
  görünür uyarı ve denetim kaydı zorunludur.
- **DAST ve sızma testi yapılmadı**; staging ortamında yapılmalıdır.
