# ADR-0002: PostgreSQL outbox + SKIP LOCKED worker (Celery/Dramatiq yerine)

## Durum
Kabul edildi — 2026-07-16

## Bağlam
Spesifikasyon "Celery, Dramatiq veya gerekçeli başka bir worker sistemi" diyor
ve outbox deseni zaten zorunlu. Celery/Dramatiq, Redis/RabbitMQ broker'ını
kritik yol hâline getirir ve iş durumu ile domain verisi arasında çift yazma
problemi doğurur.

## Karar
- Domain olayları aynı veritabanı işlemi içinde `outbox_events` tablosuna yazılır.
- `background_jobs` tablosu gecikmeli/tekrarlı işler için kullanılır.
- `visionroute worker run` süreci `FOR UPDATE SKIP LOCKED` ile güvenli paralel
  tüketim yapar; üstel geri çekilmeli yeniden deneme, ölü-mektup durumu
  (`status=dead_letter`) ve yeniden oynatma CLI'si içerir.
- Redis yalnızca önbellek ve hız sınırlama içindir; kuyruk değildir.

## Sonuçlar
- (+) Tam işlemsel tutarlılık (olay kaybı/çift yazma yok).
- (+) Daha az operasyonel bileşen; PostgreSQL zaten HA kurulacak.
- (−) Çok yüksek kuyruk hacminde Postgres'e yük biner; ölçüm metrikleri
  (kuyruk derinliği, işleme gecikmesi) eklendi, gerekirse SQS'e taşıma yolu
  `application.ports.JobQueue` arayüzü sayesinde açık.
