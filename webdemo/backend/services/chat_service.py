from ..config import DASHSCOPE_API_KEY
from ..scene_loader import load_story


def _fallback_reply(user_text: str) -> str:
    if not user_text.strip():
        return "我没听清呢，再说一遍好吗？"
    return f"你说：「{user_text}」，真棒！我们继续讲故事吧～"


def reply_to(scene_idx: int, user_text: str) -> str:
    if not DASHSCOPE_API_KEY:
        return _fallback_reply(user_text)
    try:
        import dashscope  # type: ignore

        story = load_story()
        system = (
            "你是一个亲切、耐心的绘本故事讲述者，面对的是 4-6 岁的小朋友。"
            "请使用简单、温暖、有画面感的中文，回答要短（1-2 句），不要跳出故事世界。"
            f"当前故事概要：{story.get('story_summary', '')}"
            f"当前场景序号：{scene_idx}。"
        )
        resp = dashscope.Generation.call(
            api_key=DASHSCOPE_API_KEY,
            model="qwen-turbo",
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
