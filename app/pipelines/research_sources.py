"""PDF geometry, conservative normalization and source passage provenance.

No model calls. Numeric strings are never retyped, rounded, or inferred here.
Reading-order detection is heuristic and exposes overrides and warnings.
"""

import re
from collections import Counter
from statistics import median

import pdfplumber

from app.models.research import SourcePassage

HEADINGS = {
    "abstract": r"abstract|summary",
    "introduction": r"introduction|background|backgroundinformation",
    "methods": r"methods?|methodology|materials?andmethods?|studydesign|experimentalsetup",
    "results": r"results?|experiments?|evaluation|theoreticalresults?|analysis",
    "discussion": r"discussion|resultsanddiscussion",
    "conclusions": r"conclusions?(?:andrecommendations)?|concludingremarks",
    "limitations": r"limitations?(?:andfuturework)?",
    "references": r"(?:listof)?references|bibliography|literaturecited",
    "appendices": r"appendi(?:x|ces)(?:[a-z])?|supplementary(?:material|information)?",
    "excluded": r"(?:tableof)?contents|listof(?:tables|figures|abbreviations|appendices)|acknowledg(?:e)?ments|dedication",
}
EXCLUDED = {"references", "appendices", "excluded"}
LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})
TABLE_COLUMN_LABEL = re.compile(
    r"^(?:value|df|frequency|count|(?:valid |cumulative )?percent(?:age)?|"
    r"(?:asymp\.?|exact)\s*sig\.?|p(?:[- ]?value)?)", re.I)


def is_front_listing_start(raw_text):
    """Detect front-matter lists before their entries can change section state."""
    first_lines = [line.strip() for line in raw_text.splitlines() if line.strip()][:3]
    return any(re.fullmatch(
        r"(?:table\s*of\s*)?contents|list\s*of\s*(?:tables|figures|"
        r"appendices|abbreviations)", re.sub(r"\s+", "", line), re.I)
        for line in first_lines)


def is_body_restart(raw_text):
    first = next((line.strip() for line in raw_text.splitlines() if line.strip()), "")
    compact = re.sub(r"\s+", "", first)
    if re.match(r"chapter\d+[:.\-]?(?:introduction|background)", compact, re.I):
        return True
    # Papers may restart at an unnumbered Introduction after contents pages.
    # Require substantial body text so a contents entry alone cannot reset it.
    return (len(raw_text.split()) >= 50 and bool(re.fullmatch(
        r"(?:\d+(?:\.\d+)*[.:-]?)?(?:introduction|background)", compact, re.I)))


def table_headers(rows):
    """Preserve a spanning title and an optional labelled second header row."""
    first = [normalize_text(cell or "") for cell in rows[0]]
    second = [normalize_text(cell or "") for cell in rows[1]] if len(rows) > 1 else []
    second_is_header = sum(bool(TABLE_COLUMN_LABEL.match(cell)) for cell in second) >= 2
    headers = list(first)
    if second_is_header:
        headers = [(second[i] or ("" if i == 0 else first[i]))
                   if i < len(second) else first[i] for i in range(len(first))]
    title = first[0] if second_is_header and first[0] else ""
    return headers, title, 2 if second_is_header else 1


def link_table_context(passages):
    """Attach table footnotes to result rows, and result rows back to footnotes."""
    footnote_ids = [item["id"] for item in passages if re.search(
        r"(?:^[a-z]\.|footnote|expected count|minimum expected|missing)", item["text"], re.I)]
    result_ids = [item["id"] for item in passages if item["id"] not in footnote_ids]
    for item in passages:
        related = footnote_ids if item["id"] not in footnote_ids else result_ids
        item["context_ids"] = list(dict.fromkeys(item.get("context_ids", []) + related))
    return passages


def link_text_context(passages):
    """Link short method labels and their children without merging source text.

    PDF layouts often place ``3.3 Study population`` and the population itself
    in separate blocks. The IDs remain independently auditable, while these
    links preserve the hierarchy for extraction and report synthesis.
    """
    numbered = re.compile(r"^\s*\d+(?:\.\d+)+\s+\S")
    minor = re.compile(
        r"\b(?:inclusion|exclusion)\s+criteria|sampling(?:\s+technique)?|"
        r"study\s+(?:type|design|area|setting|population)|data[- ]collection|"
        r"data\s+analysis|ethical\s+considerations\b", re.I)

    def heading_level(text):
        if numbered.search(text):
            return 1
        if len(text.split()) <= 10 and (text.rstrip().endswith(":")
                or minor.search(text)):
            return 2
        return None

    parent = local = None
    for item in passages:
        level = heading_level(item["text"])
        if level == 1:
            parent, local = item, None
            continue
        if level == 2:
            if parent:
                item["context_ids"] = list(dict.fromkeys(
                    item.get("context_ids", []) + [parent["id"]]))
                parent["context_ids"] = list(dict.fromkeys(
                    parent.get("context_ids", []) + [item["id"]]))
            local = item
            continue
        context = [candidate for candidate in (parent, local)
                   if candidate and candidate["section"] == item["section"]]
        for heading in context:
            item["context_ids"] = list(dict.fromkeys(
                item.get("context_ids", []) + [heading["id"]]))
            heading["context_ids"] = list(dict.fromkeys(
                heading.get("context_ids", []) + [item["id"]]))
    return passages


def numeric_inventory(text):
    # Compare extraction views without attempting to repair numerical strings.
    return Counter(re.findall(r"[+−-]?(?:\d+(?:[.,]\d+)*|\.\d+)(?:[eE][+−-]?\d+)?", text))


def heading_section(text):
    clean = re.sub(r"^(?:chapter\s*[\divx]+\s*[:.\-]?|\d+(?:\.\d+)*[.\s:]+)\s*", "", text.strip(), flags=re.I)
    # Only actual short headings, or an explicitly punctuated inline heading.
    label = re.split(r"[:—]", clean, maxsplit=1)[0]
    compact = re.sub(r"[\s.\-]", "", label).casefold()
    for section, pattern in HEADINGS.items():
        if re.fullmatch(pattern, compact):
            return section
    return None


def section_transition(current, detected, page_number):
    """Keep labelled subsections inside an opening structured abstract."""
    if current == "abstract" and page_number <= 3 and detected in {
            "methods", "results", "discussion", "conclusions", "limitations"}:
        return "abstract"
    return detected or current


def interleave_table_passages(text_passages, table_passages, gutters=()):
    """Place ruled table rows among text in single-column page reading order."""
    passages = list(text_passages) + list(table_passages)
    if gutters:
        return passages, "Table passages retained after column text; verify table reading order"
    passages.sort(key=lambda item: (
        item.get("bbox", (0, 0, 0, 0))[1],
        1 if item.get("kind") == "table" else 0,
        int(re.search(r"-R(\d+)$", item["id"]).group(1))
            if re.search(r"-R(\d+)$", item["id"]) else 0,
    ))
    return passages, None


def normalize_text(raw):
    text = raw.translate(LIGATURES).replace("\u00a0", " ")
    # Join alphabetic line-end hyphens only; retain the hyphen. Thus neither
    # technical compounds nor signs/ranges/numerical tokens are silently changed.
    text = re.sub(r"(?<=[A-Za-z])[-\u00ad]\s*\n\s*(?=[a-z])", "-", text)
    return " ".join(text.split())


def bbox(items):
    return (min(w["x0"] for w in items), min(w["top"] for w in items),
            max(w["x1"] for w in items), max(w["bottom"] for w in items))


def lines_from_words(words):
    rows = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not rows or abs(word["top"] - rows[-1][0]["top"]) > 3:
            rows.append([])
        rows[-1].append(word)
    return [sorted(row, key=lambda w: w["x0"]) for row in rows]


def reading_columns(words, width, mode="auto"):
    """Find persistent vertical gutters; full-width lines delimit column bands."""
    if mode != "auto":
        count = {"single": 1, "two": 2, "three": 3}[mode]
        return [width * i / count for i in range(1, count)], []
    rows = lines_from_words(words)
    if len(rows) < 6:
        return [], []
    candidates = []
    for step in range(25, 76):
        x = width * step / 100
        good = 0
        for row in rows:
            left = [w for w in row if w["x1"] < x]
            right = [w for w in row if w["x0"] > x]
            crossing = any(w["x0"] <= x <= w["x1"] for w in row)
            if left and right and not crossing:
                gap = min(w["x0"] for w in right) - max(w["x1"] for w in left)
                good += gap >= width * .025
        if good >= max(5, len(rows) * .5):
            candidates.append((good, -abs(x-width/2), x))
    gutters = []
    for _, _, x in sorted(candidates, reverse=True):
        if all(abs(x-g) > width*.22 for g in gutters):
            gutters.append(x)
        if len(gutters) == 2:
            break
    warnings = ["Automatic multi-column reading order; verify passage coordinates"] if gutters else []
    return sorted(gutters), warnings


def ordered_lines(words, gutters):
    rows = lines_from_words(words)
    if not gutters:
        return rows
    output, band = [], []

    def flush():
        for column in range(len(gutters)+1):
            selected = [w for w in band if sum(w["x0"] > x for x in gutters) == column]
            output.extend(lines_from_words(selected))
        band.clear()

    for row in rows:
        if any(w["x0"] < g < w["x1"] for w in row for g in gutters):
            flush()
            output.append(row)
        else:
            band.extend(row)
    flush()
    return output


def split_passage(text, limit):
    """Offsets always refer to the full normalized block; no overlapping windows."""
    start = 0
    while start < len(text):
        end = min(start+limit, len(text))
        if end < len(text):
            boundaries = [m.end() for m in re.finditer(r"[.!?](?=\s+[A-Z])", text[start:end])]
            end = start+boundaries[-1] if boundaries else text.rfind(" ", start, end)
            if end <= start:
                end = min(start+limit, len(text))
        yield start, end, text[start:end]
        start = end
        while start < len(text) and text[start].isspace():
            start += 1


def extract_pages(path, *, passage_chars=900, reading_order="auto"):
    """Yield one serially processed page, preserving raw lines, words and tables."""
    section = "front_matter"
    front_listing = False
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            if number > 2 and section == "front_matter":
                section = "unknown"
            warnings, table_records, passages = [], [], []
            raw_text = page.extract_text() or ""
            if is_body_restart(raw_text):
                front_listing = False
                section = "introduction"
            elif is_front_listing_start(raw_text):
                front_listing = True
                section = "excluded"
            words = page.extract_words(x_tolerance=1, x_tolerance_ratio=.12,
                                       y_tolerance=3, keep_blank_chars=False)
            if numeric_inventory(raw_text) != numeric_inventory(" ".join(w["text"] for w in words)):
                warnings.append("Numeric token discrepancy between raw and word extraction; inspect original page")
            # Ruled tables are reliable enough for MVP; no inferred cell values.
            try:
                tables = page.find_tables()
                for i, table in enumerate(tables, 1):
                    rows = table.extract(x_tolerance=1, y_tolerance=3)
                    if len(rows) < 2 or max(map(len, rows), default=0) < 2:
                        continue
                    table_records.append({"id": f"T{number}-{i}", "bbox": table.bbox,
                                          "rows": rows, "page": number,
                                          "cell_bboxes": [r.cells for r in table.rows]})
            except Exception as exc:
                warnings.append(f"Table extraction failed: {type(exc).__name__}: {exc}")
            def in_table(word):
                x, y = (word["x0"]+word["x1"])/2, (word["top"]+word["bottom"])/2
                return any(t["bbox"][0] <= x <= t["bbox"][2] and
                           t["bbox"][1] <= y <= t["bbox"][3] for t in table_records)
            body = [w for w in words if not in_table(w)]
            gutters, layout_warnings = reading_columns(body, page.width, reading_order)
            warnings.extend(layout_warnings)
            rows = ordered_lines(body, gutters)
            line_records, groups, current = [], [], []
            height = median([w["bottom"]-w["top"] for w in words]) if words else 10
            for row in rows:
                raw = " ".join(w["text"] for w in row)
                box = bbox(row)
                # Running page numbers/header/footer text stay in provenance.
                margin = box[3] < page.height*.045 or box[1] > page.height*.955
                numbered = bool(re.fullmatch(r"[\divxlcdm\s|/–-]+", raw, re.I))
                line = {"id": f"L{number}-{len(line_records)+1}", "raw_text": raw,
                        "bbox": box, "words": row, "excluded_margin": margin or numbered}
                line_records.append(line)
                if margin or numbered:
                    continue
                detected_section = None if front_listing else heading_section(raw)
                new_section = section_transition(section, detected_section, number)
                gap = box[1]-current[-1]["bbox"][3] if current else 0
                if current and (new_section or gap > height*.85 or gap < -height or
                                abs(box[0]-current[-1]["bbox"][0]) > page.width*.2):
                    groups.append((section, current)); current = []
                if new_section:
                    section = new_section
                current.append(line)
            if current:
                groups.append((section, current))
            if re.search(r"\bTable\s+\d+", raw_text, re.I) and not table_records:
                warnings.append("Table mentioned but no ruled table detected; inspect unruled tables manually")
            blocks = []
            for block_section, group in groups:
                raw = "\n".join(line["raw_text"] for line in group)
                norm = normalize_text(raw)
                blocks.append({"raw_text": raw, "text": norm, "section": block_section,
                               "line_ids": [line["id"] for line in group],
                               "bbox": (min(l["bbox"][0] for l in group), min(l["bbox"][1] for l in group),
                                        max(l["bbox"][2] for l in group), max(l["bbox"][3] for l in group))})
            for block_index, block in enumerate(blocks, 1):
                for part, (start, end, text) in enumerate(split_passage(block["text"], passage_chars), 1):
                    # A single heading isn't evidence; it remains in page blocks.
                    if heading_section(text) and len(text.split()) < 7:
                        continue
                    p = SourcePassage(id=f"P{number}-B{block_index}-{part}", page=number,
                        section=block["section"], text=text, raw_text=block["raw_text"],
                        bbox=block["bbox"], line_ids=block["line_ids"],
                        warnings=[w for w in warnings if w.startswith("Numeric token")])
                    entry = p.model_dump(mode="json")
                    entry["block_index"] = block_index
                    entry["normalized_start"] = start
                    entry["normalized_end"] = end
                    passages.append(entry)
            # Keep text passages separate: table-row passages are appended below
            # and intentionally have no block_index/normalized offsets.
            text_passages = [p for p in passages
                             if p.get("kind", "text") == "text" and "block_index" in p]
            # Adjacent pieces of the SAME paragraph retain denominator/subgroup
            # context without sending overlapping copies through extraction.
            for p in text_passages:
                p["context_ids"] = [q["id"] for q in text_passages
                                    if q["block_index"] == p["block_index"]
                                    and q["id"] != p["id"]]
            link_text_context(text_passages)
            for table in table_records:
                near_block_indexes = {
                    index for index, block in enumerate(blocks, 1)
                    if block["bbox"][3] >= table["bbox"][1]-85
                    and block["bbox"][1] <= table["bbox"][3]+85
                }
                near = [blocks[index-1] for index in sorted(near_block_indexes)]
                table["context_text"] = [b["text"] for b in near]
                table["context_ids"] = [p["id"] for p in text_passages
                                        if p["block_index"] in near_block_indexes]
                above = [b for b in blocks if b["bbox"][1] < table["bbox"][1]]
                table_section = above[-1]["section"] if above else (blocks[0]["section"] if blocks else section)
                # Keep raw cells (including units/superscripts), headings and footnotes.
                # Header association is explicit, provisional, and auditable.
                headers, title, header_rows = table_headers(table["rows"])
                table["header_rows"] = header_rows
                table_passages = []
                for ri, row in enumerate(table["rows"][1:], 1):
                    if ri < header_rows:
                        continue
                    raw = " | ".join(c or "" for c in row)
                    cells = [normalize_text(c or "") for c in row]
                    text = " | ".join(([title] if title else []) + [
                        (headers[i]+": " if i < len(headers) and headers[i] else "") + cell
                        for i, cell in enumerate(cells) if cell
                    ])
                    if len(text) > passage_chars:
                        warnings.append(f"{table['id']} row {ri} exceeds passage budget; retained only in tables")
                        continue
                    table_passages.append(SourcePassage(id=f"P{number}-{table['id']}-R{ri}",
                        page=number, section=table_section, kind="table", text=text,
                        raw_text=raw, bbox=table["bbox"], table_id=table["id"],
                        context_ids=table["context_ids"],
                        warnings=["Table header association needs review; see raw cells and context"]+
                                 [w for w in warnings if w.startswith("Numeric token")]).model_dump(mode="json"))
                # Statistical footnotes qualify every row in their table. Link
                # them explicitly so selection and synthesis cannot separate a
                # result from an expected-count or similar interpretation caveat.
                passages.extend(link_table_context(table_passages))
            if table_records:
                text_passages = [item for item in passages if item.get("kind") != "table"]
                table_passages = [item for item in passages if item.get("kind") == "table"]
                passages, order_warning = interleave_table_passages(
                    text_passages, table_passages, gutters)
                if order_warning:
                    warnings.append(order_warning)
            normalized_page = "\n\n".join([b["text"] for b in blocks] +
                ["\n".join(" | ".join(normalize_text(c or "") for c in row)
                           for row in t["rows"]) for t in table_records])
            yield {"page": number, "raw_text": raw_text,
                   "text": normalized_page,
                   "normalized_text": normalized_page,
                   "width": page.width, "height": page.height, "gutters": gutters,
                   "lines": line_records, "blocks": blocks, "tables": table_records,
                   "passages": passages, "warnings": warnings}
            page.close()
