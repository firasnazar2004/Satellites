"""Conservative geometric table extraction with explicit uncertainty."""
from app.models.research_pipeline import TableCell, TableStructure


def extract_tables(page, page_number: int, next_block_number: int):
    tables = []
    regions = []
    for index, found in enumerate(page.find_tables(), start=1):
        grid = found.extract() or []
        if not grid:
            continue
        table_id = f"T{page_number:03d}_{index:02d}"
        block_id = f"B{next_block_number + len(tables):05d}"
        rows = [[(cell or "").strip() for cell in row] for row in grid if row]
        width = max(map(len, rows), default=0)
        uncertain = width < 2 or len(rows) < 2 or any(len(row) != width for row in rows)
        headers = rows[0][1:] if rows else []
        if any(not label for label in headers):
            uncertain = True
        cells = []
        labels = []
        if not uncertain:
            for row in rows[1:]:
                label = row[0]
                if not label:
                    uncertain = True
                    break
                labels.append(label)
                for column, value in zip(headers, row[1:]):
                    if value:
                        cells.append(TableCell(row_label=label, column_label=column, value=value, source_refs=[block_id]))
        tables.append(TableStructure(table_id=table_id, page=page_number, column_labels=headers, row_labels=labels, cells=cells if not uncertain else [], source_refs=[block_id], uncertain=uncertain))
        regions.append((found.bbox, rows, block_id, table_id))
    return tables, regions


def render_table(table: TableStructure) -> str:
    if table.uncertain:
        return "[Table extraction uncertain; cells unavailable]"
    lines = [f"Table {table.table_id}. {table.caption}", "Columns: " + " | ".join(table.column_labels)]
    for row in table.row_labels:
        values = [f"{cell.column_label}: {cell.value}" for cell in table.cells if cell.row_label == row]
        lines.append(f"{row} | " + " | ".join(values))
    if table.footnotes:
        lines.append("Footnotes: " + " ".join(table.footnotes))
    return "\n".join(lines)
