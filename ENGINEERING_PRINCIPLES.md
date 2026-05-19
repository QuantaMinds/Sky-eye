# Engineering Principles — EYE-Lead / Sky-eye

> These six rules don't prevent failures. They turn failures into faster recoveries and durable lessons. Every rule is named after a failure that already happened on this codebase.

> **When to read this:** before starting a new phase. Re-read the rule that applies when a forensic finding lands. The full document takes 8 minutes; that's the cost of every phase shipping wrong.

Six rules. Not commit-required reading. A touchstone for anyone working on this codebase — including future-you on a different day. Each rule has a name, a one-sentence shape, the **why** (the failure mode it exists to prevent), the **how to apply**, and a real codebase example.

When you see one of these patterns playing out in a task, refer back here. When you find yourself violating one to ship faster, stop — the cost of the violation is bigger than the cost of the delay, every time.

These six complement, not replace, `CLAUDE.md` (which contains the four hard rules: file size, tests-must-pass, truth-first, data-quality-as-separate-gate). CLAUDE.md is the law; this is the operating culture.

---

## 1. Tests passing ≠ data quality. Budget a forensic pass on every customer-facing deliverable.

A green pytest run only proves the plumbing works. It does not prove the answers are right.

**Why:** every phase forensic pass on this codebase has found 3–8 defects with the test suite green at ship. Phase 5 forensic (commit `0b84c1a`) found seven critical silent failures while all 172 tests passed — including a city literal mismatch that would have made the labeling tool return zero candidates, a SELECT missing a column the classifier prompt depended on, and an endpoint that claimed an audit trail but wrote zero rows.

**How to apply:**
- Every phase ships with a manual forensic pass. Not "code review" — *running the live pipeline against real inputs and inspecting what lands where.* Probe the boundaries.
- Forensic defects cluster into three patterns (see Rule 6 below). The dominant one (mocks masking boundary realities) is fixed by methodology, not more unit tests.
- Schedule periodic re-runs against live upstream services — silent dependency drift (e.g., Sentinel-2 QA60 band deprecated 2022-06) only surfaces this way.

**Example:** Phase 4 shipped reportedly "109/109 green." Re-run at the same commit returned `6 failed, 135 passed`. The full suite hadn't been verified end-to-end at ship time. Phase 5 surfaced this on day one and the test methodology was tightened (Rule 2 below).

---

## 2. Ship reports must quote the full pytest output verbatim. Partial-run greens lie.

"All tests pass" without a captured pytest command and footer is unfalsifiable.

**Why:** when reporting a phase as green, run `pytest tests/ --tb=no -q` (the full suite) and paste the verbatim `N passed, M failed` footer into the commit message. Never summarize ("109/109"); never claim "green" from a subset run. Phase 4's "109/109" claim turned out to be a partial run that missed six failures elsewhere.

**How to apply:**
- Every phase commit message includes the literal pytest tail: `=== N passed in Xs ===`.
- If only a phase-specific subset was run, say so explicitly: `test_phaseN.py: 7/7 passed; full suite NOT run this turn`.
- Before opening a new phase, run the full suite once and reconcile any pre-existing red. Those failures become a Rule 2 blocker for the new phase, not a footnote.

**Example:** Phase 5 foundation commit (`7259a0d`) included the verbatim tail. The audit-fix commit (same) reconciled 5 of 6 quietly-red Phase 0–4 tests before Phase 5 detection landed. The detection commit (`d3d78a7`) shipped with `171 passed, 1 skipped, 0 failed` — the first time the full suite was actually green since the codebase started.

---

## 3. Unknowns surface as `None`. Never substitute a plausible constant.

If we don't know a value, the response says so. `None`, `null`, `source: 'unavailable'`. Never a "neutral" `0.5`, never a `True`, never a `0.0` that means "I don't know" but reads as "definitely zero."

**Why:** the canonical failure on this project — `100 Long Beach Blvd` (Edison Theatre, a commercial landmark) scored `0.82` with a narrative claiming "confirmed homeownership (1.00)" because four of seven dimensions were hard-coded constants. The pipeline ran. The answer was a lie. The customer would cross-check, find the lie, and never trust the platform again.

**How to apply:**
- Optional fields default to `None`, never to a midpoint or sentinel.
- Tri-state where appropriate: `True / False / None` (e.g., `has_permit` — None means "we don't have coverage to answer," NOT "no permit found").
- Re-normalize, don't impute: when a scoring dimension is `None`, drop it from the sum and renormalize the remaining weights. Don't pretend the dimension scored 0.5.
- Every public response includes a `source` field per dimension. `source='unavailable'` is a first-class value, not an error state.
- Matched-pair tests for any conditional gate: fires-True, fires-False, AND input-None-drops-from-score. Single-direction tests pass while over-suppressing real signal.

**Example:** `api/services/permit_matcher.py` tri-state. If `parcels_raw.permits` has zero rows for the LB jurisdiction in the requested window, `has_coverage()` returns False and `has_permit()` returns `None` for every parcel. The confidence pipeline drops the permit gate and re-normalizes the remaining four. NOT `False`, which would have inflated every parcel as "unpermitted construction" — exact Edison Theatre pattern, just in a different domain.

---

## 4. Pair every deferral with a measurable trigger.

"We'll do it later" atrophies. "We'll do it when X is true" is durable.

**Why:** deferred work without a trigger becomes invisible. Six months on, no one remembers the rationale, no one knows whether the trigger has fired, and the deferred code path either silently breaks something or silently consumes resources nobody is tracking. Every deferral on this project is paired with a concrete signal: a metric crossing a threshold, a customer asking, a date, a feature flag.

**How to apply:**
- When deferring: name the trigger in the commit message and a comment at the deferral site.
- Triggers must be observable: "when batch size routinely exceeds 5,000," "when a customer asks for last-week's report," "after the 2024 NAIP flight lands in EE." Not "later" or "eventually."
- For ML thresholds: "when N≥100 hand-labeled cases exist" is the trigger for calibration. The code carries a comment flagging it.

**Example:** `api/services/multimodal_classifier.py` is gated behind the cheap AlphaEarth distance filter. Per-key cache deduplication on `ttl_cache.get` is explicitly deferred — the comment in `api/middleware/ttl_cache.py` lists the three triggers that activate it (batch size > 5,000; Solar API cost concern; >10% duplicate keys in a customer batch).

---

## 5. For ML or scoring pipelines, separate "artifact shipped" from "claim validated."

Two gates, two completion criteria. Building the pipeline is the first gate. Quoting a precision number is the second. Conflating them produces lies.

**Why:** every ML pipeline can be demoed live ("input X, output Y") the moment the code runs end-to-end. That demo is honest. The precision/recall number against an incumbent ("beats EagleView's 8%") requires an independent labeled set of N ≥ 100 cases, labeled by a non-author. Author-as-labeler has structural confirmation bias; edge cases drift toward what the model would output, and "ground truth" becomes a reflection of the model, not reality.

**How to apply:**
- Ship the artifact; do NOT quote a precision number in customer-facing material (deck, email, UI, application form) until calibration has run.
- Demo without a number is honest. Number without validation collapses on first customer skepticism, and customer skepticism is the default state.
- The pipeline's threshold constants (e.g., AlphaEarth distance > 0.4, classifier confidence > 0.7) are starting points, NOT tuned parameters, until calibration runs. Flag them in code with the trigger condition.
- The validation set must be ≥ 100 cases, labeled by a non-author. Any single labeler should account for ≤ 80% of rows (mixed labelers reduce bias).

**Example:** `api/services/confidence_pipeline.py` carries an `UNVALIDATED THRESHOLDS` comment at the top declaring the three thresholds are intuition-chosen and must be re-tuned once the ≥100-case set exists. `scripts/benchmark_phase5.py` enforces this policy automatically — runs under N=100 print a "SMOKE RESULT — DO NOT use in a deck/email/UI" header.

---

## 6. Boundary realities require live probes. Mocks mask the failures they hide behind.

When a test mocks a BigQuery response, an Earth Engine coverage call, an HTTP return — it tests the code on the inside of the boundary while *assuming* the outside behaves as specified. The assumption is what fails.

**Why:** forensic-pass defects cluster into three patterns. Pattern 1 (mocks masking boundary realities) typically accounts for 5+ of every 7 defects. Pattern 2 (untested edge cases) is the standard happy-path gap. Pattern 3 (silent dependency drift — upstream changes invalidating correct code) is the most pernicious because no test design catches it; only periodic forensic re-runs against live services do.

**How to apply:**
- Recognize the pattern when fixing a forensic defect. Pattern 1 means *change the methodology* (probe the boundary directly), not add more unit tests against the same mock.
- For ML/external-service code, add a `scripts/_phase{N}_forensic.py` companion. Single-trace probe against real services. Run it on every phase ship.
- Pattern 3 is the case for a quarterly forensic re-run against live upstream services even when no code has changed.

**Example:** Phase 5 forensic pass found:
- *Pattern 1 (5 defects):* `city='Long Beach'` matched 86 of 103,478 LB parcels; the SELECT was missing `use_subcategory`; the endpoint never wrote to `leadlens.change_events`; the `taxlens_labels` DDL was never executed; NAIP California had no 2024 imagery. Every one of these had unit tests that passed because the test boundary was the failure boundary.
- *Pattern 2 (1 defect):* `float('nan') > 0.4` is False in Python — NaN distance silently voted "counter-evidence" in the embedding gate.
- *Pattern 3 (1 defect):* Sentinel-2 QA60 band deprecated 2022-06; SR Harmonized scenes have it all-zeros, silently disabling the cloud mask. No test could have caught this without checking actual recent S2 data.

---

## Beyond these six

The full memory directory at `C:\Users\dhanu\.claude\projects\D--EYE-Lead-Sky-eye\memory\` carries additional operational lessons collected across sessions: explicit-defense-not-accident, cluster-aware deferral, BQ streaming-buffer vs DML, gcloud project hygiene, bulk-vs-detail enrichment, two-page PDF overflow contract, parser-contract is load-bearing, and more. Those are project-specific operational rules; the six above are the cultural shape.

When onboarding a contributor: this document plus `CLAUDE.md` is the floor.
