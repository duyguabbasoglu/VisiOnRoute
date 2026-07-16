# ADR-0001: Tek Poetry paketi içinde modüler monolit

## Durum
Kabul edildi — 2026-07-16

## Bağlam
Spesifikasyon `apps/` + `packages/` çoklu-paket monorepo düzeni öneriyor ancak
"gerekçeli sapma" serbest. Çoklu Poetry paketi; sürüm senkronizasyonu, editable
kurulum karmaşası ve CI süresi maliyeti getirir. Sınırların gerçek amacı,
domain mantığının çerçevelerden bağımsız kalması ve modüller arası sızıntının
önlenmesidir.

## Karar
Tek Poetry paketi `src/visionroute/` içinde katmanlar:
`domain → application → infrastructure → (api | worker | scheduler | cli)`.
Sınırlar **import-linter** sözleşmeleriyle CI'da zorlanır; domain'in
FastAPI/SQLAlchemy/AWS SDK import etmesi yasaktır.

## Sonuçlar
- (+) Basit kurulum, tek lock dosyası, hızlı CI.
- (+) Sınır ihlali statik analizle kırmızı CI üretir.
- (−) İleride ekipler büyürse paketlere bölme işi gerekebilir; katman
  disiplini bu geçişi ucuz tutar.
