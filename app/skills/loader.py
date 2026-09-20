from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from app.models import SkillMeta, SkillRecord, SkillReference
from app.skills.schema import read_json
from app.skills.tools import normalize_tool

REQUIRED_FILES = (
    "SKILL.md",
    "tool_schema.json",
    "input_schema.json",
    "output_schema.json",
    "scripts/run.py",
    "reference/examples/demo_input.json",
    "reference/examples/demo_output.json",
)


def parse_skill_md(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")
    return meta, parts[2].lstrip("\n")


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace(",", " ").split() if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(f"cannot parse list from {value!r}")


def _category(rel: Path) -> str:
    parent = rel.parent
    if str(parent) in {"", "."}:
        return rel.name
    return parent.as_posix()


def _require_layout(skill_dir: Path) -> None:
    missing = [rel for rel in REQUIRED_FILES if not (skill_dir / rel).exists()]
    if missing:
        raise FileNotFoundError(f"{skill_dir} 缺少: {', '.join(missing)}")


def _load_text_tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return files


def _load_examples(examples_dir: Path) -> dict[str, Any]:
    if not examples_dir.is_dir():
        return {}
    examples: dict[str, Any] = {}
    for path in sorted(examples_dir.glob("*.json")):
        examples[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return examples


def _load_reference(skill_dir: Path) -> SkillReference:
    root = skill_dir / "reference"
    return SkillReference(
        examples=_load_examples(root / "examples"),
        enums=_load_text_tree(root / "enums"),
        specs=_load_text_tree(root / "specs"),
        prompts=_load_text_tree(root / "prompts"),
    )


def format_reference(reference: SkillReference) -> str:
    parts: list[str] = []
    if reference.examples:
        parts.append("## examples\n" + json.dumps(reference.examples, ensure_ascii=False, indent=2))
    for group, files in (
        ("enums", reference.enums),
        ("specs", reference.specs),
        ("prompts", reference.prompts),
    ):
        for name, text in files.items():
            parts.append(f"## {group}/{name}\n{text.strip()}")
    return "\n\n".join(parts)


def _frontmatter_record(skill_dir: Path, skills_root: Path) -> tuple[dict, str, Path]:
    _require_layout(skill_dir)
    skill_file = skill_dir / "SKILL.md"
    meta, body = parse_skill_md(skill_file.read_text(encoding="utf-8"))
    name = str(meta.get("name") or skill_dir.name).strip()
    if name != skill_dir.name:
        raise ValueError(f"skill name {name!r} must match directory {skill_dir.name!r}")
    description = str(meta.get("description") or "").strip()
    if not description:
        raise ValueError(f"{skill_file} is missing description")
    rel = skill_dir.resolve().relative_to(skills_root.resolve())
    script_path = skill_dir / "scripts" / "run.py"
    common = {
        "name": name,
        "description": description,
        "category": _category(rel),
        "rel_path": rel.as_posix(),
        "skill_dir": str(skill_dir.resolve()),
        "skill_file": str(skill_file.resolve()),
        "sort_order": int(meta.get("sort_order", meta.get("order", 100))),
        "depends_on": _as_str_list(meta.get("depends_on")),
        "disable_model_invocation": bool(
            meta.get("disable-model-invocation", meta.get("disable_model_invocation", False))
        ),
        "scripts": [str(script_path.resolve())],
        "script_path": str(script_path.resolve()),
        "tool_schema": normalize_tool(
            read_json(skill_dir / "tool_schema.json"),
            fallback_name=name,
            fallback_description=description,
        ),
        "input_schema_file": str((skill_dir / "input_schema.json").resolve()),
        "output_schema_file": str((skill_dir / "output_schema.json").resolve()),
        "pipeline": str(meta.get("pipeline") or "writing"),
    }
    return common, body, rel


def load_skill_meta(skill_dir: Path, *, skills_root: Path) -> SkillMeta:
    common, _, _ = _frontmatter_record(skill_dir, skills_root)
    return SkillMeta(**common)


def load_skill(skill_dir: Path, *, skills_root: Path) -> SkillRecord:
    common, body, _ = _frontmatter_record(skill_dir, skills_root)
    return SkillRecord(
        **common,
        body=body,
        input_schema=read_json(skill_dir / "input_schema.json"),
        output_schema=read_json(skill_dir / "output_schema.json"),
        reference=_load_reference(skill_dir),
    )


def discover_skills(skills_root: Path) -> list[SkillMeta]:
    if not skills_root.is_dir():
        raise FileNotFoundError(f"skills directory not found: {skills_root}")
    records = [
        load_skill_meta(skill_md.parent, skills_root=skills_root)
        for skill_md in sorted(skills_root.rglob("SKILL.md"))
    ]
    records.sort(key=lambda item: (item.sort_order, item.rel_path))
    return records


def load_skill_by_name(name: str, skills: list[SkillMeta], skills_root: Path) -> SkillRecord:
    for skill in skills:
        if skill.name == name:
            return load_skill(Path(skill.skill_dir), skills_root=skills_root)
    raise KeyError(name)
