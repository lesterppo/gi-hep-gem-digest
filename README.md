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
  ├── PubMed E-utilities — 4 queries:
  │     • guideline / consensus pub-types in GI-hepatology journals
  │     • guideline / consensus pub-types on GI-hepatology MeSH topics
  │     • RCTs, meta-analyses, systematic reviews in GI-hepatology journals
  │     • GI-hepatology major-topic trials in NEJM/Lancet/JAMA/Nat Med/…
  │   (Europe PMC is the fallback source tier)
  ├── Dedup against the seen-PMID cache (actions/cache, rolling key)
  ├── Gemini Flash + Extended Thinking — one block per item:
  │     Citation · Type · What it says (effect sizes, no p-values) ·
  │     Practice impact · Caveat, preceded by "Week in focus" and
  │     "Guideline watch"
  ├── Infographics:
  │     1. matplotlib evidence-mix chart (type / journal / issuing body counts)
  │     2. Gemini NotebookLM dashboard — "Guidance & consensus"
  │     3. Gemini NotebookLM dashboard — "Trials & meta-analyses"
  │     4. Gemini NotebookLM dashboard — "Practice signals"
  └── One HTML email (text summary + all infographics inline)

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
| `ABSTRACT_CHARS` | `1500` | Abstract characters sent per item |
| `GEMINI_MODEL` / `GEMINI_THINKING` | `flash` / `extended` | Web backend |
| `GEMINI_API_MODEL` | `gemini-3.5-flash` | API fallback (then flash-lite, 2.5-flash) |
| `NLM_ARTIFACTS` | `3` | How many NotebookLM dashboards to generate (guidance / trials / signals) |
| `FETCH_SOURCE` | `auto` | `pubmed` \| `epmc` pins the tier |
| `DIGEST_LANG` | `en` | `zh-Hant` writes the report in Traditional Chinese |
| `DIGEST_DRY_RUN` | *(unset)* | `1` = run everything, send nothing |
| `SEEN_KEEP_DAYS` | `120` | Dedup-cache retention |

## Files

| File | Purpose |
|------|---------|
| `gi_hep_weekly.py` | Main pipeline (fetch → analyse → infographics → email) |
| `digest_infographic.py` | NotebookLM helpers (notebook, sources, artifact, download) |
| `nlm.py` | NotebookLM CLI wrapper |
| `gemini.py`, `urllib_session.py` | Gemini CLI (gemini-webapi, cookie auth) |
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
* **Dedup cache key must stay rolling** (`gihep-seen-${{ github.run_id }}` +
  `restore-keys: gihep-seen-`); a fixed key always hits, a hit skips the save,
  and the seen-cache freezes so every run re-reports the whole window.
* **Numeric env vars tolerate empty strings** — a blank `workflow_dispatch`
  input arrives as `''`.
* **PubMed uses `datetype=edat&reldate=N`** (indexing date) — that is what
  "new this week" means.
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
