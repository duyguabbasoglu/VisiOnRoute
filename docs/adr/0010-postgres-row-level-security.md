# ADR-0010: PostgreSQL satır düzeyi güvenliği (RLS) ile kiracı yalıtımı

## Durum
Kabul edildi — 2026-07-16; kapsam testi eklendi — 2026-09-14

## Bağlam
Tek veritabanında çok kiracılı veri tutulur. Uygulama katmanındaki bir filtre hatası
(eksik `WHERE organization_id`) başka kiracının verisini sızdırmamalıdır.

## Karar
- Kiracıya bağlı her tabloda `ENABLE` + `FORCE ROW LEVEL SECURITY` ve politika:
  `app.rls_bypass = 'on'` veya `organization_id = app.tenant_id`.
- İşlem başına bağlam `set_config(..., true)` ile (yalnızca o işlem için) ayarlanır
  (`visionroute.infrastructure.db.tenancy`):
  - `set_tenant` — istek yolları (`TenantSession`),
  - `set_rls_bypass` — kimlik doğrulama, platform yönetimi, worker ve scheduler.
- Bypass kullanan kod (worker, KVKK işlemcisi, saklama temizliği, kullanım ölçümü)
  sorgularında `organization_id` filtresini açıkça uygular.
- İstisnalar gerekçeleriyle sınırlıdır: `audit_logs` (anonim/platform olayları),
  `idempotency_keys` ve `sessions` (kiracı bilinmeden çözümlenir). Bu tablolara
  erişen kod kiracı filtresi uygular.
- `tests/security/test_rls_coverage.py`, `organization_id` sütunu olan her tablonun
  FORCE RLS ve politika taşıdığını (istisnalar hariç) doğrular; yeni tabloda RLS
  unutulursa test kırılır.

## Sonuçlar
- (+) Uygulama hatası tek başına çapraz kiracı sızıntısı üretmez.
- (−) Bypass oturumları güçlüdür; yalnızca güvenilir süreçlerde ve açık kiracı
  filtresiyle kullanılmalıdır. Migration'larda veri doldurma adımları bypass'ı
  açıkça etkinleştirmelidir.
