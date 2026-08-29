# UIUX_SKILLS_MAP

Which skills in `SKILLS_ALL/` are used, where, and — as importantly — which are
rejected and why. The directive is explicit that skills are to be *selected and
combined*, not applied wholesale.

---

## What is actually in SKILLS_ALL

Five separate collections, not one library:

| Collection | Contents | Verdict |
|---|---|---|
| `.cursor/skills/ui-ux-pro-max/` | Queryable CSV design database + `search.py` | **Primary reference** |
| `ui-ux-pro-max-skill/` | Fuller upstream repo: `motion.csv` (GSAP), `google-fonts.csv`, richer palettes, `stack/design-audit.mjs` | **Used for motion + QA** |
| `agent-skills/` (Vercel) | `react-best-practices` (70 rules), `composition-patterns`, `web-design-guidelines`, `react-view-transitions` | **Used for engineering** |
| `bencium-claude-code-design-skill/` | 17 plugins; relevant: `bencium-controlled-ux-designer`, `design-audit`, `typography` | **Used selectively** |
| `claude-marketplace/` | AccessLint WCAG 2.2 skills | **Used as the a11y gate** |
| `.agents/skills/daisyui/` | daisyUI component library | **Rejected** — see below |

---

## Queries actually run

Not paraphrased — these were executed and their output shaped the design system below.

```bash
cd SKILLS_ALL/.cursor/skills/ui-ux-pro-max
python3 scripts/search.py "B2B enterprise commercial operations financial dashboard \
  data-dense approval workflow" --design-system -p "DealFlow360" -f markdown
python3 scripts/search.py "data-dense dashboard enterprise operations" --domain style -n 3
python3 scripts/search.py "financial dashboard fintech b2b saas enterprise" --domain color -n 6
python3 scripts/search.py "professional corporate dashboard data precise neutral" --domain typography -n 4
python3 scripts/search.py "table form accessibility loading empty state error" --domain ux -n 12
python3 scripts/search.py "trend comparison funnel part-to-whole waterfall gauge risk" --domain chart -n 8
python3 scripts/search.py "table form dialog sheet chart data" --stack shadcn -n 10
```

### Where the skill's own recommendation was overruled

`--design-system` returned the **Enterprise Gateway** landing pattern, **Dark
Mode (OLED)** styling, and **Fira Code / Fira Sans** typography.

Rejected, with reasons:

- *Enterprise Gateway* is a marketing-site pattern — "hero video", "client
  logos", "Contact Sales CTA". DealFlow360 is an authenticated operations tool;
  it has no hero.
- *Dark Mode (OLED)* was matched on the word "dashboard". Its own row lists its
  best uses as "night-mode apps, coding platforms, entertainment". Finance and
  operations users work in lit offices and print and share screens.
- *Fira Code* is a **programming ligature font**. Using it for headings in a
  commercial product is a category error.

This is precisely the "do not blindly apply every skill" case in §2. The
narrower `--domain style` query returned the row that actually fits.

---

## The rows that are used

### Base: `styles.csv` → "Data-Dense Dashboard"

Its design-system variables are adopted almost verbatim, because they encode
the density this product needs:

```
--grid-gap: 8px   --card-padding: 12px   --font-size-small: 12px
--table-row-height: 36px   --sidebar-width: 240px   --header-height: 56px
```

Also taken: 12-column grid, sticky table headers, row highlight on hover,
sortable tables, real loading states, export.

### Navigation: `styles.csv` → "Drill-Down Analytics"

Directly matches quote → version → line and deal → quote → approval:
breadcrumbs, context preservation, deep-linkable state, `--level-indent: 24px`,
`--expand-duration: 300ms`.

### Alerting: `styles.csv` → "Real-Time Monitoring"

Used **only** for the Control Tower's severity semantics — critical `#DC2626`,
warning, normal, status dots. Its pulse/blink animation and WebSocket
assumptions are dropped: the backend has no push channel, so a live-pulsing
indicator would be theatre.

### Colour: `colors.csv` → "B2B Service"

```
Primary #0F172A   Secondary #334155   CTA #0369A1   Background #F8FAFC   Text #020617
```

Chosen over "Financial Dashboard" (dark) and "SaaS (General)" (`#2563EB` — the
exact generic SaaS blue §9 rules out). Navy carries authority without reading
as a template.

### Typography: `typography.csv` → "Corporate Trust" (Lexend / Source Sans 3)

Its row lists "enterprise, government, healthcare, finance,
accessibility-focused". Lexend is specifically designed for reading
proficiency. A third face is added for numerals — see the design system below.

### Charts: `charts.csv`

| Need | Row used | Chart |
|---|---|---|
| Gross → discount → net → cost → margin | Cumulative Changes | **Waterfall** (increase `#4CAF50`, decrease `#F44336`) |
| Risk score vs escalation threshold | Performance vs Target | **Bullet** with threshold marker |
| Pipeline by stage | Funnel/Flow | **Funnel** with conversion % |
| Revenue trend | Trend Over Time | **Line**, 20% fill |
| Discount distribution per rep | Compare Categories | **Bar**, sorted descending |

The waterfall is the single most valuable chart here: it turns the four numbers
`/calculate` returns into the story of where the money went.

### Rejected chart guidance

Pie/donut for part-to-whole. One-time vs recurring is two values; a donut of two
slices is decoration. A labelled split bar is used instead.

---

## Engineering skills

### `agent-skills/skills/react-best-practices` (70 rules, 8 groups)

| Rule area | Applied to |
|---|---|
| `async-*` — parallelise, no waterfalls | Quote detail fires version + policy-results + impact + recommendations concurrently |
| `bundle-*` — no barrel imports, dynamic import heavy widgets | Charts and the export dialog are lazy |
| `rerender-*` (15 rules) — derive in render, don't sync with effects | Totals come from the `/calculate` response; never mirrored into state |
| `js-*`, `rendering-*` | Long tables use `content-visibility`; filters use `useDeferredValue` |

### `agent-skills/skills/composition-patterns`

`architecture-avoid-boolean-props` and `architecture-compound-components` decide
the component API. A `<DataTable>` with `isCompact`/`showFilters`/`showExport`
booleans is exactly the trap; compound children are used instead. `react19-no-forwardref`
applies — React 19 passes `ref` as a normal prop.

### `bencium-controlled-ux-designer`

Concrete thresholds adopted: 4–5 neutrals + 1–3 accents; hover darkens 10–15%;
disabled at 40–50% opacity; ≤3 type faces and ≤3 weights each; body 16px;
line-height 1.5; measure 45–75ch; 4px spacing base; motion 100–300ms;
**material honesty** — borders and padding rather than decorative shadows,
which suits a dense product where every shadow costs a pixel of clarity.

Its "always ask before every visual decision" protocol is not followed
literally — this document *is* the decision record.

### `ui-ux-pro-max-skill/data/motion.csv` (GSAP tiers)

Only the **Subtle** tier: hover 150–200 ms `power1.out`, page transition
200–300 ms, skeleton loop 1200–1600 ms. Parallax and complex scroll reveals are
rejected outright. Implemented with CSS and the View Transition API rather than
by adding GSAP — §26 forbids unnecessary dependencies.

### `agent-skills/skills/react-view-transitions`

Used for quote list → quote detail and approval inbox → approval detail, where
shared-element continuity aids comprehension. Its own guidance that tabs should
fade rather than slide is followed.

### `claude-marketplace` → AccessLint

The WCAG 2.2 gate in Phase 12:

```bash
npx -y @accesslint/cli@latest scan <url> --port "$PORT" --format json
```

### `ui-ux-pro-max-skill/stack/scripts/design-audit.mjs`

Automated visual QA across 6–7 viewports (360→1920), catching overflow, missing
focus styles, unsized media, contrast risk, and tap targets under 44×44.
This is what makes §33's "visual QA must be real" checkable rather than asserted.

---

## Rejected, and why

| Skill | Reason |
|---|---|
| **daisyUI** | Its own instruction is "even if the user does not request it, use it." It is a themed component library with a strong opinionated look — the definition of the template aesthetic §9 forbids. |
| **bencium-innovative-ux-designer** | Its description excludes routine product UI and forbids SVG during invention. It is for inventing a brand identity, not building an operations console. |
| **bencium-impact-designer** | Tone list is mostly marketing (vaporwave, Memphis). Its "Data-Driven Dashboard" and "Neo-Swiss Grid" tones are already covered by the rows above. |
| **`--design-system` composite output** | Overruled above: wrong pattern, wrong theme, programming font. |
| **`landing.csv`** (30 landing patterns) | No landing page in an authenticated tool. |
| **Real-Time Monitoring animations** | No push channel exists. Pulsing a static number is fake liveness. |
| **`deploy-to-vercel`, `vercel-cli-with-tokens`** | Not a deployment task. |

---

## Design system direction

Everything below traces to a row above or to a verified backend fact.

### Type

Three faces, each with a job:

| Role | Face | Rationale |
|---|---|---|
| Headings / UI | **Lexend** | "Corporate Trust" row; designed for reading proficiency |
| Body / labels | **Source Sans 3** | Same row; holds up at 12–13px table sizes |
| **Numerals** | **IBM Plex Mono** (tabular) | Not from the CSV — required by the data. Money must align on the decimal in a column, and `132710.00` vs `124310.00` must be scannable. Applied to money, percentages, quantities, risk scores, and IDs only |

Financial figures render with `font-variant-numeric: tabular-nums`.

### Colour

Neutral navy ramp (`#020617` → `#F8FAFC`) plus **semantic colour reserved for
meaning**. Colour is never decorative here — a red number always means margin
or risk, never emphasis.

| Token | Meaning | Source |
|---|---|---|
| `--risk-none` / `low` / `medium` / `high` / `critical` | `RiskBand` enum, 5 values | backend enum |
| `--policy-passed` / `warning` / `violated` / `n-a` | `PolicyResultStatus`, 4 values | backend enum |
| `--severity-low` → `--severity-critical` | `Severity`, 4 values | backend enum |
| `--margin-healthy` / `--margin-thin` / `--margin-breach` | relative to the `MIN_MARGIN` policy threshold | backend policy |
| `--state-draft` … `--state-superseded` | `QuoteVersionStatus`, 8 values | backend enum |

Deriving the palette from enums rather than inventing a swatch set means the UI
cannot drift from the domain. Every status colour is paired with a label or icon
— never colour alone (`ux-guidelines.csv`, severity High).

### Space, shape, depth

4px base (4/8/12/16/24/32/48). Radius 6px controls, 8px containers — restrained,
because heavy rounding at this density reads as a toy. Borders over shadows
(material honesty); elevation only for genuinely floating layers (dialog, sheet,
popover).

### Motion

150–200 ms hover, 200–300 ms transitions, `prefers-reduced-motion` honoured
throughout. Motion is spent almost entirely on one thing: **the stale-approval
transition**, where §17 asks for a state change that is impossible to miss.

---

## Skill → screen assignment

| Screen | Skills combined |
|---|---|
| Command Center | Data-Dense Dashboard + Real-Time Monitoring severity (no animation) + bullet/funnel charts |
| Quote Builder | Data-Dense + shadcn Form/RHF/Zod + composition-patterns + **waterfall** + tabular numerals |
| Approval Detail | Drill-Down Analytics + view-transitions + bullet chart for risk vs threshold |
| Stale Approval / Diff | Motion (Subtle tier) + semantic colour + typography rhythm — the one screen that spends its motion budget |
| Deal Health | Data-Dense + severity semantics + per-signal point deductions |
| Fulfilment | Split-bar allocation per warehouse; the backend's own `explanation` string as the caption |
| Tables (quotes, invoices, products, audit) | shadcn DataTable + TanStack + `content-visibility` + sticky headers + responsive horizontal scroll |
| Admin forms | shadcn Form + Zod + `ux-guidelines.csv` error placement (below the input, `role="alert"`) |
| Customer Portal | Deliberately lower density, wider measure, larger type — reads as a proposal, not a console |
