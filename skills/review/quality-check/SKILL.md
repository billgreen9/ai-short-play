---
name: quality-check
description: >-
  检查短剧概念、人物、大纲和台本的钩子、人物动机、运镜与集间衔接问题。
  在用户要审稿、质检、找问题、给修改建议时使用。
pipeline: writing
sort_order: 50
depends_on:
  - write-script
---

# 短剧质检

只输出问题清单和修改建议。问题类型见 `reference/enums/issue_types.md`。
