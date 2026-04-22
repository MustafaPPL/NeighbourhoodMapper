---
name: ppl-design
description: Use this skill to generate well-branded interfaces and assets for PPL (Private Public Limited — a B-Corp management consultancy with a difference), either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Quick orientation
- **`README.md`** — company context, content/visual/icon fundamentals, and a manifest of this skill's contents.
- **`colors_and_type.css`** — the single source of truth. Load it first in any PPL surface; it provides all colour tokens, radii, shadows, type scale, and semantic type classes (`.ppl-h1`, `.ppl-body`, `.ppl-eyebrow`).
- **`assets/`** — logos, motifs, illustrations, and reference imagery. `assets/README.md` explains which file to reach for.
- **`ui_kits/housing_gpt/`** — a reusable JSX + CSS recreation of the HousingGPT internal tool (sidebar, composer, message bubbles, sync card). Start here for any internal-tool design.
- **`design_handoff_housing_gpt/HousingGPT.html`** — a full self-contained prototype showing every token in situ. Open it to see the brand applied.

## Non-negotiables
1. **Primary purple `#490E6F`** is always the most-used colour.
2. **Gradients only inside wave motifs.** Never on buttons, cards, or text.
3. **Poppins** for everything. Inter if Poppins is unavailable.
4. **No emoji.** British spelling. Sentence case UI. UPPERCASE only for tiny letter-spaced meta labels.
5. **Three motifs, no others:** wave, dotted chevron, organic blobs.
6. **Credentials strip** on deck and product chrome: *B Corp · Social Enterprise UK · FT Leading Consultancy 2025*.
