# AI 短剧 Skills 编排

Skill 存在 Postgres `skill` 表。用户输入先和 `intent_match.msg` 做匹配：关键词检索 + 语义检索，合并后再 rerank。按每条意图自己的阈值分档：

- `score > score_limit`：自动命中
- `score_confirm_limit < score <= score_limit`：把这些 skill 交给用户确认
- 命中且 `skill_id` 不为空：使用该 skill
- 该 skill 的 `depends_on` 不为空：递归加载依赖，形成 DAG，按拓扑顺序执行
- 每个 skill 执行前若 `function_tools` 非空，请求大模型时注册这些 function tool

新增 skill 时，会把 `description` 写入 `intent_match.msg`，并生成 `msg_embedding`。

## 表结构

`skill`：`skill_name` 唯一；`depends_on` 为英文逗号分隔的 `skill_name`；`function_tools` 为逗号分隔的工具名；`status` 1 有效 / 0 无效。

`intent_match`：`msg` 有 `pg_trgm` 全文索引；`msg_embedding` 有 pgvector HNSW 索引；`skill_id` 可空（空则返回 `answer`）；`support` 默认 1（系统相关），0 表示与本系统无关。

## 一次执行怎么串

1. 对 `intent_match` 做关键词 + 向量召回，融合分数后可选 LLM rerank
2. 自动命中则展开 DAG；处于确认区间则返回候选，不执行
3. 按顺序执行 skill：带上 `skill_prompt`，若有 `function_tools` 则注册后进入工具循环
4. 下游 skill 通过 `get_artifact` 读取上游产物

## 运行

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m app --init-db
python -m app --list
python -m app --list-tools
python -m app --route-only "只要人物小传"
python -m app "帮我写一个职场复仇短剧"
python -m app --use-skill build_profiles "只要人物小传"
python -m app --add-skill --name demo --description "演示技能" --prompt "你是助手" --tools save_result
```

需要确认时，用 `--use-skill <skill_name>` 显式执行该技能及其依赖。

`.env` 里 `OPENAI_EMBEDDING_MODEL` 需要是当前账号可用的向量模型。纯文本 `doubao-embedding-*` 若返回 404，会回退到 `/embeddings/multimodal`；当前可用的是 `doubao-embedding-vision-251215`（2048 维）。没有可用向量模型时，仍会走关键词检索和 LLM rerank。

## LangSmith

`.env` 配置 `LANGSMITH_TRACING=true`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT=ai-short-play`。启动任务后图节点和 LLM 调用会上报到 [smith.langchain.com](https://smith.langchain.com)。
