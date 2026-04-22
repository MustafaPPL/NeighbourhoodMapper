# Assets — what's here and how to use it

This folder is the canonical collection of PPL brand assets. Everything that
goes into a PPL surface (UI, deck, doc, report) should come from here or be
added here.

```
assets/
├── ppl-logo.png              Purple PPL wordmark — for LIGHT backgrounds
├── ppl-logo-white.png        White PPL wordmark — for DARK / PURPLE backgrounds
├── ppl-logo-hires.jpeg       High-resolution purple wordmark (print)
├── ppl-banner.png            Full-width purple banner with wave motif
├── ppl-badges.png            Credentials lockup (B Corp, SEUK, FT, etc)
├── ppl-credentials.jpeg      Alternate credentials treatment
├── ppl-dot-arrow.jpg         Dotted-chevron motif (rightward progression arrow)
├── blob-1.png                Organic blob motif — atmosphere only
├── blob-2.png                Organic blob motif — atmosphere only
│
├── ref-palette.png           Brand-guide spread: colour palette + gradients
├── ref-typography.png        Brand-guide spread: logo + Poppins usage
├── ref-banner-wave.png       Reference of the wave motif on a banner
├── ref-illustrations.png     Reference illustration set from the brand
├── ref-illustrations-detail.png  Close-up of illustration style
├── ref-ppt-frontpiece.png    Reference PowerPoint front-page composition
├── ref-impact-report.jpg     Sample Impact Report layout (for decks/docs)
├── ref-state-partnership.jpg Sample "State of Partnership" banner treatment
├── ref-model-neighbourhood.jpg  Sample "Model Neighbourhood" hero composition
│
├── examples/                 Real published PPL assets — lift, don't invent
└── source-decks/             Original .pptx decks for mining type/imagery
```

## How to use each asset

### Logos
- **`ppl-logo.png`** — use on any light / cream background. Minimum clear
  space = height of the "P". Never recolour, rotate, or outline.
- **`ppl-logo-white.png`** — use on the primary PPL purple `#490E6F` or any
  image dark enough to read white. This is the default inside the HousingGPT
  sidebar.
- **`ppl-logo-hires.jpeg`** — use when exporting for print (reports, PDFs).
  Don't ship inside web apps.

### Banners and motif plates
- **`ppl-banner.png`** — a ready-to-use purple banner with the wave motif
  baked in. Drop it in as a hero band if you can't afford to re-render the
  wave SVG (e.g. in rich-text emails, Word docs).
- **`ref-banner-wave.png`** — reference only. Don't use in product; use the
  inline SVG wave (see `HousingGPT.html` `.sidebar::before` for the working
  implementation).

### Motifs
- **`ppl-dot-arrow.jpg`** — the dotted-chevron progression motif. Use for:
  "next step", "moving forward" moments, active-state accents, empty-state
  marks. Place in low-emphasis spots, don't make it the centrepiece.
- **`blob-1.png`, `blob-2.png`** — organic purple blobs. **Background
  atmosphere only.** Put them behind content at low opacity
  (25–50%), never in the foreground, never overlapping readable text.

### Credentials
- **`ppl-badges.png`** — use as a footer strip on decks, reports, and
  product chrome. The HousingGPT "credentials-strip" reads "B Corp · Social
  Enterprise UK · FT Leading Consultancy 2025" — mirror this exact set.
- **`ppl-credentials.jpeg`** — alternate treatment; use if you need the
  badges larger or on a dark background.

### Reference-only (DO NOT embed in product)
Anything named `ref-*` is a scan / screenshot of PPL brand-guide pages or
reference compositions. These inform the system; they are not shippable:

- `ref-palette.png`, `ref-typography.png` — primary source of truth for
  colour and type. The values in `colors_and_type.css` are extracted from
  these.
- `ref-ppt-frontpiece.png` — the archetypal PPL deck front page. The
  HousingGPT sidebar composition (deep-purple panel + top wave + white
  lockup) is lifted from here.
- `ref-illustrations*.png` — style reference for any new illustration
  commissions. Don't lift the illustrations themselves.
- `ref-impact-report.jpg`, `ref-state-partnership.jpg`,
  `ref-model-neighbourhood.jpg` — sample published compositions used as
  layout inspiration.

### `examples/` — actual published outputs
Real assets exported from PPL's live properties (website, signup flows,
decks). Use these for inspiration AND as direct-drop imagery where
appropriate:

- `PPL-State-of-Partnership-banner.jpg` — live web banner.
- `Impact-Report-web.jpg` — cover treatment from the Impact Report.
- `Model-Neighbourhood.jpg` — product/feature hero composition.
- `ppl-signup-image.jpg` — signup-page illustration/photo.
- `private_public_ltd_cover.jpeg` — generic PPL cover image.
- `ppl-deck-sample-*.png` — slides extracted from `source-decks/`, showing
  how the brand is applied in real presentations (wave title slides, blob
  atmosphere, credentials strips, section dividers).

### `source-decks/` — original PPTX files
Untouched PPT decks from the user. Use these to:
1. Pull authentic PPL copy (tone, phrasing, language patterns).
2. Export any additional imagery or illustrations as you need them.
3. Verify type sizing and slide proportions against the brand guide.

Never redistribute these externally — they are internal PPL material.

---

## Re-export guidance

If you need a different size/format of a logo or motif, go back to the
highest-res version (`ppl-logo-hires.jpeg` for print, `ppl-logo.png` /
`ppl-logo-white.png` for web). Don't upscale a low-res version.

If you need a new motif variation (e.g. a wave with different proportions),
edit the inline SVG in `HousingGPT.html`'s `.sidebar::before` rather than
painting a new PNG — keep the motif vector so it scales cleanly.
