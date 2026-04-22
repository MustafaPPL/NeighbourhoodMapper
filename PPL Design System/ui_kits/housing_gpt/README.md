# HousingGPT UI Kit

A React-based recreation of the HousingGPT (Supported Housing Knowledge)
interface using the PPL design system tokens.

## Files
- `index.html` — interactive demo. Open it to see the full UI.
- `components.jsx` — reusable pieces: `<Sidebar>`, `<Logomark>`, `<SyncCard>`,
  `<UserChip>`, `<Hero>`, `<PromptChips>`, `<Composer>`, `<Message>`.
- `styles.css` — component-scoped styles (`.pk-*` prefix). Layered on top of
  `../../colors_and_type.css` — load that first.

## How to reuse
```jsx
import "colors_and_type.css";
import "ui_kits/housing_gpt/styles.css";
import { Sidebar, Logomark, Composer, Message } from "./components";
```

The components don't own state beyond their internal UI behaviour (composer
autogrow, sync-button spinner). Messages + query + submit handler are passed
in from the parent so you can wire to a real streaming endpoint.

## Coverage
- Sidebar with wave header, logomark, sync card, user chip ✓
- Hero launcher (dotted-chevron mark + 2×2 prompt chips) ✓
- Streaming composer (textarea, attach/scope pills, send) ✓
- Message bubbles with citations ✓
- **Not included** (future work): Tweaks panel, dark theme switch,
  attachment picker, citation side-panel, settings screen.
