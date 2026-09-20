---
name: write-outline
description: >-
  把概念和人物展开成分集大纲、每集钩子与反转点。
  在用户要写大纲、剧情结构、分集节拍时使用。
pipeline: writing
sort_order: 30
depends_on:
  - generate-concept
  - build-profiles
---

# 写分集大纲

读取上游概念和人物，按 `reference/enums/beat_types.md` 组织节拍。
默认 8 集，规则见 `reference/specs/outline_spec.md`。
