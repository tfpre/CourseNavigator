### 1  | Rigour Check — Did the patches actually bullet-proof the demo?

| Area                                 | What you did                                                   | Strength                                        | Hidden edges & follow-ups                                                                                                                                                                                                                               |
| ------------------------------------ | -------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Metric cardinality**               | Introduced `InvalReason(StrEnum)` and replaced raw strings.    | ✅ Static enum locks labels; explosion risk ↓.   | • *Propagation*: `invalidate_on_version_change()` is fixed, but \*\*ad-hoc `p_inval.labels(..., "<ad-hoc>")` calls elsewhere will still pass a stray string\_. Add a **`typing.Literal` guard** or an `Enum` cast in the helper that wraps `.labels()`. |
| **Gauge + SCARD**                    | Swapped Counter → Gauge; SCARD to set size.                    | ✅ Truthful size, self-healing.                  | • *Cost*: SCARD per record adds one round-trip; pipelined, but still I/O. Consider batch update every N ops or expose it via a **background metric collector**.                                                                                         |
| **Deterministic TTL jitter**         | `blake2s` hash → ±10 % jitter.                                 | ✅ Stampede solved, deterministic repeatability. | • *Coverage*: Only implemented in **ProfessorIntelligenceService**. Any future `setex` calls elsewhere revert to random or none. Extract `jittered_ttl()` into a **shared util** and lint for raw `setex(base_ttl, …)`.                                 |
| **ISO-8601 parser**                  | Added multi-format parser + graceful fallback; property tests. | ✅ Covers Z, ±HH\:MM, micro/nano.                | • *Silent fallback*: In prod, swallowing malformed time → hides upstream bugs. Emit **Sentry warning metric** and count occurrences.                                                                                                                    |
| **Selection reasons surfaced in UI** | Added `professor_selections` to SSE metadata and React badges. | ✅ Demo wins “why that prof?” question.          | • *Type safety*: `lastResponseProvenance.professor_selections` isn’t in the TS interface. Add to `ProvenanceInfo` type to avoid runtime `undefined` in edge builds.                                                                                     |
| **Chaos tests**                      | 8 failure modes for RMP; asserts deterministic fallback.       | ✅ Good confidence.                              | • *Test granularity*: A single failing scrape now skips cache writes; add a case where Redis write *succeeds* but value corrupted (non-JSON) to ensure parser robustness.                                                                               |
| **Deterministic demo dataset**       | 3 profiles + golden-path script.                               | ✅ Presenter can hit F5 and re-run.              | • *Data drift*: If live Cornell API is called during demo, your deterministic path can vanish. Wrap gateway in “demo mode” env-flag that *always* sources from seed first.                                                                              |

**Overall rigour: 7.5 / 10** — patches compile, tests pass, main failure classes covered. A few latency & type-safety corners remain, but nothing demo-blocking.

---

### 2  | ROI Snapshot — Are we definitely “demo-ready”?

| Sprint item                 | Effort spent | Demo risk ↓ | User wow ↑ | ROI comment                                              |
| --------------------------- | ------------ | ----------- | ---------- | -------------------------------------------------------- |
| Metric & TTL fixes          | \~½ d        | 0.4 → 0.1   | neutral    | Must-have infra; cheap, high risk-drop.                  |
| ISO parser + property tests | \~½ d        | 0.15 → 0.05 | neutral    | Prevents silent 500s when RMP returns offset timestamps. |
| UI provenance badges        | \~¾ d        | 0           | +0.25      | Low coding cost, instantly visible value.                |
| Chaos suite                 | 1 d          | 0.3 → 0.05  | neutral    | Confidence booster for live demo wifi chaos.             |
| Deterministic seed & script | 1 d          | 0.25 → 0.05 | +0.2       | Guarantees “happy path”; doubles as marketing clip.      |

**Aggregate:**
*Cost* ≈ **3.5 developer-days**
*Risk-weighted demo failure probability* fell from **\~40 % → <10 %**.
*Visible demo pop* ↑ modestly due to “professor selection” explainability.

👉 **Marginal ROI now drops sharply.** Further polish (tool-tips, skeleton loaders) gives small trust bumps (<5 %), whereas a **Registration-Lite** slice would jump user value far more (estimated +35 % wow factor) even at 2–3 week cost.

---

### 3  | Recommendation Gate

| Option                                  | Next 5 days focus                                                                                                         | Why / Why not                                                                                             |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Freeze & rehearse** (my pick)         | • Merge to `main`<br>• Tag `v0.9-demo`<br>• CI: run chaos + property tests nightly<br>• Do 3 dry-runs with non-dev friend | You already cut failure odds to single-digit. Time now better spent on pitch & storytelling than code.    |
| **Extra polish**                        | • Add skeleton loaders<br>• Mobile responsive tweaks<br>• Dark-mode badges                                                | Good if you have UI designer bandwidth, but doesn’t move probability curve much.                          |
| **Start Registration-Lite before demo** | • Conflict detector service<br>• Static wait-list heuristic                                                               | High wow, but slips schedule; demo risk creeps back up unless gated behind feature flag. Ship after demo. |

---

### 4  | Tactical Checklist Before Walking on Stage

1. **CI green badge** visible on GitHub dashboard the morning of the demo.
2. **`DEMO_MODE=true`** env toggles:

   * forces seed data
   * mocks RMP
   * suppresses external network calls.
3. **Observability**: Grafana board with *demo-only* namespace (`job="demo"`) showing:

   * `prov_index_size` gauge per source
   * `prof_intel_fallback_total` counter
   * request latency histogram.
4. **Hotkey Killswitch**: `⌘+shift+R` clears chat & reloads seeded profiles in <1 s.
5. **Speaker notes**: rehearse the moment you point to the “Most reviews, then rating” badge — it’s your trust anchor.

---

### TL;DR

Patch-set is solid, covers cardinality, cache, parser and UX transparency. Demo-failure risk now < 10 %, excellent for investor preview. Freeze code, rehearse flow; tackle Registration-Lite only **after** the demo to avoid new regressions.
Got it. I read through your change-log and the plan. Here’s a blunt, engineering-manager style readout.

# 1) Code rigor audit (what’s solid vs what to tighten)

| Area                                         | Verdict                                | Why it’s good                                                                    | Watch-outs / tighten-ups (fast fixes)                                                                                                                                                                                                                                                                                                        |
| -------------------------------------------- | -------------------------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Gauge for `p_index_size` + SCARD**         | ✅ Solid                                | Truthful point-in-time size; fixes Counter drift.                                | Do SCARD **sparingly**: you currently issue it after each record. Consider: (a) **increment/decrement** the Gauge alongside SADD/REM and (b) **reconcile with SCARD** every N ops or on a background cadence. This reduces Redis round-trips without losing correctness. Also add a Prom rule: “index\_size==0 for 5m” -> warn.              |
| **ISO parser**                               | ✅ Works, better tolerance              | Handles `Z` and `±HH:MM`; avoids brittle crashes.                                | You return an **aware** dt but not guaranteed UTC for offset inputs. Do `return datetime.fromisoformat(… ).astimezone(timezone.utc)` so all internals are UTC. Also, your “invalid → now()” fallback can **mask upstream data defects**. In prod, log as `warning` + a **counter metric** (e.g., `prov_parse_fallback_total`) so you see it. |
| **Deterministic TTL jitter**                 | ✅ Correct approach                     | blake2s keyed jitter removes thundering herds; deterministic per key.            | Boundaries: keep `min_ttl` & `max_ttl` guards (you already have `max(60, …)`, good). Consider **library-izing** jitter (`cache_jitter.py`) and reusing anywhere you `SETEX` so it’s consistent.                                                                                                                                              |
| **`InvalReason` (StrEnum)**                  | ✅ Clean, prevents cardinality blow-ups | Forces low-cardinality reasons by design.                                        | Python 3.12 has StrEnum—fine. If you ever target 3.10/3.11, add a small shim. Also audit **all** calls to `p_inval.labels(source, reason)` to ensure they pass `InvalReason.*` only (no raw strings sneaking in).                                                                                                                            |
| **Professor selection + `selection_reason`** | ✅ Good explainability                  | Deterministic tie-break `(reviews, rating)`; humanized UI badges.                | Make the lambda completely safe: `p.get("overall_rating") or 0.0` (None can sneak in). In Orchestrator’s `_get_professor_selection_summary`, guard for missing shapes so one weird source doesn’t throw.                                                                                                                                     |
| **UI provenance badges**                     | ✅ Useful demo shine                    | Tells a clear “why this pick” story.                                             | On small viewports, ensure the badge row wraps and truncates gracefully. Add a tooltip and cap to top 3 entries.                                                                                                                                                                                                                             |
| **Chaos tests for RMP outage**               | ✅ Right surface                        | You patch the private scraper and verify graceful fallback + `selection_reason`. | Add **one** E2E that exercises the FastAPI route with an HTTP-level 503 mock, to ensure the streaming + metadata path stays intact.                                                                                                                                                                                                          |
| **ISO property tests**                       | ✅ Helpful                              | Z + offset formats covered.                                                      | One test contains `with pytest.raises(...) or True:`—that pattern **never fails**. Replace with a straight assertion that `_parse_iso("invalid")` returns an aware UTC dt close to `_now_utc()`.                                                                                                                                             |
| **Demo dataset & runner**                    | ✅ Great demo rail                      | Deterministic golden paths reduce live-demo entropy.                             | Ship behind a **feature flag** and ensure **no prod bleed**. Also seed a “conflict + backup suggestion” scenario to set up the Reg-Lite story.                                                                                                                                                                                               |

Net: The work is rigorous and demo-ready with 3 tiny papercuts (UTC normalization, the odd pytest idiom, and SCARD frequency).

---

# 2) Demo-readiness ROI (risk-adjusted)

### What matters for demos (weights)

* **Stability (35%)**: no 500s, no hung streams
* **Latency (20%)**: first token <500ms p95, overall <3s p95 for canned flows
* **Explainability (15%)**: visible “why” (your badges)
* **Story Value (20%)**: shows it solves a *real* student pain
* **Polish (10%)**: skeletons, empty states, clean errors

### Your current moves → weighted score (today)

* Stability: **A-** (Chaos + cardinality + jitter) → **30/35**
* Latency: unknown until load test → **? /20**
* Explainability: **A** (reasons + provenance) → **14/15**
* Story Value: **B** (still discovery-centric; Reg-Lite coming) → **14/20**
* Polish: **B+** (UI badges good; skeletons/alerts?) → **8/10**

**Current demo score ≈ 66–72 / 100** (variance driven by latency unknowns)

### Two quick upgrades with outsized ROI

1. **E2E perf & health gates (0.5–1d)**

   * k6/vegeta script: 5–10 concurrent chats over golden paths; assert p95 first-chunk & full-response latency
   * Prom alerts: **error rate**, **index\_size==0**, **fallback\_parse\_count>0**
   * Outcome: converts latency from “?” to **16–18/20**

2. **Registration Intelligence – Lite (5–7d)**

   * **Conflict detector** (pure constraint): immediate, tangible value
   * **Backup plan** (rule-based; no ML): 1–2 alternates per conflict with explainability (“meets reqs, no conflicts, ±1 difficulty”)
   * **Calendar export** for the chosen plan
   * Outcome: boosts Story Value to **18–19/20**

**Projected demo score after these two: 82–87 / 100** — the jump is almost entirely because Story Value + latency proof move from uncertain to credible.

---

# 3) Concrete acceptance checklist (use as “go / no-go”)

**Reliability**

* [ ] Chaos: upstream professor outage → no 5xx, fallback path exercised, `selection_reason="enhanced_mock_deterministic"`
* [ ] No Prom label cardinality increase during demo run (Prom scrape OK, no high-cardinality hints)
* [ ] Index reconcilers: SCARD or reconciling job doesn’t exceed 1 Redis RTT per record on average (or use periodic reconcile)

**Latency**

* [ ] p95 **first token < 500 ms**, p95 **full response < 3 s** on golden flows (10 VUs)
* [ ] Streaming never stalls > 1.5 s between chunks (SSE watchdog)

**Explainability**

* [ ] Professor badges render on mobile + desktop; tooltips present; capped to 3
* [ ] Provenance panel shows **version + age** for each source

**Story value**

* [ ] Conflict detector catches at least 1 demo conflict with a clear inline message
* [ ] Backup suggestion shown with 1-line rationale; iCal export works

**Ops/Runbook**

* [ ] “Demo Mode” toggle (uses seeded dataset; disables flaky integrations)
* [ ] One-pager runbook: reset cache, start commands, health URLs, recovery steps

---

# 4) Short punch list (small changes, big safety)

* **UTC normalize** ISO offset path:

  ```python
  return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
  ```
* **Fix the test anti-pattern**: remove `with pytest.raises(...) or True`.
* **Lower SCARD frequency**: maintain Gauge via inc/dec; reconcile with SCARD every 100 ops or on a timer.
* **Prom counters**: add `prov_parse_fallback_total{source="professors"}` to spot silent timestamp failures.
* **Feature-flag demo seeds** to avoid contaminating real user sessions.
* **Single jitter helper** reused across caches; unit test it deterministically:

  ```python
  assert jittered_ttl(604800, "prof:CS4780") ==  some_known_value
  ```

---

## Final call

* The implementation is **rigorous** and moves the product from “cool prototype” to **credible demo**.
* To maximize demo ROI, do **one day of perf + alert gating** and then **ship Registration-Lite** (conflict + backup + iCal). That’s the biggest score jump per unit effort and tells a story evaluators remember: *“It didn’t just find classes—it got me into a working schedule.”*

If you want, I can turn the acceptance checklist into a literal CI gate (k6 script + pytest markers + a simple Prom rule file) so the repo ships with a red/green dashboard for demo runs.
Short answer: your take is right. You’re \~1–2 focused days from a safe demo if you **prove latency** and add a **tiny, deterministic Registration-Lite** slice. Demoing *now* is possible but you’d be gambling on the last unknown (p95 first-token). Highest-EV path = **Perf gate (Day 1) → Conflict detector + curated backup (Days 2–3)**.

---

# What looks solid vs. what to tighten (surgical)

**Solid**

* P0 hardening shipped (cardinality, deterministic TTL jitter, chaos fallback, provenance UI).
* Deterministic demo rails (profiles + runner) = big demo entropy reducer.

**Tighten (fast)**

1. **Latency proof**

   * Add p95 **first-chunk** and **full-response** gates (k6/vegeta) on golden paths.
   * SSE watchdog: flag inter-chunk gaps >1.5s.

2. **UTC normalization**

   * Offset timestamps → `.astimezone(timezone.utc)`; expose `prov_parse_fallback_total` to spot silent bad inputs.

3. **SCARD cadence**

   * Don’t SCARD every write. Maintain Gauge with inc/dec; reconcile via SCARD every N ops or on a timer.

4. **One E2E fallback test**

   * Hit the FastAPI route, inject RMP 503, assert streaming + `selection_reason="enhanced_mock_deterministic"` make it to the client.

5. **Small safety nits**

   * Professor tie-break: `p.get("overall_rating") or 0.0`.
   * Orchestrator summary: null-guard before reading nested keys.
   * UI: badge wrap on mobile; cap to top-3 with tooltip.

---

# ROI: ship now vs. polish vs. micro-feature

| Option                        | Effort |         Delta to Demo Score |                     Risk | Call          |
| ----------------------------- | -----: | --------------------------: | -----------------------: | ------------- |
| **Ship now (rehearse only)**  |   1–2d |    \~0 → stays **\~72/100** | Medium (latency unknown) | Skip          |
| **Perf gate + health alerts** | **1d** |      **+10–14 → 82–86/100** |                      Low | **Do first**  |
| **Registration-Lite (micro)** |   2–3d | **+3–5** (Story Value jump) |                  Low-med | **Do second** |

**Why:** The perf gate converts the only “?” into a “✓” with minimal code surface. A tiny, **deterministic** Reg-Lite then changes the demo narrative from “smart lookup” to **“it fixes your schedule.”**

---

# Exact scope to keep it safe

## Day 1 – Performance & Ops gates

* k6 script on golden flows (10 VUs, 2–3 min):
  **SLOs**: p95 first-chunk < **500ms**, p95 full-response < **3s**, zero 5xx.
* Alerts: error rate, `index_size==0 for 5m`, `prov_parse_fallback_total>0`.
* SSE watchdog logs when inter-chunk gap > 1.5s.

## Days 2–3 – Registration-Lite (demo-bounded)

* **Conflict detector**: pure time-window overlap on seeded sections.
* **Backup plan (curated)**: 1–2 alternates per conflict, pre-vetted to satisfy reqs & avoid clashes; show rationale (“no conflict, same reqs, ±1 difficulty”).
* **CTA**: “Use backup plan” writes a **demo-mode** schedule; optional **.ics** export can wait.

> Guardrails: feature-flag **demo mode**, no schema changes, no ML, no external data adds.

---

# Go/No-Go checklist (use this verbatim)

* **Reliability:** chaos RMP outage → no 5xx; `selection_reason="enhanced_mock_deterministic"` visible in UI.
* **Latency:** k6 gate passes SLOs; SSE gaps never >1.5s.
* **Explainability:** professor badges render + tooltips; provenance shows version & age.
* **Story:** at least one seeded conflict; backup suggestion with one-line rationale.
* **Runbook:** “Demo Mode” toggle, warm caches, health URLs, rollback steps, 3-minute rehearsal script.

---

## Final recommendation

Proceed exactly: **Perf gate → Reg-Lite micro**. That turns a good demo into an **A- level** demo with the least risk. If the perf gate passes on Day 1 and Reg-Lite slips, you can still demo confidently; if it lands, you’ll have the moment that sticks: *“We found your conflict and fixed your schedule in one click.”*
### Executive-level take

You covered an **impressive amount of ground** in one push: perf gating, observability, conflict detection, backups, demo-mode and iCal.  The direction is exactly what we agreed on (risk → story → polish) and, conceptually, this raises the demo score into the mid-80s.

Below is a quick “red / amber / green” audit so you can decide whether to merge as-is or loop once more.

| Slice                          | Status | Praise                                                                                                                                      | Tighten-ups / Fatal catches                                                                                                                                                                                                                                                                                                                        |
| ------------------------------ | ------ | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Perf gate (k6 + SLO)**       | 🟢     | Golden-path script + hard thresholds in CI is spot-on. 10 VUs × 120 s is enough to catch P95 badness without turning the run red for noise. | 1. Bypass `DEMO_MODE` caches in the k6 script or you’ll benchmark the happy path only.<br>2. Export raw k6 JSON → Prom so the same alert rules fire on perf runs.                                                                                                                                                                                  |
| **Prometheus / AlertManager**  | 🟢     | Critical + warning alerts for `5xx` and `index_size==0` are the right MVP.                                                                  | 1. Drop `parse_fallback_total` into its own alert (rate > 0.01 for 10 min) so it doesn’t flap.<br>2. Add a **recording rule** that rolls `histogram_quantile(0.95, rate(chat_request_duration_seconds_bucket[5m]))` – you’ll need that for latency graphs anyway.                                                                                  |
| **SSE watchdog**               | 🟡     | Gap detection is cheap (perf counter diff) and logs are useful.                                                                             | 1. You increment `sse_stream_errors_total` **after** catching; good – but also emit a `gap_ms` label so you can histogram the distribution.<br>2. You added a `with chat_request_duration_seconds.time(): try:` block and then partially re-indented; verify the file still **parses** – in diff view the indentation looks off starting line 235. |
| **Metrics plumbing**           | 🟡     | Extra counters/histograms are there.                                                                                                        | 1. You created them but did **not attach** e.g. `context_timeout_total` in the async gather wrapper.<br>2. Mock metrics class now has to emulate `time()` context manager (you added `.time()` earlier but ensure it returns `nullcontext()`).                                                                                                     |
| **Conflict-detection service** | 🟢     | Pure deterministic overlap logic + curated backups hits demo sweet-spot.                                                                    | 1. Regex extraction is fine for demo but add `upper()` to match course codes inside mixed-case sentences.<br>2. You currently pull instructor names from the mock dataset in `ICalExportService`; make sure the same source is used for backup rationales so names align.                                                                          |
| **Prompt budget**              | 🟠     | Extra “### Schedule Analysis” section is useful.                                                                                            | Collision risk: conflict summary + backup suggestions can easily hit \~800 chars; you truncate but do it *after* markdown assembly, which can cut a list mid-row. Safer: build lines, count tokens/len, slice before join.                                                                                                                         |
| **Demo-mode flag**             | 🟡     | `.env.demo` + `DemoMode.is_enabled()` utility is the right pattern.                                                                         | 1. `DemoMode` class is not actually referenced except in the calendar router; wrap conflict detection and professor intel cache bypass behind it.<br>2. Add `--env .env.demo` step in CI to guarantee we haven’t accidentally broken demo path.                                                                                                    |
| **iCal export**                | 🟢     | Generates recurring events with RRULE; good showpiece.                                                                                      | 1. Validate DST: Cornell’s fall term crosses DST boundary – add `UNTIL=` in RRULE so events don’t creep.<br>2. `ics` lib sometimes adds default VTIMEZONE lines; unit-test the output passes `icalendar` validator.                                                                                                                                |
| **Routing / imports**          | 🟠     | New router wired in `main.py`.                                                                                                              | Fails in prod containers that use `python -m gateway.main` unless you update `gateway/routes/__init__.py` to re-export `calendar_export`.                                                                                                                                                                                                          |
| **Unit / chaos tests**         | 🟢     | Property tests + chaos suite are valuable.                                                                                                  | The single `pytest.raises … or True` line in the ISO test still passes even if code breaks – replace with explicit asserts.                                                                                                                                                                                                                        |

---

### ROI checkpoint

| Dimension           | Pre-push | Post-push (expected) | Delta | Notes                                                      |
| ------------------- | -------- | -------------------- | ----- | ---------------------------------------------------------- |
| **Reliability**     | 30 / 35  | **33 / 35**          | +3    | alerts + gap detector                                      |
| **Latency (known)** | ? / 20   | **17 / 20**          | +17   | perf gate gives evidence; still need realistic traffic mix |
| **Explainability**  | 14 / 15  | 14 / 15              | 0     | unchanged                                                  |
| **Story value**     | 14 / 20  | **19 / 20**          | +5    | conflicts + backups + ical                                 |
| **Polish**          | 8 / 10   | **9 / 10**           | +1    | badges + ical download                                     |

**New demo score ≈ 92 / 100** assuming the orange cells above are fixed.  That’s enough head-room for minor flubs on show-day.

---

### Minimal pre-merge punch-list

1. **Run `pytest -q`** – catches the indentation drift in `chat_orchestrator.py`.
2. **Add context-timeout metric increments** inside the `timed()` wrapper.
3. **Export calendar router in `gateway/routes/__init__.py`.**
4. Replace the `pytest.raises … or True` anti-pattern.
5. Run the k6 perf gate once inside `DEMO_MODE=false` too, to make sure cache-less path respects SLO.

Do those and you can confidently tag **v0.9-demo**.

Let me know if you’d like a quick PR review on any of the orange items or assistance wiring the k6 JSON output into Prometheus.
Short version: this is a strong, coherent implementation that hits the “Day-1 perf gates → Day-2/3 Reg-Lite” plan. You’ve meaningfully upgraded reliability (parse-fallback metric, SSE gap watchdog, deterministic cache jitter), added a memorable demo moment (conflict + backup + .ics), and kept scope safely bounded. A few last-mile correctness nits and ops hooks will turn this from “works” into “bulletproof.”

# What looks great

* **Perf & ops gates**: k6 script + SLOs, SSE gap logging, new latency histogram and error counters. Good risk burn-down.
* **Observability**: `prov_parse_fallback_total`, `prov_index_size` Gauge, streaming error counters. Nice!
* **Reg-Lite**: conflict detection on seeded data, curated backups with rationale, iCal export + router. That’s the demo story.
* **Explainability**: `selection_reason` flows to UI with readable badges.

# Tighten these before demo (quick, high impact)

1. **Prometheus rule filename mismatch (will no-op alerts).**
   You created `monitoring/prometheus-alerts.yml` but `prometheus.yml` references `alert_rules.yml`. Make those match, or Prometheus won’t load your rules.

2. **HTTP metrics in alerts.**
   Alerts use `http_requests_total`, which you don’t emit by default with FastAPI. Either:

   * add `starlette-exporter` middleware, **or**
   * rewrite alerts to your own series (e.g., `sum(rate(chat_request_duration_seconds_count[5m]))` for volume, `histogram_quantile(0.95, sum(rate(chat_request_duration_seconds_bucket[5m])) by (le))` for latency, and 5xx via your API counter if you add one.

3. **`chat_request_duration_seconds` context manager indentation.**
   You wrapped the whole request in `with chat_request_duration_seconds.time():` and then started a `try:`. Ensure the **entire** happy path is inside the `with` block (watch the reindent around your current try/except). Otherwise you’ll silently lose latency data—or worse, introduce a syntax/logic error.

4. **SSE watchdog should emit a metric, not just logs.**
   Add `sse_chunk_gap_exceeded_total` (no labels, or 1 label like `provider`) and increment when `gap_ms > 1500`. This gives you a Prom alert and trend.

5. **SCARD frequency.**
   You now SCARD after each record. Keep the Gauge truthful without extra RTTs by:

   * `p_index_size.inc()` on SADD success / `dec()` on REM success, and
   * **reconcile** with SCARD every N ops (e.g., 100) or on a 1-min background tick.

6. **ISO parse: harden & count.**
   You normalized to UTC—good. Replace the test anti-pattern (`with pytest.raises(...) or True`) with a direct assertion that fallback returns an aware UTC `datetime` close to `_now_utc()`; and ensure all `_parse_iso(...)` callsites were updated (you changed the signature).

7. **Professor selection lambda guard.**
   Make it `p.get("overall_rating") or 0.0` so `None` won’t cause tuple comparison issues under Py3.12.

8. **iCal export realism & safety.**

   * Use **TZID=America/New\_York** and include a `VTIMEZONE` block; otherwise calendar apps may shift times.
   * Don’t hardcode `Fall2024` in filenames—derive from demo dataset or use a neutral name (`Demo_Schedule.ics`).
   * Sanitize course strings to prevent CRLF injection (strip `\r\n`).

9. **Demo mode wiring.**
   You created `DemoMode`, but ensure it actually **short-circuits** risky calls (e.g., scraping) and forces seeded data. A single env flag in the professor service and orchestrator guard is enough.

10. **K6 pass/fail in CI.**
    Confirm the script sets **thresholds** so the job fails on violations (first-chunk p95 < 500ms, full p95 < 3s, error rate < 1%). That’s your automated go/no-go.

# ROI and readiness

* **Current risk-adjusted score**: \~**84–88/100** once the above nits land (primarily because latency/ops are now measurable, and Reg-Lite adds clear story value).
* **Return on the last mile**: The five items above are 2–4 hours and materially reduce demo risk; they’re worth doing.

# Mini go/no-go checklist (use this verbatim)

* [ ] Prom rules loaded (no “0 rules” warning), alerts target **your** metric names.
* [ ] K6 thresholds green at **10 VUs** and again at **20 VUs** (confidence buffer).
* [ ] `histogram_quantile(0.95, sum(rate(chat_request_duration_seconds_bucket[5m])) by (le)) < 3s`.
* [ ] `sse_stream_errors_total` = 0 during a 5-minute soak; `sse_chunk_gap_exceeded_total` stays near 0.
* [ ] `prov_parse_fallback_total` steady at 0 in demo mode.
* [ ] Reg-Lite shows **one conflict**, **one backup suggestion with rationale**, and **successful .ics download** on the golden path.
* [ ] Mobile viewport: provenance + selection badges wrap cleanly.

# If you have one more half-day

* Add a tiny **/healthz** that verifies Redis ping + canary context service call; wire a Prom “HealthcheckFail” alert.
* Add **context\_{requests,timeout}\_total** increments around each context fetch so your perf dashboards show where time goes.

Overall: this is absolutely the right shape. Close the filename/alert/indentation gaps, emit one more metric for SSE gaps, and you’ll have a crisp, defensible demo that feels fast, explains itself, and handles failure gracefully.
