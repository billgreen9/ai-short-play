---
name: publish-final-cut
description: >-
  把换声后的成片发布为可被其他系统读取的 output_url。
  在用户要成片地址、发布、给下游系统取片时使用。
pipeline: voice-replace
sort_order: 130
depends_on:
  - swap-character-voice
---

# 发布成片

`run.py` 只声明 `media_job.action=publish`。adapter 写入 `media_assets` 表，其他系统按 run_id 查询 `kind=final_cut` 的 `output_url`。
