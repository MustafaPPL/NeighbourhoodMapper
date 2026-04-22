# PPL Design System

A design system and UI kit for **PPL** (Private Public Limited) — a B-Corp
management consultancy that works with the public and social sectors in the
UK. Their tagline: *"A management consultancy with a difference."*

PPL's credentials strip, visible across their surfaces:
**B Corp · Social Enterprise UK · FT Leading Consultancy 2025**.

This system packages up PPL's brand foundations (purple, Poppins, waves,
blobs, dotted chevrons) and a first product — the **HousingGPT** internal
knowledge tool for the Supported Housing team — so designers and engineers
can build new PPL surfaces that feel unmistakably PPL.

---

## Sources

Everything here is extracted from material the user supplied:

- **Brand-guide spreads** — scans of PPL's official brand deck, stored as
  `assets/ref-palette.png` and `assets/ref-typography.png`. These are the
  canonical source of truth for colours and type rules.
- **Live published assets** — banners, Impact Report covers, State-of-
  Partnership title treatments, signup hero image. Stored in
  `assets/examples/`.
- **Source decks (.pptx)** — two real PPL presentations stored in
  `assets/source-decks/` for mining authentic copy and slide composition.
- **HousingGPT design handoff** — a self-contained HTML prototype for the
  Supported Housing internal knowledge tool, plus a written handoff brief.
  See `design_handoff_housing_gpt/HousingGPT.html` and its `README.md`.
- **GitHub** — `analytics-PPL/HousingGPT` (the product repo). Not imported
  into this project; browse on demand if you need the production wiring.

---

## Products represented

1. **HousingGPT · Supported Housing Knowledge** — internal AI assistant.
   SharePoint-synced corpus; prompt chips → chat → cited answers.
   See `ui_kits/housing_gpt/` for the reusable JSX kit and
   `design_handoff_housing_gpt/HousingGPT.html` for the full handoff prototype.

PPL themselves are a consultancy, not a SaaS company — so the surfaces in
play are **decks, reports, banners, and internal tools** rather than a
customer-facing web app. The colour system and motifs were designed for
print + presentation first; they translate to web through the HousingGPT
prototype.

---

## CONTENT FUNDAMENTALS

How PPL writes. Pulled from the live HousingGPT prototype, published
banners, and source decks.

### Voice
Confident, grounded, specific. Plain British English. PPL are consultants
talking to public-sector operators; they earn trust by being precise, not
by being breezy. No marketing fluff. No exclamation marks.

### Casing
- **Sentence case everywhere** for UI labels, buttons, menu items,
  chips, and most section titles. "Sync now", not "Sync Now".
- **Title Case** only occasionally in deck titles and printed reports
  ("Further Together", "A State of Partnership").
- **UPPERCASE with letter-spacing** reserved for tiny meta labels — the
  eyebrow/overline style. "STATUS", "KNOWLEDGE", "B CORP ·
  SOCIAL ENTERPRISE UK · FT LEADING CONSULTANCY 2025".

### Person / pronouns
- Product chrome speaks in **imperative** ("Ask about policy, procedure,
  or operational guidance…", "Sync now", "Enter to send").
- Brand voice uses **"we" / "our"** ("PPL's font is Poppins. It is modern,
  fresh and clear.", "We use 6 point spacing after paragraphs…").
- Users are never addressed as "you" in deck copy. UI placeholders may.

### British spelling
`colour`, `organisation`, `behaviour`, `centred`, `analyse`. Never American.
Even in code comments, the CSS file uses `colors_and_type.css` as a filename
(lifted from a US-leaning dev convention) but all prose spelling is UK.

### Tone examples (verbatim)
- "Answers are grounded in approved material. Always verify citations."
  — disclaimer under the composer. Short, declarative, responsible.
- "Last synced 12 min ago · 2,418 files" — meta rows use a middle-dot
  separator, concrete numbers, no adjectives.
- "Ask about policy, procedure, competitor insight or operational
  guidance…" — composer placeholder. Domain-specific, comma-separated,
  ends in ellipsis because the thought continues into the user's question.
- "Target relet time is **21 days** for non-support-needs voids and
  **28 days** for schemes requiring additional assessment." — answer
  pattern: specific number in bold, defined scope, exceptions noted.
- "The PPL purple is our primary colour. It is recognisably and
  distinctly PPL." — brand-guide voice. Calm, authoritative.

### Typography in copy
- **Bold for emphasis** on specific numbers, named policies, or defined
  terms. Never for whole sentences.
- Middle dot `·` separates meta tokens. Em-dashes `—` separate clauses.
- Three-dot ellipsis `…` (single glyph) at the end of composer
  placeholders.

### Emoji
**Never.** Not in UI. Not in decks. Not in running copy. This is a
management consultancy serving the public sector — emoji would undercut
the tone. Unicode symbols like `·`, `—`, `→` are fine as typography.

### Unicode / special chars
- `·` for meta separators
- `→` in progression contexts (often rendered as the dotted-chevron motif
  instead of a literal arrow)
- `✓` / `✗` not used — use semantic colour dots or short words.

---

## VISUAL FOUNDATIONS

How PPL **looks**. Everything below maps to tokens in `colors_and_type.css`
and motifs in `assets/`.

### Colour
- **Primary** `#490E6F` — the PPL purple. The single most-used brand
  colour; appears on sidebars, deck backgrounds, primary buttons, and
  all heading accents.
- **Deep** `#350355` — secondary depth, used for contrast (hover on
  purple buttons, darker bands in waves).
- **Mid** `#724CBF` — the back band of the wave motif. Rarely on UI.
- **Lilac** `#9576FF` — the *pop* colour. Used sparingly: sync CTAs,
  "click here to read" pills on banners, active-state dots.
- **Tints** `#D2C4DC` / `#EDE7F1` / `#F2EFFF` — for soft backgrounds,
  user-message bubbles, meta pills.
- **Neutrals** `#0D0517` (ink), `#3B2F48` (ink-2), `#6B6078` (muted),
  `#EAE3F0` (line), `#FAF6FD` (cream/app-bg), `#FFFFFF` (paper).

**Gradient rule (strict):** gradients are used **only** inside the wave
motif. Never on buttons, cards, CTAs or text. This is load-bearing — the
wave is the single place in the system where purple→lilac is permitted.

**Colour vibe of imagery:** when photography is used (e.g. staff
portraits in decks), it's shot against a neutral light-lilac-purple
backdrop so faces read warm against the primary purple. Illustrations are
monochrome purple line-work on blob grounds. No grain, no heavy filters,
no duotones beyond the purple family.

### Type
- **Family:** Poppins, loaded from Google Fonts. Weights 400/500/600/
  700/800 are in active use; 300 and 900 are available but unused. Inter
  is the documented fallback if Poppins can't be loaded.
- **Scale (web):** Display 48–64 / H1 48 / H2 28 / H3 20 / body 14–15 /
  caption 11–12 / eyebrow 9.5–10 uppercase 0.16–0.18em.
- **Scale (deck):** slide titles **28 pt**, subheadings **14 pt**, body
  **12 pt** (never below 10). 6pt spacing after paragraphs; 8pt around
  headings. Line height **1.12** on headings. These numbers are from the
  brand guide and should be respected for anything that prints.
- **Emphasis rule:** Poppins Bold is used "sparingly to add visual
  hierarchy or emphasis to certain words or phrases" (brand guide).
  Bold individual words — never whole sentences.

### Spacing
4-pt scale: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48 / 64. Cards breathe;
inner padding on composers and chat bubbles is `14–16px`, outer gutters
around hero regions are `28–32px`.

### Backgrounds
Two treatments only:
1. **Cream** `#FAF6FD` — the default content background. Very slightly
   purple-tinted to feel part of the palette even though it reads white.
2. **Deep purple** `#490E6F` — used on full-bleed sidebars, deck covers,
   section dividers, and banner bands.

There are **no** photo backgrounds in the product. Full-bleed imagery
appears only in published material (State-of-Partnership banner, Impact
Report cover). Patterns/textures are not used — the wave and blob motifs
do all the atmospheric work.

### Corner radii
- `4` (tiny — inline badges only)
- `8` (small controls)
- `12` (default cards, sync card, chips)
- `18` (composer, message bubbles)
- `24` (hero cards, modal shells)
- `999px` pills (all rounded buttons and meta chips)

### Borders
- Default hairline `1px solid #EAE3F0` (--line).
- Strong hairline `1px solid #D9CFE3` (--line-strong) on focused/hover
  states.
- **On deep-purple surfaces**, borders are `rgba(255,255,255,.12)` —
  never a lighter purple.

### Shadows
Shadows are **purple-tinted**, never neutral grey. This is signature:
- SM: `0 1px 2px rgba(73,14,111,.06), 0 2px 8px rgba(73,14,111,.04)`
- MD: `0 4px 14px rgba(73,14,111,.08), 0 10px 30px rgba(73,14,111,.06)`
- LG: `0 20px 50px rgba(73,14,111,.14)`

No inner shadows. No glow. Elevation moves from SM → MD → LG as importance
grows; MD is the default for cards and composers.

### Capsules vs gradients (protection layers)
No "protection gradient" scrims are used to float text on imagery. When
text lives on imagery, it goes inside a **solid lilac capsule** (see the
Impact Report "Click here to read" pill) or a deep-purple bar. Solid
surfaces, not gradients, do the protection work.

### Transparency and blur
- `rgba(255,255,255,.08)` on purple sidebars — the "workspace card"
  inner surface. Often paired with `backdrop-filter: blur(6px)`.
- `rgba(149,118,255,.18)` for dark-theme lilac accents on text pills.
- Blur is reserved for (a) the sidebar workspace-card glass effect and
  (b) background blobs (`filter: blur(20–32px)`). Never on content text.

### Motion
- **Easing:** `cubic-bezier(.2, .7, .2, 1)`. Used for every transition.
- **Durations:** 150ms (hover), 280ms (page-level fades), 400ms (modal).
- **Entry animation:** messages slide up 6px and fade in over 350ms.
- **Hover lift:** `transform: translateY(-1px)` + shadow upgrade SM→MD
  on all interactive pills and chips. This is PPL's signature hover.
- **Press state:** inherits the hover transform but drops the shadow
  slightly; buttons darken from `--ppl` to `--ppl-deep`. No scale-down.
- **Loaders:** the sync button spins its refresh icon (`1s linear
  infinite`). Typing indicator uses three pulsing dots with `pplPulse`
  keyframes, staggered 0.15s / 0.3s. No spinners; no progress bars.
- **Entry/exit fades** between hero → conversation states are
  `opacity + translateY(8px)` over 280ms.

### Cards
A PPL card is:
- `--paper` (white) background
- `--radius-md` (12px) or `--radius-lg` (18px) corners
- `1px solid --line` border **or** `--shadow-sm` (not both) for resting
  state; `--shadow-md` on hover/focus
- inner padding `12–16px`
- no inner gradients, no coloured left-border accents

### Layout rules
- Sidebars are **272px fixed**, deep purple, sticky full-height.
- Main content maxes at **780–820px** centred, which reads as a single
  clean column of prose even on wide screens.
- Composer is sticky to the bottom of main, offset by the sidebar width.
- The credentials strip runs full-width across the absolute bottom on
  decks and on the HousingGPT app.

### Motifs
Three motifs — document these before inventing new ones:

1. **Wave** — liquid S-curve, two offset bands (lilac back `#D2C4DC`,
   mid-purple front `#724CBF` at 75% opacity), flat top edge. Appears
   on sidebar headers, deck covers, and banner transitions. Reconstruct
   with inline SVG; never bitmap.
2. **Dotted chevron** — graduated lilac dots forming a rightward arrow.
   Means "progression" or "moving forward". Used as hero marks and as
   section-divider accents. `assets/ppl-dot-arrow.jpg` carries the
   reference; the HousingGPT prototype re-renders it in SVG.
3. **Organic blobs** — soft overlapping purple shapes at low opacity,
   sometimes blurred. Background atmosphere only. Never in the
   foreground. `assets/blob-1.png`, `blob-2.png`. Also used as
   illustration grounds (see `ref-illustrations.png` for how the brand
   lands line illustrations on blob circles).

---

## ICONOGRAPHY

PPL has **no proprietary icon font or icon pack**. Icons in-product come
from one place:

### Stroke-style line icons (inline SVG)
The HousingGPT prototype uses **Lucide-style** stroke icons rendered
inline: `stroke-width: 2`, `stroke-linecap: round`, `stroke-linejoin:
round`, 12–18px in the UI. Examples in the prototype:
- Refresh/sync (4-arc rotating arrows)
- Paperclip (attach)
- Globe with grid (scope)
- Up arrow (send)
- Document with corner fold (citations)
- Sliders (tweaks)

When you need a new icon, pull it from **Lucide** (https://lucide.dev)
at the same stroke weight. This is a **substitution** documented to the
user — PPL's brand guide doesn't prescribe an icon system, and Lucide is
the closest match to the HousingGPT prototype's in-use style.

### Brand illustrations
- **Blob-circle line illustrations** (see `assets/ref-illustrations.png`):
  continuous-line monochrome drawings on a solid purple blob. Themes so
  far: location pin, people gathered, megaphone, lightbulb puzzle,
  target with arrow. These are bespoke art, not icons — treat them as
  featured illustrations, not inline glyphs. Commission new ones in the
  same style rather than substituting.
- **Dotted chevron** is used in place of a literal arrow glyph in hero
  and transition contexts.

### Credentials lockup
`assets/ppl-badges.png` carries the four official credential marks:
- B Corp Certified
- Social Enterprise UK
- FT / Statista Leading Management Consultants 2025
These ship as a PNG lockup; don't recreate them individually. Use on
decks, reports, and in the app footer credentials strip.

### Emoji / unicode
**No emoji.** Unicode is limited to typographic glyphs: `·` for meta
separation, `—` for clause breaks, `…` for trailing prompts, `→` where
a literal arrow is unavoidable. Avoid any decorative unicode.

### File assets in this system
- `assets/ppl-logo.png` — purple wordmark, use on light.
- `assets/ppl-logo-white.png` — white wordmark, use on purple.
- `assets/ppl-logo-hires.jpeg` — print-quality wordmark.
- `assets/ppl-dot-arrow.jpg` — dotted-chevron reference.
- `assets/blob-1.png`, `blob-2.png` — organic blob motifs.
- `assets/ppl-banner.png` — ready-to-use purple+wave banner plate.
- `assets/ppl-badges.png` — credentials lockup.

---

## Index / manifest

Root of this design system:

```
/
├── README.md                   ← you are here
├── SKILL.md                    ← agent skill manifest (portable)
├── colors_and_type.css         ← CSS custom properties + type classes
│
├── assets/                     ← logos, motifs, illustrations, refs
│   ├── README.md               ← per-asset usage notes
│   ├── examples/               ← real published PPL outputs
│   └── source-decks/           ← original .pptx files (internal only)
│
├── fonts/                      ← Poppins loading instructions
│   └── README.md
│
├── preview/                    ← cards for the Design System tab
│   ├── colors-primary.html, colors-tints.html, colors-semantic.html
│   ├── type-display.html, type-body.html, type-weights.html
│   ├── radii.html, shadows.html
│   ├── motif-wave.html, motif-chevron.html, motif-blobs.html
│   ├── brand-logo.html, brand-sidebar.html
│   └── components-{buttons,chips,composer,messages}.html
│
├── design_handoff_housing_gpt/ ← original handoff bundle
│   ├── HousingGPT.html         ← the full self-contained prototype
│   ├── README.md               ← handoff brief (intent, not-to-preserve)
│   └── assets/                 ← handoff-local logo copies
│
└── ui_kits/
    └── housing_gpt/            ← reusable JSX recreation of HousingGPT
        ├── README.md
        ├── index.html          ← interactive demo
        ├── components.jsx
        └── styles.css
```

## How to use this system

1. Load `colors_and_type.css` first — it provides all design tokens and
   semantic type classes (`.ppl-h1`, `.ppl-body`, `.ppl-eyebrow`, etc).
2. Copy assets from `assets/` into your project rather than referencing
   across folders.
3. For UI that resembles an internal PPL tool, start from
   `ui_kits/housing_gpt/` — the sidebar, composer, and message bubbles
   are already styled.
4. For decks, reuse the `ppl-banner.png` and `ppl-badges.png` plates and
   keep to the type scale in `colors_and_type.css`.
5. Before inventing a new motif, check the three documented ones (wave,
   chevron, blobs). The brand is consistent precisely because it's small.
