# GI & Hepatology Weekly — Digest (GitHub Actions + Gemini)

A scheduled GitHub Actions job (Mondays 01:30 UTC / 09:30 HKT) that collects the
guidelines, consensus statements and clinical studies newly indexed for
gastroenterology and hepatology, summarises each one with **Gemini Flash +
Extended Thinking**, generates a **comprehensive clinical infographic with
Gemini NotebookLM**, and emails the whole thing as a single HTML report.

No local machine is involved in the weekly run — the workflow executes entirely
on GitHub's runners and delivers the email.

## What it does

```
GitHub Actions (Mon 01:30 UTC)
  ├── PubMed E-utilities — 6 queries:
  │     • guideline / consensus pub-types in GI-hepatology journals
  │     • guideline / consensus pub-types on GI-hepatology MeSH topics
  │     • RCTs, meta-analyses, systematic reviews in GI-hepatology journals
  │     • GI-hepatology major-topic trials in NEJM/Lancet/JAMA/Nat Med/…
  │     • guidelines / consensus in the major general journals (title words,
  │       not MeSH — MeSH lags weeks behind indexing)
  │     • retractions / errata in the GI journals (listed, never analysed)
  │   (Europe PMC is the fallback source tier; per-query caps are paged
  │    past, up to 100 per query, so a busy week never silently drops items)
  ├── Dedup against the seen-PMID cache (actions/cache, rolling key, plus
  │   the committed state/seen_ids.json — the cache alone evicts after 7 idle
  │   days and a weekly cadence sits exactly on that boundary)
  ├── Gemini Flash + Extended Thinking — one block per item:
  │     Citation · Type · Design · What it says (effect sizes, no p-values) ·
  │     Practice impact · Caveat, preceded by "Week in focus" and
  │     "Guideline watch". Selection is kind-first with a floor of 8
  │     trial/meta-analysis/review slots, so a guideline-heavy week cannot
  │     push out every trial.
  ├── Verification gate (every run):
  │     • duplicate item blocks dropped (the model re-wrote an item with a
  │       different journal on a live run)
  │     • blocks for PMIDs outside the analysed set are dropped, never
  │       delivered — a block for a PMID we never fetched cannot be verified
  │     • every figure stated is traced back to the SAME truncated abstract
  │       text the model was given (What-it-says, Practice impact, Caveat and
  │       the Week-in-focus bullets); a stated time unit must appear next to
  │       its number in the source. The email footer reports "no unmatched
  │       numbers" or names the unverified ones; if the check never ran, the
  │       email says so in a banner instead of staying silent
  ├── Infographics:
  │     1. matplotlib evidence-mix chart (type / journal / issuing body counts)
  │     2. Gemini NotebookLM dashboard — "Guidance & consensus"
  │     3. Gemini NotebookLM dashboard — "Trials & meta-analyses"
  │     4. Gemini NotebookLM dashboard — "Practice signals"
  ├── One HTML email (text summary + all infographics inline). The subject
  │   and header report the counts of what was ACTUALLY delivered (items the
  │   model blocked vs items shown from the raw abstract only) — never the
  │   fetched count. A run with any failed analysis batch, or an email that
  │   never left, exits 2.
  └── After a sent email: the digest HTML + run manifest are committed to
      archive/ together with state/seen_ids.json. The push resets GitHub's
      60-day scheduled-workflow auto-disable clock and is the permanent
      archive of every digest sent (the workflow was disabled for inactivity
      on 2026-11-23 exactly because nothing was ever committed).

The week is split into THREE NotebookLM dashboards on purpose: one artifact
covering every item has to cram, which is where garbled text and dropped
sections come from. Each dashboard gets its own notebook (dated), its own
source set (guidance / studies / cross-cutting) and its own deep instruction
set — every guideline card carries 3 recommendation bullets, every study card
carries its headline numbers, and the signals dashboard says what to change,
what to verify and what to watch. `NLM_ARTIFACTS` caps how many are generated.
```

**No ranking, no scoring** — every item in the window is reported with its
numbers and its practice implication.

## Sources covered

* Guideline / consensus publication types: *Guideline*, *Practice Guideline*,
  *Consensus Development Conference* (+ NIH), plus title patterns
  (guideline, consensus, recommendations, position statement, clinical practice
  update, Delphi) scoped to GI-hepatology journals or MeSH topics.
* Clinical studies: randomised controlled trials, controlled clinical trials,
  phase II/III trials, meta-analyses, systematic reviews.
* Journals: Gut, Gastroenterology, J Hepatol, Hepatology, Am J Gastroenterol,
  Clin Gastroenterol Hepatol, J Crohns Colitis, Endoscopy, Gastrointest Endosc,
  Aliment Pharmacol Ther, Liver Int, J Gastroenterol Hepatol, UEG J, Hepatol Int,
  Clin Mol Hepatol, JHEP Rep, Dig Endosc, Therap Adv Gastroenterol, plus
  NEJM / Lancet / Lancet GH / JAMA / Nat Med / Ann Intern Med / BMJ and more
  (full list in `gi_hep_weekly.py`).

## Setup

1. **Gemini cookies** (web backend, no API key needed):
   ```bash
   python3 gemini.py --init          # writes ~/.gemini-cli/auth.json
   python3 refresh_gh_secrets.py lesterppo/gi-hep-gem-digest
   ```
2. **Gemini API key** (fallback backend, free AI Studio tier) — secret
   `GEMINI_API_KEY`. If the web cookies die, the digest still runs on this.
3. **NotebookLM session** (infographic):
   ```bash
   python3 nlm_cookie_sync.py lesterppo/gi-hep-gem-digest
   ```
   Pushes `NLM_STORAGE_STATE_GZ` (gzipped storage_state, all `*.google.com`
   cookies from one signed-in Firefox profile).
4. **Email** — secrets `SMTP_USER`, `SMTP_PASS` (Gmail app password),
   `RECIPIENT`.

| Secret | Purpose |
|--------|---------|
| `GEMINI_SID`, `GEMINI_TS` | Gemini web session cookies (`__Secure-1PSID`, `__Secure-1PSIDTS`) |
| `GEMINI_API_KEY` | Free-tier AI Studio key — fallback analysis backend |
| `NLM_STORAGE_STATE_GZ` | NotebookLM session (base64+gzip of `storage_state.json`) |
| `SMTP_USER`, `SMTP_PASS`, `RECIPIENT` | Delivery |

## Running it

* Weekly: automatic (Mondays 01:30 UTC).
* Manual: Actions → *GI & Hepatology Weekly Digest (Gemini)* → **Run workflow**.
  Inputs: `dry_run` (no email), `back_days`, `max_items`, `fetch_source`
  (`auto|pubmed|epmc`), `ignore_seen`.

## Env reference

| Variable | Default | Notes |
|----------|---------|-------|
| `RUN_BACK_DAYS` | `14` | Look-back window in days (no-miss margin + dedup) |
| `ANALYSIS_MAX_ITEMS` | `34` | Cap on items analysed per run |
| `MAX_GUIDE_CANDIDATES` / `MAX_TRIAL_CANDIDATES` | `25` / `15` | Per-query fetch caps |
| `BATCH_SIZE` | `18` | Items per Gemini call |
| `ABSTRACT_CHARS` | `2500` | Abstract characters sent per item (sentence-aware truncation that keeps RESULTS / CONCLUSIONS) |
| `MIN_TRIAL_SLOTS` | `8` | Floor of trial/meta-analysis/review slots in the analysed set |
| `GEMINI_MODEL` / `GEMINI_THINKING` | `flash` / `extended` | Web backend |
| `GEMINI_API_MODEL` | `gemini-3.8-flash` | API fallback (then 3.6-flash, flash-lite, 2.5-flash). 3.5-flash is deprecated on the Developer API — requests to it are silently routed to 3.6-flash, so it is no longer the lead. |
| `GEMINI_WEB_DEAD` | *(unset)* | `1` = skip the web backend entirely (set by the workflow's liveness preflight when the web session is dead) |
| `NLM_ARTIFACTS` | `3` | How many NotebookLM dashboards to generate (guidance / trials / signals; `0` skips) |
| `NLM_BUDGET` | `900` | Seconds for the whole infographic phase before remaining dashboards are skipped |
| `RUN_DEADLINE_S` | `1500` | Seconds from run start by which the infographic phase must stop (the email is the last step; the phase budget is measured against this deadline, not from the phase start) |
| `FETCH_SOURCE` | `auto` | `pubmed` \| `epmc` pins the tier |
| `DIGEST_LANG` | `en` | `zh-Hant` writes the report in Traditional Chinese |
| `DIGEST_DRY_RUN` | *(unset)* | `1` = run everything, send nothing |
| `SEEN_KEEP_DAYS` | `120` | Dedup-cache retention |

## Verification

`digest_audit.py` is not just a dev tool — it runs inside every CI run:

```
audit: 26 block(s) traced to 25 abstract(s) — 0 number error(s), 0 warning(s)
```

It re-fetches each item's PubMed record and checks that (a) no PMID gets two
blocks, (b) every number, percentage, CI and confidence level the digest states
appears in that item's abstract or title — in What-it-says, Practice impact,
Caveat AND the Week-in-focus bullets, and against the same truncated abstract
text the model was given (a number that only appears past the truncation point
could not have been grounded), (c) a stated time unit appears next to its number
("12 months" when the abstract says "12 weeks" is flagged), (d) the block
carries its What-it-says / Practice-impact / Caveat lines, and (e) the cited
journal matches PubMed. Blocks for PMIDs outside the analysed set are audited
too (they surface as "PMID not found on PubMed") and are never delivered. Run
it by hand on any digest text:

```bash
python3 digest_audit.py state/digest_b1.md state/digest_b2.md
```

Why it exists: on a live run the model emitted the same item twice, the second
copy citing the wrong journal, and nothing in the logs noticed. Numbers that
cannot be traced are surfaced in the email rather than silently shipped.

## Files

| File | Purpose |
|------|---------|
| `gi_hep_weekly.py` | Main pipeline (fetch → analyse → infographics → email) |
| `digest_infographic.py` | NotebookLM helpers (notebook, sources, artifact, download) |
| `nlm.py` | NotebookLM CLI wrapper |
| `gemini.py`, `urllib_session.py` | Gemini CLI (gemini-webapi, cookie auth) |
| `digest_audit.py` | Trace digest numbers back to PubMed abstracts (CI gate) |
| `test_review_fixes.py` | Offline logic test for the review fixes (30 checks, no network/secrets) — `python3 test_review_fixes.py` |
| `nlm_cookie_sync.py` | Refresh the NotebookLM session jar + push the secret |
| `refresh_gh_secrets.py` | Push Gemini cookies to GitHub secrets |
| `.github/workflows/weekly.yml` | The scheduled job |

## Maintenance notes (for whoever edits this repo next)

* **No ranking/scoring, ever.** Item blocks carry numbers (effect sizes, CIs,
  N) but no scores, ratings, GRADE letters or p-values. Any p-value that leaks
  into the NotebookLM source text is stripped (`PVAL_GROUP_RE` / `PVAL_RE`) —
  the artifact generator garbles them and pairs them with contradictory
  "significant" claims.
* **NotebookLM sources are curated, not raw.** Sources are compact
  `TYPE / SOCIETY / JOURNAL / DATE / PMID / TITLE / KEY POINTS / PRACTICE /
  CAVEAT` blocks parsed from the digest text, capped by `NLM_MAX_SOURCES`
  (default 10). Feeding raw abstracts produced a 3/10 infographic (garbled
  terms, "98% CI", an invented "2020" date range); curated blocks + verbatim
  window dates score ~6-8/10.
* **The NotebookLM prompt must carry the real window dates** — the header strip
  is quoted from the computed window, otherwise the generator invents its own
  date range.
* **NotebookLM rotates its session token on use**, so a harvested jar covers
  roughly **one** CI session. The fix is one harvest per morning, straight
  before the run slots — `nlm_digests_pre_run.sh` (Hermes cron, daily 09:15 HKT,
  covers all three digest repos) runs `nlm_cdp_harvest.py`, which verifies the
  jar with a live RPC before publishing it. Deliberately **not** hourly: each
  harvest consumes the token it is meant to protect, so more frequent refresh
  makes things worse, not better. If the jar is stale the digest is designed to
  still ship — drop to the locally rendered poster, say so in the email, and
  never fail the run.
* **Generate the artifact first, reuse only on the daily cap.** Reusing "today's
  artifact" before generating serves a stale image whenever the prompt or the
  sources changed (the vendored `digest_infographic.nlm_generate_infographic`
  does pre-reuse; `_nlm_generate()` in `gi_hep_weekly.py` deliberately does not).
* **`digest_infographic.py` / `nlm.py` / `gemini.py` / `urllib_session.py` are
  vendored** from the sibling digests (`arxiv-gem-digest`,
  `yt-finance-digest`). Do not fork their behaviour inside `gi_hep_weekly.py`;
  extend the vendored helpers so all three digests keep the same NLM fixes.
* **Never fail silently:** no items *and* a source error → WARN email + exit 2.
  A run with any failed analysis batch, or an email that never left, also exits
  2 — a green run means the digest shipped whole. The audit result is written
  to `state/audit_<date>.json` (uploaded as an artifact); the workflow's alert
  step reads that JSON, not a log file.
* **The run commits its archive.** After a sent email, `archive/<date>.html`
  + `archive/<date>.json` (manifest: analysed/unanalysed PMIDs, backends, audit
  errors, dashboards) and `state/seen_ids.json` are committed and pushed. That
  push is what keeps the schedule alive — GitHub disables a scheduled workflow
  after 60 days of repo inactivity, which is what happened on 2026-11-23. The
  commit step is best-effort (`continue-on-error`) and runs after the email, so
  a push conflict can never block delivery. The committed content holds no
  secrets (no recipient address; `seen_ids.json` is PMIDs + dates).
* **Liveness, not just presence.** The workflow checks the Gemini web session
  (`gemini.py --account-status`) and the API key (models list) before the run;
  a dead web session sets `GEMINI_WEB_DEAD=1` so the run skips straight to the
  API backend instead of burning three timed-out web attempts. Cookies still
  need a refresh when they die — the check only routes around them.
* **Pinned dependencies.** `requirements.txt` pins exact versions (verified
  green by the 2026-11-24 dry run). Bump one at a time and re-run a dry run.
* **Playwright is cached** (`~/.cache/ms-playwright`, static key) — the browser
  is not re-downloaded every run.
* **Abstracts are truncated sentence-aware** (`_truncate_abstract()`): the head
  up to a third of the budget, then RESULTS and CONCLUSIONS, each cut at a
  sentence boundary. A hard character cut used to land mid-Results.
* **Full cards split into "Practice-changing" and "Worth knowing"** by the
  Practice-impact line; items the model never blocked carry a
  "[summary unavailable]" title marker and are shown from the raw abstract.
* **Guideline-watch society fallback:** journal → society map when the
  title/abstract never names the issuing body; an Asia-Pacific tag marks
  recognisably Asia-Pacific items.
* **Dedup cache key must stay rolling** (`gihep-seen-${{ github.run_id }}` +
  `restore-keys: gihep-seen-`); a fixed key always hits, a hit skips the save,
  and the seen-cache freezes so every run re-reports the whole window.
* **Numeric env vars tolerate empty strings** — a blank `workflow_dispatch`
  input arrives as `''`.
* **PubMed uses `datetype=edat&reldate=N`** (indexing date) — that is what
  "new this week" means.
* **Never filter a recent window by MeSH.** MeSH terms are assigned weeks after
  indexing, so `MeSH Major Topic` on the general-journal trial query returned 0
  hits every week; it now uses title/abstract keywords with a longer (30-day)
  look-back, and dedup stops it re-reporting the same study.
* **Europe PMC syntax is not PubMed syntax** (`MESH:"…"`, `JOURNAL:"…"`,
  `PUB_TYPE:"…"`, `FIRST_PDATE:[a TO b]`); it is only the fallback tier because
  its full-text indexing lags PubMed by weeks.
* `digest_infographic.py`, `nlm.py`, `gemini.py` and `urllib_session.py` are
  vendored from the sibling digests (`arxiv-gem-digest`, `yt-finance-digest`) —
  keep their behaviour in sync instead of forking it here.

## Caveats

* Automated summaries are a screening aid — **verify full texts before changing
  practice**. Every item carries its PMID link.
* Abstracts missing or truncated are flagged in the item's Caveat line.
* NotebookLM's artifact generator has a per-account daily cap; when it is hit
  the run reuses the notebook's latest completed infographic and says so.
* If the fetcher returns nothing **and** a source errored, the run sends a WARN
  email and exits non-zero — a green run always means a digest was produced.
