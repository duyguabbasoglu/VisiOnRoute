# ADR-0009: Manuel faturalama, ödeme sağlayıcısı entegrasyonu yok

## Durum
Kabul edildi — 2026-07-17; kullanım ölçümü ve deneme bitişi ile güncellendi — 2026-09-14

## Bağlam
Hedef müşteriler Türkiye'deki kurumsal filolardır; satın alma çoğunlukla sözleşme ve
e-fatura ile yürür. Ödeme sağlayıcısı kimlik bilgisi, vergi/e-fatura kuralları ve
iade süreçleri henüz tanımlı değildir (docs/OPEN_QUESTIONS.md).

## Karar
- Abonelikler `billing_mode=manual_invoice` ile yönetilir. Planlar araç/kullanıcı
  limiti ve azami saklama süresi tanımlar; limitler uygulama katmanında zorlanır.
- Platform yöneticisi plan atar (`POST /api/v1/platform/organizations/{id}/plan`);
  bu işlem aboneliği `active` yapar ve denetim kaydına yazılır.
- Günlük kullanım ölçümleri `usage_records` tablosuna idempotent yazılır; fatura
  bu ölçümlerden platform dışında hazırlanır.
- Deneme süresi dolan abonelik `past_due` olur: yeni araç/kullanıcı eklenemez;
  veri alımı, olay üretimi ve mevcut verilere erişim sürer.
- **Ödeme sağlayıcısı (Stripe vb.) entegre edilmemiştir.** Şemadaki
  `billing_mode='stripe'` değeri gelecekteki bir adaptör için ayrılmıştır; hiçbir kod
  yolu bunu kullanmaz.

## Sonuçlar
- (+) Sahte ödeme akışı yok; güvenlik verisi ödeme durumundan dolayı kaybolmaz.
- (−) Tahsilat ve plan etkinleştirme manueldir; ölçek büyüdüğünde sağlayıcı
  adaptörü ve e-fatura entegrasyonu için yeni bir ADR gerekir.
