# Devir Kaydı / Handover Log

Tamamlanamayan veya kısmen tamamlanan işler burada açıkça kayıt altına alınır.
Her kilometre taşı sonunda güncellenir.

## Ortam kısıtlarından doğan kalıcı notlar

- **Docker yok**: `docker-compose.yml` yazıldı ancak bu makinede doğrulanamadı.
  Entegrasyon testleri yerel PostgreSQL 17 kümesiyle koşuyor.
- **Terraform CLI yok**: `terraform validate` CI işinde tanımlı; yerelde koşulamadı.
- **Gerçek kimlik bilgisi yok**: AWS, SMTP, SMS, Stripe, telematik sağlayıcı,
  RTSP kamera kimlik bilgileri mevcut değil. İlgili adaptörler sözleşme
  testleriyle doğrulandı; canlı doğrulama kimlik bilgisi sağlandığında yapılmalı.

(İlk kilometre taşı kapanışında ayrıntılı bölümler eklenecek.)
