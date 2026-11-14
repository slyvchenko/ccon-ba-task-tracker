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

## Design system v1 (2026-11-13)

One accent family, one control scale, one chip scale. Tokens live in the
single canonical `:root` of `assets/dashboard.css`; the "Design system v1"
layer at the end of that file is the only place that styles controls,
chips, section titles and selection states.

### Tokens

| Role | Token | Value | Use |
| --- | --- | --- | --- |
| Accent | `--accent` (= `--brand-blue`) | `#5d37a0` | Primary action, selection, links, focus ring |
| Accent hover | `--accent-strong` | `#4b2a89` | Hover/pressed of accent |
| Accent bright | `--accent-bright` | `#7c4ddb` | Title marker gradient only |
| Accent soft | `--accent-soft` | `#f3edfa` | Hover of secondary, selected row/tile fill, counters |
| Accent border | `--accent-border` | `#d9cdee` | Secondary button border, counters, selected outline |
| Accent ink | `--accent-ink` | `#3f2a66` | Secondary button text, group headings |
| Deep accent | `--accent-deep`, `--accent-deep-2`, `--accent-glow` | `#241a3d`, `#332452`, `#4b337a` | «Що зробити зараз» hero gradient |
| Text | `--ink` | `#211b31` | Body text |
| Muted | `--muted` | `#5e576d` | Labels, help text |
| Canvas | `--canvas` | `#f8f6fb` | Page background |
| Divider | `--line` / `--line-strong` | `#e6e0ed` / `#ddd4e9` | Separators / control borders |
| Status tones | `--green`, `--amber`, `--red` | `#155640`, `#744209`, `#9b1e2a` | Status chips and tile bars only |
| Control | `--control-h`, `--control-h-lg`, `--radius-control` | `36px`, `40px`, `10px` | Buttons / inputs |

Values are a product palette, **not a sourced official AERTiCKET brand palette**.

### Components

- **Buttons** — same metrics everywhere (36px high, radius 10px, 13.5px/600):
  - *Primary* (filled accent): one per area — «Виконано → Далі», «Відкрити в пошті», «Відкрити Jira».
  - *Secondary* (white, accent text, accent-border): everything else, including header tools.
  - *On dark* (translucent white): only inside the «Що зробити зараз» hero.
  - *Small* (32px, 12.5px): inline/row actions (Jira link, template address, logs folder, Kibana).
  - Never green/blue one-off buttons; status colour belongs to chips, not to actions.
- **Chips** — pill, 11.5px/650; tone = meaning (green ok, amber needs action, red blocked, gray no data).
  Counters (`.sec-count`, `.queue-group-count`) use the accent-soft pill.
- **Section titles** — L2 `.focus-title` 20px with a 4px accent gradient marker; L3 `.sub-heading` 15px; L4 labels 13px muted.
- **Selection** — queue row and active «Важливо для мене» tile: accent-soft fill + accent outline.
- **Focus** — 2px accent outline (light lilac on the dark hero).
- **Forms** — inputs/selects 40px, radius 10px, `--line-strong` border, accent border on hover.

### Rules

- The accent is for *interaction and selection*; status is expressed with tone chips plus text.
- Add new controls with existing classes (`primary`, default button, small contexts) — no per-feature button CSS.
- Do not add a second `:root`, `.primary {` or `.row-title {` rule (guarded by `tests/css-cleanup.test.mjs`).

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

## Design system v2 (2026-11-13) — visual refinement

v2 changes only the visual layer (colour, type, borders, radii, shadows, controls); the layout from v1 is unchanged.

- **Neutral scale** `--n-0 … --n-900` for surfaces, borders and secondary text. Lavender is no longer used for borders; the accent is reserved for primary actions, selection, focus and links.
- **Type:** `--font-ui` (Segoe UI Variable Text) for UI, `--font-display` (Segoe UI Variable Display) for headings. Section titles are 18px / 600 with slight negative tracking, with no decorative marker bar. Numbers use tabular figures.
- **Surfaces:** cards have a 1px `--n-200` border, a 14px `--radius-card` and a soft `--shadow-card`. The dark "Що зробити зараз" card keeps the signature accent gradient.
- **Buttons:** the secondary button is neutral (white, `--n-300` border); the primary button is filled accent with an inset highlight; both are 36px, with small variants at 30px and an 8px `--radius-control`. On the dark card buttons are glassy, and the disabled state stays readable.
- **Fields:** neutral border; on focus, an accent border plus a `--ring` halo.
- **Chips:** soft tone fill, no outline, 6px `--radius-chip`, 12px / 550.
- **Focus tiles:** white cards; tone is shown by a dot and the value colour, and the active tile gets an accent ring.

## Design system v3 (2026-11-13) — analyst feedback pass

Feedback: too much noise, unclear hierarchy, dated look; button labels, buttons on the dark card, the font, sizes and weights, grey meta text, badges, the queue, fields and background. Changes (visual only):

- **Font:** Inter (variable, bundled in `assets/fonts`, OFL), weights 400/500/600 only, 14px base, `cv11`/`ss03`.
- **Hierarchy:** task title 24/600 > section titles 15/600 > body 14 > labels 11.5 uppercase. Meta text is 12.5px in `--n-600`.
- **Noise:** no rules under section titles or between "Ситуація" rows; flat cards (no shadow); the delta strip is plain text.
- **Buttons:** short labels ("Скопіювати чернетку", "Зберегти й далі", "Jira ↗", "Адреса з шаблону", "Пакет листів · 3"); `.quiet` is a ghost button; on the dark card the first action is solid white and the rest are glass.
- **Badges:** one pill shape with a neutral fill; tone is shown only by a dot.
- **Queue:** no coloured bar on each row; status is shown by a dot; the selected row has a light fill and a 2px accent edge; group headers are small uppercase labels.
- **Fields:** white fields on a near-white page, accent ring on focus, thin scrollbars.
