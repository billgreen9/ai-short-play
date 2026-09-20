---
name: build-profiles
description: >-
  根据故事概念生成短剧人物小传、人物关系与每集可消费的人设冲突。
  在用户要做人设、角色、人物小传或关系网时使用。
pipeline: writing
sort_order: 20
depends_on:
  - generate-concept
---

# 生成人物小传

调度层读取 `tool_schema.json` 填人物参数，`scripts/run.py` 只做结构化组装。

依赖上游 `artifacts.generate-concept`。角色类型见 `reference/enums/role_types.md`。
