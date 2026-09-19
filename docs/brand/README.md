# VisiOnRoute brand assets

The product name is written exactly **VisiOnRoute**.

## Files

| File | What it is |
|------|------------|
| `docs/brand/VisiOnRoute-wordmark.png` | Official wordmark as supplied (612×408, transparent). Source of every derived file. |
| `apps/web/public/brand/visionroute-wordmark.png` | Byte-identical copy of the official wordmark. |
| `apps/web/public/brand/visionroute-wordmark-trimmed.png` | The wordmark with only its fully transparent margin removed (439×140). Used in the UI. |
| `apps/web/public/brand/visionroute-icon.png` | The shield emblem: a pixel-exact crop of the wordmark (131×140). Compact and mobile contexts. |
| `apps/web/src/app/icon.png`, `apple-icon.png`, `favicon.ico` | The shield on a white plate (browser tab, home screen). |
| `apps/web/src/app/opengraph-image.png` | The wordmark on white, 1200×630 (link previews). |
| `docs/brand/VisiOnRoute-icon-provided.png` | A separate icon file supplied with the wordmark. It does not match the wordmark's emblem, so it is not used; the shield crop is the compact mark instead. |

Crops are verified pixel-for-pixel against the source; nothing is redrawn,
recolored or stretched.

## Usage rules

- Use the wordmark where horizontal space allows and the shield alone where it does not
  (mobile header, favicon). `BrandLogo` (`apps/web/src/components/BrandLogo.tsx`) handles
  both, including a `responsive` variant (shield below 400px, wordmark above).
- Only ever set the height; the width follows the intrinsic aspect ratio.
- The logo is dark navy. On dark surfaces, place it on the white plate (`plate` prop)
  instead of changing its colors.
- Do not recolor, outline, add effects to, or recreate the artwork.
