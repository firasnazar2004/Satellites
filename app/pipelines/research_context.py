"""Overlapping bounded model views over immutable source blocks."""
from app.models.research_pipeline import ContextWindow, ResearchSourceMap


def build_context_windows(source: ResearchSourceMap, max_chars: int, overlap_blocks: int) -> list[ContextWindow]:
    blocks = [b for b in source.blocks if b.section_path.role != "references" and b.block_type != "heading"]
    windows = []
    abstract = [b for b in blocks if any(part.casefold() == "abstract" for part in b.section_path.parts) and len(b.normalized_text) >= 20]
    if abstract and sum(len(b.normalized_text) + 30 for b in abstract) <= max_chars:
        refs = [b.block_id for b in abstract]
        rendered = "\n".join(f"[{b.block_id} p.{b.page} {b.block_type}{' NUMERIC_LAYOUT_UNCERTAIN' if b.numeric_uncertain else ''}] {b.normalized_text}" for b in abstract)
        windows.append(ContextWindow(window_id="RW-ABSTRACT", section_path=abstract[0].section_path, source_refs=refs, rendered_text=rendered))
        windows.append(ContextWindow(window_id="RW-ABSTRACT-ROLES", section_path=abstract[0].section_path, source_refs=refs, rendered_text=rendered))
    start = 0
    while start < len(blocks):
        size = 0
        end = start
        while end < len(blocks):
            addition = len(blocks[end].normalized_text) + 30
            if end > start and size + addition > max_chars:
                break
            size += addition
            end += 1
        chosen = blocks[start:end]
        refs = [b.block_id for b in chosen]
        rendered = "\n".join(f"[{b.block_id} p.{b.page} {b.block_type}] {b.normalized_text}" for b in chosen)
        windows.append(ContextWindow(window_id=f"RW-{len(windows)+1:03d}", section_path=chosen[0].section_path, source_refs=refs, previous_context_refs=[b.block_id for b in blocks[max(0,start-overlap_blocks):start]], next_context_refs=[b.block_id for b in blocks[end:end+overlap_blocks]], rendered_text=rendered))
        if end == len(blocks):
            break
        start = max(start+1, end-overlap_blocks)
    return windows
