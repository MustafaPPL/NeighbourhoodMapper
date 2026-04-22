# Slide templates — PPL

Four sample 16:9 (1280×720) slides demonstrating the PPL brand in deck form.
Each is a self-contained HTML file with a scaled canvas, suitable as a
starting point for a full deck.

- `TitleSlide.html` — deep purple title with oversized lilac headline and
  three dotted chevrons bottom-right. Lifted from the "A State of
  Partnership" banner composition.
- `SectionDivider.html` — deep purple with an S-curve wave right-side, for
  separating chapters.
- `ContentSlide.html` — light cream body with three KPI columns and a
  purple top bar. Use for findings, principles, options.
- `QuoteSlide.html` — deep purple with atmospheric blobs, centred quote,
  named attribution. The only place we use the oversized quotation mark.

All four respect the brand rules:
- Gradients only inside wave motifs (SectionDivider).
- Poppins (bold for display, 600 for subhead).
- Credentials strip on the footer.
- Sentence case, no emoji, `·` middle-dot as separator.
- Purple-tinted shadows (cream slide).

### How to chain into a real deck
Convert each `.html` into a `<section>` inside a `<deck-stage>` web
component (copy starter component `deck_stage.js`) and drop the wrapper
markup. The inner `.slide` divs here follow the 1280×720 convention
that `deck_stage` expects.
