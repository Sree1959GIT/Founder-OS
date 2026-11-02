# FounderOS UI design (Claude Design)

- **Live canvas (private to the founder):** https://claude.ai/artifact/W51rFuAt5xn7LGr3b8JWv4
- **Source snapshots:** `mockups/*.dc.html`. These are reference only. Re-sync them if the founder edits the canvas,
  because the live canvas wins over the snapshots.

## Screens
| Board | Shows | Milestone |
|---|---|---|
| 1 · Decision Workspace (`Main.dc.html`) | Top bar (workspace, data sync, privacy badge, service health); left: Advisor conversation and voice controller (PTT/full-duplex, waveform, mic); centre: decision header with reversibility tag, KPI cards with lineage chips, runway chart (base vs scenario, amber "under 3 months of cash" band, zero-cash marker) with live sliders and a Monte Carlo range, pre-mortem and Scout cards; right: compact agent rail | M0 shell, M4 |
| 2 · Agent Activity (`AgentActivity.dc.html`) | Planner team proposal with editable briefs and Approve / Run locally; local and cloud slot usage; agent cards (type, brief, current step, progress, status, local/cloud badge, cancel/re-run); Gantt timeline view | M4 (backend events in M3a) |
| 3 · Decision Memo & Priorities (`Memo.dc.html`) | 2×2 priority matrix (value × feasibility, bubble = cost, founder weights); memo on a paper-style sheet with key numbers and lineage IDs, options and rejected alternatives, predictions for calibration, kill criteria, wikilinks, export .md/PDF | M4 |

## Design tokens ("Graphite & Signal")
| Token | Value | Use |
|---|---|---|
| `--bg` | `#0E1116` | app background |
| `--panel` | `#11151B` | side panels, top bar |
| `--card` | `#161A21` | cards |
| `--border` | `#262B35` / `#2A303B` | card and control borders |
| `--text` | `#E6E8EC` | primary text |
| `--text-muted` | `#9AA3B2` | labels (passes 4.5:1 on `--card`) |
| `--signal` | `#F2A93B` | amber accent: scenario, running, attention, danger band |
| `--signal-soft` | `#F2C77A` | amber text on dark |
| `--info` | `#7FB2F5` | base series, links, lineage chips |
| `--ok` | `#7FDCB8` | done, local, healthy |
| `--paper` | `#F6F4EE` | decision memo sheet |
| Fonts | Inter (UI), JetBrains Mono (numbers, lineage, code), Source Serif 4 (memo body) | |
| Radius | 8 (controls), 10–14 (cards), 999 (chips) | |

Rules: every number uses the mono font and has a lineage chip; status is never shown by colour alone (always a text label);
touch targets are at least 40–44 px; there are no emoji.
