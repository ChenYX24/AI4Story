from ..config import DASHSCOPE_API_KEY
from ..scene_loader import _load_scene_json, load_story


def _fallback_reply(user_text: str) -> str:
    if not user_text.strip():
        return "我没听清呢，再说一遍好吗？"
    return f"你说：「{user_text}」，真有趣！我们继续讲故事吧～"


def _build_char_notes(global_chars: list[dict]) -> str:
    lines = []
    for c in global_chars:
        name = c.get("name", "")
        desc = c.get("appearance_description", "")
        lines.append(f"  - {name}：{desc}")
    return "\n".join(lines) or "  （无）"


def reply_to(scene_idx: int, user_text: str, story_id: str | None = None) -> str:
    if not DASHSCOPE_API_KEY:
        return _fallback_reply(user_text)
    try:
        import dashscope  # type: ignore

        story = load_story(story_id)
        global_chars = story.get("global_content", {}).get("characters", [])
        char_notes = _build_char_notes(global_chars)

        scene_context = ""
        scene_chars_str = ""
        try:
            scene = _load_scene_json(scene_idx, story_id)
            scene_context = (scene.get("narration") or scene.get("event_summary") or "").strip()
            scene_chars = [c["name"] for c in scene.get("characters", [])]
            scene_chars_str = "、".join(scene_chars) or "（无）"
        except Exception:
            pass

        system = (
            "你是一个互动绘本故事中的旁白兼角色扮演者，面对的是 4-6 岁的小朋友。\n"
            "请使用简单、温暖、有画面感的中文，回答要短（1-2 句），不要跳出故事世界。\n\n"
            f"【当前故事】{story.get('story_summary', '')}\n"
            f"【当前场景】{scene_context}\n"
            f"【当前场景角色】{scene_chars_str}\n\n"
            "【故事角色性格（必须严格遵守）】\n"
            f"{char_notes}\n\n"
            "⚠️ 重要规则：\n"
            "- 每个角色都有自己的立场和动机，绝对不能违背角色设定\n"
            "- 反派角色（如大灰狼）永远不会好心帮助或保护主角，会用阴谋手段应对\n"
            "- 不要一味顺着小朋友的话，角色需要根据自己的性格和动机来回应\n"
            "- 如果小朋友的说法与故事逻辑矛盾，用角色视角温和地引导\n"
            "- 以当前场景在场角色的口吻或旁白回答，保持故事沉浸感\n"
            "- 回答简短有趣，适合 5 岁儿童理解，不超过 2 句"
        )

        resp = dashscope.Generation.call(
            api_key=DASHSCOPE_API_KEY,
            model="qwen3.6-plus",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            result_format="message",
        )
        if resp.status_code == 200:
            choices = resp.output.get("choices") or []
            if choices:
                return choices[0]["message"]["content"].strip()
        return _fallback_reply(user_text)
    except Exception:
        return _fallback_reply(user_text)
