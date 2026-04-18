# ACTIVE_CONTEXT

- 目标：基于 `scenes/` 现有资产搭建儿童互动故事书网页 demo（FastAPI + 原生前端 + edge-tts + 浏览器 ASR + Seedream 结果图生成）。
- 活动文档：[webdemo/README.md](webdemo/README.md)、[计划文件](/Users/cyx/.claude/plans/sorted-napping-meerkat.md)
- SSOT：
  - 故事数据：[scenes/story_scenes.json](scenes/story_scenes.json)、各 `scenes/{NNN}/scene.json`
  - 资产路径约定：[webdemo/backend/asset_resolver.py](webdemo/backend/asset_resolver.py)（`manifest.json` 一律忽略）
  - 图像生成：`scripts/image_generation/seedream_client.py::generate_image_bytes` + `scripts/workflow/story_asset_workflow.py::create_reference_board`
- 验证：
  - `conda activate ai4story && pip install -r requirements.txt`
  - `export ARK_API_KEY=...; export DASHSCOPE_API_KEY=... (可选)`
  - `uvicorn webdemo.backend.main:app --reload --port 8000`
  - 冒烟：`curl http://127.0.0.1:8000/api/story` / `curl http://127.0.0.1:8000/api/scene/2`
  - 端到端：Chrome 打开 http://localhost:8000，走 6 幕（叙事 1 → 交互 2 → 叙事 3 → 交互 4 → 叙事 5 → 叙事 6）
- 版本状态：
  - Git：`master`（有未提交改动：`requirements.txt` 追加 5 个依赖、新增 `webdemo/`）
  - 备注：工作区已存在用户变更 `D scenes/story_scenes.json`，本任务未触碰。
