# AI 短剧 Skills 编排

用户一句话进入系统后，先在数据库里匹配技能，再按依赖展开成 DAG，用 LangGraph 依次执行。Skill 不再放磁盘目录，全部存在 Postgres。

## 整体链路

```text
用户输入
  → intent_match：关键词检索 + 语义检索 → 按 skill_id 去重（留最高分）→ rerank
  → 只要匹配到 skill，先暂停等用户确认（确认前不调用执行大模型）
  → 用户确认后递归展开 depends_on，得到执行 DAG
  → 按拓扑顺序执行每个 skill（带 skill_prompt；function_tools 非空则注册工具）
  → 上游产物写入内存 artifacts，只向下游传递
  → 汇总输出，写入 runs / run_steps
```

LangGraph 节点：`match → confirm（interrupt 等确认）→ execute（循环）→ assemble`。Checkpoint 和业务表在同一套 Postgres。

`--use-skill` 跳过匹配和确认，直接执行。普通请求在 rerank 之后一定会 `interrupt()`：**invoke 立即返回，确认前不会调用 skill 执行大模型**。CLI 在本地等输入，续跑再开一条 LangSmith trace。rerank 用的是匹配阶段的小请求；执行大模型只在确认之后。

## 意图匹配

用户输入和 `intent_match.msg` 做匹配：

1. 关键词：`pg_trgm` + 中文字面覆盖分
2. 语义：把查询做成向量，和 `msg_embedding` 做余弦检索
3. 合并召回后，按 `skill_id` 去重，同一 skill 只保留分值最大的一条（`skill_id` 为空的应答行不去重）
4. 再 LLM rerank
5. 用**该条意图自己的**阈值分档：
   - `score > score_limit` 或落在确认区间：列出候选，**先等用户确认，再调用执行大模型**
   - 其余：未命中

命中后：

- `skill_id` 不为空：先确认，再展开依赖 DAG 并调用执行大模型
- `skill_id` 为空：直接返回 `answer`（`support=1` 系统相关，`support=0` 与本系统无关）

新增 skill 时，会把 `description` 作为 `msg` 插入 `intent_match`，并调用向量模型写入 `msg_embedding`。也可以再追加短口语句，提高关键词命中。

向量调用走火山方舟。纯文本 `/embeddings` 若 404，会回退到 `/embeddings/multimodal`。当前可用模型是 `doubao-embedding-vision-251215`（2048 维）。没有向量时仍走关键词和 rerank。

## 依赖 DAG

`skill.depends_on` 是英文逗号分隔的 `skill_name`。命中入口 skill 后递归加载全部依赖，检测环，再拓扑排序。

例如 `create_short_play → quality_check → write_script → write_outline → generate_concept, build_profiles`，实际执行顺序是：

```text
generate_concept → build_profiles → write_outline → write_script → quality_check → create_short_play
```

每个 skill 只执行一次。某个步骤失败则中断后续。

## 上下文传递（单向）

**上游可以把结果传给下游；下游不能把结果返回给上游。**

这是线性流水线，不是父子双向调用：

```text
A.save_result() → artifacts["A"]
B 执行时读取 artifacts["A"]（system 消息里的「上游产物」JSON，或 get_artifact）
B.save_result() → artifacts["B"]
C 可以读 A 和 B
C 的结果不会回到已经结束的 A
```

实现要点：

- 每个 skill `save_result` 后，产物写入内存 `artifacts[skill_name]`
- 下游执行时，已完成产物会放进 system 消息；注册了 `get_artifact` 时也可以按 skill 名读取
- 上游跑完即结束，不会等待下游，也不会被再次唤醒
- 下游不能回写、覆盖或回调上游 skill

如果以后需要「上游调用下游并拿到返回值再继续」，要改成嵌套调用，和当前 DAG 不是同一套模型。

## Skill 执行与 function tools

执行某个 skill 前先看 `function_tools` 是否为空：

- 为空：用结构化 messages 请求大模型
- 非空：同样用 messages，并把对应 function tool 注册进本次请求，进入工具循环

`execute_skill` 不再把用户输入拼进一段 prompt。调用大模型时使用 OpenAI 风格的 `messages`：

| role | 内容 |
| --- | --- |
| `system` | `skill_prompt`、技能名/说明、工具使用提示、上游产物 JSON |
| `user` | 用户原话（不做二次包装） |

内置工具：

| 工具 | 作用 |
| --- | --- |
| `save_result` | 保存当前 skill 的结构化输出，供下游读取 |
| `get_artifact` | 读取**已经执行完的**上游产物 |
| `list_artifacts` | 列出当前任务里已有产物名称 |

`function_tools` 字段是逗号分隔的工具名，例如 `get_artifact,save_result`。

## 表结构

### skill

| 字段 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `skill_name` | 唯一名 |
| `description` | 技能说明；新增时同步到 `intent_match.msg` |
| `skill_prompt` | 执行时的系统提示词 |
| `function_tools` | 逗号分隔的工具名，可为空字符串 |
| `depends_on` | 逗号分隔的上游 `skill_name` |
| `status` | `1` 有效，`0` 无效 |

### intent_match

| 字段 | 说明 |
| --- | --- |
| `msg` | 匹配文本，`pg_trgm` 索引 |
| `msg_embedding` | 查询向量，pgvector HNSW（2048 维用 `halfvec`） |
| `score_limit` / `score_confirm_limit` | 自动命中 / 需确认的阈值 |
| `skill_id` | 可空；空则返回 `answer` |
| `answer` | 无 skill 时的应答 |
| `support` | 默认 `1` 系统相关；`0` 表示与本系统无关 |

另外还有 `runs`、`run_steps` 记录一次任务的计划和逐步产物。

## 运行

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m app --init-db
python -m app --list
python -m app --list-tools
python -m app --backfill-embeddings
python -m app --route-only "只要人物小传"
python -m app "帮我写一个职场复仇短剧"
python -m app --use-skill build_profiles "只要人物小传"
python -m app --add-skill --name demo --description "演示技能" --prompt "你是助手" --tools save_result
```

交互运行时，分数落在确认区间会**暂停并等待你输入** skill 名或序号（`skip` 取消）。`--use-skill` 仍可跳过匹配、直接执行。

## LangSmith

`.env` 配置 `LANGSMITH_TRACING=true`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT=ai-short-play`。图节点和 LLM 调用会上报到 [smith.langchain.com](https://smith.langchain.com)。
