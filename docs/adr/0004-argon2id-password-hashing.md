# ADR-0004: Parolalar için Argon2id

## Durum
Kabul edildi — 2026-07-16

## Bağlam
Kullanıcı parolaları platformun en hassas kimlik bilgisidir. Veritabanı sızıntısında
çevrimdışı kaba kuvvet saldırısına dayanıklı, bellek-yoğun ve bakımı süren bir
algoritma gerekir.

## Karar
- `argon2-cffi` ile **Argon2id**; OWASP etkileşimli parametreleri:
  `time_cost=3`, `memory_cost=64 MiB`, `parallelism=2`
  (`visionroute.infrastructure.security.passwords`).
- Parametreler değişirse doğrulama sırasında yeniden hash'leme yapılır
  (`check_needs_rehash`).
- Bilinmeyen hesapla girişte sahte bir Argon2 doğrulaması yapılır; yanıt süresi
  hesabın varlığını sızdırmaz.
- Silinen (KVKK) hesaplarda parola alanı rastgele, kimsenin bilmediği bir değerin
  hash'iyle değiştirilir.

## Sonuçlar
- (+) GPU/ASIC saldırılarına karşı bellek maliyeti.
- (−) Giriş başına ~64 MiB bellek ve onlarca ms CPU; hız sınırlama ve hesap
  kilitleme bu maliyeti kötüye kullanıma karşı sınırlar.
