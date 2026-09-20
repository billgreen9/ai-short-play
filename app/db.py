from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import get_settings
from app.models import SkillMeta, StepResult

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS skills (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    skill_dir TEXT NOT NULL,
    skill_file TEXT NOT NULL,
    sort_order INT NOT NULL DEFAULT 100,
    depends_on TEXT[] NOT NULL DEFAULT '{}',
    disable_model_invocation BOOLEAN NOT NULL DEFAULT FALSE,
    scripts TEXT[] NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS skills_description_trgm
    ON skills USING gin (description gin_trgm_ops);

CREATE TABLE IF NOT EXISTS runs (
    id UUID PRIMARY KEY,
    user_input TEXT NOT NULL,
    plan TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    route_reason TEXT,
    route_strategy TEXT,
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
    skill_body TEXT,
    script_path TEXT,
    script_output JSONB,
    stdout TEXT,
    stderr TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plays (
    run_id UUID PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    concept JSONB,
    characters JSONB,
    outline JSONB,
    script JSONB,
    review JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS media_assets (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    source_url TEXT,
    output_url TEXT,
    from_character TEXT,
    to_character TEXT,
    meta JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS media_assets_run_kind
    ON media_assets (run_id, kind);
"""

PLAY_FIELD_BY_SKILL = {
    "generate-concept": "concept",
    "build-profiles": "characters",
    "write-outline": "outline",
    "write-script": "script",
    "quality-check": "review",
}


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row, autocommit=True) as conn:
        yield conn


def init_schema() -> None:
    with get_conn() as conn:
        conn.execute(SCHEMA_SQL)


def upsert_skills(skills: list[SkillMeta]) -> None:
    sql = """
        INSERT INTO skills (
            name, description, category, rel_path, skill_dir, skill_file,
            sort_order, depends_on, disable_model_invocation, scripts, updated_at
        )
        VALUES (
            %(name)s, %(description)s, %(category)s, %(rel_path)s, %(skill_dir)s, %(skill_file)s,
            %(sort_order)s, %(depends_on)s, %(disable_model_invocation)s, %(scripts)s, now()
        )
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description,
            category = EXCLUDED.category,
            rel_path = EXCLUDED.rel_path,
            skill_dir = EXCLUDED.skill_dir,
            skill_file = EXCLUDED.skill_file,
            sort_order = EXCLUDED.sort_order,
            depends_on = EXCLUDED.depends_on,
            disable_model_invocation = EXCLUDED.disable_model_invocation,
            scripts = EXCLUDED.scripts,
            updated_at = now()
    """
    names = [skill.name for skill in skills]
    fields = (
        "name",
        "description",
        "category",
        "rel_path",
        "skill_dir",
        "skill_file",
        "sort_order",
        "depends_on",
        "disable_model_invocation",
        "scripts",
    )
    with get_conn() as conn:
        with conn.cursor() as cur:
            for skill in skills:
                cur.execute(sql, skill.model_dump(include=set(fields)))
            if names:
                cur.execute("DELETE FROM skills WHERE NOT (name = ANY(%s))", (names,))


def create_run(run_id: str, user_input: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO runs (id, user_input, status)
            VALUES (%s, %s, 'running')
            """,
            (run_id, user_input),
        )


def update_run_plan(run_id: str, plan: list[str], reason: str, strategy: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE runs
            SET plan = %s, route_reason = %s, route_strategy = %s
            WHERE id = %s
            """,
            (plan, reason, strategy, run_id),
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


def insert_step(run_id: str, skill_body: str, step: StepResult) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO run_steps (
                run_id, skill_name, step_index, status, skill_body,
                script_path, script_output, stdout, stderr, error
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                step.skill_name,
                step.step_index,
                step.status,
                skill_body,
                step.script_path,
                Json(step.output),
                None,
                None,
                step.error,
            ),
        )
        play_field = PLAY_FIELD_BY_SKILL.get(step.skill_name)
        if play_field and step.output:
            conn.execute(
                f"""
                INSERT INTO plays (run_id, {play_field}, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (run_id) DO UPDATE SET
                    {play_field} = EXCLUDED.{play_field},
                    updated_at = now()
                """,
                (run_id, Json(step.output)),
            )


def load_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = %s", (run_id,)).fetchone()
        return dict(row) if row else None


def upsert_media_asset(
    *,
    run_id: str,
    skill_name: str,
    kind: str,
    status: str,
    source_url: str | None,
    output_url: str | None,
    from_character: str | None = None,
    to_character: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sql = """
        INSERT INTO media_assets (
            run_id, skill_name, kind, status, source_url, output_url,
            from_character, to_character, meta, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        RETURNING *
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (
                run_id,
                skill_name,
                kind,
                status,
                source_url,
                output_url,
                from_character,
                to_character,
                Json(meta or {}),
            ),
        ).fetchone()
        return dict(row)


def load_final_cut(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM media_assets
            WHERE run_id = %s AND kind = 'final_cut' AND status = 'ready'
            ORDER BY id DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        return dict(row) if row else None
