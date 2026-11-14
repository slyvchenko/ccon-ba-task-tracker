# CCON BA Desk design system (AERTiCKET-inspired)

Status: provisional; exact corporate brand-guide compliance not claimed.

## Source and intent

The public company press kit provides AERTiCKET logos:
https://www.aerticket.de/en/press/press-kit

AERTiCKET's public wordmark uses blue + near-black on white. This
prototype intentionally uses **CSS text**, not an unlicensed bundled logo
or a third-party hotlink. The implemented theme is aligned to the public
look and feel, but is not advertised as an exact corporate reproduction.
Official internal brand guidelines, original SVG and typography approvals
should be used before company deployment.

## Current design system

All styles live in `assets/dashboard.css`. The file is layered: base tokens in the single canonical `:root` (the soft-pastel layer tokens `--soft-*`, `--ink-btn*`, `--pastel*` and `--card-radius` are defined on `:is(body)`, so change them there, not in `:root`), then the design-system layers in cascade order. The latest layer wins, so add new rules at the end of the matching layer, not as one-off overrides.

### Tokens

| Role | Token | Value |
| --- | --- | --- |
| Accent | `--accent` (= `--brand-blue`) | `#5d37a0` (primary action, selection, links, focus) |
| Accent hover / bright | `--accent-strong` / `--accent-bright` | `#4b2a89` / `#7c4ddb` |
| Accent soft / border / ink | `--accent-soft` / `--accent-border` / `--accent-ink` | `#f3edfa` / `#d9cdee` / `#3f2a66` |
| Neutral scale | `--n-0 … --n-900` | `#fff` … `#18161f` (surfaces, borders, secondary text) |
| Page canvas / soft fill | `--soft-canvas` / `--soft-fill` | `#f3f3f6` / `#f4f4f7` |
| Ink button | `--ink-btn` / `--ink-btn-hover` | `#10121f` / `#262a3d` |
| Active-state gradient | `--pastel` / `--pastel-soft` | lavender → pink → peach |
| Radii | `--card-radius` / `--radius-control` / `--radius-chip` | `20px` / `8px` / `6px` |
| Focus ring | `--ring` | `0 0 0 3px #7c4ddb2e` |

These values are a product palette, **not a sourced official AERTiCKET brand palette**.

### Type

- **Onest** (variable, Cyrillic-first, bundled in `assets/fonts`, OFL) for body, controls and headings; Inter and system UI fonts are fallbacks.
- Weights 400/500/600. Hierarchy: task title > section titles > body > small uppercase labels; meta text uses the muted neutral.

### Layout and components

- **Header:** tools on the right; the daily report is a link «Звіт · N змін ↗» next to «Оновлено». Its tooltip lists the breakdown (new, changed, completed, reopened, Done in Jira, out of JQL, questions, warnings). The status row appears only for a message or the undo button.
- **Queue column:** a tinted header band with the filters, card-like rows, status as a tinted pill, and a subtle animated edge. The animation is disabled for `prefers-reduced-motion`, and `forced-colors` gets a plain outline.
- **Task card:** «Що зробити зараз» is the first card, and there is no sticky next-action strip. «Важливо для мене» tiles stay collapsed until one is chosen. The active tile closes its panel again (`aria-expanded`), and the choice is kept per task. Section titles are full-width header bands with an icon.
- **Buttons:** one primary action per area; secondary buttons are grey-filled. Status colour belongs to pills and chips, never to actions.
- **Pills/chips:** one pill shape; tone = meaning (ok, needs action, blocked, no data), always with text.

### Themes

`assets/theme-init.js` runs before first paint and sets `<html data-theme="light|dark">` from the user's choice (`system`, `light`, `dark`, stored in `localStorage` as `ccon-theme`) or the system setting. The header toggle switches it. The dark layer reuses the same structure and accents under `[data-theme="dark"]`.

### Rules

- The accent is for interaction and selection; status is expressed with tone pills plus text.
- Add new controls with existing classes (`primary`, default button, small contexts). Don't add per-feature button CSS.
- Do not add a second `:root`, `.primary {` or `.row-title {` rule (guarded by `tests/css-cleanup.test.mjs`).
- Any new colour must work in both themes.

## Product UI constraints

- The current active sprint must be recognizable within 1 second.
- Clearly label "not verified" sprint status, instead of showing a misleading badge.
- Do not use color alone for critical distinctions; include text and icon
  or contrasting text labels.
- Progressive disclosure: «Що зробити зараз» and «Ситуація за 30 секунд» first;
  facts, sources, timeline, QA scenarios and scope in «Другорядне».
- Preserve keyboard accessibility and mobile responsiveness.
- Never render unescaped Jira body/HTML; source links are HTTP(S) only.
- Cloud version must include sign-in identity and "last successful sync" indicator.
- Use approved official logo only after confirming reuse rights and correct file.
