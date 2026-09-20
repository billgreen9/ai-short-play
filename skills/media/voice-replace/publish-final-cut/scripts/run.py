from __future__ import annotations

from typing import Any


def run(params: dict[str, Any]) -> dict[str, Any]:
    swap = (params.get("artifacts") or {}).get("swap-character-voice") or {}
    ingest = (params.get("artifacts") or {}).get("ingest-source-video") or {}
    swapped_url = swap.get("swapped_url")
    return {
        "from_character": swap.get("from_character"),
        "to_character": swap.get("to_character"),
        "source_url": ingest.get("source_url") or swap.get("source_url"),
        "swapped_url": swapped_url,
        "media_job": {"action": "publish", "output_url": swapped_url},
        "markdown": "准备发布成片，等待 adapter 写入 media_assets.output_url",
    }
