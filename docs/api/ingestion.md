# Veri Alımı (Ingestion) API

Bu belge, VISiOnRoute'a veri gönderen entegratörler içindir. Tüm alım
uçları makineler arası kimlik doğrulama (API anahtarı) kullanır.

## Kimlik doğrulama

Alım uçları `X-API-Key` başlığıyla kimliği doğrulanır. Anahtar, panelden
**Entegrasyonlar → API İstemcileri** altında oluşturulur ve yalnızca
oluşturma anında bir kez gösterilir (yalnızca SHA-256 özeti saklanır).

Anahtarın `ingest:write` kapsamına sahip olması gerekir.

```
X-API-Key: vrk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Kanonik olay zarfı (sürüm 1.0)

```json
{
  "schema_version": "1.0",
  "source": "telematik-saglayici",
  "event_id": "saglayici-olay-kimligi",
  "event_type": "telemetry.position",
  "occurred_at": "2026-07-16T09:30:00Z",
  "received_at": "2026-07-16T09:30:02Z",
  "vehicle_external_id": "34ABC123",
  "driver_external_id": "surucu-008",
  "payload": { "latitude": 39.92, "longitude": 32.85, "speed_kph": 54.0 },
  "signature": {}
}
```

Zorunlu alanlar: `source`, `event_id`, `event_type`, `occurred_at`,
`vehicle_external_id`. Zaman damgaları saat dilimi içermelidir (UTC önerilir).

Desteklenen `event_type` değerleri: `telemetry.position`, `trip.start`,
`trip.end`, `device.status`, `provider.event`.

### Telemetri yükü (`telemetry.position`)

| Alan | Zorunlu | Aralık |
|------|---------|--------|
| latitude | evet | -90..90 |
| longitude | evet | -180..180 |
| speed_kph | hayır | 0..400 |
| heading_deg | hayır | 0..360 |
| acceleration_ms2 | hayır | -50..50 |
| lateral_acceleration_ms2 | hayır | -50..50 |
| odometer_km | hayır | ≥0 |
| gps_hdop | hayır | 0..100 |
| satellites | hayır | 0..64 |
| data_origin | hayır | Sentetik veride `"synthetic"` |
| environment | hayır | Sentetik veride `"demo"` |

## Olay gönderme

```
POST /api/v1/ingest/events
{
  "source_key": "telematik-1",
  "events": [ { ...zarf... } ]
}
```

Yanıt, her olay için sonucu döner:

```json
{
  "schema_version": "1.0",
  "accepted": 1,
  "duplicates": 0,
  "quarantined": 0,
  "outcomes": [{ "event_id": "...", "status": "accepted" }]
}
```

### Idempotency

Bir olay `(organizasyon, source, event_id)` üçlüsüyle tekilleştirilir.
Aynı olayın yeniden gönderilmesi güvenlidir; `duplicates` sayacı artar,
kopya kayıt oluşmaz.

### Karantina nedenleri

Reddedilen olaylar kaybolmaz; `quarantined` durumuyla saklanır ve
`rejection_reason` taşır:

- `schema_version_unsupported` — desteklenmeyen şema sürümü
- `invalid_payload` — yük doğrulanamadı
- `timestamp_in_future` — olay zamanı gelecekte
- `timestamp_too_old` — canlı akış için çok eski (tarihsel içe aktarma kullanın)
- `unknown_vehicle` — `vehicle_external_id` tanımlı değil
- `coordinates_out_of_range` — konum geçersiz

## CSV toplu içe aktarma

```
POST /api/v1/ingest/import/csv?source_key=telematik-1
Content-Type: multipart/form-data
```

Kolonlar zarf alanlarıyla eşleşir; telemetri alanları `payload.` ön ekiyle
verilir (ör. `payload.latitude`). Dosya boyutu 10 MiB ile sınırlıdır.

## Referans simülatör (yalnızca demo)

```
poetry run visionroute simulate telemetry \
  --api-key <ANAHTAR> --source-key telematik-1 --count 20
```

Simülatör aynı genel sözleşme üzerinden sentetik veri gönderir; her kayıt
`data_origin="synthetic"`, `environment="demo"` taşır ve üretim adreslerine
karşı çalışmayı reddeder.
