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


def norm(s: str) -> str:
    return (s or "").replace("\u2013", "-").replace("\u2014", "-") \
        .replace("\u2265", ">=").replace("\u2264", "<=").replace(",", "")


def audit(blocks: list, src: dict) -> list:
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
        ab = norm(rec.get("abstract", "")) + " " + norm(rec.get("title", ""))
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
        # numbers in the block's What-it-says must exist in the abstract
        for tok in NUM_RE.findall(norm(b["what"])):
            t = tok.strip()
            if not t or len(t) <= 1:
                continue
            core = re.match(r"\d+(?:\.\d+)?", t)
            if not core:
                continue
            num = core.group(0)
            # Compare the NUMERIC CORE only: a legit summary may expand a unit
            # ("2 wk" -> "2.0 weeks") or pad a decimal, which is not a
            # hallucination. Also accept the spelled-out form (five <-> 5).
            words = {"one": "1", "two": "2", "three": "3", "four": "4",
                     "five": "5", "six": "6", "seven": "7", "eight": "8",
                     "nine": "9", "ten": "10"}
            spelled = [w for w, d in words.items() if d == num.split(".")[0]]
            found = (num in ab or num.rstrip("0").rstrip(".") in ab
                     or any(w in ab.lower() for w in spelled))
            if not found:
                findings.append({"pmid": b["pmid"], "level": "error",
                                 "issue": f"number '{t}' (core {num}) in "
                                          f"What-it-says is NOT in the abstract"})
        # confidence levels must not be invented/altered
        for cl in CI_RE.findall(b["raw"]):
            if f"{cl}% CI" not in ab and f"{cl} % CI" not in ab:
                findings.append({"pmid": b["pmid"], "level": "error",
                                 "issue": f"'{cl}% CI' does not appear in the "
                                          f"abstract"})
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
