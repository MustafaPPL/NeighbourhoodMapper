# Fonts

PPL uses **Poppins** throughout.

No `.ttf`/`.otf` files are checked in — Poppins is loaded from Google Fonts
via the `@import` at the top of `colors_and_type.css`:

```
https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap
```

## Weights in active use

- 400 — body
- 500 — UI labels, nav items
- 600 — eyebrows, subheadings, emphasis, buttons
- 700 — H1–H3
- 800 — display

300, 900 are available but not currently used anywhere in the system.

## Self-hosting

If you need to self-host (air-gapped env, offline builds):

1. Download the Poppins family from Google Fonts:
   <https://fonts.google.com/specimen/Poppins>
2. Drop the `.ttf` or `.woff2` files into this folder.
3. Replace the `@import` in `colors_and_type.css` with a `@font-face` block
   pointing to the local files, and remove the Google Fonts `<link>` tags
   from any HTML.

## Substitution

If Poppins genuinely can't be used, the closest free substitute is
**Inter** — similar geometric sans, very close proportions. Flag the
substitution; do not silently swap.
