# ADR-0008: Yapay zekâ yardımı varsayılan kapalı ve henüz uygulanmadı

## Durum
Kabul edildi — 2026-07-16; durum doğrulandı — 2026-09-14

## Bağlam
LLM tabanlı özetleme veya koçluk taslağı değer katabilir; ancak güvenlik kararları,
kişisel veri ve halüsinasyon riski nedeniyle sınırları önceden belirlenmelidir.
Sağlayıcı ve bütçe seçilmedi (docs/OPEN_QUESTIONS.md #6).

## Karar
- Yapılandırmada yalnızca kapalı bayraklar vardır (`VISIONROUTE_AI_ASSIST_ENABLED=false`,
  sağlayıcı/anahtar alanları). **Hiçbir kod yolu bir LLM çağırmaz.**
- Gelecekteki her yapay zekâ özelliği şu kurallara uymak zorundadır:
  - yalnızca sınırlı, şema doğrulamalı görevler (özet, koçluk taslağı, not sınıflandırma),
  - sayısal telemetri sınıflandırması, disiplin kararı, SQL veya kod üretimi yapılmaz,
    kanıt uydurulmaz,
  - çıktı güvenilmez kabul edilir, HTML olarak işlenmez, kritik kayıtları değiştiremez,
  - kiracı verisi sağlayıcıya gönderilmeden önce veri işleme sözleşmesi ve KVKK
    yurt dışı aktarım değerlendirmesi yapılır.

## Sonuçlar
- (+) Ürün, yapay zekâ olmadan deterministik ve açıklanabilir kurallarla çalışır.
- (−) Özelliğin etkinleştirilmesi yeni bir ADR, tehdit modeli güncellemesi ve testler gerektirir.
