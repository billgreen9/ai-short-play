# AI 短剧 Skills 编排

根据用户输入匹配多级目录 skills，用 LangGraph 按依赖逐步执行。每个 skill 的标准布局：

```text
skills/xxx_skill/
├── SKILL.md                 # 调度 frontmatter + LLM 执行说明
├── tool_schema.json         # OpenAI FunctionCall，调度层动态组装 tools
├── input_schema.json        # 脚本入参校验
├── output_schema.json       # 脚本出参校验
├── reference/               # 仅在 skill 被选中后给 LLM 读
│   ├── examples/
│   ├── enums/
│   ├── specs/
│   └── prompts/
└── scripts/run.py           # 纯函数 run(params) -> dict，无 stdin/stdout/DB/HTTP
```

## 一次执行怎么串

1. Catalog 只读 `name` / `description` / `tool_schema.json`
2. Route 排出 plan；需要模型时用已组装的 OpenAI tools 做参考
3. 执行某个 skill：读 `SKILL.md` + `reference/`，按 `tool_schema` 让模型填参
4. 用 `input_schema.json` 校验参数，调用 `run(params)`
5. 用 `output_schema.json` 校验结果，写入内存 `artifacts` 给下游

大模型请求在调度层的 executor，不在 `run.py`。`run.py` 只产出 JSON 作业单；下载/换声/合成/上传在 `app/adapters/`。成片 URL 写入 `media_assets`，其他系统按 `run_id` 查询。

下游 skill 从内存 `artifacts` 取上游 JSON。

## 运行

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m app --list
python -m app --dump-tools
python -m app --route-only "只要人物小传"
python -m app "帮我写一个职场复仇短剧"
python -m app "把视频里林晚的声音换成沈衡"
python -m app --final-url <run_id>
```

## LangSmith

`.env` 配置 `LANGSMITH_TRACING=true`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT=ai-short-play`。启动任务后图节点和 LLM 调用会上报到 [smith.langchain.com](https://smith.langchain.com)，项目名 `ai-short-play`。
