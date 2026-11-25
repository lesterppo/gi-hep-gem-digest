#!/usr/bin/env python3
"""Audit the digest's item blocks against the PubMed abstracts they came from.

Checks, per item:
  * PMID/journal/type pairing (block metadata vs PubMed record)
  * every number the block states (percentages, CIs, OR/HR/RR, N, counts)
    must appear in the source abstract (formatting-normalised)
  * the block must not be missing a What-it-says / Practice-impact / Caveat line

Usage: python3 digest_audit.py <digest.md> [<digest2.md> ...] [--json out.json]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
UA = "gi-hep-digest-audit/1.0"


def fetch_abstracts(pmids: list) -> dict:
    out = {}
    for i in range(0, len(pmids), 100):
        chunk = pmids[i:i + 100]
        data = urllib.parse.urlencode({
            "db": "pubmed", "id": ",".join(chunk),
            "retmode": "xml", "rettype": "abstract"}).encode()
        req = urllib.request.Request(f"{EUTILS}efetch.fcgi", data=data,
                                     headers={"User-Agent": UA,
                                              "Content-Type":
                                              "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=90) as r:
            root = ET.fromstring(r.read())
        for pa in root.iter("PubmedArticle"):
            cit = pa.find("MedlineCitation")
            if cit is None:
                continue
            art = cit.find("Article")
            if art is None:
                continue
            pmid = (cit.findtext("PMID") or "").strip()
            j = art.find("Journal")
            journal = (j.findtext("ISOAbbreviation") or j.findtext("Title")
                       or "").strip() if j is not None else ""
            abs_txt = " ".join("".join(a.itertext())
                               for a in art.findall(".//Abstract/AbstractText"))
            pts = [(p.text or "") for p in cit.findall(".//PublicationType")]
            out[pmid] = {"journal": journal, "abstract": abs_txt,
                         "pubtypes": pts,
                         "title": " ".join(
                             (art.find("ArticleTitle").itertext()
                              if art.find("ArticleTitle") is not None else []))}
        time.sleep(0.4)
    return out


def parse_blocks(text: str) -> list:
    """Item blocks only.

    The '## Week in focus' / '## Guideline watch' sections cite PMIDs in their
    bullets, so a naive split counts them as blocks and reports phantom
    duplicates and missing fields. Item blocks always start with '### '."""
    text = text or ""
    first = text.find("### ")
    if first > 0:
        text = text[first:]
    blocks = []
    for chunk in re.split(r"\n(?=###\s)", text):
        m = re.search(r"PMID\s+(\d{6,9})", chunk)
        if not m:
            continue
        blocks.append({"pmid": m.group(1), "raw": chunk,
                       "title": (re.match(r"###\s+(.*)", chunk.strip())
                                 or [None, ""])[1] if re.match(
                                     r"###\s+(.*)", chunk.strip()) else "",
                       "what": (re.search(r"\*\*What it says\*\*:\s*(.*)",
                                          chunk) or [None, ""])[1] if
                       re.search(r"\*\*What it says\*\*:\s*(.*)", chunk) else "",
                       "impact": (re.search(r"\*\*Practice impact\*\*:\s*(.*)",
                                            chunk) or [None, ""])[1] if
                       re.search(r"\*\*Practice impact\*\*:\s*(.*)", chunk) else "",
                       "caveat": (re.search(r"\*\*Caveat\*\*:\s*(.*)", chunk)
                                  or [None, ""])[1] if
                       re.search(r"\*\*Caveat\*\*:\s*(.*)", chunk) else ""})
    return blocks


NUM_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|mg|ml|mm|kg|weeks?|months?|years?|days?|"
    r"patients?|participants?|studies|trials?|cases|items)?")
CI_RE = re.compile(r"\b(\d{2})\s*%\s*CI\b")
# Time units whose confusion changes meaning (12 weeks vs 12 months): when
# a stated number carries one, the unit must appear next to the number in
# the source, not just the bare number somewhere in the abstract.
TIME_UNIT_VARIANTS = {
    "week": r"weeks?|wks?",
    "month": r"months?|mos?",
    "year": r"years?|yrs?",
    "day": r"days?",
}
TIME_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(weeks?|wks?|months?|mos?|years?|yrs?|days?)\b", re.I)


def parse_focus_bullets(text: str) -> list:
    """'## Week in focus' bullets: [{pmid, text}].

    The focus bullets cite PMIDs and state findings in ≤25 words, but
    parse_blocks() only takes '### ' blocks, so they were never traced."""
    out = []
    m = re.search(r"(?mi)^##\s+Week in focus\s*$", text or "")
    if not m:
        return out
    head = text[m.end():]
    # The section ends at the NEXT heading of any level — "## Guideline
    # watch" or the first "### " item block. The old pattern only stopped
    # at "## " headings, so it swallowed every item block's "- **Citation**:"
    # line (PMID + DOI + date) as a "focus bullet" and the number check
    # flagged the citation metadata as untraced figures (2026-11-25 dry
    # run: 131 audit errors, ~124 of them from swallowed citation lines).
    end = re.search(r"(?m)^#{1,6}\s", head)
    section = head[:end.start()] if end else head
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        pm = re.search(r"PMID\s+(\d{6,9})", line)
        if pm:
            out.append({"pmid": pm.group(1), "text": line})
    return out


def norm(s: str) -> str:
    return (s or "").replace("\u2013", "-").replace("\u2014", "-") \
        .replace("\u2265", ">=").replace("\u2264", "<=").replace(",", "")


def _check_numbers(pmid: str, text: str, ab: str, findings: list,
                   where: str) -> None:
    """Every number in `text` must exist in the source abstract `ab`.

    Core-number matching is lenient by design (a legit summary may expand a
    unit — "2 wk" -> "2.0 weeks" — or pad a decimal, and spelled-out numbers
    count). Two strictnesses on top: a stated TIME unit (weeks/months/years/
    days) must appear next to the number in the source — "12 months" when the
    abstract says "12 weeks" is a real error the core check misses — and a
    stated % must appear as a percentage, not just as the bare number.
    A PMID reference ("PMID 40222222") is an identifier, not a clinical
    number, and is stripped before checking."""
    words = {"one": "1", "two": "2", "three": "3", "four": "4",
             "five": "5", "six": "6", "seven": "7", "eight": "8",
             "nine": "9", "ten": "10"}
    text = re.sub(r"PMID\s*\d{6,9}", "", norm(text) or "")
    # DOIs and URLs are identifiers, not clinical numbers: a focus bullet or
    # a citation line carries "10.1001/jamanetworkopen.2026.41241" and a
    # pubmed URL whose digits must never be checked against the abstract
    # (the same reason PMIDs are stripped above).
    text = re.sub(r"10\.\d{4,9}/[^\s,;)\]]+", "", text)
    text = re.sub(r"https?://[^\s]+", "", text)
    for tok in NUM_RE.findall(text):
        t = tok.strip()
        if not t or len(t) <= 1:
            continue
        core = re.match(r"\d+(?:\.\d+)?", t)
        if not core:
            continue
        num = core.group(0)
        spelled = [w for w, d in words.items() if d == num.split(".")[0]]
        found_digits = (num in ab or num.rstrip("0").rstrip(".") in ab)
        found = found_digits or any(w in ab.lower() for w in spelled)
        if not found:
            findings.append({"pmid": pmid, "level": "error",
                             "issue": f"number '{t}' (core {num}) in {where} "
                                      f"is NOT in the abstract"})
            continue
        # Unit check, only when the number was found as digits (a spelled-out
        # match cannot be located reliably).
        if not found_digits:
            continue
        unit_m = TIME_UNIT_RE.search(t)
        if unit_m:
            unit = unit_m.group(1).lower()
            stem = next((k for k, pat in TIME_UNIT_VARIANTS.items()
                         if re.fullmatch(pat, unit, re.I)), None)
            if stem:
                # A bracketed IQR/range may sit between the number and its
                # unit — "5.7 [2.3-11.5] months" (median [IQR] vs median
                # [IQR] months) — so allow one "[...]" group there. Without
                # it the strict adjacent-unit rule flags a correctly stated
                # median as unverified (live 2026-11-25: '5.7 months').
                adj = re.search(
                    rf"{re.escape(num)}\s*(?:\[[^\]]*\]\s*)?-?\s*"
                    rf"(?:{TIME_UNIT_VARIANTS[stem]})"
                    rf"\b", ab, re.I)
                if not adj:
                    findings.append({
                        "pmid": pmid, "level": "error",
                        "issue": f"number '{t}' in {where}: the unit "
                                 f"('{unit}') does not appear next to {num} "
                                 f"in the abstract"})
        elif t.endswith("%"):
            ab_pct = ab.replace(" %", "%")
            if (f"{num}%" not in ab_pct
                    and f"{num} percent" not in ab.lower()):
                findings.append({
                    "pmid": pmid, "level": "error",
                    "issue": f"number '{t}' in {where}: no {num}% in the "
                             f"abstract"})


def audit(blocks: list, src: dict, truncated: dict | None = None,
          focus: list | None = None) -> list:
    """Trace digest numbers back to their PubMed abstracts.

    `truncated` maps PMID -> the abstract text the model was actually given
    (same truncation as the prompt). Numbers are checked against THAT text,
    not the full abstract: a number that only appears past the truncation
    point could not have been grounded, however correct it is. `focus` is
    the Week-in-focus bullets from parse_focus_bullets()."""
    findings = []
    seen: set = set()
    for b in blocks:
        if b["pmid"] in seen:
            findings.append({
                "pmid": b["pmid"], "level": "error",
                "issue": "duplicate item block for the same PMID (the model "
                         "re-wrote an item, sometimes with a different journal)"})
            continue
        seen.add(b["pmid"])
        rec = src.get(b["pmid"], {})
        if not rec:
            findings.append({"pmid": b["pmid"], "level": "error",
                             "issue": "PMID not found on PubMed"})
            continue
        # numbers may legitimately come from the title (e.g. IL-23 in a title)
        full = norm(rec.get("abstract", "")) + " " + norm(rec.get("title", ""))
        trunc = truncated.get(b["pmid"]) if truncated else None
        ab = (norm(trunc) + " " + norm(rec.get("title", ""))) \
            if trunc is not None else full
        for field in ("what", "impact", "caveat"):
            if not b.get(field):
                findings.append({"pmid": b["pmid"], "level": "warn",
                                 "issue": f"missing '{field}' line"})
        # journal sanity
        jr = norm(rec.get("journal", "")).lower()
        stated = norm(b["raw"].split("**Citation**")[1][:160]).lower() \
            if "**Citation**" in b["raw"] else ""
        if jr and stated and jr.split()[0] not in stated:
            findings.append({"pmid": b["pmid"], "level": "warn",
                             "issue": f"journal mismatch: block says "
                                      f"'{stated[:60]}', PubMed says "
                                      f"'{rec['journal']}'"})
        # numbers in What-it-says, Practice impact AND Caveat must exist in
        # the abstract — a hallucinated number in Practice impact ("reduce
        # the dose by 50%") used to pass unchecked.
        for field, label in (("what", "What-it-says"),
                             ("impact", "Practice impact"),
                             ("caveat", "Caveat")):
            if b.get(field):
                _check_numbers(b["pmid"], b[field], ab, findings, label)
        # confidence levels must not be invented/altered. Normalize phrasing
        # variants first: abstracts write "95% confidence interval(s)",
        # "95%CI", "95 % CI" as often as the canonical "95% CI" (live 09-21:
        # 4 of 6 flags were this false positive on real CIs).
        ab_ci = re.sub(r"confidence intervals?", "CI", ab, flags=re.I)
        ab_ci = re.sub(r"(\d)\s+%", r"\1%", ab_ci)
        ab_ci = re.sub(r"%\s*CI\b", "% CI", ab_ci)
        for cl in CI_RE.findall(b["raw"]):
            if f"{cl}% CI" not in ab_ci:
                findings.append({"pmid": b["pmid"], "level": "error",
                                 "issue": f"'{cl}% CI' does not appear in the "
                                          f"abstract"})
    # Week-in-focus bullets: same number check, against the cited item's
    # abstract (truncated text when available).
    for fb in focus or []:
        rec = src.get(fb["pmid"], {})
        if not rec:
            findings.append({"pmid": fb["pmid"], "level": "error",
                             "issue": "Week in focus: PMID not found on "
                                      "PubMed"})
            continue
        trunc = truncated.get(fb["pmid"]) if truncated else None
        ab = (norm(trunc) + " " + norm(rec.get("title", ""))) \
            if trunc is not None else \
            norm(rec.get("abstract", "")) + " " + norm(rec.get("title", ""))
        _check_numbers(fb["pmid"], fb["text"], ab, findings, "Week in focus")
    return findings


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    maybe_out = [a for a in sys.argv[1:] if a.startswith("--json")]
    text = "\n".join(open(f, encoding="utf-8").read() for f in args)
    blocks = parse_blocks(text)
    print(f"digest blocks: {len(blocks)}")
    src = fetch_abstracts([b["pmid"] for b in blocks])
    print(f"PubMed records fetched: {len(src)}")
    findings = audit(blocks, src)
    errs = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]
    print(f"\nERRORS ({len(errs)}):")
    for f in errs:
        print(f"  PMID {f['pmid']}: {f['issue']}")
    print(f"\nWARNINGS ({len(warns)}):")
    for f in warns:
        print(f"  PMID {f['pmid']}: {f['issue']}")
    if maybe_out:
        json.dump({"blocks": len(blocks), "errors": errs, "warnings": warns},
                  open(maybe_out[0].split("=", 1)[-1].lstrip("=") or
                       "/tmp/digest_audit.json", "w"), indent=1)
    # exit non-zero when a stated number is not in its source abstract
    return 2 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
