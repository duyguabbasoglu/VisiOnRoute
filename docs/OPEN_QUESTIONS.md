# Açık Sorular / Open Questions

Cevaplanmadan varsayılanlarla ilerlenen konular. Varsayılanlar ADR'lerde gerekçelendirildi.

| # | Soru | Geçici varsayım | Karar sahibi |
|---|------|-----------------|--------------|
| 1 | Hedef AWS hesabı/bölgesi? | `eu-central-1` (Frankfurt) varsayıldı; KVKK veri yerleşimi için müşteriyle teyit gerekli | Ürün sahibi |
| 2 | Hangi telematik sağlayıcılarla ilk entegrasyon? | Sağlayıcı-nötr adaptör arayüzü + kanonik zarf; ilk gerçek adaptör kimlik bilgisi geldiğinde | Ürün sahibi |
| 3 | SMS sağlayıcısı? | Adaptör arayüzü hazır, sağlayıcı yapılandırılmadı | Ürün sahibi |
| 4 | Stripe mi manuel fatura mı öncelikli? | Manuel fatura modu varsayılan (ADR-0009) | Satış |
| 5 | Video kanıt ve konum verisi saklama süresi yasal alt/üst sınırları? | Plan üst sınırı (90/365/730 gün), organizasyon en az 30 güne kısaltabilir; saatlik temizlik; hukuk incelemesi gerekli | Hukuk |
| 6 | LLM sağlayıcısı ve bütçesi? | AI özellikleri varsayılan kapalı (ADR-0008) | Ürün sahibi |
