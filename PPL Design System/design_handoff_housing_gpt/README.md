# Handoff: PPL Knowledge — Supported Housing (HousingGPT)

## Overview
A single-page internal AI assistant for PPL's Supported Housing team. Users ask
natural-language questions about policy, commissioning, voids, move-on
pathways, etc. Answers are grounded in a SharePoint-synced corpus. The design
renders:

- A deep-purple branded sidebar with the PPL logo, a SharePoint-sync status
  card, and the signed-in user.
- A main stage with a "prompt chip" launcher (four canned starter questions)
  that transitions into a chat conversation.
- A sticky composer with attach / scope controls and a send button.
- A light "Tweaks" overlay (theme, density, sidebar on/off, wave-intensity)
  used for design review — **do not ship this in production**.

## About the Design Files
Everything in this bundle is a **design reference** — an HTML/CSS/JS prototype
demonstrating intended look and behaviour. It is not production code to lift
verbatim.

The task is to **recreate this design in PPL's existing application
environment** using its established patterns, component primitives, and
libraries. If no such environment exists yet, implement it in whatever
framework the team standardises on (React + CSS-in-JS, Next.js, etc.).

Preserve:
- The visual language (PPL purple, Poppins, wave motif, deep-purple sidebar).
- The interaction model (prompt chips → composer → chat, streaming reply,
  citations panel).
- The copy exactly as written.

Do NOT preserve:
- The Tweaks panel.
- The `localStorage` persistence wiring.
- The inline SVG/data-URI wave — re-export as an SVG component in your app.

## Fidelity
**High-fidelity.** Colours, typography, spacing, radii, shadows, and motion
are all final. Recreate pixel-perfectly within your codebase's component
system.

## Screens / Views

### 1. Idle (empty) state
- **Purpose:** Launch point. User picks a starter prompt or types their own.
- **Layout:** Two-column grid `272px | 1fr`. Sidebar is sticky, full-height,
  deep purple. Main column is a vertical flex: topbar → stage (hero) →
  sticky composer → thin credentials strip.
- **Hero:** Centred vertical stack — decorative chevron/wave mark, then a
  2×2 grid of prompt-chip buttons. No headline copy.

### 2. Conversation state
- **Purpose:** User has sent a message; answer streams in.
- **Transition:** Hero fades out (~280ms), `.conversation` fades in.
- **Message cards:**
  - User: right-aligned, `var(--ppl-tint-3)` bg, ink text.
  - Assistant: left-aligned, white paper card, `var(--shadow-md)`, typing
    indicator while streaming, then streamed text.
- **Citations:** Each assistant answer ends with a horizontal row of
  "source chips" (document icon + title + folder path). Clicking would open
  the SharePoint doc in a new tab.

### 3. Sync state
- Sidebar "Sync now" button → shows a spinner on the refresh icon and
  updates `#syncStatus` text (`Syncing… / Last synced just now · N files`).

## Components

### Sidebar (`.sidebar`)
- `background: var(--ppl)` (#490E6F), white text.
- **Wave header:** `.sidebar::before` — absolute, top 0, height 110px, two
  overlapping SVG paths (lilac `#D2C4DC` back band + mid-purple `#724CBF`
  front band at 75% opacity), flat top edge, S-curve downward. Logo sits
  *below* the wave at `margin-top: 92px` so the curve cuts through/around it.
- **Logomark:** white PPL wordmark (`assets/ppl-logo-white.png`, 60×28) +
  vertical divider + two-line product label ("KNOWLEDGE" eyebrow / "Supported
  Housing" name).
- **Sync panel:**
  - Card at `rgba(255,255,255,.08)` on `rgba(255,255,255,.12)` border,
    `--radius-md`, 12/14 padding.
  - "STATUS" eyebrow, then "Last synced 12 min ago · 2,418 files".
  - Three meta rows (`Source / Model / Embeddings`) — **right-column
    `text-align: right`**, Important because values can wrap.
  - Pill button "Sync now" — lilac `#9576FF` bg, white text, 7/11 padding,
    fully rounded, refresh-spinner icon.
- **Footer user-chip:** Avatar (purple tint, initials "MH") + name
  "Mustafa Hussain" / role "Housing Team · PPL".

### Topbar (`.topbar`)
- Flex row, space-between.
- Left: breadcrumb `.here` = "Supported Housing" (the only crumb).
- Right: a single icon-button for Tweaks (`.icon-btn#tweaksBtn`) — **drop
  this in production.**

### Hero launcher (`.hero`)
- Vertical flex, centred, `max-width: 780px`, 80px top padding.
- `.hero-mark`: small dotted-chevron motif (graduated lilac dots).
- `.prompt-chips`: 2-column grid, gap 12px.
  - Each `.chip` is a rounded `--radius-md` card, white bg, `--line` border,
    `--shadow-sm`, left-aligned title, hover lifts with `--shadow-md` and
    `border-color: var(--ppl-tint-2)`.
  - Clicking populates the textarea with the chip's `data-q`.

### Composer (`.composer-wrap`)
- Sticky to bottom of main column, max-width 780px, centred.
- `.composer`: white card, `--radius-lg`, `--shadow-md`, 14px padding.
  - `<textarea>` auto-grows 1–180px, placeholder "Ask about policy,
    procedure, competitor insight or operational guidance…".
  - Row below: left-side pill buttons (Attach, Scope="Supported Housing"
    which is `.active`), right-side "Enter to send" hint + circular send
    button.
- `.disclaimer`: centred 11px muted text — "Answers are grounded in approved
  material. Always verify citations."

### Credentials strip
- Thin full-width bar at the very bottom of main, 11px, letter-spaced,
  `color: var(--muted)`, text: `B Corp · Social Enterprise UK · FT Leading
  Consultancy 2025`.

## Interactions & Behavior

- **Chip click:** fills textarea via `data-q`, focuses composer.
- **Submit (Enter or send button):**
  1. If hero visible: add `.fade-out`, then swap to `.conversation` after
     280ms.
  2. Append user message (right-aligned bubble).
  3. Append assistant message with typing indicator.
  4. After ~650ms, replace indicator with streamed text (setInterval
     pushing characters at ~15ms/char).
  5. On completion, append a citations row (3 source chips).
- **Shift+Enter:** newline (default).
- **Enter alone:** submits if non-empty.
- **Send button:** `disabled` while textarea is empty.
- **Sync button:** adds `.is-syncing` class (spins icon), updates status
  text to "Syncing…" then "Last synced just now · 2,418 files" after ~1.4s.
- **Hover lifts:** all pill buttons, chips, and send button use
  `transform: translateY(-1px)` + shadow upgrade on hover.

## Animation tokens
- Hero fade-out: `opacity .28s ease, transform .28s ease` (translateY 8px).
- Conversation fade-in: `opacity .3s ease`.
- Message enter: `opacity .25s ease, transform .25s ease` from translateY 6px.
- All hover transitions: 150ms ease.

## State Management

Conceptual state (implement with your state library of choice):

```ts
type Message = {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  streaming?: boolean;
};

type Citation = {
  title: string;     // "Voids Recovery Policy 2024.docx"
  path: string;      // "/Supported Housing/Policies"
  url: string;       // SharePoint deep link
};

type AppState = {
  mode: 'idle' | 'conversation';
  messages: Message[];
  composer: string;
  sync: { status: 'idle' | 'syncing'; lastSyncedAt: Date; fileCount: number };
};
```

Transitions:
- `SUBMIT_PROMPT` → `mode: 'conversation'`, push user msg, push assistant
  placeholder, kick off streaming.
- `STREAM_CHUNK(text)` → append to last assistant msg.
- `STREAM_DONE(citations)` → set `streaming: false`, attach citations.
- `TRIGGER_SYNC` → `sync.status = 'syncing'`, resolve to `idle` + update
  `lastSyncedAt` / `fileCount`.

Real implementation should replace the mock `setInterval` streaming with
SSE/WebSocket from the LLM backend (the prototype currently logs
`gpt-5-mini` + `text-embedding-3-large` as placeholder model names — confirm
the production model IDs with the team).

## Design Tokens

### Colours
```
--ppl:        #490E6F   /* Primary, most-used */
--ppl-deep:   #350355   /* Secondary deep */
--ppl-mid:    #724CBF   /* Secondary mid */
--ppl-lilac:  #9576FF   /* Bright lilac accent (pops only) */
--ppl-tint-1: #D2C4DC
--ppl-tint-2: #EDE7F1
--ppl-tint-3: #F2EFFF

--ink:        #0D0517
--ink-2:      #3B2F48
--muted:      #6B6078
--line:       #EAE3F0
--line-strong:#D9CFE3
--paper:      #FFFFFF
--cream:      #FAF6FD   /* app background */
```

Gradient rule: **gradients are used ONLY inside wave motifs**, never on
buttons or cards.

Dark theme tokens are in the source under `[data-theme="dark"]`. Only
implement if the team needs dark mode — otherwise drop.

### Typography
- **Family:** Poppins (300, 400, 500, 600, 700, 800, 900). Load from Google
  Fonts or self-host.
- **Scale (web):**
  - Display 48–64px / 700 / -0.02em / 1.12
  - H2 28px / 700 / 1.2
  - H3 20px / 600 / 1.3
  - Body 14–15px / 400 / 1.55
  - Caption / label 11–12px / 500–600 / 1.4
  - Eyebrow 9.5–10px / 600 / letter-spacing 0.16–0.18em, UPPERCASE

### Spacing / radii / shadows
```
--radius-xl: 24px
--radius-lg: 18px
--radius-md: 12px
--radius-sm: 8px

--shadow-sm: 0 1px 2px rgba(73,14,111,.06), 0 2px 8px rgba(73,14,111,.04)
--shadow-md: 0 4px 14px rgba(73,14,111,.08), 0 10px 30px rgba(73,14,111,.06)
--shadow-lg: 0 20px 50px rgba(73,14,111,.14)
```
Shadows intentionally use PPL-purple alpha, not neutral grey.

## Motifs

Three brand motifs are referenced. Re-export each as an SVG component:

1. **Wave** — liquid S-curve, scalloped, purple→lighter-purple.
   - Used on sidebar header (see `.sidebar::before`).
   - Used for section transitions and hero backgrounds.
   - Two stacked bands offset slightly for depth.
2. **Dotted chevron** — graduated lilac dots forming a rightward arrow.
   - Used for progression, "moving forward", and active-state accents.
3. **Organic blobs** — soft layered purple shapes used as background
   atmosphere only. Low opacity. `assets/blob-1.png`, `blob-2.png` on
   disk are acceptable to reuse.

## Assets

The prototype references:
- `assets/ppl-logo-white.png` — white PPL wordmark for deep-purple bg.
- `assets/ppl-logo.png` — purple wordmark for light bg (not currently
  rendered but should be used if the sidebar is off / theme inverts).

These are NOT included in this handoff bundle — pull the canonical versions
from PPL's brand asset library. Reference files in the design project under
`/assets/` include blobs, wave banners, palette swatches, and typography
samples for reference only.

## Files

- `HousingGPT.html` — the prototype itself (self-contained; inline CSS +
  inline JS, no build step).

Open it in a browser to see the intended interaction. All CSS variables,
motif SVGs (inline data-URIs), and the streaming chat loop are in the single
file.

## Out of scope for implementation

- The Tweaks panel (`#tweaksPanel`, `.tweaks`, `TWEAK_DEFAULTS`,
  `__edit_mode_*` postMessage plumbing). This is a design-review tool only.
- `localStorage` persistence of theme/density.
- The mock streaming loop (`setInterval` over `.split('')`). Replace with
  your actual LLM streaming transport.
- The hard-coded citations array — wire to real retrieval results.
