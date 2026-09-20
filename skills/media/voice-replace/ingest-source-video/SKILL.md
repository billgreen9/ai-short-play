---
name: ingest-source-video
description: >-
  登记待处理视频、解析角色音轨。在用户要处理视频、换配音、替换角色声音前使用。
pipeline: voice-replace
sort_order: 110
depends_on: []
---

# 源视频入库

只产出作业单 `media_job.action=ingest`。下载、转码、落库由调度层 adapter 执行。
