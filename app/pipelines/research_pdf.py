"""Text-native PDF validation and provenance-preserving source extraction."""
import re
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils import extract_text

from app.models.research_pipeline import (
    BlockType, PDFExtractionMetadata, ResearchSourceMap, SectionPath, SourceBlock,
)
from app.pipelines.research_tables import extract_tables, render_table


class ResearchFailure(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def validate_pdf(path: Path, max_pages: int):
    with path.open("rb") as stream:
        signature = stream.read(5)
    if signature != b"%PDF-":
        raise ResearchFailure("INVALID_PDF", "Missing PDF signature")
    try:
        pdf = pdfplumber.open(path)
        if not pdf.pages or len(pdf.pages) > max_pages:
            pdf.close()
            raise ResearchFailure("INVALID_PDF", f"Expected 1–{max_pages} pages")
        return pdf
    except ResearchFailure:
        raise
    except PDFPasswordIncorrect as exc:
        raise ResearchFailure("ENCRYPTED_PDF", "A password is required") from exc
    except Exception as exc:
        message = str(exc).lower()
        code = "ENCRYPTED_PDF" if "password" in message or "encrypt" in message else "INVALID_PDF"
        raise ResearchFailure(code, f"Cannot read PDF: {exc}") from exc


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _heading(text: str) -> bool:
    clean = text.strip()
    if not clean or len(clean) > 100 or len(clean.split()) > 12:
        return False
    if re.match(r"^(references|bibliography|abstract|introduction|background|methods?|materials and methods|results?|discussion|conclusions?|limitations|acknowledg(e)?ments)$", clean, re.I):
        return True
    if re.match(r"^\d+(?:\.\d+){0,2}\s+[A-Z][^.!?]{2,75}$", clean):
        return True
    return clean.isupper() and len(clean) > 3 and not re.search(r"\d", clean)


def _type(text: str) -> BlockType:
    if _heading(text):
        return BlockType.HEADING
    if re.match(r"^(table\s+\d+|tab\.\s*\d+)", text, re.I):
        return BlockType.TABLE_CAPTION
    if re.match(r"^(figure|fig\.)\s*\d+", text, re.I):
        return BlockType.FIGURE_CAPTION
    if re.match(r"^(?:[•\-]|\d+[.)])\s+", text):
        return BlockType.LIST
    if re.match(r"^(?:\*|†|‡)\s", text):
        return BlockType.FOOTNOTE
    return BlockType.PARAGRAPH


def _line_fragments(line: dict, page_width: float) -> list[dict]:
    """Separate text columns merged into one line by PDF extraction."""
    chars = line.get("chars") or []
    if len(chars) < 2:
        return [line]
    midpoint = page_width / 2
    cuts = [i for i in range(len(chars) - 1)
            if chars[i]["x1"] < midpoint < chars[i + 1]["x0"]
            and chars[i + 1]["x0"] - chars[i]["x1"] > 8]
    if not cuts:
        return [line]
    cut = max(cuts, key=lambda i: chars[i + 1]["x0"] - chars[i]["x1"])
    if cut < 5 or len(chars) - cut < 6:
        return [line]
    result = []
    for part in (chars[:cut + 1], chars[cut + 1:]):
        result.append({**line, "chars": part, "text": extract_text(part, x_tolerance=1).strip(),
                       "x0": min(char["x0"] for char in part), "x1": max(char["x1"] for char in part),
                       "top": min(char["top"] for char in part), "bottom": max(char["bottom"] for char in part)})
    return result


def _bold_heading(text: str, chars: list[dict]) -> bool:
    return (bool(chars) and len(text.split()) <= 8 and len(text) <= 80
            and bool(re.match(r"^[A-Z][A-Za-z\s/-]+$", text))
            and not re.match(r"^(?:Table|Figure|Fig)\b", text, re.I)
            and sum("Bold" in char.get("fontname", "") for char in chars) / len(chars) >= 0.8
            and max(char.get("size", 0) for char in chars) >= 9.5)


def _unnamed_references_start(blocks: list[SourceBlock]) -> int | None:
    """Locate a bibliography whose PDF omits an extractable heading."""
    for i, block in enumerate(blocks):
        if block.page <= max(1, blocks[-1].page // 2):
            continue
        if not re.match(r"^1\.\s+[A-Z][A-Za-z-]+,?\s", block.raw_text):
            continue
        next_number = 2
        last_index = i
        for j in range(i + 1, min(i + 12, len(blocks))):
            number = re.match(r"^(\d+)\.\s+", blocks[j].raw_text)
            if number and int(number.group(1)) == next_number and j - last_index <= 3:
                next_number += 1
                last_index = j
                if next_number == 4:
                    return i
    return None


def extract_source_map(path: Path, max_pages: int, pdf=None) -> ResearchSourceMap:
    pdf = pdf if pdf is not None else validate_pdf(path, max_pages)
    blocks = []
    tables = []
    characters = []
    empty_pages = []
    suspicious = []
    heading_count = 0
    page_heights = []
    section = []
    references = False
    try:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_heights.append(page.height)
            page_text = page.extract_text(x_tolerance=1) or ""
            chars = len(_normalize(page_text))
            characters.append(chars)
            if chars < 40:
                empty_pages.append(page_number)
            if chars < 150:
                suspicious.append(page_number)
            page_tables, regions = extract_tables(page, page_number, len(blocks) + 1)
            table_bboxes = [region[0] for region in regions]
            raw_lines = page.extract_text_lines(layout=False, strip=True, x_tolerance=1) or []
            fragments = [_line_fragments(line, page.width) for line in raw_lines]
            split_tops = [part[0]["top"] for part in fragments if len(part) == 2]
            column_start = min(split_tops) if len(split_tops) >= 3 else None
            lines = [line for parts in fragments for line in parts]
            items = []
            for line in lines:
                text = line.get("text", "").strip()
                if not text:
                    continue
                center = ((line["x0"] + line["x1"]) / 2, (line["top"] + line["bottom"]) / 2)
                if any(b[0] <= center[0] <= b[2] and b[1] <= center[1] <= b[3] for b in table_bboxes):
                    continue
                items.append((line["top"], line["x0"], text, (line["x0"], line["top"], line["x1"], line["bottom"]), None, _bold_heading(text, line.get("chars") or [])))
            for table, (bbox, _rows, block_id, table_id) in zip(page_tables, regions):
                items.append((bbox[1], bbox[0], render_table(table), bbox, table_id, False))
            if column_start is None:
                items.sort(key=lambda item: (item[0], item[1]))
            else:
                items.sort(key=lambda item: (0, item[0], item[1]) if item[0] < column_start
                           else (1 if item[1] < page.width / 2 else 2, item[0], item[1]))
            grouped = []
            for top, left, text, bbox, table_id, bold_heading in items:
                kind = BlockType.TABLE if table_id else BlockType.HEADING if bold_heading else _type(text)
                if not table_id and kind == BlockType.PARAGRAPH and grouped:
                    prior = grouped[-1]
                    gap = top - prior["bbox"][3]
                    if prior["kind"] == BlockType.PARAGRAPH and 0 <= gap < 8 and abs(left - prior["bbox"][0]) < 18 and len(prior["text"]) < 1800:
                        prior["text"] += "\n" + text
                        prior["bbox"] = (prior["bbox"][0], prior["bbox"][1], max(prior["bbox"][2], bbox[2]), bbox[3])
                        continue
                grouped.append({"text": text, "bbox": bbox, "kind": kind, "table_id": table_id})
            for order, item in enumerate(grouped):
                text = item["text"]
                kind = item["kind"]
                if kind == BlockType.HEADING:
                    heading_count += 1
                    clean = re.sub(r"^\d+(?:\.\d+)*\s+", "", text).strip()
                    if clean.casefold() in {"references", "bibliography"}:
                        references = True
                    if re.match(r"^\d+\.\d+", text) and section:
                        section = [section[0], clean]
                    else:
                        section = [clean]
                block = SourceBlock(
                    block_id=f"B{len(blocks)+1:05d}", page=page_number, order=order,
                    block_type=kind, raw_text=text, normalized_text=_normalize(text),
                    section_path=SectionPath(parts=section.copy(), role="references" if references else "body"),
                    bbox=item["bbox"], table_id=item["table_id"],
                )
                blocks.append(block)
                if kind == BlockType.FOOTNOTE and tables and tables[-1].page == page_number:
                    tables[-1].footnotes.append(text)
                    tables[-1].source_refs.append(block.block_id)
                if item["table_id"]:
                    table = next(t for t in page_tables if t.table_id == item["table_id"])
                    refs = [block.block_id]
                    table.source_refs = refs
                    for cell in table.cells:
                        cell.source_refs = refs
                    # Captions are separate, nearest preceding block on same page.
                    if len(blocks) > 1 and blocks[-2].block_type == BlockType.TABLE_CAPTION:
                        table.caption = blocks[-2].raw_text
                        table.source_refs.insert(0, blocks[-2].block_id)
                    tables.append(table)
        if not any(count >= 40 for count in characters):
            raise ResearchFailure("SCANNED_PDF_UNSUPPORTED", "No meaningful extractable text; OCR is unsupported")
        if sum(characters) < 200 or len([n for n in characters if n >= 40]) / len(characters) < 0.25:
            raise ResearchFailure("INSUFFICIENT_TEXT", "Too little text for reliable analysis")
        if not references:
            start = _unnamed_references_start(blocks)
            if start is not None:
                for block in blocks[start:]:
                    block.section_path = SectionPath(parts=["References"], role="references")
        for i, block in enumerate(blocks):
            block.previous_block_id = blocks[i-1].block_id if i else None
            block.next_block_id = blocks[i+1].block_id if i+1 < len(blocks) else None
            if (block.raw_text.strip().isdigit() and len(block.raw_text.strip()) <= 3
                and block.bbox and block.bbox[1] < page_heights[block.page-1] * 0.85
                and 0 < i < len(blocks)-1
                and blocks[i-1].page == block.page == blocks[i+1].page
                and blocks[i-1].block_type == BlockType.PARAGRAPH
                and blocks[i+1].block_type == BlockType.PARAGRAPH):
                blocks[i-1].numeric_uncertain = True
                block.numeric_uncertain = True
                blocks[i+1].numeric_uncertain = True
        return ResearchSourceMap(
            source_filename=path.name,
            metadata=PDFExtractionMetadata(page_count=len(pdf.pages), pages_with_text=len(characters)-len(empty_pages), characters_by_page=characters, empty_pages=empty_pages, suspicious_pages=suspicious, tables_detected=len(tables), headings_detected=heading_count, numeric_uncertain_blocks=[b.block_id for b in blocks if b.numeric_uncertain]),
            blocks=blocks, tables=tables,
        )
    finally:
        pdf.close()
