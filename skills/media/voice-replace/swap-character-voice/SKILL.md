---
name: swap-character-voice
description: >-
  把视频中某个角色的全部对白替换为另一个角色的声线。
  在用户说换声、配音、把A的声音换成B时使用。
pipeline: voice-replace
sort_order: 120
depends_on:
  - ingest-source-video
---

# 角色换声

`run.py` 只生成 `media_job.action=swap_voice`。克隆、对齐、混音由 adapter 完成。
