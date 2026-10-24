# AERTiCKET-inspired CCON BA Desk design system

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

## CSS palette in prototype

| Role | Token | Value | Purpose |
| --- | --- | --- | --- |
| Accent | `--brand-blue` | `#0879b6` | Wordmark emphasis, primary action |
| Text | `--brand-ink` | `#161f27` | Headlines, professional contrast |
| App canvas | `--brand-canvas` | `#f4f7f9` | Calm light backgrounds |
| Selected row | `--brand-blue-light` | `#e7f3f9` | Active workflow selection |
| Divider | `--line` | `#dbe3e9` | Structural separation |

Values are a visual approximation, **not a sourced official brand hex palette**.

## Product UI constraints

- The current active sprint must be recognizable within 1 second.
- Clearly label "not verified" sprint status, instead of showing a misleading badge.
- Do not use color alone for critical distinctions; include text and icon
  or contrasting text labels.
- Progressive disclosure: 30-second briefing first, timeline, IF/THEN,
  raw Jira comments and ZIP details behind expanders.
- Preserve keyboard accessibility and mobile responsiveness.
- Never render unescaped Jira body/HTML; source links are HTTP(S) only.
- Cloud version must include sign-in identity and "last successful sync" indicator.
- Use approved official logo only after confirming reuse rights and correct file.
