# Operasyon El Kitabı / Runbook

## Sağlık kontrolleri

- `GET /health/live` — süreç ayakta mı (yapılandırma sızdırmaz)
- `GET /health/ready` — kritik: `database` erişilebilir ve `migrations` (veritabanı
  şema sürümü koddaki migration başıyla aynı). Biri başarısızsa 503 → ALB trafiği
  kesmeli. `rate_limiter` yalnızca bilgi amaçlıdır (Redis kesintisinde fail-open).
- `GET /api/v1/platform/health` (platform admin) — outbox bekleyen/ölü,
  karantina, webhook ve e-posta DLQ sayaçları

Dağıtım sırası: **önce** `alembic upgrade head` görevi, **sonra** yeni API/worker
imajı. Yeni imaj `migrations=false` raporluyorsa migration görevi çalışmamıştır.

## Metrikler (Prometheus)

- API: `GET /metrics`, yalnızca `VISIONROUTE_METRICS_TOKEN` tanımlıysa açık;
  `Authorization: Bearer <token>`. Token yoksa uç nokta 404 döner.
- Worker / scheduler: `visionroute worker run --metrics-port 9101 --metrics-host 0.0.0.0`
  (yalnızca iç ağ; güvenlik grubu ile kısıtlayın, ALB'ye bağlamayın).

| Seri | Anlamı |
|---|---|
| `visionroute_http_requests_total{method,route,status}` | İstek sayısı (rota şablonu) |
| `visionroute_http_request_duration_seconds` | Yanıt başlığına kadar süre |
| `visionroute_queue_depth{queue,state}` | outbox / email / webhook / privacy bekleyen ve başarısız; ingest karantina |
| `visionroute_queue_oldest_pending_seconds{queue}` | En eski bekleyen öğenin yaşı |
| `visionroute_live_stream_subscribers`, `visionroute_live_hub_connected` | Açık canlı akışlar, LISTEN bağlantısı |
| `visionroute_worker_items_total{source}` | Worker'ın işlediği öğeler |
| `visionroute_scheduler_ticks_total{result}` | ran / skipped / failed |
| `visionroute_retention_purged_total{category}` | Saklama temizliği |
| `visionroute_usage_snapshot_records_total`, `visionroute_trials_expired_total` | Kullanım ölçümü, deneme bitişleri |

### Önerilen alarmlar

| Koşul | Eşik (başlangıç) | İlk bakılacak yer |
|---|---|---|
| 5xx oranı | 5 dk'da > %2 | API logları (`request_id`), son dağıtım |
| `queue_oldest_pending_seconds{queue="outbox"}` | > 300 sn | Worker görevleri ayakta mı, DB kilitleri |
| `queue_depth{state="failed"}` artışı | 15 dk'da > 0 artış | İlgili tablo `last_error` / `error_code` |
| `queue_depth{queue="ingest",state="quarantined"}` | ani artış | Kaynak eşlemeleri (aşağıda) |
| `scheduler_ticks_total{result="failed"}` | 1 saatte ≥ 2 | Scheduler logları |
| `live_hub_connected == 0` | 5 dk | DB bağlantı limiti / ağ; akışlar yoklamaya düşer |
| `/health/ready` 503 | 2 ardışık | Veritabanı, migration görevi |

## Sık senaryolar

### Telemetri akmıyor
1. Kaynak sağlığını kontrol edin: Entegrasyonlar ekranı → kabul/red sayaçları.
2. Karantina nedenlerine bakın (`ingest_events.status='quarantined'`,
   `rejection_reason`): `unknown_vehicle` → araç `external_id` eşlemesi eksik;
   `timestamp_*` → cihaz saati bozuk.
3. Worker koşuyor mu? `queue_oldest_pending_seconds{queue="outbox"}` sürekli
   artıyorsa worker ölmüştür.

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

### E-posta gitmiyor
1. `email_messages` durumları: `dead_letter` → `last_error` (5xx kalıcı; 4xx/ağ
   geçici olarak yeniden denenir).
2. SMTP kimlik bilgisi/sunucu değiştiyse secret'ı güncelleyip worker'ı döndürün;
   ardından `UPDATE email_messages SET status='pending', attempts=0,
   next_attempt_at=now() WHERE status='dead_letter' AND ...`.
   Tek kullanımlık bağlantı içeren iletilerin token'ı süresi dolmuş olabilir;
   kullanıcıdan işlemi (ör. parola sıfırlama) yeniden başlatmasını isteyin.

### KVKK talebi başarısız (`privacy_requests.status='failed'`)
1. `error_code`: `SUBJECT_NOT_FOUND` (kişi silinmiş), `OWNER_CANNOT_BE_ERASED`
   (sahiplik devri gerekir) kalıcıdır; `StorageError` / veritabanı hataları
   5 denemeden sonra `failed` olur.
2. Depo erişimini düzelttikten sonra yönetici panelden yeni talep oluşturur
   (başarısız talep yeniden açılmaz; denetim izi korunur).
3. Yasal süre: talepler en geç 30 gün içinde sonuçlandırılmalıdır.

### Kanıt medyası / nesne deposu
- Yükleme `complete` adımında reddediliyorsa (`evidence.upload_rejected` denetim
  kaydı) istemci yanlış tür/boyut gönderiyordur; nesne otomatik silinir.
- S3 erişim hatalarında API 503 `SERVICE_NOT_CONFIGURED` döner; görev rolünün
  bucket ve KMS izinlerini kontrol edin. İmzalı URL'ler 5 dk geçerlidir.
- Otomatik yüz/plaka anonimleştirme yoktur; ham medya yalnızca
  `events.evidence.raw_media` yetkisiyle açılır ve her erişim denetime yazılır.

### Saklama ve kullanım ölçümü
- Scheduler saatlik bakımda saklama temizliği, dün+bugün kullanım anlık görüntüsü
  ve deneme bitişlerini çalıştırır; tek replika kilidi (`pg_try_advisory_xact_lock`).
- Deneme süresi dolan organizasyon `past_due` olur: yeni araç/kullanıcı eklenemez,
  veri alımı sürer. Manuel faturadan sonra platform yöneticisi plan atayarak
  (`POST /api/v1/platform/organizations/{id}/plan`) aboneliği `active` yapar.

### Canlı operasyon akışı
- Akışlar PostgreSQL `LISTEN visionroute_live` bağlantısına dayanır. Bağlantı
  koparsa hub geri çekilmeli yeniden bağlanır; tarayıcılar 10 sn yoklamaya düşer.
- Akış başına veritabanı bağlantısı tutulmaz; bağlantı havuzu doygunluğunda
  önce RDS bağlantı sayısına bakın.

### Hesap kilitlenmesi
Kullanıcı 10 başarısız girişten sonra 15 dk kilitlenir. Acil açma (denetim
kaydı düşerek): `UPDATE users SET locked_until=NULL WHERE email=...` yerine
tercihen süreyi bekleyin; müdahale ederseniz audit_logs'a manuel kayıt ekleyin.

### Anahtar rotasyonu
- **Alan şifreleme / JWT / webhook**: `docs/operations/key-rotation.md`.
- **API anahtarları (ingest)**: panelden yeni anahtar üretin, eskini iptal
  edin (`DELETE /integrations/tokens/{id}`), müşteriye yenisini iletin.
- **Metrik token'ı**: yeni değeri secret'a yazın, scraper yapılandırmasını
  güncelleyin, API görevlerini döndürün.
- **DB parolası**: Secrets Manager'da yeni sürüm + ECS görevlerini döndürün.

## İzleme (CloudWatch tarafı)

- ALB 5xx oranı, hedef sağlıksız sayısı
- RDS CPU/bağlantı doygunluğu, depolama
- ECS görev yeniden başlatma döngüleri
- Bütçe alarmı (aws_budgets_budget, %80 tahmini)

## Olay müdahalesi (özet)

1. Etkiyi sınıflandırın (veri sızıntısı şüphesi → derhal erişim anahtarlarını
   iptal edin, oturumları `sessions.revoked_at` ile kapatın).
2. `audit_logs` değişmezdir — zaman çizelgesini oradan kurun.
3. KVKK kapsamında kişisel veri ihlali: veri sorumlusu Kurul'a en geç 72 saat
   içinde bildirim yapmakla yükümlüdür; hukuk ekibini derhal bilgilendirin.
4. Kök neden + düzeltme + `docs/PROGRESS.md`'ye olay notu.
