import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.6-plus"
NARRATIVE_SCENE = "叙事场景"
INTERACTIVE_SCENE = "交互场景"


def load_story_text(text: str | None, input_file: str | None) -> str:
    if text:
        return text.strip()
    if input_file:
        return Path(input_file).resolve().read_text(encoding="utf-8").strip()
    raise ValueError("Please provide --text or --input-file.")


def build_messages(story_text: str, target_total_scenes: int | None, max_narrative_scenes: int | None) -> list[dict[str, Any]]:
    schema_hint = {
        "story_summary": "一句话概括完整故事",
        "global_content": {
            "characters": [
                {
                    "name": "角色名",
                    "appearance_description": "跨多个场景保持一致的整体外观描述",
                }
            ],
            "objects": [
                {
                    "name": "核心可复用物体名",
                    "appearance_description": "跨多个场景保持一致的整体外观描述",
                }
            ],
        },
        "scenes": [
            {
                "scene_index": 1,
                "scene_type": NARRATIVE_SCENE,
                "event_summary": "只描述这个场景的开头状态与结果状态",
                "narration": "用于推进故事的简短旁白",
                "dialogue": [
                    {
                        "speaker": "说话角色名",
                        "content": "简短台词内容",
                        "tone": "语气，例如温柔、焦急、严肃、试探",
                    }
                ],
                "characters": [
                    {
                        "name": "角色名",
                        "pose": "只描述人物自己的动作、姿态、表情,描述中严禁出现别的人物",
                        "related_objects": [
                            {
                                "name": "与人物构成整体参考图的物体名",
                                "relationship": "为什么人物与这个物体需要一起生成",
                            }
                        ],
                    }
                ],
                "objects": [
                    {
                        "name": "物体名",
                        "appearance_description": "只描述这个物体本身，不提其他人物和其他物体",
                    }
                ],
                "background_visual_description": "除去前面列出的人物与物体后，背景环境的视觉描述",
            }
        ],
    }

    prompt = f"""
你是一个儿童故事分场景规划助手。请把输入的故事文本拆成适合后续图像生成的 JSON。

必须遵守以下规则：
1. 只输出 JSON 本体，不要输出 markdown，不要输出解释。
2. 输出语言必须是中文。
3. 顶层必须包含 `story_summary`、`global_content`、`scenes`。
4. `global_content.characters` 和 `global_content.objects` 只放会在多个场景重复出现、需要提前统一生成参考图的人物和物体。
5. `characters` 中只列出人物，以及人物自己的动作姿态和表情。
6. 【极度重要】`pose` 必须是“绿幕单人棚拍 / 动作捕捉参考照”视角的去场景化描述。请把人物想象成站在纯白背景下单独拍定妆照，只描述这个人物自己的身体姿态、手势、朝向、表情、视线状态。
7. `pose` 严禁提及任何环境参照物和其他人物。不要写床、门、窗、桌椅、树木、道路、房间，也不要写“看着某人”“站在某人身后”“抓住某人”等关系性描述。
8. 视线与朝向必须使用绝对方向或中性描述，例如“看向右下方”“平视前方”“侧身站立”“低头”。绝不能写“看着外婆”“面向猎人”“躲在树后”。
9. `pose` 正误示例：
   - 错误：`站在小红帽侧后方，身体微微前倾，眼睛盯着小红帽`
   - 正确：`侧向站立，身体微微前倾，嘴角上扬露出狡猾的笑容，视线看向侧前方`
   - 错误：`站在床边，眼神充满疑惑地看着床上的人`
   - 正确：`双腿并拢站立，身体微微前倾，眉头微皱，眼神充满疑惑地看向斜下方`
   - 错误：`躲在树后，紧紧抓住猎人的手臂`
   - 正确：`身体蜷缩，双手做出紧紧抓握的动作，神情紧张`
10. `objects` 中只列出物体自身外观。不能把人物、动作关系、其他物体写进 `appearance_description`。
11. 如果人物与物体构成整体参考图，例如“躺在床上”“抱着篮子”“坐在椅子上”，就在该人物的 `related_objects` 中引用该物体。
12. 如果只是普通位置关系，例如“站在窗边”“走在路上”，不要使用 `related_objects`。
13. `{INTERACTIVE_SCENE}` 不再只写一个笼统摘要，而是必须额外包含三个字段：`initial_frame`、`interaction_goal`、`event_outcome`。
14. `initial_frame` 只描述交互发生前的起始画面，是用户开始介入前看到的画面。
15. `interaction_goal` 只描述该场景中某一方想达成什么，不描述具体实现过程；这段过程应该留给用户自定义。
16. `event_outcome` 只描述无论中间如何交互，这个场景最终会落到什么结果。
17. `{INTERACTIVE_SCENE}` 的 `event_summary` 需要是对 `initial_frame + interaction_goal + event_outcome` 的简短汇总。
18. `characters[].pose` 必须按照 `initial_frame` 来写，只能反映交互开始前的初始姿态，不能提前写进过程或结局信息。
19. 每个场景都必须包含 `narration` 和 `dialogue`。
20. 只有 `{NARRATIVE_SCENE}` 需要生成 `dialogue`。`dialogue` 是简短台词数组，每条都要包含 `speaker`、`content`、`tone`，用于辅助后续叙事连环画推进。
21. `{INTERACTIVE_SCENE}` 的 `dialogue` 必须为空数组，不需要生成台词内容。
22. 叙事场景的台词必须简短、适合儿童故事连环画，一般 0 到 2 句即可；如果该叙事场景没有自然台词，也要保留空数组。
23. `{NARRATIVE_SCENE}` 继续使用 `event_summary`，只描述该场景的开头状态和结果状态。
24. 第一个场景必须是 `{NARRATIVE_SCENE}`。
25. 最后一个场景必须是 `{NARRATIVE_SCENE}`。
26. 每个 `{INTERACTIVE_SCENE}` 后面都必须紧跟一个 `{NARRATIVE_SCENE}`，用于表现该交互之后产生的结果画面。
27. `{INTERACTIVE_SCENE}` 应聚焦故事真正的核心冲突、决策、对抗、博弈、关键转折。
28. 低张力的尾声、拥抱、恢复平静、承诺、总结教训，如果只是故事收束，不要扩写成新的核心场景，应压缩到最后一个叙事场景的结果里。
29. 你需要根据故事节奏自适应决定拆分几个场景，以“少而精、结构完整”为原则，优先保留真正推动故事的关键场景。
30. 像“小红帽和外婆在安全环境中拥抱，并承诺以后不再轻信陌生人”这种内容，通常应直接作为故事最终结尾，不应被拆成新的核心互动场景。

物体选择规则：
29. 每个 `{INTERACTIVE_SCENE}` 的 `objects` 必须恰好有 9 个。
30. 这些物体必须是逻辑上可能出现在当前场景的背景中，并且必须是具体、可操作、可被人物使用的物体。
31. 必须参考 scene 的 `background_visual_description` 来决定这些物体是否合理出现，确保物体多样化。
32. 严禁把人物服饰、人物配件、人物身体特征当作物体，例如斗篷、睡帽、裙子、围裙、鞋子、眼镜、耳朵、尾巴、牙齿、爪子。
33. 严禁把整片环境或整个场景当作物体，例如森林小路、卧室、厨房、房间、树林、草地、村庄、天空、阳光，这类用户无法拿起不能做为物体。
34. 在 `{INTERACTIVE_SCENE}` 中，凡是已经通过 `characters[].related_objects` 与人物形成整体参考图的物体，不能再出现在该场景的 `objects` 里。
35. 在 `{INTERACTIVE_SCENE}` 中，`objects` 必须只包含与人物解绑的独立交互道具，并且总数仍然保持 9 个。
36. 在 `{NARRATIVE_SCENE}` 中，`objects` 只保留那些确实需要跨场景保持一致性的物体，不需要满足 9 个。
37. 如果一个元素更适合作为背景的一部分，就写进 `background_visual_description`，不要写进 `objects`。
38. 叙事场景中不在全局资产里的临时环境物体，优先并入 `background_visual_description`，避免滥列无价值道具。

数量偏好：
39. 不要为了凑数量而拆分场景，也不要为了压缩数量而合并关键冲突。
40. 如果故事较短，可以只拆成较少的场景；如果故事包含多个关键冲突，也可以自然增加场景数量。
41. 只要满足“首尾为叙事场景、每个交互场景后面紧跟叙事场景”的结构即可。

推荐场景骨架：
{NARRATIVE_SCENE} -> {INTERACTIVE_SCENE} -> {NARRATIVE_SCENE} -> {INTERACTIVE_SCENE} -> {NARRATIVE_SCENE} ...

小红帽的参考拆分方式：
- 叙事：妈妈交代小红帽去外婆家，小红帽在路上遇到大灰狼。
- 交互：大灰狼与小红帽对话，诱导她去采花，支开她。
- 叙事：大灰狼抄近路到外婆家，吃掉外婆并伪装成外婆。
- 交互：小红帽到外婆家后对“外婆”产生怀疑并质问。
- 叙事：大灰狼露出真面目并吃掉小红帽。
- 交互：猎人进入屋内并设法解救小红帽与外婆。
- 叙事：故事结束，危险解除，角色回到安全状态。

JSON 结构参考：
{json.dumps(schema_hint, ensure_ascii=False, indent=2)}

交互场景示例理解：
- 小红帽：
  initial_frame：大灰狼与小红帽在路上相遇。
  interaction_goal：大灰狼想办法诱骗小红帽离开大路。
  event_outcome：大灰狼趁机抄近路顺利跑向外婆家。
- 孙悟空三借芭蕉扇：
  initial_frame：孙悟空准备再次与铁扇公主周旋。
  interaction_goal：孙悟空想办法逼迫铁扇公主交出扇子。
  event_outcome：铁扇公主被迫交出假扇，随后孙悟空骗得真扇却又被夺回。

故事文本：
{story_text}
""".strip()
    return [{"role": "user", "content": prompt}]


def normalize_response_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "text" and isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return str(content).strip()


def parse_json_from_response(content: Any) -> dict[str, Any]:
    content_text = normalize_response_content(content)
    try:
        return json.loads(content_text)
    except json.JSONDecodeError:
        if "```json" in content_text:
            fenced = content_text.split("```json", 1)[1].split("```", 1)[0].strip()
            return json.loads(fenced)
        if "```" in content_text:
            fenced = content_text.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(fenced)
        start = content_text.find("{")
        end = content_text.rfind("}")
        if start != -1 and end != -1 and start < end:
            return json.loads(content_text[start : end + 1])
        raise


def build_repair_messages(bad_json_text: str, error_message: str | None = None) -> list[dict[str, Any]]:
    error_hint = f"\n当前检测到的问题：{error_message}\n" if error_message else "\n"
    prompt = f"""
下面是一段格式不合法或结构不符合要求的 JSON。请在不改变原有故事语义的前提下，把它修复成严格合法且满足规则的 JSON。

修复规则：
1. 只输出 JSON 本体。
2. 不要输出 markdown。
3. 不要输出解释。
4. 顶层必须保留 `global_content` 和 `scenes`。
5. 第一个场景必须是 `{NARRATIVE_SCENE}`。
6. 最后一个场景必须是 `{NARRATIVE_SCENE}`。
7. 每个 `{INTERACTIVE_SCENE}` 后面都必须紧跟一个 `{NARRATIVE_SCENE}`。
8. 每个 `{INTERACTIVE_SCENE}` 的 `objects` 必须恰好有 9 个。
9. `{INTERACTIVE_SCENE}` 必须包含 `initial_frame`、`interaction_goal`、`event_outcome` 三个字段。
10. `initial_frame` 只描述交互开始前的起始画面。
11. `interaction_goal` 只描述该场景里某一方想达成什么，不描述具体实现过程。
12. `event_outcome` 只描述这个交互场景最后落到的结果。
13. `event_summary` 对于 `{INTERACTIVE_SCENE}` 应该是对 `initial_frame + interaction_goal + event_outcome` 的简要汇总；对于 `{NARRATIVE_SCENE}` 则仍然是开头状态和结果状态。
14. 尾声、拥抱、恢复平静、总结教训，如果只是低张力结尾，应并入最后一个叙事场景，不要扩展成新的核心场景。
15. `characters[].pose` 必须使用“绿幕单人棚拍 / 动作捕捉参考照”视角来重写，只保留单人、去场景化的姿态描述。
16. `characters[].pose` 只能写该人物在 `initial_frame` 中的初始动作姿态、表情、朝向，不能提到其他人物，也不能提到床、门、窗、树、桌椅、道路等环境参照物。
17. `objects[].appearance_description` 只能写物体自身，不能出现人物和其他物体。
18. 在 `{INTERACTIVE_SCENE}` 中，`characters[].related_objects` 不能引用同场景 `objects` 中的物体；这些与人物绑定的物体应来自 `global_content.objects`，或者直接删除该引用。
19. 在 `{INTERACTIVE_SCENE}` 中，`objects` 只保留与人物解绑的独立交互道具，总数必须仍然保持 9 个。
20. 在 `{NARRATIVE_SCENE}` 中，`objects` 只保留需要保证一致性的物体，不需要满足 9 个。
21. 每个场景都必须包含 `narration` 和 `dialogue`。
22. 只有 `{NARRATIVE_SCENE}` 需要保留非空或可选的简短 `dialogue`；`{INTERACTIVE_SCENE}` 的 `dialogue` 必须修正为空数组。
23. `dialogue` 里的台词必须简短、适合连环画，不要过长；没有自然台词时可以返回空数组。

{error_hint}
待修复内容：
{bad_json_text}

Additional hard rules for every interactive scene:
1. `initial_frame` must describe only the visual starting state of the scene.
2. `initial_frame` must not describe a concrete action process, strategy, or multi-step behavior.
3. `interaction_goal` must be written from one character's perspective as a goal or task.
4. `interaction_goal` must not include implementation details, tactics, persuasion steps, or specific means.
5. `event_outcome` must describe only the result state after the interaction.
6. `event_outcome` must not describe the detailed execution process or how the goal was achieved.
7. Remove process wording from `event_summary` as much as possible. Keep only the opening situation and the resulting state.
8. `characters[].pose` must match the starting visual frame only, and must not include other characters, props, environment anchors, or process actions.
9. Treat every `pose` like a single-character studio reference shot on a pure white backdrop.
10. Pose examples:
   - Bad: `站在小红帽侧后方，眼睛盯着小红帽`
   - Good: `侧向站立，身体微微前倾，视线看向侧前方`
   - Bad: `站在床边看着床上的人`
   - Good: `双腿并拢站立，身体微微前倾，眉头微皱，视线看向斜下方`
11. Every scene must include concise `narration` and a `dialogue` array with short comic-style lines.
    """.strip()
    return [{"role": "user", "content": prompt}]


def build_semantic_cleanup_messages(draft_payload: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = f"""
下面是一份已经基本成型的故事场景 JSON。请你在不改变核心剧情的前提下，对它做一次“JSON 语义整理”，并输出整理后的合法 JSON。

整理目标：
1. 统一同一人物、同一物体在全局和各场景中的命名，让同一个实体始终使用同一个名称。
2. 人物的 `pose` 必须改写成“绿幕单人棚拍 / 动作捕捉参考照”视角的去场景化描述，只描述这个人物自己的姿态、动作、朝向、表情、视线状态。
3. 人物的 `pose` 不能提到任何其他人物，也不要提到任何物体或环境锚点；如果人物和物体需要绑定参考图，请放到 `related_objects`。
4. `{INTERACTIVE_SCENE}` 必须包含 `initial_frame`、`interaction_goal`、`event_outcome` 三个字段。
5. `initial_frame` 应是用户开始介入前看到的起始画面；人物 `pose` 必须与这个起始画面一致。
6. `interaction_goal` 只能表达场景中某一方想达成什么，不要写死具体执行步骤，因为这些过程需要留给用户自定义。
7. `event_outcome` 只描述该交互场景最终会收束到的结果。
8. `{INTERACTIVE_SCENE}` 中，`objects` 必须保留 9 个独立交互道具；任何已经与人物绑定到 `related_objects` 的物体，都不能再出现在该场景的 `objects` 中。
9. `{NARRATIVE_SCENE}` 中，`objects` 只保留那些确实需要跨场景保持一致性的物体，而且这些物体必须来自 `global_content.objects`。
10. `{NARRATIVE_SCENE}` 里其他不需要单独保持一致的环境内容，都应该并入 `background_visual_description`，不要继续放在 `objects` 中。
11. 保持原有场景顺序、场景类型和整体故事走向不变。
12. 每个场景都要补充 `narration` 和 `dialogue`，用于后续连环画叙事。
13. `narration` 是一条简短旁白，概括该场景正在发生什么。
14. `dialogue` 是简短台词数组，每条台词都包含 `speaker`、`content`、`tone`。没有自然台词时可以返回空数组。
15. 只输出 JSON，不要输出解释，不要输出 markdown。

待整理 JSON：
{json.dumps(draft_payload, ensure_ascii=False, indent=2)}

Focus especially on interactive scenes and rewrite them with these hard rules:
1. Rewrite `initial_frame` into a purely visual opening frame. It should describe what is visible at the start, not what someone is doing through a process.
2. Rewrite `interaction_goal` into a single character-centered goal. It should answer "what does this character want to achieve in this scene" and must not include any method, tactic, or implementation path.
3. Rewrite `event_outcome` into the end state only. It should describe what changed or what result happened, without explaining the process.
4. Remove procedural wording from `event_summary`. Keep it concise and centered on the scene opening plus the resulting state.
5. Ensure `characters[].pose` reflects only the initial visual frame. It must not mention any other character, any prop, or any environment anchor, and should avoid describing a method or multi-step action.
6. For narrative scenes, keep `objects` limited to global-consistency objects only. Move all other environmental details into `background_visual_description`.
7. Think of every `pose` as a studio character reference image on a plain white backdrop, not as a scene description.
8. Pose examples:
   - Bad: `站在小红帽侧后方，身体微微前倾，眼睛盯着小红帽`
   - Good: `侧向站立，身体微微前倾，嘴角上扬露出狡猾的笑容，视线看向侧前方`
   - Bad: `站在床边，眼神充满疑惑地看着床上的人`
   - Good: `双腿并拢站立，身体微微前倾，眉头微皱，眼神看向斜下方`
9. Add concise `narration` for every scene, but only keep `dialogue` content for narrative scenes.
10. `dialogue` lines must remain short and story-forwarding, with explicit speaker and tone. Interactive scenes must use an empty dialogue array.

Examples:
- Bad interaction_goal: "大灰狼想办法诱骗小红帽离开大路去采更多的花，从而拖延她的时间。"
- Good interaction_goal: "大灰狼想办法拖延小红帽的时间。"
- Bad event_outcome: "小红帽被花朵吸引留在原地采花唱歌，大灰狼趁机转身飞快地跑向外婆家。"
- Good event_outcome: "小红帽被吸引，大灰狼趁机跑向外婆家。"
    """.strip()
    return [{"role": "user", "content": prompt}]


def build_pose_audit_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = f"""
下面是一份已经通过基础结构校验的故事场景 JSON。请你作为“语义质检器”，检查其中的人物 `pose` 是否仍然存在不适合生成单人参考图的问题。

审查标准：
1. `pose` 必须是“绿幕单人棚拍 / 动作捕捉参考照”视角。
2. `pose` 只能描述该人物自己的身体姿态、手势、朝向、表情、视线状态。
3. `pose` 不能提到其他人物。
4. `pose` 不能提到任何物体或环境锚点，例如床、门、窗、桌椅、树木、道路、房间等。
5. `pose` 不能写成关系性描述，例如“看着某人”“站在某人身后”“抓住某人”“躲在树后”。
6. `pose` 必须与 `initial_frame` 一致，但只能保留其中适合单人参考图的部分。
7. 你必须基于语义理解做判断，不要做机械词面替换。

输出格式必须是严格 JSON，格式如下：
{{
  "valid": true,
  "issues": [],
  "fixed_payload": {{...整理后的完整 payload...}}
}}

如果发现任何 pose 不合格：
- `valid` 必须为 false
- `issues` 中逐条给出问题
- `fixed_payload` 必须返回你修正后的完整 payload

如果全部合格：
- `valid` 为 true
- `issues` 为空数组
- `fixed_payload` 仍然返回完整 payload，便于后续继续使用

正误示例：
- 错误：`站在小红帽侧后方，身体微微前倾，眼睛盯着小红帽`
- 正确：`侧向站立，身体微微前倾，嘴角上扬露出狡猾的笑容，视线看向侧前方`
- 错误：`站在床边，眼神充满疑惑地看着床上的人`
- 正确：`双腿并拢站立，身体微微前倾，眉头微皱，眼神看向斜下方`

待审查 JSON：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()
    return [{"role": "user", "content": prompt}]


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


def normalize_text_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def sentenceize(text: str) -> str:
    normalized = normalize_text_value(text).rstrip("。！？!?;；，, ")
    if not normalized:
        return ""
    return f"{normalized}。"


def compose_interactive_event_summary(scene: dict[str, Any]) -> str:
    initial_frame = normalize_text_value(scene.get("initial_frame"))
    event_outcome = normalize_text_value(scene.get("event_outcome"))
    interaction_goal = normalize_text_value(scene.get("interaction_goal"))

    if initial_frame and event_outcome:
        start = initial_frame.rstrip("。！？!?;；，, ")
        end = event_outcome.rstrip("。！？!?;；，, ")
        if start == end:
            return sentenceize(start)
        return sentenceize(f"{start}，{end}")
    if event_outcome:
        return sentenceize(event_outcome)
    if initial_frame:
        return sentenceize(initial_frame)
    if interaction_goal:
        return sentenceize(interaction_goal)
    return ""


def is_narrative_scene(scene_type: Any) -> bool:
    return scene_type == NARRATIVE_SCENE


def is_interactive_scene(scene_type: Any) -> bool:
    return scene_type == INTERACTIVE_SCENE


def validate_object_entry(obj: dict[str, Any], scene_index: int, object_names: set[str] | None = None) -> str:
    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Scene {scene_index} has an object with invalid or empty name.")

    description = obj.get("appearance_description", "")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"Scene {scene_index} object '{name}' must have a non-empty appearance_description.")

    normalized = normalize_name(name)
    if object_names is not None:
        object_names.add(normalized)
    return normalized


def sanitize_related_objects(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        payload.pop("_semantic_audit_issues", None)

    global_content = payload.get("global_content", {})
    scenes = payload.get("scenes", [])
    if not isinstance(global_content, dict) or not isinstance(scenes, list):
        return payload

    global_object_names: set[str] = set()
    for obj in global_content.get("objects", []):
        if isinstance(obj, dict):
            name = obj.get("name")
            description = obj.get("appearance_description", "")
            if isinstance(name, str) and name.strip() and isinstance(description, str):
                global_object_names.add(normalize_name(name))

    for scene in scenes:
        if not isinstance(scene, dict):
            continue

        scene["event_summary"] = normalize_text_value(scene.get("event_summary"))
        if is_interactive_scene(scene.get("scene_type")) and not scene["event_summary"]:
            scene["event_summary"] = compose_interactive_event_summary(scene)
        scene["narration"] = normalize_text_value(scene.get("narration")) or scene["event_summary"]
        if not isinstance(scene.get("dialogue"), list):
            scene["dialogue"] = []
        if is_interactive_scene(scene.get("scene_type")):
            scene["dialogue"] = []

        scene_object_names: set[str] = set()
        objects = scene.get("objects", [])
        if is_narrative_scene(scene.get("scene_type")) and isinstance(objects, list):
            kept_objects: list[dict[str, Any]] = []
            background_additions: list[str] = []
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                name = obj.get("name")
                description = obj.get("appearance_description", "")
                if not isinstance(name, str) or not name.strip() or not isinstance(description, str):
                    continue
                normalized = normalize_name(name)
                if normalized in global_object_names:
                    kept_objects.append(obj)
                elif description.strip():
                    background_additions.append(description.strip())

            if background_additions:
                background_description = scene.get("background_visual_description", "")
                if not isinstance(background_description, str):
                    background_description = ""
                merged_parts = [background_description.strip()] if background_description.strip() else []
                for addition in background_additions:
                    if addition not in merged_parts:
                        merged_parts.append(addition)
                scene["background_visual_description"] = " ".join(merged_parts).strip()
            scene["objects"] = kept_objects
            objects = kept_objects

        if isinstance(objects, list):
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                name = obj.get("name")
                description = obj.get("appearance_description", "")
                if isinstance(name, str) and name.strip() and isinstance(description, str):
                    scene_object_names.add(normalize_name(name))

        for char in scene.get("characters", []):
            if not isinstance(char, dict):
                continue
            related_objects = char.get("related_objects")
            if not isinstance(related_objects, list):
                continue

            filtered: list[dict[str, Any]] = []
            for rel in related_objects:
                if not isinstance(rel, dict):
                    continue
                rel_name = rel.get("name")
                if not isinstance(rel_name, str) or not rel_name.strip():
                    continue
                normalized = normalize_name(rel_name)
                if is_interactive_scene(scene.get("scene_type")):
                    if normalized in global_object_names and normalized not in scene_object_names:
                        filtered.append(rel)
                elif normalized in scene_object_names or normalized in global_object_names:
                    filtered.append(rel)
            char["related_objects"] = filtered

    return payload


def validate_scene_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Top-level result must be a JSON object.")

    global_content = payload.get("global_content")
    scenes = payload.get("scenes")
    if not isinstance(global_content, dict):
        raise ValueError("Missing or invalid global_content object.")
    if not isinstance(global_content.get("characters"), list):
        raise ValueError("global_content.characters must be an array.")
    if not isinstance(global_content.get("objects"), list):
        raise ValueError("global_content.objects must be an array.")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("scenes must be a non-empty array.")
    if len(scenes) < 3:
        raise ValueError("scenes must contain at least 3 scenes so the story can start and end with narrative scenes.")
    if not is_narrative_scene(scenes[0].get("scene_type")):
        raise ValueError("The first scene must be a narrative scene.")
    if not is_narrative_scene(scenes[-1].get("scene_type")):
        raise ValueError("The last scene must be a narrative scene.")

    global_object_names: set[str] = set()
    for obj in global_content.get("objects", []):
        if isinstance(obj, dict):
            validate_object_entry(obj, scene_index=0, object_names=global_object_names)

    banned_phrases = [
        "用户可选择",
        "用户可以选择",
        "可选择最终结局",
        "补充细节",
        "用户可决定",
        "可互动",
        "用户可以",
        "由用户决定",
    ]
    banned_phrases = []
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} must be an object.")

        scene_type = scene.get("scene_type")
        if scene_type not in {NARRATIVE_SCENE, INTERACTIVE_SCENE}:
            raise ValueError(f"Scene {index} has invalid scene_type: {scene_type}")

        event_summary = scene.get("event_summary")
        if not isinstance(event_summary, str) or not event_summary.strip():
            raise ValueError(f"Scene {index} event_summary must be a non-empty string.")
        if any(phrase in event_summary for phrase in banned_phrases):
            raise ValueError(f"Scene {index} event_summary contains interactive meta wording.")

        narration = scene.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise ValueError(f"Scene {index} narration must be a non-empty string.")
        dialogue = scene.get("dialogue")
        if not isinstance(dialogue, list):
            raise ValueError(f"Scene {index} dialogue must be an array.")
        if is_interactive_scene(scene_type) and dialogue:
            raise ValueError(f"Scene {index} is {INTERACTIVE_SCENE} and dialogue must be an empty array.")
        for line in dialogue:
            if not isinstance(line, dict):
                raise ValueError(f"Scene {index} contains an invalid dialogue item.")
            speaker = line.get("speaker")
            content = line.get("content")
            tone = line.get("tone")
            if not isinstance(speaker, str) or not speaker.strip():
                raise ValueError(f"Scene {index} dialogue speaker must be a non-empty string.")
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"Scene {index} dialogue content must be a non-empty string.")
            if not isinstance(tone, str) or not tone.strip():
                raise ValueError(f"Scene {index} dialogue tone must be a non-empty string.")

        if is_interactive_scene(scene_type):
            initial_frame = scene.get("initial_frame")
            interaction_goal = scene.get("interaction_goal")
            event_outcome = scene.get("event_outcome")
            if not isinstance(initial_frame, str) or not initial_frame.strip():
                raise ValueError(f"Scene {index} is {INTERACTIVE_SCENE} and must contain a non-empty initial_frame.")
            if not isinstance(interaction_goal, str) or not interaction_goal.strip():
                raise ValueError(f"Scene {index} is {INTERACTIVE_SCENE} and must contain a non-empty interaction_goal.")
            if not isinstance(event_outcome, str) or not event_outcome.strip():
                raise ValueError(f"Scene {index} is {INTERACTIVE_SCENE} and must contain a non-empty event_outcome.")

        if not isinstance(scene.get("characters"), list):
            raise ValueError(f"Scene {index} characters must be an array.")
        if not isinstance(scene.get("objects"), list):
            raise ValueError(f"Scene {index} objects must be an array.")
        if is_interactive_scene(scene_type) and len(scene["objects"]) != 9:
            raise ValueError(f"Scene {index} is {INTERACTIVE_SCENE} and must contain exactly 9 objects.")

        object_names: set[str] = set()
        for obj in scene["objects"]:
            if not isinstance(obj, dict):
                raise ValueError(f"Scene {index} contains a non-object item in objects.")
            validate_object_entry(obj, scene_index=index, object_names=object_names)

        if is_narrative_scene(scene_type):
            for normalized_name in object_names:
                if normalized_name not in global_object_names:
                    raise ValueError(
                        f"Scene {index} is {NARRATIVE_SCENE}, but object '{normalized_name}' "
                        "is not defined in global_content.objects."
                    )

        for char in scene["characters"]:
            if not isinstance(char, dict):
                raise ValueError(f"Scene {index} contains a non-object item in characters.")
            name = char.get("name")
            pose = char.get("pose")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Scene {index} has a character with invalid or empty name.")
            if not isinstance(pose, str) or not pose.strip():
                raise ValueError(f"Scene {index} character '{name}' must have a non-empty pose.")

            related_objects = char.get("related_objects", [])
            if related_objects is None:
                continue
            if not isinstance(related_objects, list):
                raise ValueError(f"Scene {index} character related_objects must be an array.")

            for rel in related_objects:
                if not isinstance(rel, dict):
                    raise ValueError(f"Scene {index} has an invalid related_objects entry.")
                rel_name = rel.get("name")
                rel_normalized = normalize_name(rel_name) if isinstance(rel_name, str) else ""
                if not rel_normalized or (rel_normalized not in object_names and rel_normalized not in global_object_names):
                    raise ValueError(
                        f"Scene {index} character related_objects references '{rel_name}', "
                        "but that object name does not exist in scene.objects or global_content.objects."
                    )
                if is_interactive_scene(scene_type) and rel_normalized in object_names:
                    raise ValueError(
                        f"Scene {index} interactive related_objects references '{rel_name}', "
                        "but interactive scene related objects must not also appear in scene.objects."
                    )

        if is_interactive_scene(scene_type):
            if index >= len(scenes):
                raise ValueError(f"Interactive scene {index} must be followed by a narrative scene, but it is the last scene.")
            next_scene_type = scenes[index].get("scene_type")
            if not is_narrative_scene(next_scene_type):
                raise ValueError(
                    f"Interactive scene {index} must be followed by a narrative scene, "
                    f"but scene {index + 1} is {next_scene_type!r}."
                )


def semantic_audit_payload(
    api_key: str,
    model: str,
    payload: dict[str, Any],
    base_url: str,
    timeout: int,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    audit_data, audit_content = request_json_text(
        api_key=api_key,
        model=model,
        messages=build_pose_audit_messages(payload),
        base_url=base_url,
        temperature=0,
        timeout=timeout,
    )
    audit_result = parse_json_from_response(audit_content)
    if not isinstance(audit_result, dict):
        raise ValueError("Semantic audit did not return a JSON object.")

    issues = audit_result.get("issues", [])
    if not isinstance(issues, list):
        issues = [str(issues)]

    fixed_payload = audit_result.get("fixed_payload")
    if not isinstance(fixed_payload, dict):
        raise ValueError("Semantic audit did not return a valid fixed_payload object.")

    valid = audit_result.get("valid")
    if valid is False:
        fixed_payload["_semantic_audit_issues"] = [
            str(item).strip() for item in issues if str(item).strip()
        ]

    return fixed_payload, audit_data, audit_content


def post_chat(api_key: str, base_url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Request failed with HTTP {response.status_code} at {url}\n"
            f"Response body:\n{response.text[:3000]}"
        )
    return response.json()


def request_json_text(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    base_url: str,
    temperature: float,
    timeout: int,
) -> tuple[dict[str, Any], str]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "stream": False,
        "enable_thinking": False,
    }
    data = post_chat(api_key=api_key, base_url=base_url, payload=payload, timeout=timeout)
    content = normalize_response_content(data["choices"][0]["message"]["content"])
    return data, content


def run_json_roundtrip(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    base_url: str,
    temperature: float,
    timeout: int,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    data, content = request_json_text(
        api_key=api_key,
        model=model,
        messages=messages,
        base_url=base_url,
        temperature=temperature,
        timeout=timeout,
    )
    parsed = parse_json_from_response(content)
    return parsed, data, content


def call_bailian_chat(
    api_key: str,
    model: str,
    story_text: str,
    base_url: str,
    temperature: float,
    timeout: int,
    target_total_scenes: int | None,
    max_narrative_scenes: int | None,
    show_progress: bool,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    progress = tqdm(total=6, desc="Story scene split", unit="step", disable=not show_progress)
    progress.set_postfix_str("building prompt")
    draft_messages = build_messages(story_text, target_total_scenes=target_total_scenes, max_narrative_scenes=max_narrative_scenes)
    progress.update(1)

    progress.set_postfix_str("generating draft")
    draft_data, draft_content = request_json_text(
        api_key=api_key,
        model=model,
        messages=draft_messages,
        base_url=base_url,
        temperature=temperature,
        timeout=timeout,
    )
    progress.update(1)

    try:
        draft_parsed = parse_json_from_response(draft_content)
        progress.set_postfix_str("semantic cleanup")
        cleaned_parsed, cleaned_data, cleaned_content = run_json_roundtrip(
            api_key=api_key,
            model=model,
            messages=build_semantic_cleanup_messages(draft_parsed),
            base_url=base_url,
            temperature=0,
            timeout=timeout,
        )
        progress.update(1)

        progress.set_postfix_str("semantic audit")
        parsed = cleaned_parsed
        parsed = sanitize_related_objects(parsed)
        parsed, audit_data, audit_content = semantic_audit_payload(
            api_key=api_key,
            model=model,
            payload=parsed,
            base_url=base_url,
            timeout=timeout,
        )
        progress.update(1)

        progress.set_postfix_str("validating response")
        parsed = sanitize_related_objects(parsed)
        validate_scene_payload(parsed)
        progress.update(2)
        progress.close()
        return parsed, {"draft_response": draft_data, "cleanup_response": cleaned_data, "audit_response": audit_data}, audit_content
    except (json.JSONDecodeError, ValueError) as exc:
        progress.set_postfix_str("repairing response")
        repair_source = draft_content
        if 'cleaned_content' in locals():
            repair_source = cleaned_content
        parsed, repaired_data, repaired_content = run_json_roundtrip(
            api_key=api_key,
            model=model,
            messages=build_repair_messages(repair_source, error_message=str(exc)),
            base_url=base_url,
            temperature=0,
            timeout=timeout,
        )
        parsed, cleanup_after_repair, repaired_cleaned_content = run_json_roundtrip(
            api_key=api_key,
            model=model,
            messages=build_semantic_cleanup_messages(parsed),
            base_url=base_url,
            temperature=0,
            timeout=timeout,
        )
        parsed = sanitize_related_objects(parsed)
        progress.update(2)
        progress.set_postfix_str("semantic audit")
        parsed, audit_after_repair, repaired_audit_content = semantic_audit_payload(
            api_key=api_key,
            model=model,
            payload=parsed,
            base_url=base_url,
            timeout=timeout,
        )
        progress.update(1)
        progress.set_postfix_str("validating response")
        parsed = sanitize_related_objects(parsed)
        validate_scene_payload(parsed)
        progress.update(1)
        progress.close()
        return parsed, {
            "draft_response": draft_data,
            "repair_response": repaired_data,
            "cleanup_response": cleanup_after_repair,
            "audit_response": audit_after_repair,
        }, repaired_audit_content


def main() -> None:
    parser = argparse.ArgumentParser(description="Split story text into narrative/interactive scenes using Qwen on Bailian.")
    parser.add_argument("--text", default=None, help="Story text passed directly on the command line.")
    parser.add_argument("--input-file", default=None, help="Path to a UTF-8 text file containing the story.")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "outputs" / "story_scenes" / "story_scenes.json"), help="Path to save the parsed scene JSON.")
    parser.add_argument("--raw-output", default=str(PROJECT_ROOT / "outputs" / "story_scenes" / "story_scenes_raw.json"), help="Path to save the raw API response.")
    parser.add_argument("--raw-text-output", default=str(PROJECT_ROOT / "outputs" / "story_scenes" / "story_scenes_raw_text.txt"), help="Path to save the raw model text before JSON parsing.")
    parser.add_argument("--api-key", default=None, help="Bailian API key. Defaults to DASHSCOPE_API_KEY env var.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Bailian OpenAI-compatible base URL.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name to call.")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature.")
    parser.add_argument("--timeout", type=int, default=300, help="HTTP timeout in seconds.")
    parser.add_argument("--target-total-scenes", type=int, default=0, help="Optional scene-count hint. Use 0 to let the model decide adaptively.")
    parser.add_argument("--max-narrative-scenes", type=int, default=0, help="Optional narrative-scene hint. Use 0 to let the model decide adaptively.")
    parser.add_argument("--no-progress", action="store_true", help="Disable tqdm progress display.")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("Missing API key. Set DASHSCOPE_API_KEY or pass --api-key.")

    parsed, raw, raw_text = call_bailian_chat(
        api_key=api_key,
        model=args.model,
        story_text=load_story_text(args.text, args.input_file),
        base_url=args.base_url,
        temperature=args.temperature,
        timeout=args.timeout,
        target_total_scenes=args.target_total_scenes if args.target_total_scenes > 0 else None,
        max_narrative_scenes=args.max_narrative_scenes if args.max_narrative_scenes > 0 else None,
        show_progress=not args.no_progress,
    )

    output_path = Path(args.output).resolve()
    raw_output_path = Path(args.raw_output).resolve()
    raw_text_output_path = Path(args.raw_text_output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_text_output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_output_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_text_output_path.write_text(raw_text, encoding="utf-8")

    print(f"Model: {args.model}")
    print(f"Saved parsed scene JSON to: {output_path}")
    print(f"Saved raw API response to: {raw_output_path}")
    print(f"Saved raw model text to: {raw_text_output_path}")
    print(f"Scene count: {len(parsed.get('scenes', [])) if isinstance(parsed, dict) else 0}")


if __name__ == "__main__":
    main()
