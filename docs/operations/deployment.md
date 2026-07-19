# Dağıtım / Deployment

## Ortamlar

| Ortam | Terraform kökü | Profil |
|-------|----------------|--------|
| staging | `infra/terraform/envs/staging` | Ucuz: t4g.micro, tek AZ, silme koruması kapalı |
| production | `infra/terraform/envs/production` | m7g.large, multi-AZ, silme koruması, onay kapısı |

## İlk kurulum (tek seferlik)

1. **Terraform durumu**: `visionroute-terraform-state` S3 bucket'ı (versiyonlu,
   şifreli) ve `visionroute-terraform-locks` DynamoDB tablosu oluşturun;
   env köklerindeki `backend "s3"` bloklarının yorumunu açın.
2. **GitHub OIDC**: AWS'de GitHub Actions için OIDC sağlayıcısı ve
   `AWS_DEPLOY_ROLE_ARN` rolü oluşturun (uzun ömürlü anahtar YOK).
3. **ACM sertifikası**: alan adınız için `eu-central-1`'de sertifika alın,
   `certificate_arn` değişkenine verin.
4. **JWT anahtarları**: dağıtım hattında üretin ve Terraform'un oluşturduğu
   `jwt-keys` secret'ına yazın:
   ```bash
   poetry run visionroute keys generate --out /tmp/keys
   aws secretsmanager put-secret-value --secret-id <jwt_keys_secret_arn> \
     --secret-string "$(jq -n --arg p "$(cat /tmp/keys/jwt-private.pem)" \
        --arg u "$(cat /tmp/keys/jwt-public.pem)" '{private:$p,public:$u}')"
   ```
5. **PostGIS**: RDS'te ilk migration öncesi bir kez:
   `CREATE EXTENSION IF NOT EXISTS postgis;`
6. **İlk yönetici**: `visionroute admin bootstrap` (tek seferlik, güvenli).

## Olağan dağıtım

`v*` etiketi push edin veya `cd.yml`'i elle tetikleyin:

1. imajlar derlenir, SBOM üretilir, Grype `--fail-on high` ile taranır,
2. ECR'a itilir (immutable etiket),
3. Terraform plan + apply (production'da GitHub environment onayı),
4. migration ayrı tek seferlik ECS görevi olarak koşar (API asla otomatik
   migrate etmez),
5. smoke test `/health/ready`'yi doğrular.

## Geri alma (rollback)

- **Uygulama**: önceki imaj etiketiyle `terraform apply -var image_tag=<önceki>`.
- **Şema**: `alembic downgrade <revizyon>` — yıkıcı migration'larda önce
  yedeğe dönmeyi değerlendirin (bkz. backup-restore.md). Tüm migration'lar
  up→down→up testinden geçer ancak üretim verisiyle downgrade her zaman
  veri kaybı riski taşır; migration notlarını okuyun.

## Yedekleme ve geri yükleme

RDS otomatik yedekleri 14 gün saklanır; point-in-time recovery açıktır.
Ayrıntı: `docs/operations/backup-restore.md`.
