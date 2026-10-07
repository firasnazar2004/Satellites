"""Server-owned limits for serial research analysis."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchConfig:
    model: str = os.environ.get("LOCAL_AI_RESEARCH_MODEL", "qwen3:8b")
    num_ctx: int = 8192
    num_predict: int = 2400
    window_chars: int = 5200
    window_overlap_blocks: int = 2
    packet_chars: int = 3200
    max_pages: int = 80
    synthesis_retries: int = 2


CONFIG = ResearchConfig()
