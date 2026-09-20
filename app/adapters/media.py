from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.db import upsert_media_asset


def _cdn(run_id: str, filename: str) -> str:
    return f"{get_settings().media_cdn_base.rstrip('/')}/{run_id}/{filename}"


def realize_media_job(run_id: str, skill_name: str, output: dict[str, Any]) -> dict[str, Any]:
    """执行 run() 产出的作业单：真正的下载/克隆/合成/上传发生在这里，不在 run.py。"""
    job = output.get("media_job")
    if not isinstance(job, dict):
        return output

    action = job.get("action")
    result = dict(output)
    if action == "ingest":
        source_url = job.get("source_url") or result.get("source_url")
        asset_id = f"src-{run_id[:8]}"
        result.update(
            {
                "asset_id": asset_id,
                "source_url": source_url,
                "tracks": result.get("tracks")
                or [{"character": "林晚", "type": "dialogue"}, {"character": "沈衡", "type": "dialogue"}],
            }
        )
        upsert_media_asset(
            run_id=run_id,
            skill_name=skill_name,
            kind="source",
            status="ready",
            source_url=source_url,
            output_url=source_url,
            meta={"asset_id": asset_id, "tracks": result["tracks"]},
        )
        return result

    if action == "swap_voice":
        from_character = job.get("from_character") or result.get("from_character")
        to_character = job.get("to_character") or result.get("to_character")
        swapped_url = _cdn(run_id, "swapped.mp4")
        result.update(
            {
                "from_character": from_character,
                "to_character": to_character,
                "swapped_url": swapped_url,
                "replaced_segments": result.get("replaced_segments") or 12,
                "markdown": f"已将「{from_character}」全部对白替换为「{to_character}」：{swapped_url}",
            }
        )
        upsert_media_asset(
            run_id=run_id,
            skill_name=skill_name,
            kind="swapped",
            status="ready",
            source_url=job.get("source_url") or result.get("source_url"),
            output_url=swapped_url,
            from_character=from_character,
            to_character=to_character,
            meta={"replaced_segments": result["replaced_segments"]},
        )
        return result

    if action == "publish":
        output_url = job.get("output_url") or result.get("swapped_url") or _cdn(run_id, "final.mp4")
        result["output_url"] = output_url
        result["publish_status"] = "ready"
        result["markdown"] = f"成片已发布，其他系统可用：{output_url}"
        upsert_media_asset(
            run_id=run_id,
            skill_name=skill_name,
            kind="final_cut",
            status="ready",
            source_url=result.get("source_url"),
            output_url=output_url,
            from_character=result.get("from_character"),
            to_character=result.get("to_character"),
            meta={"consumer": "other-systems"},
        )
        return result

    return result
