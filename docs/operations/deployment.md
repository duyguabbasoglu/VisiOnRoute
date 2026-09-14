# Dağıtım / Deployment

> Bu belgedeki AWS adımları **henüz gerçek bir hesapta uygulanmadı**. Terraform
> yapılandırması `terraform validate` ile doğrulandı (staging ve production);
> `plan`/`apply` kimlik bilgisi gerektirir.

## Ortamlar

| Ortam | Terraform kökü | Profil |
|-------|----------------|--------|
| staging | `infra/terraform/envs/staging` | t4g.micro, tek AZ, silme koruması kapalı |
| production | `infra/terraform/envs/production` | m7g.large, multi-AZ, silme koruması, son anlık görüntü, onay kapısı |

Her iki ortam da üretim benzeridir: HTTPS, SMTP, S3, Redis hız sınırlama,
veritabanı TLS'i ve alan şifreleme anahtarı olmadan uygulama **başlamaz**
(`Settings.validate_for_runtime`).

## Servisler

| ECS servisi | İmaj | Komut | Not |
|---|---|---|---|
| `api` | api | uvicorn (Dockerfile varsayılanı) | ALB `/api/*`, `/health/*` |
| `worker` | api | `visionroute worker run` | outbox, e-posta, webhook, KVKK talepleri |
| `scheduler` | api | `visionroute scheduler run` | tek replika; partisyon, saklama, kullanım ölçümü, deneme bitişi |
| `web` | web | `node server.js` | ALB varsayılan hedefi |

`/metrics` ALB'ye yönlendirilmez; Prometheus iç ağdan görevlere erişmelidir.

## Gerekli girdiler

Terraform değişkenleri (CD'de GitHub environment secret'larından `TF_VAR_*`):

| Değişken | GitHub secret | Açıklama |
|---|---|---|
| `app_domain` | `APP_HOSTNAME` | Ör. `filo.ornek.com.tr` (şemasız) |
| `certificate_arn` | `ACM_CERTIFICATE_ARN` | `eu-central-1` ACM sertifikası |
| `smtp_host`, `smtp_from`, `smtp_username` | `SMTP_HOST`, `SMTP_FROM`, `SMTP_USERNAME` | SPF/DKIM doğrulanmış gönderen |
| `budget_alert_email` | `BUDGET_ALERT_EMAIL` | Boşsa bütçe alarmı oluşturulmaz |
| `image_tag` | — | CD üretir |

Diğer GitHub secret'ları: `AWS_DEPLOY_ROLE_ARN` (imaj itme + migration görevi),
`AWS_TERRAFORM_ROLE_ARN` (Terraform apply), `ECR_API_URL`, `ECR_WEB_URL`,
`PRIVATE_SUBNET_IDS`, `SERVICE_SG_ID`.

## İlk kurulum (tek seferlik)

1. **Terraform durumu**: versiyonlu ve şifreli `visionroute-terraform-state`
   S3 bucket'ı ile `visionroute-terraform-locks` DynamoDB tablosunu oluşturun;
   ortam köklerindeki `backend "s3"` bloklarının yorumunu açın.
2. **Terraform rolü**: GitHub OIDC ile üstlenilen, yığının tamamını
   yönetebilen bir rolü hesap yöneticisi oluşturur (`AWS_TERRAFORM_ROLE_ARN`).
   Modül, `github_repository` verildiğinde yalnızca ECR itme ve migration
   görevi çalıştırma yetkili dar bir rol (`github_deploy_role_arn` çıktısı)
   üretir; Terraform apply yetkisi bu role verilmez.
3. **ACM sertifikası**: alan adınız için sertifika alın; DNS'te alan adını ALB'ye
   (`alb_dns_name` çıktısı) yönlendirin.
4. **İlk `terraform apply`** (yerelde, Terraform rolüyle): secret kapları,
   ağ, RDS, Redis, S3, ECR ve ECS oluşur. Servisler secret değerleri
   yazılana kadar başlamaz.
5. **JWT anahtarları** (`jwt_keys_secret_arn` çıktısı, JSON anahtarları `private`, `public`):
   ```bash
   poetry run visionroute keys generate --out /tmp/vr-keys
   aws secretsmanager put-secret-value --secret-id <jwt_keys_secret_arn> \
     --secret-string "$(jq -n --arg p "$(cat /tmp/vr-keys/jwt-private.pem)" \
        --arg u "$(cat /tmp/vr-keys/jwt-public.pem)" '{private:$p,public:$u}')"
   rm -rf /tmp/vr-keys
   ```
6. **Uygulama sırları** (`app_secrets_arn` çıktısı). Anahtarların hepsi bulunmalıdır;
   kullanılmayanlar boş dize olabilir:
   ```bash
   FIELD_KEY=$(poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
   aws secretsmanager put-secret-value --secret-id <app_secrets_arn> \
     --secret-string "$(jq -n --arg f "{\"k1\": \"$FIELD_KEY\"}" --arg s "<smtp-parolası>" \
        --arg m "$(openssl rand -hex 32)" \
        '{field_encryption_keys:$f, smtp_password:$s, metrics_token:$m}')"
   ```
   `field_encryption_primary_key_id` değişkeni (varsayılan `k1`) JSON'daki
   anahtar kimliğiyle aynı olmalıdır. Rotasyon: `docs/operations/key-rotation.md`.
7. **PostGIS**: migration'lar `CREATE EXTENSION postgis` çalıştırır; RDS ana
   kullanıcısı (`rds_superuser`) bunu yapabilir.
8. **İlk yönetici**: migration'dan sonra tek seferlik görev:
   `visionroute admin bootstrap` (bkz. `docs/security`); parola ortam
   değişkeninde bırakılırsa uygulama başlamaz.

## Olağan dağıtım

`v*` etiketi push edin veya `cd.yml`'i elle tetikleyin:

1. API ve (ortamın `https://APP_HOSTNAME` kökeniyle derlenen) web imajları
   oluşturulur, sabit sürümlü Syft ile SBOM üretilir, Grype `--fail-on high`
   ile iki imaj taranır, ECR'a itilir (immutable etiket).
2. Yalnızca yeni API görev tanımı kaydedilir (`terraform apply -target`).
3. Aynı imajla `alembic upgrade head` tek seferlik ECS görevi çalışır;
   çıkış kodu 0 değilse dağıtım durur (servisler eski sürümde kalır).
4. Tam `terraform plan` + `apply`: api, worker, scheduler, web güncellenir;
   ECS devre kesicisi başarısız dağıtımı otomatik geri alır.
5. Smoke test `/health/ready` (veritabanı + şema sürümü) ve `/giris`.

Production için GitHub environment onayı gerekir.

## Ağ ve güvenlik notları

- Görevler özel alt ağlarda; servis güvenlik grubu yalnızca ALB'den 8000/3000.
  Bu nedenle `FORWARDED_ALLOW_IPS=*` güvenlidir; görevleri başka bir yoldan
  erişilebilir yaparsanız bu değeri daraltın.
- Kanıt bucket'ı: genel erişim engeli, KMS şifreleme, yalnızca TLS politikası,
  uygulama kökeninden imzalı POST için CORS, eski sürümler 7 gün.
- ElastiCache (tek düğüm `aws_elasticache_cluster`) aktarım şifrelemesi
  sunmaz; Redis yalnızca VPC içinde hız sınırlama sayaçları taşır. Aktarım
  şifrelemesi gerekiyorsa replication group'a geçin.
- CloudWatch log grupları AWS varsayılan şifrelemesini kullanır.

## Geri alma (rollback)

- **Uygulama**: önceki imaj etiketiyle CD'yi yeniden çalıştırın veya
  `terraform apply -var image_tag=<önceki>`. Önceki kod yeni şemayla uyumlu
  olmalıdır (migration'lar geriye uyumlu yazılır).
- **Şema**: `alembic downgrade <revizyon>` — yıkıcı migration'larda önce
  yedeğe dönmeyi değerlendirin (bkz. backup-restore.md). Tüm migration'lar
  up→down→up testinden geçer ancak üretim verisiyle downgrade her zaman veri
  kaybı riski taşır.

## Yedekleme ve geri yükleme

RDS otomatik yedekleri 14 gün saklanır; point-in-time recovery açıktır.
Ayrıntı: `docs/operations/backup-restore.md`.
