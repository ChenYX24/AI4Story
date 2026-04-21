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


def _compute_stats(interactions: list) -> dict[str, int]:
    total_ops = sum(len(it.ops) for it in interactions)
    total_custom = sum(len(it.custom_props) for it in interactions)
    scenes_changed = len(interactions)
    two_way_ops = sum(1 for it in interactions for op in it.ops if op.subject and op.target)
    single_ops = sum(1 for it in interactions for op in it.ops if op.subject and not op.target)
    freeform_ops = sum(1 for it in interactions for op in it.ops if not op.subject)
    return {
        "total_ops": total_ops,
        "total_custom": total_custom,
        "scenes_changed": scenes_changed,
        "two_way_ops": two_way_ops,
        "single_ops": single_ops,
        "freeform_ops": freeform_ops,
    }


def _clamp_pct(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            return 50
    return max(10, min(95, n))


def build_report(req: ReportRequest) -> dict[str, Any]:
    story = load_story(req.story_id)
    story_summary = story.get("story_summary", "")

    ops_summary = _format_ops(req.interactions)
    stats = _compute_stats(req.interactions)

    prompt = (
        "你要给一位 4-6 岁小朋友和他的家长写一份完整的互动故事报告。"
        "小朋友刚刚玩完一个《小红帽》互动故事书，在原著基础上通过选择道具和动作改写了情节。\n\n"
        f"【原著大纲】{story_summary}\n\n"
        f"【互动统计】操作总数 {stats['total_ops']}（双物 {stats['two_way_ops']} / 单物 {stats['single_ops']} / 自由描述 {stats['freeform_ops']}），"
        f"新创物品 {stats['total_custom']} 个，改写场景 {stats['scenes_changed']} 幕。\n\n"
        f"【小朋友的互动记录】{ops_summary}\n\n"
        "请严格输出以下 JSON，不要其它文字、不要代码块标记：\n"
        "{\n"
        '  "share": {\n'
        '    "summary": "1 句温暖的总结，像长辈夸奖孩子那样（30 字内）",\n'
        '    "honor_title": "基于孩子表现给一个可爱的 4-6 字荣誉称号，例如「温柔的小画家」「勇敢的故事工程师」",\n'
        '    "achievements": [\n'
        '      {"icon": "🎨", "text": "具体成就短语（10 字内，体现孩子做了什么）"}\n'
        '    ]\n'
        "  },\n"
        '  "kid_section": {\n'
        '    "title": "给你的故事报告",\n'
        '    "your_story": "用 3-4 句温暖口语化的话概括小朋友刚刚创造的故事",\n'
        '    "original_story": "用 3-4 句话告诉小朋友真正的《小红帽》里发生了什么",\n'
        '    "differences": ["3 条最有意思的不同点，每条 15 字以内"],\n'
        '    "questions": ["3 个适合 4-6 岁的启发性思考问题"]\n'
        "  },\n"
        '  "parent_section": {\n'
        '    "title": "给家长看的观察报告",\n'
        '    "traits": ["3-5 条性格/行为亮点，每条一句话"],\n'
        '    "weaknesses": ["2-3 条温和表述的薄弱项（用「可以加强...」「有时...」等温和措辞，避免负面标签）"],\n'
        '    "observations": ["2-3 条具体行为证据，引用孩子的具体操作"],\n'
        '    "suggestions": ["3-4 条面向家长的温和教育建议"],\n'
        '    "metrics": [\n'
        '      {"name": "维度名（2-4 个字）", "value": 0-100, "evidence": "必须引用孩子的具体操作作为证据：引用 op 或 custom_prop 的名字，说明为什么给这个分数（20-60 字）"}\n'
        "    ]\n"
        "  }\n"
        "}\n\n"
        "要求：\n"
        "- achievements 3-5 条，icon 用单个 emoji；文字要具体引用孩子的互动\n"
        "- kid_section 口语、温暖、像长辈讲故事\n"
        "- parent_section 客观、具体、基于证据；weaknesses 必须温和\n"
        "- metrics 由你根据孩子的实际表现自选 4-6 个最能体现的能力维度（例如想象力/同理心/解决问题/语言表达/冒险精神/合作倾向/专注力/好奇心/情绪调节等；不必每次都相同，选最相关的）\n"
        "- 每个 metric.evidence 必须直接引用记录里出现过的操作或新物品名字作为证据（用【】标出），不能只说泛泛的评价；若找不到证据，就不要选这个维度\n"
        "- value 为 10-95 整数，要与 evidence 里描述的强弱匹配（只有 1-2 条弱证据就不要给 85 以上）\n"
        "- 全程不出现危险/恐怖/暴力词；不给孩子贴负面标签\n"
        "- 如果孩子的互动极少，也要给鼓励性总结与合理建议"
    )

    try:
        result = call_json(prompt, temperature=0.5, timeout=60)
    except QwenError as e:
        raise RuntimeError(f"报告生成失败：{e}") from e

    share = result.get("share") or {}
    kid = result.get("kid_section") or {}
    parent = result.get("parent_section") or {}

    share.setdefault("summary", "这是一次属于你的故事冒险 ✨")
    share.setdefault("honor_title", "故事小主人")
    share.setdefault("achievements", [
        {"icon": "🎨", "text": f"改写了 {stats['scenes_changed']} 幕故事"},
        {"icon": "✨", "text": f"创造了 {stats['total_custom']} 个新物品"},
        {"icon": "💭", "text": f"安排了 {stats['total_ops']} 个精彩互动"},
    ])

    kid.setdefault("title", "给你的故事报告")
    kid.setdefault("your_story", "")
    kid.setdefault("original_story", story_summary)
    kid.setdefault("differences", [])
    kid.setdefault("questions", [])

    parent.setdefault("title", "给家长看的观察报告")
    parent.setdefault("traits", [])
    parent.setdefault("weaknesses", [])
    parent.setdefault("observations", [])
    parent.setdefault("suggestions", [])

    raw_metrics = parent.get("metrics") or []
    metrics: list[dict[str, Any]] = []
    for m in raw_metrics:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", "")).strip()
        # accept both "evidence" and legacy "description"
        evidence = str(m.get("evidence") or m.get("description") or "").strip()
        if not name or not evidence:
            # enforce: no metric without evidence
            continue
        metrics.append({
            "name": name,
            "value": _clamp_pct(m.get("value", 60)),
            "evidence": evidence,
        })
    # fallback when model returns nothing usable
    if not metrics:
        metrics = [
            {
                "name": "参与度",
                "value": 55,
                "evidence": f"孩子在 {stats['scenes_changed']} 幕里一共安排了 {stats['total_ops']} 个操作。",
            },
        ]
    parent["metrics"] = metrics[:8]

    return {"share": share, "kid_section": kid, "parent_section": parent}
