# Veri Kaynağı Kaydı / Data Source Register

Her dış veri kaynağı burada lisans, atıf, tazelik ve kısıtlarıyla kaydedilir.
**Hiçbir kaynak, lisansı ve kullanım koşulları doğrulanmadan üretime bağlanamaz.**

| Kaynak | Tür | Lisans | Atıf | Yenileme | Kapsam | Ticari kullanım | Durum |
|--------|-----|--------|------|----------|--------|-----------------|-------|
| Müşteri telematik beslemesi | Müşteriye ait | Müşteri sözleşmesi | — | Gerçek zamanlı | Müşteri filosu | Sözleşmeyle | Adaptör hazır, kimlik bilgisi bekleniyor |
| Müşteri RTSP kameraları | Müşteriye ait | Müşteri sözleşmesi | — | Akış | Araç içi | Sözleşmeyle | Kayıt/doğrulama akışı hazır |
| OpenStreetMap (harita karoları, MapLibre ile) | İzinli açık veri | ODbL | © OpenStreetMap katkıcıları (UI'da gösterilir) | Sağlayıcıya göre | Global | Karo sunucusu koşullarına tabi | Karo sağlayıcısı seçimi bekliyor (OPEN_QUESTIONS #1) |
| Hava durumu zenginleştirme | Resmî API | Sağlayıcıya göre | Sağlayıcıya göre | Saatlik | TR | Anahtar gerekli | Adaptör arayüzü hazır, sağlayıcı seçilmedi |
| Yol çalışması/kapanma beslemeleri | Resmî/lisanslı besleme | Kaynağa göre | Kaynağa göre | Kaynağa göre | TR | Doğrulanacak | Entegre edilmedi |
| Manuel doğrulanmış saha raporları | Manuel | İç veri | — | Anlık | Kiracı bölgesi | Evet | Ürün içi akış (yol riski gözlemleri) |

## Kurallar

- Robots/koşul ihlali yapan scraping yasaktır; anti-bot atlatma uygulanmaz.
- Her kaynak için `data_sources` tablosunda: lisans, atıf, yenileme aralığı,
  coğrafi kapsam, ticari kısıt, son başarılı güncelleme, güvenilirlik alanları tutulur.
- Sentetik/simülatör verisi her kayıtta `data_origin="synthetic"`,
  `environment="demo"` ile işaretlenir ve üretim verisiyle asla karıştırılmaz.
