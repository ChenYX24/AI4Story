# AI4Story Web Demo

面向学龄前儿童的互动故事书网页。左侧播故事 / 右侧接受语音或文字输入；交互场景里小朋友可以把道具拖到背景上，连续安排多个「谁对谁做什么」，最终让 Seedream 画出结果图，丝滑过渡到下一幕。

## 架构

- 后端：FastAPI + edge-tts + 现有 `scripts/image_generation/seedream_client.py` 和 `scripts/workflow/story_asset_workflow.create_reference_board`
- 前端：原生 HTML/CSS/ES modules。TTS 用服务端 edge-tts 流式输出，ASR 用浏览器 `webkitSpeechRecognition`。
- 资产：直接复用 `scenes/` 下的 PNG（忽略里面的 Windows manifest）

## 运行

```bash
cd /path/to/AI4Story
source ~/miniconda3/etc/profile.d/conda.sh && conda activate ai4story
pip install -r requirements.txt

export ARK_API_KEY=sk-...            # 必须：Seedream
export DASHSCOPE_API_KEY=sk-...      # 可选：叙事聊天用 Qwen

uvicorn apps.api.main:app --reload --port 8000
open http://localhost:8000           # 推荐 Chrome / Edge（语音识别支持）
```

## 目录（monorepo）

```
apps/
├── api/                                 # 后端
│   ├── main.py                          # FastAPI 入口，挂载静态
│   ├── config.py                        # env / 路径常量
│   ├── scene_loader.py                  # 读 story_scenes.json + scene.json
│   ├── asset_resolver.py                # 统一路径解析（忽略 Windows manifest）
│   ├── models.py                        # Pydantic 请求体
│   ├── routers/{story,tts,interact,chat,...}.py
│   └── services/{tts,interact,chat,...}_service.py
└── web/                                 # 前端
    ├── index.html
    ├── css/app.css
    └── js/{app,router,state,api,tts,asr,toast,narrative_view,interactive_view}.js

outputs/webdemo/{session_id}/            # 运行时：生成的参考板 + 结果图（.gitignore）
```

## API

- `GET /api/story` → 故事概要 + 场景索引 + 全局角色/物品
- `GET /api/scene/{idx}` → 单幕完整数据（叙事含 comic_url + storyboard；交互含 background_url + characters + props）
- `GET /api/tts?text=...&voice=zh-CN-XiaoxiaoNeural` → audio/mpeg 流
- `POST /api/interact` → 收 placements + ops，出结果图 URL
- `POST /api/chat` → （可选）Qwen 回复，无 key 时回显

## 交互流程

1. 叙事场景：连环画自动按句朗读，右侧可文字/语音追问
2. 交互场景：顶部显示交互目标；拖道具到背景；点一个物品→点另一个→底部动作条输入「做什么」→加入序列；最后「完成并生成」出结果图 → 过渡下一幕

## 注意

- Seedream 出图单次通常 30-90s，设有 180s 超时
- iOS Safari 无 `webkitSpeechRecognition`，仅支持文字输入
- 刷新页面即重新开始（session_id 重置）
