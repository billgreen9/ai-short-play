from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from pgvector import HalfVector, Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import get_settings
from app.models import IntentMatchRecord, SkillRecord, StepResult


def _vector_spec(embedding_dim: int) -> tuple[str, str]:
    if embedding_dim > 2000:
        return f"halfvec({embedding_dim})", "halfvec_cosine_ops"
    return f"vector({embedding_dim})", "vector_cosine_ops"


def _adapt_embedding(values: list[float] | None):
    if values is None:
        return None
    if get_settings().embedding_dim > 2000:
        return HalfVector(values)
    return Vector(values)


def _schema_sql(embedding_dim: int) -> str:
    vector_type, index_ops = _vector_spec(embedding_dim)
    return f"""
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS skill (
    id BIGSERIAL PRIMARY KEY,
    skill_name VARCHAR NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    skill_prompt TEXT NOT NULL DEFAULT '',
    function_tools VARCHAR(512) NOT NULL DEFAULT '',
    depends_on VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status INT NOT NULL DEFAULT 1,
    CONSTRAINT skill_skill_name_key UNIQUE (skill_name)
);

CREATE TABLE IF NOT EXISTS intent_match (
    id BIGSERIAL PRIMARY KEY,
    msg VARCHAR NOT NULL,
    msg_embedding {vector_type},
    score_limit DOUBLE PRECISION NOT NULL,
    score_confirm_limit DOUBLE PRECISION NOT NULL,
    skill_id BIGINT NULL REFERENCES skill(id) ON DELETE SET NULL,
    answer TEXT NULL,
    support INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS intent_match_msg_trgm
    ON intent_match USING gin (msg gin_trgm_ops);
CREATE INDEX IF NOT EXISTS intent_match_skill_id
    ON intent_match (skill_id);
CREATE INDEX IF NOT EXISTS intent_match_embedding_hnsw
    ON intent_match USING hnsw (msg_embedding {index_ops});


CREATE TABLE IF NOT EXISTS runs (
    id UUID PRIMARY KEY,
    user_input TEXT NOT NULL,
    plan TEXT[] NOT NULL DEFAULT '{{}}',
    status TEXT NOT NULL,
    route_reason TEXT,
    final_output TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS run_steps (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL,
    step_index INT NOT NULL,
    status TEXT NOT NULL,
    output JSONB,
    error TEXT,
    tools TEXT[] NOT NULL DEFAULT '{{}}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row, autocommit=True) as conn:
        register_vector(conn)
        yield conn


def init_schema() -> None:
    settings = get_settings()
    with get_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS skills")
        conn.execute(_schema_sql(settings.embedding_dim))


def row_to_skill(row: dict[str, Any]) -> SkillRecord:
    return SkillRecord(
        id=int(row["id"]),
        skill_name=row["skill_name"],
        description=row.get("description") or "",
        skill_prompt=row.get("skill_prompt") or "",
        function_tools=row.get("function_tools") or "",
        depends_on=row.get("depends_on"),
        status=int(row.get("status") or 0),
    )


def fetch_skill_by_id(skill_id: int) -> SkillRecord | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM skill WHERE id = %s AND status = 1",
            (skill_id,),
        ).fetchone()
        return row_to_skill(row) if row else None


def fetch_skill_by_name(skill_name: str, *, include_disabled: bool = False) -> SkillRecord | None:
    sql = "SELECT * FROM skill WHERE skill_name = %s"
    params: list[Any] = [skill_name]
    if not include_disabled:
        sql += " AND status = 1"
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return row_to_skill(row) if row else None


def list_skills(*, include_disabled: bool = False) -> list[SkillRecord]:
    sql = "SELECT * FROM skill"
    if not include_disabled:
        sql += " WHERE status = 1"
    sql += " ORDER BY id"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
        return [row_to_skill(row) for row in rows]


def upsert_skill(
    *,
    skill_name: str,
    description: str,
    skill_prompt: str,
    function_tools: str = "",
    depends_on: str | None = None,
    status: int = 1,
) -> SkillRecord:
    sql = """
        INSERT INTO skill (
            skill_name, description, skill_prompt, function_tools, depends_on, status, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (skill_name) DO UPDATE SET
            description = EXCLUDED.description,
            skill_prompt = EXCLUDED.skill_prompt,
            function_tools = EXCLUDED.function_tools,
            depends_on = EXCLUDED.depends_on,
            status = EXCLUDED.status,
            updated_at = now()
        RETURNING *
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (skill_name, description, skill_prompt, function_tools or "", depends_on, status),
        ).fetchone()
        return row_to_skill(row)


def insert_intent_match(
    *,
    msg: str,
    embedding: list[float] | None,
    score_limit: float,
    score_confirm_limit: float,
    skill_id: int | None,
    answer: str | None = None,
    support: int = 1,
) -> int:
    sql = """
        INSERT INTO intent_match (
            msg, msg_embedding, score_limit, score_confirm_limit, skill_id, answer, support, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        RETURNING id
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (msg, _adapt_embedding(embedding), score_limit, score_confirm_limit, skill_id, answer, support),
        ).fetchone()
        return int(row["id"])


def update_intent_match_msg(
    intent_id: int,
    *,
    msg: str,
    embedding: list[float] | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE intent_match
            SET msg = %s, msg_embedding = %s, updated_at = now()
            WHERE id = %s
            """,
            (msg, _adapt_embedding(embedding), intent_id),
        )


def find_canonical_intent(skill_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM intent_match
            WHERE skill_id = %s
            ORDER BY id
            LIMIT 1
            """,
            (skill_id,),
        ).fetchone()


def list_intent_matches() -> list[dict[str, Any]]:
    with get_conn() as conn:
        return list(conn.execute("SELECT id, msg, msg_embedding FROM intent_match ORDER BY id").fetchall())


def find_intent_by_skill_msg(skill_id: int, msg: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM intent_match
            WHERE skill_id = %s AND msg = %s
            LIMIT 1
            """,
            (skill_id, msg),
        ).fetchone()


def keyword_search(query: str, top_k: int) -> list[dict[str, Any]]:
    sql = """
        SELECT
            i.id,
            i.msg,
            i.score_limit,
            i.score_confirm_limit,
            i.skill_id,
            i.answer,
            i.support,
            s.skill_name,
            s.status AS skill_status,
            GREATEST(similarity(i.msg, %(query)s), word_similarity(%(query)s, i.msg)) AS keyword_score
        FROM intent_match i
        LEFT JOIN skill s ON s.id = i.skill_id
        WHERE i.skill_id IS NULL OR s.status = 1
        ORDER BY keyword_score DESC, i.id
        LIMIT %(top_k)s
    """
    with get_conn() as conn:
        return list(conn.execute(sql, {"query": query, "top_k": top_k}).fetchall())


def semantic_search(embedding: list[float], top_k: int) -> list[dict[str, Any]]:
    sql = """
        SELECT
            i.id,
            i.msg,
            i.score_limit,
            i.score_confirm_limit,
            i.skill_id,
            i.answer,
            i.support,
            s.skill_name,
            s.status AS skill_status,
            (1 - (i.msg_embedding <=> %(embedding)s)) AS semantic_score
        FROM intent_match i
        LEFT JOIN skill s ON s.id = i.skill_id
        WHERE i.msg_embedding IS NOT NULL
          AND (i.skill_id IS NULL OR s.status = 1)
        ORDER BY i.msg_embedding <=> %(embedding)s, i.id
        LIMIT %(top_k)s
    """
    with get_conn() as conn:
        return list(conn.execute(sql, {"embedding": _adapt_embedding(embedding), "top_k": top_k}).fetchall())


def row_to_intent(row: dict[str, Any]) -> IntentMatchRecord:
    return IntentMatchRecord(
        id=int(row["id"]),
        msg=row["msg"],
        score_limit=float(row["score_limit"]),
        score_confirm_limit=float(row["score_confirm_limit"]),
        skill_id=int(row["skill_id"]) if row.get("skill_id") is not None else None,
        answer=row.get("answer"),
        support=int(row.get("support") if row.get("support") is not None else 1),
        skill_name=row.get("skill_name"),
        skill_status=int(row["skill_status"]) if row.get("skill_status") is not None else None,
    )


def create_run(run_id: str, user_input: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO runs (id, user_input, status)
            VALUES (%s, %s, 'running')
            ON CONFLICT (id) DO NOTHING
            """,
            (run_id, user_input),
        )


def update_run_status(run_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = %s
            WHERE id = %s
            """,
            (status, run_id),
        )


def update_run_plan(run_id: str, plan: list[str], reason: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE runs
            SET plan = %s, route_reason = %s
            WHERE id = %s
            """,
            (plan, reason, run_id),
        )


def finish_run(run_id: str, status: str, final_output: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = %s, final_output = %s, finished_at = now()
            WHERE id = %s
            """,
            (status, final_output, run_id),
        )


def insert_step(run_id: str, step: StepResult) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO run_steps (run_id, skill_name, step_index, status, output, error, tools)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                step.skill_name,
                step.step_index,
                step.status,
                Json(step.output),
                step.error,
                step.tools,
            ),
        )


def load_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = %s", (run_id,)).fetchone()
        return dict(row) if row else None


def delete_skill_by_name(skill_name: str) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM skill WHERE skill_name = %s", (skill_name,)).fetchone()
        if not row:
            return
        skill_id = row["id"]
        conn.execute("DELETE FROM intent_match WHERE skill_id = %s", (skill_id,))
        conn.execute("DELETE FROM skill WHERE id = %s", (skill_id,))
