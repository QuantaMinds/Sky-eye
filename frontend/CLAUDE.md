# CLAUDE.md — Sky-eye Frontend (LeadLens UI)

Operating rules for the **Sky-eye/frontend** package. Read before editing. These rules are **mandatory** — no exceptions without an explicit override from the user in the current conversation. They mirror the root `Sky-eye/CLAUDE.md` and apply specifically to the Vite + React + TypeScript codebase in this folder.

---

## Stack (locked 2026-05-18)

- **Vite** (build tool) — not Next.js
- **React 19** + **TypeScript**
- **Tailwind v4** via `@tailwindcss/vite` plugin (CSS-only config)
- **shadcn/ui** (slate base, CSS variables)
- **React Router v7** (`react-router-dom`)
- **axios** for backend HTTP calls
- **Vitest** + **React Testing Library** for tests

Backend lives at `../api/` (FastAPI). Dev base URL: `http://localhost:8000`.

---

## Rule 1 — File size: <100 LOC or 1 module

Every file MUST satisfy one of:

- **Under 100 lines of code** (blank lines and comments don't count toward the limit, but be honest about it), OR
- **Exactly one cohesive module** — one component, one hook, one helper, one responsibility.

If a component grows past 100 LOC and isn't a single tight unit, **split before committing**:

- Extract child components into their own files (`<DimensionCard>`, `<VerifyLink>`, `<ScoreBadge>` — one per file).
- Extract custom hooks (`useScoreLead`, `useAddressSearch`) into `src/hooks/`.
- Extract pure helpers (formatters, type guards, URL builders) into `src/lib/`.
- Prefer many small focused files over one large file.

## Rule 2 — Tests must pass before moving on

Every phase, every feature, every code change MUST pass its test cases before being marked done or moving to the next phase. Do not advance with red tests.

- Unit tests with **Vitest** for hooks and helpers (`*.test.ts`).
- Component tests with **React Testing Library** (`*.test.tsx`) — assert on what the user sees, not implementation details.
- If a test is wrong, fix the test in the same change and explain why in the commit. Don't just delete it.

## Rule 3 — Truth-first: never display fabricated values

The backend can return `null` or `source: "unavailable"` for any dimension. The UI MUST surface that honestly.

- **`null` score** → render a ghost card, a dash (`—`), or an explicit "Phase 2 coming soon" placeholder. **Never** render `0`, `0.5`, or a fake-looking real number.
- **`source: "mock"` or `"unavailable"`** → show a visible badge/note so the user knows the value isn't real.
- **Loading state** → distinct from "unavailable". Use a skeleton, never a placeholder number.
- **Error state** → show the error clearly, do not silently fall back to a default score.

Mirrors backend Rule 3. Fabricated values dressed as real data are worse than no data.

## Rule 4 — Easy to modify and test

The whole point of small files + tests is that you (or the next contributor) can change one thing without breaking three others. So:

- **Pure components** wherever possible. Side-effects go in hooks.
- **Named exports** (not default exports) so refactors are greppable.
- **Props over context** unless three+ levels of drilling justify a provider.
- **No god-components.** A page is a layout + a handful of named children, not a 400-line `<HomePage>` with all state inline.
- **No inline mega-objects.** Demo data, dimension metadata, URL builders — all go in `src/lib/` so tests can import them without rendering React.

## Rule 5 — Data quality is the highest priority, and it is NOT the same as tests passing

**Tests passing ≠ correct display.** Both gates are required:

| Gate | What it checks | How to verify |
|---|---|---|
| **Tests pass** | Components render, contracts hold, no console errors | `npm test` is green |
| **Data quality** | The right number is in the right place, in the right units, attributed to the right source | Manual inspection, run the dev server, click through with real backend responses |

Examples of "tests pass, UI is wrong" — watch for all of these:

- Score badge shows `0.83` but the user is on the page for a *different* APN (stale params, race condition).
- Dimension shows `1.0` because the backend returned `null` and `Number(null) === 0` was rendered.
- "Verify on LA Assessor Portal" link uses unformatted AIN (`1234567890`) instead of dashed (`1234-567-890`) → portal returns "not found".
- kWh vs MWh / sqft vs sqm mismatch — number is right but the unit label is wrong.
- Map centered on the wrong lat/lng because the result page didn't refetch when the URL changed.

**Every page MUST be visually verified against a real backend response before being marked done.** Green Vitest is the floor, not the ceiling.

---

## Layout (target)

```
frontend/
├── public/
├── src/
│   ├── main.tsx                 React entry
│   ├── App.tsx                  Router + layout wrapper
│   ├── index.css                Tailwind v4 import + globals
│   ├── pages/                   Route-level components (one file per route)
│   │   ├── Landing.tsx
│   │   ├── ScoreResult.tsx
│   │   └── Batch.tsx
│   ├── components/              Presentational components (one per file)
│   │   ├── ui/                  shadcn/ui generated components
│   │   ├── DimensionCard.tsx
│   │   ├── ScoreBadge.tsx
│   │   ├── VerifyLink.tsx
│   │   └── DemoCard.tsx
│   ├── hooks/                   Custom hooks (one per file)
│   │   ├── useScoreLead.ts
│   │   └── useAddressSearch.ts
│   ├── lib/                     Pure helpers (one concept per file)
│   │   ├── format.ts            formatAIN, formatScore, etc.
│   │   ├── verify-urls.ts       Assessor / Sunroof / Census link builders
│   │   ├── demo-data.ts         Hardcoded JSON for landing page demo cards
│   │   └── api.ts               axios instance + typed score-lead call
│   └── types/                   Shared TS types matching backend Pydantic models
│       └── score.ts
└── tests/                       Vitest specs (mirror src/ layout)
```

## Run

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173
npm test             # Vitest
npm run build        # production bundle
```

Set `VITE_API_BASE_URL=http://localhost:8000` in `frontend/.env` (or `.env.local`) so axios knows where to find the FastAPI backend.

---

## Reminders

- The root `Sky-eye/CLAUDE.md` still governs the backend. This file governs anything under `frontend/`.
- When in doubt about a dimension's meaning, source, or units, **read the backend file** for that dimension under `../api/services/dimensions/` rather than guess.
- Verification hyperlinks are the killer feature. Every claim on the result page must link to its authoritative source (LA Assessor portal, Project Sunroof, data.census.gov, etc.) opening in a new tab.
