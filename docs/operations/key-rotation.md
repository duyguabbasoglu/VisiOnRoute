# Anahtar Rotasyonu / Key Rotation

Bu belge VISiOnRoute'taki tüm kriptografik anahtarların üretim, saklama ve
rotasyon prosedürlerini tanımlar. Üretimde tüm değerler **AWS Secrets
Manager**'da tutulur ve ECS görev tanımına ortam değişkeni olarak enjekte
edilir. Hiçbir anahtar depoya, loglara veya veritabanına yazılmaz.

## 1. Alan şifreleme anahtarları (`VISIONROUTE_FIELD_ENCRYPTION_KEYS`)

Veritabanında saklanması zorunlu sırları korur: webhook imza sırları
(`webhook_endpoints.secret_enc`), MFA TOTP sırları ve e-posta kuyruğundaki
tek kullanımlık bağlantı token'ları.

- Biçim: `enc1:<anahtar_kimliği>:<fernet_token>` (Fernet = AES-128-CBC +
  HMAC-SHA256, `cryptography` kütüphanesi; özel kriptografi yok).
- Yapılandırma: `VISIONROUTE_FIELD_ENCRYPTION_KEYS='{"k1": "<anahtar>"}'`,
  `VISIONROUTE_FIELD_ENCRYPTION_PRIMARY_KEY_ID=k1`.
- Üretim benzeri ortamlar anahtar olmadan **başlamaz**.

### Anahtar üretimi

```bash
poetry run visionroute keys generate-field-key --key-id k2026b
```

### Kesintisiz rotasyon

1. Yeni anahtarı **eski anahtarla birlikte** secret'a ekleyin; birincil
   kimliği henüz değiştirmeyin: `{"k2026a": "...", "k2026b": "..."}`.
   Tüm görevleri yeniden dağıtın (her iki anahtar da çözebilir hale gelir).
2. `VISIONROUTE_FIELD_ENCRYPTION_PRIMARY_KEY_ID=k2026b` yapın ve yeniden
   dağıtın. Yeni yazımlar yeni anahtarla şifrelenir.
3. Mevcut değerleri yeni anahtarla yeniden şifreleyin (idempotent, tekrar
   çalıştırılabilir):
   ```bash
   visionroute security reencrypt
   ```
4. Komut `0 kayıt` raporlayana kadar bekleyin, ardından eski anahtarı
   secret'tan çıkarıp yeniden dağıtın.

**Uyarı**: Bir anahtarı, onunla şifrelenmiş kayıt kalmışken silmek o
kayıtları kalıcı olarak okunamaz yapar (webhook sırrı yeniden üretilmeli,
MFA yeniden kaydedilmelidir). 3. adımı atlamayın.

### Anahtar sızıntısı şüphesi

1. Yukarıdaki rotasyonu hemen uygulayın.
2. Tüm webhook sırlarını müşteriyle birlikte yenileyin
   (`POST /api/v1/webhooks/{id}/rotate-secret`) — sızan anahtar eski sırları
   çözebilir.
3. Olayı `docs/operations/runbook.md` olay müdahalesi adımlarıyla kaydedin.

## 2. JWT imzalama anahtarları (RS256)

- Geliştirme: `poetry run visionroute keys generate --out .dev/keys`.
- Üretim: anahtar çifti dağıtım hattında üretilir ve `jwt-keys` secret'ına
  yazılır (bkz. `deployment.md`).
- Access token ömrü 15 dk'dır; rotasyon sonrası eski token'lar en geç bu süre
  içinde geçersizleşir. Refresh token'lar opak ve veritabanında hash'lidir,
  JWT anahtarından etkilenmez.

Rotasyon: yeni çift üretin → secret'ı güncelleyin → API'yi yeniden dağıtın.
Bu sırada oturumu açık kullanıcılar bir sonraki istekte 401 alır ve
arayüz refresh cookie ile sessizce yeni token alır.

## 3. API anahtarları (makineden makineye veri alımı)

Yalnızca SHA-256 özetleri saklanır. Panelden yeni anahtar üretin, müşteri
cihazlarını güncelleyin, eskisini iptal edin
(`DELETE /api/v1/integrations/tokens/{id}`).

## 4. Webhook imza sırları

`POST /api/v1/webhooks/{id}/rotate-secret` yeni sırrı bir kez gösterir; eski
sır anında geçersizleşir. Alıcıyı güncelledikten sonra test teslimatı
gönderin (`POST /api/v1/webhooks/{id}/test`).

## 5. Veritabanı ve SMTP parolaları

Secrets Manager'da yeni sürüm oluşturun, ECS servislerini yeniden başlatın
(`aws ecs update-service --force-new-deployment`). SMTP sağlayıcısında eski
kimlik bilgisini yeni dağıtım sağlıklı olduktan sonra iptal edin.
