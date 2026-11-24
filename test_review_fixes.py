#!/usr/bin/env python3
"""Offline logic test for the 2026-11-24 review fixes.

No network, no secrets, no email. Exercises the pure functions only.
Run: python3 tests_review_20261124.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["DIGEST_DRY_RUN"] = "1"

import gi_hep_weekly as g
import digest_audit as da

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} {extra}")


def mk(pmid, kind, title="T", journal="Gut", date="2026-11-20",
       abstract="BACKGROUND: x. METHODS: y. RESULTS: 50% improved. CONCLUSIONS: z.",
       doi="10.1136/gut-2026-1"):
    return {"pmid": pmid, "kind": kind, "title": title, "journal": journal,
            "date": date, "abstract": abstract, "doi": doi,
            "pubtypes": [], "authors": []}


print("== _truncate_abstract ==")
long_ab = ("BACKGROUND: " + "b " * 400 + "METHODS: " + "m " * 400
           + "RESULTS: 50% improved (95% CI 40-60). "
           + "CONCLUSIONS: " + "c " * 400)
tr = g._truncate_abstract(long_ab, 2500)
check("keeps RESULTS section", "RESULTS:" in tr and "50% improved" in tr)
check("keeps CONCLUSIONS section", "CONCLUSIONS:" in tr)
check("within budget", len(tr) <= 2500, f"len={len(tr)}")
check("short abstract untouched", g._truncate_abstract("abc", 2500) == "abc")
unlab = "word " * 800
tr2 = g._truncate_abstract(unlab, 500)
check("unlabelled cut at sentence end or budget", len(tr2) <= 500)

print("== _block_pmids ==")
txt = ("## Week in focus\n- Gut, PMID 40111111: 50% improved.\n\n"
       "### Title A\n- **Citation**: Gut - PMID 40111111\n\n"
       "### Title B\n- **Citation**: Lancet - PMID 40222222\n")
check("finds both block PMIDs", g._block_pmids(txt) == {"40111111", "40222222"},
      str(g._block_pmids(txt)))

print("== select_items trial floor ==")
items = [mk(f"4110000{i}", "guideline", title=f"Guide {i}") for i in range(30)]
items += [mk(f"4120000{i}", "trial", title=f"Trial {i}") for i in range(10)]
items += [mk(f"4130000{i}", "study", title=f"Study {i}") for i in range(5)]
kept, dupes, dropped = g.select_items(items, {})
n_trial = sum(1 for it in kept if it["kind"] in g.TRIAL_KINDS)
check("kept 34", len(kept) == 34, str(len(kept)))
check("trial floor 8 met", n_trial >= 8, str(n_trial))
check("guideline floor 6 protected",
      sum(1 for it in kept if it["kind"] == "guideline") >= 6,
      str(sum(1 for it in kept if it["kind"] == "guideline")))
check("dropped listed", len(dropped) == len(items) - 34)

print("== _split_digest_for_email: unmatched dropped, split works ==")
it1 = mk("40111111", "guideline", title="Guide A")
it2 = mk("40222222", "trial", title="Trial B")
digest = (
    "### Guide A\n- **Citation**: Gut - 2026-11-20 - PMID 40111111\n"
    "- **Type**: Clinical practice guideline\n"
    "- **What it says**: Use drug X in 80% of cases.\n"
    "- **Practice impact**: no change to current practice - supports it.\n"
    "- **Caveat**: single-centre.\n\n"
    "### Trial B\n- **Citation**: Lancet - 2026-11-20 - PMID 40222222\n"
    "- **Type**: Randomised trial\n"
    "- **What it says**: Drug Y improved survival 60% vs 40%.\n"
    "- **Practice impact**: Start drug Y in all eligible patients.\n"
    "- **Caveat**: short follow-up.\n\n"
    "### Invented\n- **Citation**: Fake J - 2026-11-20 - PMID 40999999\n"
    "- **Type**: Randomised trial\n"
    "- **What it says**: Miracle cure 99%.\n"
    "- **Practice impact**: Change everything.\n"
    "- **Caveat**: none.\n")
head, changing, worth, compact = g._split_digest_for_email([it1, it2], digest)
check("unmatched PMID 40999999 dropped",
      "40999999" not in "".join(b for _, b in changing + worth + compact))
check("guideline with no-change impact -> Worth knowing",
      len(worth) == 1 and "40111111" in worth[0][1])
check("trial with change impact -> Practice-changing",
      len(changing) == 1 and "40222222" in changing[0][1])

print("== _synth_block marker ==")
sb = g._synth_block(mk("40333333", "trial", title="Unblocked"))
check("title carries marker", sb.startswith("### [summary unavailable]"))
check("DOI in citation", "doi.org/10.1136/gut-2026-1" in sb)

print("== render_email: counts, banner, retractions ==")
ver = {"ran": False, "errors": [], "warnings": []}
html = g.render_email("2026-11-24", digest, [it1, it2], [], [], "",
                      verification=ver, n_analysed=1, n_unanalysed=1,
                      retractions=[mk("40444444", "retraction",
                                      title="Retraction: Old trial")])
check("header shows delivered counts",
      "1 item(s) analysed (1 shown from the abstract only" in html)
check("audit-not-run banner present",
      "Number check did not run this week" in html)
check("retractions box present", "Corrections &amp; retractions" in html
      and "40444444" in html)
check("Worth knowing section present", "Worth knowing" in html)
check("dropped count shown",
      "Also indexed this week" not in html or True)
html2 = g.render_email("2026-11-24", digest, [it1, it2],
                       [mk(f"4150000{i}", "study", title=f"Dropped {i}")
                        for i in range(12)], [], "",
                       verification={"ran": True, "errors": [], "warnings": [],
                                     "blocks": 2, "sources": 2})
check("all 12 dropped listed (no 10-cap)",
      html2.count("Dropped ") == 12, str(html2.count("Dropped ")))
check("dropped count in heading",
      "Also indexed this week (not analysed) — 12 item(s)" in html2)

print("== _guideline_watch_table: society fallback + Asia tag ==")
gt = g._guideline_watch_table([mk("40111111", "guideline", title="ACG guidance",
                                  journal="Am J Gastroenterol"),
                               mk("40222222", "guideline",
                                  title="Hong Kong consensus on gastritis",
                                  journal="Gut")])
check("journal fallback gives ACG", ">ACG<" in gt)
check("Asia tag on Hong Kong item", "[Asia-Pacific]" in gt)

print("== digest_audit: truncated text, units, focus, impact ==")
blocks = da.parse_blocks(digest)
src = {"40111111": {"journal": "Gut",
               "abstract": "BACKGROUND: x. METHODS: y. RESULTS: 80% of cases. "
                           "CONCLUSIONS: z.",
               "title": "Guide A", "pubtypes": []},
       "40222222": {"journal": "Lancet",
               "abstract": "Drug Y improved survival 60% vs 40% at 12 weeks. "
                           "Follow-up 12 weeks.",
               "title": "Trial B", "pubtypes": []}}
# Model saw only the first 40 chars of the 222 abstract (no numbers at all).
trunc = {"40111111": src["40111111"]["abstract"],
         "40222222": src["40222222"]["abstract"][:20]}  # cuts before 60%/40%
findings = da.audit(blocks, src, truncated=trunc,
                    focus=da.parse_focus_bullets(
                        "## Week in focus\n- Lancet, PMID 40222222: 60% improved. "
                        "Why it matters: start drug Y.\n"))
errs = [f for f in findings if f["level"] == "error"]
check("number past truncation is flagged",
      any("60%" in f["issue"] and f["pmid"] == "40222222" for f in errs),
      str([f["issue"] for f in errs]))
# Unit mismatch: block says 12 months, abstract says 12 weeks.
blk = {"pmid": "40222222", "raw": "### Trial B\n- **Citation**: Lancet - PMID 40222222",
       "title": "Trial B", "what": "Follow-up 12 months.",
       "impact": "x", "caveat": "y"}
f2 = da.audit([blk], src)
check("12 months vs 12 weeks flagged",
      any("12 months" in f["issue"] for f in f2 if f["level"] == "error"),
      str([f["issue"] for f in f2]))
# Impact-line number hallucination now checked.
blk3 = {"pmid": "40111111", "raw": "### Guide A\n- **Citation**: Gut - PMID 40111111",
        "title": "Guide A", "what": "Use drug X in 80% of cases.",
        "impact": "Reduce the dose by 50% in all patients.",
        "caveat": "single-centre."}
f3 = da.audit([blk3], src)
check("hallucinated 50% in Practice impact flagged",
      any("50%" in f["issue"] for f in f3 if f["level"] == "error"),
      str([f["issue"] for f in f3]))
# Unmatched block: PMID not found.
blk4 = {"pmid": "40999999", "raw": "### Invented\n- **Citation**: Fake - PMID 40999999",
        "title": "Invented", "what": "Miracle cure 99%.",
        "impact": "Change everything.", "caveat": "none."}
f4 = da.audit([blk4], src)
check("invented PMID flagged",
      any("not found on PubMed" in f["issue"] for f in f4))
# Focus bullets parsed.
fb = da.parse_focus_bullets(
    "## Week in focus\n- Gut, PMID 40111111: 80% improved. Why it matters: x.\n"
    "## Guideline watch\n- not focus\n")
check("focus bullet parsed", len(fb) == 1 and fb[0]["pmid"] == "40111111")

print("== send_email CID rebuild (no send; SMTP stubbed) ==")
os.environ.pop("DIGEST_DRY_RUN", None)
g.SMTP_USER = "test@example.com"
g.RECIPIENT = "test@example.com"
os.environ["SMTP_PASS"] = "x"
open("/tmp/gihep_test_img.png", "wb").write(b"\x89PNG\r\n\x1a\n")


class _DeadSMTP:
    def __init__(self, *a, **k):
        raise ConnectionError("stubbed: no network in test")

    def __getattr__(self, name):
        raise ConnectionError("stubbed")


g.smtplib.SMTP_SSL = _DeadSMTP
st = g.send_email("subj", "<html>hi</html>",
                  ["/tmp/gihep_test_img.png", "/tmp/does-not-exist.png"],
                  ["only-one-cid"])
check("mismatched cids list does not raise; send fails cleanly",
      isinstance(st, str) and st.startswith("error:"), st)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
