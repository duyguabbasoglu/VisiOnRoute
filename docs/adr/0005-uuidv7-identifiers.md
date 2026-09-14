# ADR-0005: Birincil anahtarlar için UUIDv7

## Durum
Kabul edildi — 2026-07-16

## Bağlam
Kimlikler istemcilere açılır (URL, API), çok kiracılı tablolarda tahmin edilemez
olmalı ve B-tree indekslerde ekleme sırasına yakın kalmalıdır. Rastgele UUIDv4
indeks sayfa bölünmesine yol açar; ardışık tamsayılar kayıt sayısını ve sırasını
sızdırır.

## Karar
- Uygulama tarafında **UUIDv7** (RFC 9562) üretilir (`visionroute.domain.ids.uuid7`);
  Python 3.13 standart kütüphanesinde bulunmadığı için küçük, test edilmiş bir
  uygulama kullanılır.
- Kimlikler yetkilendirme yerine geçmez: her erişim kiracı ve izin kontrolünden
  (RLS dahil) geçer. Gizli bağlantılar için UUID değil 256 bit opak token kullanılır.

## Sonuçlar
- (+) Milisaniye sıralı kimlikler indeks yerelliğini korur, kayıtlar zaman sırasıyla listelenebilir.
- (−) Kimlik oluşturulma zamanını milisaniye hassasiyetle ifade eder; bu bilgi
  gizli kabul edilen alanlarda kimlik olarak kullanılmamalıdır.
