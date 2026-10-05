#!/usr/bin/env python3
"""Checks the built report against the formatting rules in the assignment brief.

    python3 audit_docx.py [path/to/report.docx]

Reads the Word XML directly and resolves style inheritance, so it tests what
Word will apply rather than what the builder meant to write. Exits 1 on any
failure.
"""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent
DOCX = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "out" / "MaltaShop_Microservices_Report.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
BODY_FONT, CODE_FONT = "Times New Roman", "Courier New"
CODE_STYLES = {"CodeBlock", "CodeListing"}
AMERICAN = r"\b(\w+iz(e|es|ed|ing|ation)|colou?r(?<!colour)|behavior|center|analyz\w*|favor\w*|modeling|labeled)\b"
# Book titles keep their published spelling.
AMERICAN_ALLOWED = {"size", "sizes", "sized", "Organizing"}  # "Organizing": a book title in the references

failures: list[str] = []


def w(name: str) -> str:
    return f"{{{W}}}{name}"


def check(condition: bool, message: str) -> None:
    print(("  ok    " if condition else "  FAIL  ") + message)
    if not condition:
        failures.append(message)


with zipfile.ZipFile(DOCX) as archive:
    document = etree.fromstring(archive.read("word/document.xml"))
    styles = etree.fromstring(archive.read("word/styles.xml"))
    footers = {name: etree.fromstring(archive.read(name))
               for name in archive.namelist() if re.match(r"word/footer\d*\.xml", name)}

style_by_id = {s.get(w("styleId")): s for s in styles.findall("w:style", NS)}
doc_defaults = styles.find("w:docDefaults", NS)


def style_chain(style_id: str | None) -> list:
    chain = []
    while style_id and style_id in style_by_id:
        style = style_by_id[style_id]
        chain.append(style)
        based = style.find("w:basedOn", NS)
        style_id = based.get(w("val")) if based is not None else None
    return chain


def first_value(elements: list, path: str, attribute: str):
    for element in elements:
        if element is None:
            continue
        found = element.find(path, NS)
        if found is not None and found.get(w(attribute)) is not None:
            return found.get(w(attribute))
    return None


def paragraph_style(paragraph) -> str:
    found = paragraph.find("w:pPr/w:pStyle", NS)
    return found.get(w("val")) if found is not None else "Normal"


def effective_ppr(paragraph, path: str, attribute: str):
    sources = [paragraph.find("w:pPr", NS)]
    sources += [s.find("w:pPr", NS) for s in style_chain(paragraph_style(paragraph))]
    sources.append(doc_defaults.find("w:pPrDefault/w:pPr", NS) if doc_defaults is not None else None)
    return first_value(sources, path, attribute)


def effective_rpr(run, paragraph, path: str, attribute: str):
    sources = [run.find("w:rPr", NS)]
    run_style = run.find("w:rPr/w:rStyle", NS)
    if run_style is not None:
        sources += [s.find("w:rPr", NS) for s in style_chain(run_style.get(w("val")))]
    sources += [s.find("w:rPr", NS) for s in style_chain(paragraph_style(paragraph))]
    sources.append(doc_defaults.find("w:rPrDefault/w:rPr", NS) if doc_defaults is not None else None)
    return first_value(sources, path, attribute)


body = document.find("w:body", NS)
paragraphs = body.findall(".//w:p", NS)
top_level = [p for p in paragraphs if p.getparent() is body]
# The front page reproduces the official Learn Key form, so the body-text rules
# apply from the contents page onwards.
contents_title = next(p for p in top_level if paragraph_style(p) == "ContentsTitle")
report_paragraphs = paragraphs[paragraphs.index(contents_title):]
report_top_level = top_level[top_level.index(contents_title):]

print(f"Auditing {DOCX.name}")

print("Page setup")
section = body.find("w:sectPr", NS)
size = section.find("w:pgSz", NS)
check(size.get(w("w")) == "11906" and size.get(w("h")) == "16838", "A4 page size (21.0 x 29.7 cm)")
check(size.get(w("orient")) in (None, "portrait"), "portrait orientation")
margins = section.find("w:pgMar", NS)
check(all(int(margins.get(w(edge))) >= 1134 for edge in ("top", "bottom", "left", "right")),
      "margins of at least 2 cm")

print("Footer")
footer_ref = section.find("w:footerReference", NS)
check(footer_ref is not None, "section has a footer")
footer_xml = b"".join(etree.tostring(f) for f in footers.values()).decode()
footer_text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", footer_xml))
check(re.search(r"\bPAGE\b", footer_xml) is not None and "NUMPAGES" in footer_xml,
      "footer uses PAGE and NUMPAGES fields")
check(footer_text.startswith("Page ") and " of " in footer_text, f'footer reads "Page X of Y" ({footer_text!r})')

print("Body text")
normal = style_by_id["Normal"]
check(first_value([normal.find("w:rPr", NS)], "w:rFonts", "ascii") == BODY_FONT, "Normal style is Times New Roman")
check(first_value([normal.find("w:rPr", NS)], "w:sz", "val") == "24", "Normal style is 12 pt")
check(first_value([normal.find("w:pPr", NS)], "w:spacing", "line") == "360", "Normal style has 1.5 line spacing")
check(first_value([normal.find("w:rPr", NS)], "w:lang", "val") == "en-GB", "Normal style language is British English")

prose = []
for p in report_top_level:
    style = paragraph_style(p)
    text = "".join(p.itertext()).strip()
    if style in CODE_STYLES or not text or p.find(".//w:drawing", NS) is not None:
        continue
    if style.lower().startswith("toc") or style == "ContentsTitle":
        continue
    prose.append((p, style, text))

bad_spacing = [t[:50] for p, s, t in prose
               if not s.startswith("Heading") and effective_ppr(p, "w:spacing", "line") != "360"]
check(not bad_spacing, f"{len(prose)} body paragraphs use 1.5 line spacing"
      + (f" (not: {bad_spacing[:3]})" if bad_spacing else ""))

justified = [("".join(p.itertext())[:50]) for p in paragraphs if effective_ppr(p, "w:jc", "val") in ("both", "distribute")]
check(not justified, "no paragraph is fully justified" + (f" ({justified[:3]})" if justified else ""))
not_left = [t[:50] for p, s, t in prose if effective_ppr(p, "w:jc", "val") not in (None, "left", "start")]
check(not not_left, "body paragraphs are left-aligned" + (f" (not: {not_left[:3]})" if not_left else ""))

print("Fonts")
wrong_font, wrong_size = [], []
for p in report_paragraphs:
    style = paragraph_style(p)
    for run in p.findall("w:r", NS) + p.findall("w:hyperlink/w:r", NS):
        text = "".join(t.text or "" for t in run.findall("w:t", NS))
        if not text.strip():
            continue
        font = effective_rpr(run, p, "w:rFonts", "ascii")
        size = effective_rpr(run, p, "w:sz", "val")
        code = font == CODE_FONT
        if font not in (BODY_FONT, CODE_FONT):
            wrong_font.append((font, text[:30]))
        if style in CODE_STYLES and not code:
            wrong_font.append((font, text[:30]))
        if not code and not style.startswith("Heading") and size not in ("24",) and style != "ContentsTitle":
            wrong_size.append((size, text[:30]))
check(not wrong_font, "all text is Times New Roman, with Courier New only for code"
      + (f" ({wrong_font[:3]})" if wrong_font else ""))
check(not wrong_size, "all non-heading prose is 12 pt" + (f" ({wrong_size[:3]})" if wrong_size else ""))
theme_fonts = [s.get(w("styleId")) for s in style_by_id.values()
               if s.find("w:rPr/w:rFonts", NS) is not None
               and s.find("w:rPr/w:rFonts", NS).get(w("asciiTheme")) is not None
               and any(paragraph_style(p) == s.get(w("styleId")) for p in paragraphs)]
check(not theme_fonts, "no style in use falls back to a theme font" + (f" ({theme_fonts})" if theme_fonts else ""))

print("Contents")
instructions = " ".join(t.text or "" for t in body.iter(w("instrText")))
check(re.search(r"TOC\s+\\o", instructions) is not None, "a real TOC field is present")
anchors = {h.get(w("anchor")) for h in body.iter(w("hyperlink")) if h.get(w("anchor"))}
bookmarks = {b.get(w("name")) for b in body.iter(w("bookmarkStart"))}
check(anchors and anchors <= bookmarks, f"all {len(anchors)} contents links point at a heading bookmark")
toc_text = [("".join(p.itertext())) for p in paragraphs if paragraph_style(p).lower().startswith("toc")]
check(toc_text and all(re.search(r"\d+$", line.strip()) for line in toc_text),
      f"all {len(toc_text)} contents entries carry a page number")

print("Cover sheet and word count")
all_text = "".join(body.itertext())
stated = re.search(r"([\d,]+) words \(excluding", all_text)
counted = subprocess.run([sys.executable, str(ROOT / "wordcount.py")], capture_output=True, text=True)
total = int(re.search(r"TOTAL_WORDS=(\d+)", counted.stdout).group(1))
check(stated is not None and int(stated.group(1).replace(",", "")) == total,
      f"cover word count matches the counter ({total:,})")
check(3600 <= total <= 4400, f"word count {total:,} is within 4,000 ±10%")
for label in ("Learner Name and Surname:", "Learner Registration No.", "Unit Title", "Declaration of authenticity:"):
    check(label in all_text, f'cover has "{label}"')

print("British English")
content = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "content").glob("*.md")))
content = re.sub(r"```.*?```", "", content, flags=re.S)
content = re.sub(r"`[^`]+`", "", content)
allowed = {word.lower() for word in AMERICAN_ALLOWED}
american = sorted({m.group(0) for m in re.finditer(AMERICAN, content) if m.group(0).lower() not in allowed})
check(not american, "no American spellings in the report text" + (f" ({american})" if american else ""))

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("all formatting checks passed")
