import logging

from ..config import DASHSCOPE_API_KEY
from ..scene_loader import _load_scene_json, load_story
from .qwen_service import DEFAULT_MODEL

log = logging.getLogger(__name__)


class ChatServiceError(RuntimeError):
    """Chat 无法生成回复时抛出（API key 缺失 / 远端异常 / 返回格式错误）。
    路由层应转为 HTTP 502，前端弹 toast 告知用户，而不是伪造一个"正常"回复。"""


def _build_char_notes(global_chars: list[dict]) -> str:
    lines = []
    for c in global_chars:
        name = c.get("name", "")
        desc = c.get("appearance_description", "")
        lines.append(f"  - {name}：{desc}")
    return "\n".join(lines) or "  （无）"


def reply_to(scene_idx: int, user_text: str, story_id: str | None = None) -> str:
    if not user_text.strip():
        # 空输入就别调模型了
        return "我没听清呢，再说一遍好吗？"
    if not DASHSCOPE_API_KEY:
        raise ChatServiceError("DASHSCOPE_API_KEY 未配置；无法调用讲故事大模型。")

    import dashscope  # type: ignore

    try:
        story = load_story(story_id)
    except FileNotFoundError:
        raise
    except Exception as e:
        log.warning("[chat] load_story failed: %s", e)
        story = {}

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

    try:
        resp = dashscope.Generation.call(
            api_key=DASHSCOPE_API_KEY,
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            result_format="message",
        )
    except Exception as e:
        log.exception("[chat] dashscope call raised")
        raise ChatServiceError(f"讲故事大模型调用失败：{e}") from e

    if getattr(resp, "status_code", None) != 200:
        code = getattr(resp, "code", "unknown")
        msg = getattr(resp, "message", "unknown")
        log.warning("[chat] dashscope non-200 status=%s code=%s msg=%s model=%s",
                    getattr(resp, "status_code", None), code, msg, DEFAULT_MODEL)
        raise ChatServiceError(f"模型返回错误：status={resp.status_code} code={code} {msg}")

    choices = (resp.output or {}).get("choices") or []
    if not choices:
        log.warning("[chat] dashscope empty choices: %s", resp.output)
        raise ChatServiceError("模型返回为空，请稍后重试。")

    content = choices[0].get("message", {}).get("content", "").strip()
    if not content:
        raise ChatServiceError("模型返回为空字符串。")
    return content
