# Yedekleme ve Geri Yükleme / Backup & Restore

## Yedekleme (üretim)

- **RDS otomatik yedekler**: 14 gün saklama, point-in-time recovery (PITR) açık
  (Terraform: `backup_retention_period = 14`).
- **S3 kanıt bucket'ı**: versiyonlama açık; eski sürümler 30 gün sonra silinir.
- **Terraform durumu**: S3 (versiyonlu, şifreli) + DynamoDB kilidi.

## Geri yükleme tatbikatı (staging'de en az yılda iki kez)

1. PITR ile yeni bir örnek oluşturun:
   ```bash
   aws rds restore-db-instance-to-point-in-time \
     --source-db-instance-identifier visionroute-production-... \
     --target-db-instance-identifier visionroute-restore-drill \
     --restore-time 2026-07-17T10:00:00Z \
     --db-subnet-group-name <mevcut> --no-publicly-accessible
   ```
2. Yeni örneğe bağlanıp doğrulayın:
   - `SELECT count(*) FROM organizations;`
   - `SELECT max(occurred_at) FROM safety_events;` (beklenen zaman aralığında mı)
   - `alembic current` head ile eşleşiyor mu
3. Tatbikat sonucunu tarih + süre + doğrulama çıktısıyla bu dosyanın altına
   işleyin; örneği silin.

## Yerel geliştirme yedeği

```bash
/opt/homebrew/opt/postgresql@17/bin/pg_dump -h localhost -p 5433 -U visionroute \
  -Fc visionroute > visionroute-$(date +%Y%m%d).dump
pg_restore -h localhost -p 5433 -U visionroute -d visionroute --clean --if-exists dump
```

## Tatbikat kaydı

| Tarih | Ortam | Süre | Sonuç |
|-------|-------|------|-------|
| — | — | — | Henüz gerçek AWS ortamı yok (bkz. HANDOVER) |
