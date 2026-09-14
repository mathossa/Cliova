# Command Center asset placeholders

The command-center UI already references these paths. Assets are intentionally not committed yet so they can be created independently without changing component code.

## Required assets

### `public/assets/maps/world-overview.webp`

- Purpose: primary operational/world map background in the right-hand data view.
- Recommended source size: 1920×1080 or larger, 16:9.
- Format: WebP preferred; keep the exact filename unless the code reference is updated.
- Composition: neutral strategic relief/topographic map, no baked-in labels, markers, borders, UI, legends or text. Those are rendered by the web UI.
- Contrast: medium-low. Settlements/markers and data overlays must remain readable above it.
- Avoid: strong fantasy ornament, metal frames, logos, vignette baked into the art, or historical labels.

### `public/assets/regions/northreach.webp`

- Purpose: selected-region preview image in the left context panel.
- Recommended source size: 960×540, 16:9.
- Format: WebP preferred.
- Composition: neutral landscape/reference image representative of the region. No text or UI baked in.
- Current placeholder concept: dry plateau / broad basin / sparse settlement context.

## Runtime behavior while missing

Both references already exist in `src/features/command-center/command-center.tsx`. CSS/HTML provide neutral fallback surfaces, so the interface remains usable while these files are absent. Browser requests will return 404 until the real assets are added.
