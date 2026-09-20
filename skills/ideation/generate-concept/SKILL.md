---
name: generate-concept
description: >-
  从用户一句话生成短剧故事核、类型、logline、钩子和集数规划。
  在用户要做创意、选题、故事概念、logline，或开始一部新短剧时使用。
pipeline: writing
sort_order: 10
depends_on: []
---

# 生成短剧概念

调度框架读取本文件 frontmatter 做路由；执行时把正文和 `reference/` 交给 LLM，按 `tool_schema.json` 填参，再调用无 IO 的 `scripts/run.py`。

## 何时使用

用户要立项、要故事核、还没有人物和剧本时。

## 约束

- 只产出概念，不写人物小传、大纲、台本。
- 类型枚举见 `reference/enums/genre_list.md`。
- 时长与钩子规则见 `reference/specs/concept_spec.md`。
- 子 prompt 见 `reference/prompts/inner_sub_prompt.txt`。
