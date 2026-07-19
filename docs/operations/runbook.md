# Operasyon El Kitabı / Runbook

## Sağlık kontrolleri

- `GET /health/live` — süreç ayakta mı (yapılandırma sızdırmaz)
- `GET /health/ready` — veritabanı erişilebilir mi (503 → degraded)
- `GET /api/v1/platform/health` (platform admin) — outbox bekleyen/ölü,
  karantina, webhook DLQ sayaçları

## Sık senaryolar

### Telemetri akmıyor
1. Kaynak sağlığını kontrol edin: Entegrasyonlar ekranı → kabul/red sayaçları.
2. Karantina nedenlerine bakın (`ingest_events.status='quarantined'`,
   `rejection_reason`): `unknown_vehicle` → araç `external_id` eşlemesi eksik;
   `timestamp_*` → cihaz saati bozuk.
3. Worker koşuyor mu? `outbox_pending` sürekli artıyorsa worker ölmüştür.

### Outbox ölü mektuplar (dead_letter)
```sql
SET app.rls_bypass='on';
SELECT id, event_type, last_error FROM outbox_events WHERE status='dead_letter';
-- Kök neden giderildikten sonra yeniden kuyruğa alma:
UPDATE outbox_events SET status='pending', attempts=0, next_attempt_at=now()
WHERE status='dead_letter' AND event_type='...';
```

### Webhook teslim edilemiyor
1. `webhook_deliveries.last_error` alanına bakın.
2. Alıcı imza doğruluyor mu? Şema: `X-VisiOnRoute-Signature: t=<ts>,v1=<hex>`;
   HMAC-SHA256(`{ts}.{gövde}`), 5 dakikadan eski zaman damgasını reddedin.
3. Ölü mektupları yeniden kuyruğa almak için status='pending', attempts=0.

### Hesap kilitlenmesi
Kullanıcı 10 başarısız girişten sonra 15 dk kilitlenir. Acil açma (denetim
kaydı düşerek): `UPDATE users SET locked_until=NULL WHERE email=...` yerine
tercihen süreyi bekleyin; müdahale ederseniz audit_logs'a manuel kayıt ekleyin.

### Anahtar rotasyonu
- **JWT**: yeni çift üretin → `jwt-keys` secret'ını güncelleyin → API'yi
  yeniden dağıtın. `kid` başlığı sürümü taşır; eski access token'lar 15 dk
  içinde doğal olarak ölür.
- **API anahtarları (ingest)**: panelden yeni anahtar üretin, eskini iptal
  edin (`DELETE /integrations/tokens/{id}`), müşteriye yenisini iletin.
- **Webhook secret**: yeni endpoint oluşturup eskisini pasifleştirin.
- **DB parolası**: Secrets Manager'da yeni sürüm + ECS görevlerini döndürün.

## İzleme önerileri (CloudWatch)

- ALB 5xx oranı, hedef sağlıksız sayısı
- `outbox_pending` büyümesi (özel metrik/log filtresi)
- RDS CPU/bağlantı doygunluğu
- ECS görev yeniden başlatma döngüleri
- Bütçe alarmı (aws_budgets_budget, %80 tahmini)

## Olay müdahalesi (özet)

1. Etkiyi sınıflandırın (veri sızıntısı şüphesi → derhal erişim anahtarlarını
   iptal edin, oturumları `sessions.revoked_at` ile kapatın).
2. `audit_logs` değişmezdir — zaman çizelgesini oradan kurun.
3. KVKK kapsamında bildirim gerekiyorsa hukuk ekibini 24 saat içinde bilgilendirin.
4. Kök neden + düzeltme + `docs/PROGRESS.md`'ye olay notu.
