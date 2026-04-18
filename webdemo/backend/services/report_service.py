import json
from typing import Any

from ..models import ReportRequest
from ..scene_loader import load_story
from .qwen_service import QwenError, call_json


def _format_ops(interactions: list) -> str:
    lines = []
    for it in interactions:
        lines.append(f"\n场景 {it.scene_idx}（目标：{it.interaction_goal or '无'}）:")
        if it.custom_props:
            names = "、".join(p.name for p in it.custom_props)
            lines.append(f"  小朋友创造的新物品：{names}")
        for i, op in enumerate(it.ops, 1):
            if op.subject and op.target:
                lines.append(f"  {i}. 让「{op.subject}」对「{op.target}」：{op.action}")
            elif op.subject:
                lines.append(f"  {i}. 让「{op.subject}」：{op.action}")
            else:
                lines.append(f"  {i}. 场景事件：{op.action}")
        if it.dynamic_summary:
            lines.append(f"  生成的新段落：{it.dynamic_summary}")
    return "\n".join(lines) or "（没有记录到具体互动）"


def build_report(req: ReportRequest) -> dict[str, Any]:
    story = load_story()
    story_summary = story.get("story_summary", "")

    ops_summary = _format_ops(req.interactions)

    prompt = (
        "你同时要给一个 4-6 岁小朋友和他的家长写一份故事报告。"
        "小朋友刚刚玩完一个互动故事书，在原著《小红帽》的基础上，通过选择不同的道具和动作改写了情节。\n\n"
        f"【原著大纲】{story_summary}\n\n"
        f"【小朋友的互动记录】{ops_summary}\n\n"
        "请严格输出以下 JSON，不要其它文字、不要代码块标记：\n"
        "{\n"
        '  "kid_section": {\n'
        '    "title": "给你的故事报告",\n'
        '    "your_story": "用 3-4 句温暖口语化的话，概括小朋友刚刚创造的故事（重点体现他的选择和新物品）",\n'
        '    "original_story": "用 3-4 句简洁的话，告诉小朋友真正的《小红帽》里发生了什么",\n'
        '    "differences": ["小朋友的故事 vs 原著的 3 个最有意思的不同点，每条 15 字以内"],\n'
        '    "questions": ["3 个适合 4-6 岁的启发性思考问题，让他思考善良、勇敢、陌生人、帮助他人等价值"]\n'
        "  },\n"
        '  "parent_section": {\n'
        '    "title": "给家长看的观察报告",\n'
        '    "traits": ["3-5 条从孩子的互动中观察到的性格/行为倾向，每条一句话（比如：富有同情心、喜欢解决冲突用对话而非暴力、想象力活跃）"],\n'
        '    "observations": ["2-3 条具体的行为证据，引用孩子的具体操作（比如：他选择让小红帽跟大灰狼做朋友，说明...）"],\n'
        '    "suggestions": ["3 条面向家长的温和教育建议，基于上面的观察（比如：可以和他一起读《陌生人与朋友》的绘本扩展安全意识...）"]\n'
        "  }\n"
        "}\n\n"
        "要求：\n"
        "- kid_section 要口语、温暖、像长辈讲故事\n"
        "- parent_section 要客观、具体、基于证据\n"
        "- 不要用危险、恐怖、暴力词；避免给孩子下定义或贴负面标签\n"
        "- 如果孩子的互动极少或空，也要尽量给出善意的总结与鼓励性建议"
    )

    try:
        result = call_json(prompt, temperature=0.5, timeout=60)
    except QwenError as e:
        raise RuntimeError(f"报告生成失败：{e}") from e

    kid = result.get("kid_section") or {}
    parent = result.get("parent_section") or {}
    # defensive defaults
    kid.setdefault("title", "给你的故事报告")
    kid.setdefault("your_story", "")
    kid.setdefault("original_story", story_summary)
    kid.setdefault("differences", [])
    kid.setdefault("questions", [])
    parent.setdefault("title", "给家长看的观察报告")
    parent.setdefault("traits", [])
    parent.setdefault("observations", [])
    parent.setdefault("suggestions", [])
    return {"kid_section": kid, "parent_section": parent}
