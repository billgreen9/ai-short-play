from __future__ import annotations

from app.skills.store import add_intent_msg, add_skill

SEED_SKILLS = [
    {
        "skill_name": "generate_concept",
        "description": "从用户一句话生成短剧故事核、类型、logline、钩子和集数规划。用户要做创意、选题、故事概念，或开始一部新短剧时使用。",
        "skill_prompt": (
            "你是短剧创意编辑。只产出故事概念，不写人物小传和剧本。"
            "结果包含 title、genre、logline、hook、episode_count、core_conflict。"
            "若可调用 save_result，把这些字段放进 result。"
        ),
        "function_tools": "save_result",
        "depends_on": None,
    },
    {
        "skill_name": "build_profiles",
        "description": "根据故事概念生成短剧人物小传、人物关系与每集可消费的人设冲突。用户要做人设、角色、人物小传或关系网时使用。",
        "skill_prompt": (
            "你是短剧人物导演。先用 get_artifact 读取 generate_concept。"
            "产出 3-5 个角色，含 name、role_type、want、wound、relationship。"
            "调用 save_result 保存。"
        ),
        "function_tools": "get_artifact,save_result",
        "depends_on": "generate_concept",
    },
    {
        "skill_name": "write_outline",
        "description": "把概念和人物展开成分集大纲、每集钩子与反转点。用户要写大纲、剧情结构、分集节拍时使用。",
        "skill_prompt": (
            "你是短剧结构编剧。读取上游概念和人物，输出 6-12 集大纲，"
            "每集含 episode、title、beat、hook、turn。调用 save_result 保存。"
        ),
        "function_tools": "get_artifact,save_result",
        "depends_on": "generate_concept,build_profiles",
    },
    {
        "skill_name": "write_script",
        "description": "按分集大纲写短剧台本，含场景、动作、台词、运镜和转场。用户要写剧本、台本、对白、分场、镜头时使用。",
        "skill_prompt": (
            "你是短剧台本作者。读取 write_outline，先写第 1-2 集完整台本，"
            "镜头含 scene、action、dialogue、camera、transition。调用 save_result 保存。"
        ),
        "function_tools": "get_artifact,save_result",
        "depends_on": "write_outline",
    },
    {
        "skill_name": "quality_check",
        "description": "检查短剧概念、人物、大纲和台本的钩子、人物动机、运镜与集间衔接问题。用户要审稿、质检、找问题、给修改建议时使用。",
        "skill_prompt": (
            "你是短剧审稿编辑。读取已有产物，输出 score、issues、suggestions。"
            "只找问题，不重写全文。调用 save_result 保存。"
        ),
        "function_tools": "get_artifact,save_result",
        "depends_on": "write_script",
    },
    {
        "skill_name": "create_short_play",
        "description": "从一句话创意完整创作一部短剧，包含概念、人物、大纲、剧本和质检。用户要写一部短剧、全流程创作、一键生成时使用。",
        "skill_prompt": (
            "你是短剧制片统筹。上游技能已经跑完时，用 get_artifact 汇总各产物，"
            "给出简短交付说明，并 save_result。"
        ),
        "function_tools": "get_artifact,save_result",
        "depends_on": "quality_check",
    },
]


SEED_UTTERANCES = {
    "generate_concept": ["写故事概念", "生成短剧创意", "做选题"],
    "build_profiles": ["只要人物小传", "写人物小传", "做人设"],
    "write_outline": ["写分集大纲", "写剧情结构"],
    "write_script": ["写剧本", "写台本", "写对白"],
    "quality_check": ["审稿", "质检一下"],
    "create_short_play": ["写一个短剧", "帮我写一部短剧", "全流程创作短剧", "一键生成短剧"],
}


def seed_default_skills() -> None:
    for item in SEED_SKILLS:
        skill = add_skill(**item)
        for msg in SEED_UTTERANCES.get(skill.skill_name, []):
            add_intent_msg(skill, msg)
