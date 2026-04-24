# API Model Pipeline 优化分析

> 本文档梳理项目中所有需要调用外部 AI 模型的 pipeline，从**生成效率**和**生成精确度**两个维度分析当前现状并给出优化建议。

---

## 一、Pipeline 总览

| # | Pipeline | 调用的模型 | 当前耗时量级 | 入口 |
|---|----------|-----------|-------------|------|
| 1 | 交互场景 → 下一幕四格漫画 | Qwen(text) + Seedream(image) | ~30-60s | `POST /interact` → `narrative_generator.py:249` |
| 2 | 自定义道具生成（单件/批量/智能解析） | Qwen(JSON) + Seedream(image) + rembg | ~15-40s | `POST /create_prop` · `/create_props_batch` · `/create_props_smart` → `prop_generator.py` |
| 3 | 报告生成 | Qwen(JSON) | ~8-15s | `POST /report/stream` → `report_service.py:56` |
| 4 | 场景对话（Chat） | Qwen(text) | ~3-8s | `POST /chat` → `chat_service.py:24` |
| 5 | 布局规划（Placement） | Qwen(JSON) 或 Qwen-VL(vision) | ~3-10s | `GET /placements` → `placement_service.py:107` |
| 6 | 自定义故事全量资源生成 | Qwen(text) + Qwen-VL(vision) + Seedream(image) × N + rembg × N | ~3-10min | `POST /stories/custom` → `custom_story_service.py:37` |
| 7 | TTS 语音合成 | Xiaomi MiMo v2 TTS | ~2-5s | `GET /tts` → `tts_service.py:66` |

---

## 二、逐 Pipeline 分析

### Pipeline 1：交互场景 → 下一幕四格漫画

**当前流程** `narrative_generator.py:249 generate_dynamic_node`
```
Qwen(text, 120s) ──串行──→ Seedream(image, 180s)
```
1. Qwen 生成叙事文本（summary / narration / dialogue / 4-panel storyboard_panels）
2. 用 storyboard_panels 构建 Seedream prompt + 参考图 refboard → 生成四格漫画

#### 效率问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **Qwen ↔ Seedream 完全串行** | `narrative_generator.py:277→342` | 两次 API 调用无重叠，总延迟 = Qwen延迟 + Seedream延迟。但由于 Seedream prompt 依赖 Qwen 输出的 storyboard_panels，无法简单并行 |
| **参考图 refboard 每次重建** | `narrative_generator.py:306` | 同一幕多次交互（如用户多次点"继续"），背景 + 角色图不变但每次重新拼板 |
| **refboard base64 编码开销** | `seedream_client.py:43-48` | 多张高清 PNG 每次编码成 data URL，refboard 可能 3-5MB |
| **Seedream 分辨率固定 1920×1920** | `config.py:24` | 四格漫画不需要 1920×1920，1280×1280 足矣，可减少 ~55% 像素量、加速生成 |
| **无超时分级重试** | `narrative_generator.py:342` | Seedream 失败直接抛异常，无 backoff 重试；Qwen 有 1 次重试但无退避 |

#### 精确度问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **Qwen prompt 里物品/自造道具 = 全集 → 已修复** | `narrative_generator.py:271` | 此前会把道具栏里未上舞台的道具也告知 Qwen，导致四格漫画画了不该出现的东西（已修复） |
| **Seedream prompt 中角色只列名字，无外观描述** | `story_asset_workflow.py:752-760` `build_narrative_comic_prompt` | `Characters to keep consistent with references: 小红帽. 大灰狼.` 仅列名字，没有将角色外观描述写入 prompt，Seedream 全靠参考图理解角色造型 |
| **storyboard_text 重复传入 prompt 和 Seedream** | `narrative_generator.py:309` | storyboard 文本既作为 `build_narrative_comic_prompt` 的参数，又被 Qwen 已经写进了 panel description，存在信息冗余和潜在矛盾 |
| **用户别名 vs 物品名不一致** | — | 用户 op.action 里写"凳子"但舞台物品叫"椅子"，Qwen 和 Seedream 没有名称归一逻辑，可能造成多余物体 |
| **pseudo_scene.characters 用 scene 全集** | `narrative_generator.py:325` | Seedream prompt 里 Characters 仍是 scene.characters 全集，而不是画布上的角色 |

#### 优化建议

1. **缓存 refboard**：对同一 (story_id, scene_idx) 的背景 + 角色 refboard，首次生成后缓存到 session 目录，后续只追加/替换变化的道具格子。
2. **Seedream 分辨率降级**：四格漫画改用 `1280×1280`（仍满足 Seedream 最低像素要求），估计缩短 30-40% 生图时间。
3. **Qwen 流式输出 + 提前构建 prompt**：Qwen 开启 `stream: true`，在 storyboard_panels 流出后立即开始构建 Seedream prompt + 编码 refboard，减少等待。
4. **增加 Seedream 退避重试**：至少 2 次重试，间隔 5s / 15s，降低一次性失败率。
5. **Seedream prompt 增加角色外观描述**：将 `global_content.characters[].appearance_description` 拼入 prompt，减少角色走形。
6. **名称归一化**：在 `_build_qwen_prompt` 里增加一段"舞台上的物品名称列表"，让 Qwen 在生成 panel description 时只使用这些名字。

---

### Pipeline 2：自定义道具生成

**当前流程** `prop_generator.py`

- **单件** (`create_custom_prop`, :102)：`Seedream(image) → rembg → crop → outline → save`
- **批量** (`create_custom_props_batch`, :244)：`Seedream(3×3 grid) → rembg(全图) → 裁切 9 格 → save`
- **智能解析** (`smart_create_props`, :229)：`Qwen(JSON) → 单件 or 批量`

#### 效率问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **批量固定 padding 到 9 格** | `prop_generator.py:265` | 用户只要 2 个道具也生成 3×3 grid（9 格），7 个空格浪费像素和 Seedream 计算量 |
| **rembg 对全图处理** | `prop_generator.py:293` | 1920×1920 全图做一次 rembg，耗时约 3-5s；可以先裁切成小格再并行 rembg |
| **单件生成无并行** | `prop_generator.py:239` | `smart_create_props` 中单件走 `create_custom_prop`，如果用户一次要多件（≤9），每件都独立调 Seedream |
| **reference_image 编码重复** | `prop_generator.py:121-123` | 如果同一参考图被多次调用（用户基于同一张手绘创建多个道具），每次重新读取+编码 |

#### 精确度问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **grid prompt 无场景上下文** | `prop_generator.py:272-280` | 批量生成只描述物品外观，不告知当前故事风格/色调，生成的道具可能与故事风格不一致 |
| **rembg 失败时降级为原图** | `prop_generator.py:299-301` | 白底原图作为道具会在舞台上显示白色方块，严重影响体验 |
| **单件 prompt 重复 has_reference 块** | `prop_generator.py:89-98` | 两个 `if has_reference:` 块（:89 和 :94）拼出了语义重复的指令，可能让 Seedream 过度关注参考图而忽略风格要求 |

#### 优化建议

1. **动态 grid 大小**：1-2 件用单件模式（无 grid），3-4 件用 2×2 grid，5-9 件用 3×3 grid，减少空格浪费。
2. **先裁切后 rembg**：grid 生成后立即按格子裁切，每个格子独立并行 rembg，速度约快 2-3 倍。
3. **加入场景风格 context**：在 grid prompt 中追加 `"Match the visual style of: {background_visual_description}"` 让道具风格一致。
4. **rembg 降级改用绿幕提示**：在 prompt 中要求 Seedream 用纯白背景生成，配合简单阈值抠图作为 rembg 的 fallback，避免白块问题。

---

### Pipeline 3：报告生成

**当前流程** `report_service.py:56 build_report`
```
格式化 interactions → 拼 prompt → Qwen(JSON, 60s) → 解析 + 补默认值
```

#### 效率问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **单次大 JSON 请求** | `report_service.py:109` | 整份报告（share + kid + parent + metrics）一次性让 Qwen 输出，JSON 结构复杂时容易超时或截断 |
| **timeout 仅 60s** | `report_service.py:109` | 互动记录较多时（4+ 场景、20+ 操作），60s 可能不够，且无重试 |
| **SSE 流式但后端仍同步** | `report.py:66` | 虽然 SSE 包装了进度，但 `build_report` 本身是一次性调用，用户看到的"进度"是伪进度 |

#### 精确度问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **metrics 归一化覆盖了 Qwen 证据** | `report_service.py:162-185` | Qwen 辛苦生成的 evidence 被硬编码的 `criteria` dict 覆盖（:177 `"evidence": criteria[name]`），丢失了个性化分析 |
| **Qwen 可能幻觉 metrics** | `report_service.py:100-103` | 要求 Qwen 自选 4-6 个维度 + 引用证据，但 Qwen 经常虚构操作名，prompt 中只说"必须引用"但无强约束 |
| **hardcoded 建议可能与场景无关** | `report_service.py:187-192` | `real_world_suggestions` 4 条固定建议，无论什么故事都一样，没有结合具体故事主题 |
| **prompt 硬编码"小红帽"** | `report_service.py:65` | `"一个《小红帽》互动故事书"` 写死，自定义故事的报告也会提到"小红帽" |

#### 优化建议

1. **拆分为 2 次 Qwen 调用**：第一次生成 `share + kid_section`（简单、快），第二次生成 `parent_section`（复杂、需深度分析），两次可并行。
2. **保留 Qwen 的 evidence**：将 Qwen 返回的 evidence 和 value 保留，只做 clamp 和安全过滤，不用 criteria dict 覆盖。
3. **去掉硬编码故事名**：`prompt` 中用 `story_summary` 动态替代"一个《小红帽》互动故事书"。
4. **增加 timeout 和重试**：timeout 提升到 90s，retries=2。
5. **将 interactions 中的操作名原文传入 prompt 的约束区**：在 prompt 底部加一段"以下是可引用的操作名列表：[...]，evidence 中只能引用这些名字"，减少幻觉。

---

### Pipeline 4：场景对话（Chat）

**当前流程** `chat_service.py:24 reply_to`
```
构建 system prompt（含故事大纲 + 场景上下文 + 角色性格） → Qwen(text, 60s)
```

#### 效率问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **无重试** | `chat_service.py:71` | `call_text` 默认 retries=0（:75-82 无 retries 参数），失败即报错 |
| **无上下文缓存** | — | 每次对话都重新拼 system prompt，无多轮对话记忆 |
| **每次重新 load_story + load_scene** | `chat_service.py:31,44` | 虽然 `load_story` 有内存缓存，但 `_load_scene_json` 每次都读磁盘 |

#### 精确度问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **无多轮上下文** | — | 每次对话都是独立问答，用户问"然后呢？"时 Qwen 不知道"然后"指什么 |
| **角色扮演不稳定** | `chat_service.py:51-65` | system prompt 虽然有角色立场约束，但没有 few-shot 示例，Qwen 有时仍会"好心的大灰狼" |
| **scene_chars_str 可能为空** | `chat_service.py:47` | `_load_scene_json` 失败时 `scene_chars_str=""` 但不报错，Qwen 不知道当前谁在场 |

#### 优化建议

1. **增加 retries=1**：`call_text(user_text, ..., retries=1)`，`call_text` 需要扩展支持 retries 参数。
2. **多轮对话记忆**：在 session 中维护最近 4-6 轮 (user, assistant) 消息历史，作为 Qwen messages 传入。
3. **Few-shot 示例**：在 system prompt 中增加 1-2 个角色扮演示例（正确回复 vs 错误回复），强化角色一致性。
4. **scene 加载缓存**：给 `_load_scene_json` 加 `@lru_cache`，或在 `chat_service` 中缓存上一次的场景数据。

---

### Pipeline 5：布局规划（Placement）

**当前流程** `placement_service.py:107 plan_layout`
```
查磁盘 placements.json → 有则返回（LRU 缓存）
                       → 无则 Qwen(JSON, 30s) → 保存 + 返回
```

#### 效率：当前已较优

- 有 `@lru_cache(maxsize=64)` 内存缓存 + 磁盘 `placements.json` 持久化
- 首次计算后后续请求 O(1)
- 自定义故事在构建阶段已通过 `precompute_scene_placements`（Qwen-VL）预计算

#### 精确度问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **Qwen-VL 和纯文本 Qwen 两套布局逻辑** | `story_asset_workflow.py:103` vs `placement_service.py:72` | 预构建用 Qwen-VL（看图），运行时 fallback 用纯文本 Qwen（不看图），两者坐标可能不一致 |
| **fallback 布局过于机械** | `placement_service.py:37-62` | 角色均匀排底部、物品 3 列 grid 排顶部，与场景语义无关 |

#### 优化建议

1. **统一走 Qwen-VL**：运行时也优先尝试 Qwen-VL（如果背景图存在），保持与预构建一致。
2. **fallback 布局加入场景语义**：根据 `initial_frame` 描述调整位置（如"树后"→ 靠边）。

---

### Pipeline 6：自定义故事全量资源生成

**当前流程** `custom_story_service.py:58 _build_story_assets → story_asset_workflow.py run_workflow`
```
Qwen(text, 拆场景 300s)
  → 逐场景并行 (ThreadPool, max_workers=4-8)：
      叙事场景：Qwen(storyboard, 300s) → Seedream(comic) + refboard
      交互场景：Seedream(background) + Seedream(char grid) × ceil(n/9) + Seedream(obj grid) × ceil(m/9) + rembg × N + Qwen-VL(placements)
```

#### 效率问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **场景拆分单次调用 300s** | `story_scene_splitter.py` | 整个故事文本 → 结构化 JSON 一次性生成，长故事容易超时 |
| **角色资源逐场景重复生成** | `story_asset_workflow.py` | 同一角色（如"小红帽"）在每个交互场景都重新生成，没有跨场景复用全局角色图 |
| **全局角色/物品 grid 串行** | `story_asset_workflow.py` | 全局角色和全局物品的 grid 生成是串行的，可以并行 |
| **rembg 在主线程** | — | 部分场景的 rembg 后处理没有并行化 |
| **无断点续传** | `custom_story_service.py:62` | 失败后 `shutil.rmtree(workspace)` 清空重来，已生成的资源全部丢弃 |

#### 精确度问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **场景拆分质量不稳定** | `story_scene_splitter.py` | Qwen 一次性输出 6+ 场景的结构化 JSON，容易出现字段遗漏、格式错误 |
| **交互场景 objects 数量失控** | — | Qwen 有时为一个交互场景生成 10+ 个物品，导致 grid 需要多轮 Seedream 调用 |
| **叙事场景 storyboard 与 comic prompt 信息冗余** | `story_asset_workflow.py:887-897` | storyboard_text 和 comic prompt 都包含场景描述，Seedream 可能被重复指令困惑 |

#### 优化建议

1. **全局角色一次生成，跨场景复用**：先生成全局角色/物品图，交互场景只生成场景特有的背景和新增物品。
2. **增量式构建 + 断点续传**：检查已有资源，只生成缺失的部分。
3. **限制交互场景物品数量**：在场景拆分 prompt 中硬约束 `objects ≤ 6`。
4. **并行全局资源**：全局角色 grid + 全局物品 grid 并行生成。

---

### Pipeline 7：TTS 语音合成

**当前流程** `tts_service.py:66 synthesize_bytes`
```
文本 + 语气标签 → Xiaomi MiMo v2 TTS API → base64 audio bytes
```

#### 效率问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **无缓存** | `tts.py:9` | 相同文本 + 语气的 TTS 每次都重新调用 API，响应头设了 `Cache-Control: public, max-age=3600` 但只在浏览器端生效 |
| **无批量合成** | — | 前端逐句请求 TTS（每个 storyboard line 一次），多句场景会串行发 5-8 次请求 |
| **无重试** | `tts_service.py:96-103` | 网络错误直接抛异常 |
| **WAV 格式** | `config.py:32` | 默认 WAV 格式，文件体积大；换 MP3/OGG 可减少 70-80% 传输量 |

#### 精确度问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **语气映射不完整** | `tts_service.py:20-41` | `_TONE_STYLE_MAP` 只覆盖了部分语气，如"虚弱做作"会直接作为 style 标签传入，MiMo 可能无法识别 |
| **无角色音色区分** | — | 所有角色都用同一个 `voice`，小红帽和大灰狼听起来一样 |

#### 优化建议

1. **服务端 LRU 缓存**：对 `(text, voice, tone)` 三元组做 hash key，缓存最近 100 条 TTS 结果到内存或磁盘。
2. **默认格式改 MP3**：`XIAOMI_TTS_FORMAT=mp3`，减少网络传输。
3. **批量合成接口**：新增 `POST /tts/batch`，一次提交多句，服务端并行调用 TTS API 后合并返回。
4. **完善语气映射表**：根据 Qwen 常见输出的 tone 值扩展 `_TONE_STYLE_MAP`。
5. **角色音色映射**：维护一个 `{角色名 → voice_id}` 映射表，不同角色用不同音色。

---

## 三、跨 Pipeline 共性问题

### 3.1 Qwen 调用层 (`qwen_service.py`)

| 问题 | 位置 | 影响 |
|------|------|------|
| **`call_text` 无 retries 参数** | `qwen_service.py:75-108` | Chat pipeline 等使用 `call_text` 的地方完全没有重试机制 |
| **无指数退避** | `qwen_service.py:57` | `call_json` 的重试是立即重试，遇到限流（429）会连续失败 |
| **同步阻塞** | `qwen_service.py:59` | 使用 `requests.post` 同步调用，在 FastAPI 的同步路由中会阻塞工作线程 |
| **模型写死** | `qwen_service.py:10` | `DEFAULT_MODEL = "qwen3.5-122b-a10b"` 但 `custom_story_service` 用 `qwen3.6-plus`，各处模型不一致 |

**优化建议**
1. 给 `call_text` 增加 `retries` 参数，复用 `call_json` 相同的重试逻辑。
2. 增加指数退避：`time.sleep(2 ** attempt)`，429 时自动退避。
3. 考虑迁移到 `httpx.AsyncClient`，配合 FastAPI 的 async 路由，避免线程池耗尽。
4. 统一模型配置到 `config.py`，通过环境变量切换。

### 3.2 Seedream 调用层 (`seedream_client.py`)

| 问题 | 位置 | 影响 |
|------|------|------|
| **参考图 base64 重复编码** | `seedream_client.py:51-58` | 同一幕的背景/角色图每次调用都重新读文件 + base64 编码 |
| **无重试** | `seedream_client.py:110` | 除 404 fallback 外无任何重试逻辑 |
| **payload 日志不含 prompt** | `seedream_client.py:107` | 日志只记录 refs 数量和大小，调试时看不到实际 prompt |

**优化建议**
1. 在 session 级别缓存已编码的 base64 图片（按文件路径 + mtime 做 key）。
2. 增加通用重试逻辑（至少 2 次，指数退避）。
3. 在 debug 级别记录完整 prompt，方便排查生图质量问题。

### 3.3 错误处理统一

当前各 pipeline 的错误类型不统一：
- `QwenError` / `TTSError` / `RuntimeError` / `TimeoutError` 混用
- 前端无法区分"超时"、"限流"、"内容安全过滤"等不同错误类型

**建议**：定义统一的 `AIServiceError` 基类，包含 `error_code`（`timeout` / `rate_limit` / `content_filter` / `internal`），让前端可以针对性提示用户。

---

## 四、优先级排序

按"投入产出比"排序，建议优先实施：

| 优先级 | 优化项 | 预期收益 | 实施难度 |
|--------|--------|---------|---------|
| P0 | 报告 prompt 去掉硬编码"小红帽" + 保留 Qwen evidence | 自定义故事报告可用 | 低 |
| P0 | `call_text` 增加 retries + Qwen 指数退避 | 所有 Qwen 调用鲁棒性提升 | 低 |
| P1 | Seedream 四格漫画降分辨率 1280×1280 | 生图速度提升 30-40% | 低 |
| P1 | TTS 服务端缓存 + 改 MP3 格式 | 语音延迟降低 50%+，带宽节省 70%+ | 低 |
| P1 | Seedream 增加重试 + 退避 | 生图成功率提升 | 低 |
| P2 | 道具批量生成动态 grid | 减少 Seedream 空格浪费 | 中 |
| P2 | Chat 多轮上下文 | 对话连贯性大幅提升 | 中 |
| P2 | 报告拆分为 2 次并行 Qwen 调用 | 报告生成时间减半 | 中 |
| P3 | refboard 缓存 | 重复交互场景生成加速 | 中 |
| P3 | 自定义故事断点续传 | 失败恢复体验提升 | 高 |
| P3 | TTS 角色音色映射 + 批量合成 | 沉浸感提升 | 中 |
| P3 | Qwen/Seedream 迁移 async | 全局并发能力提升 | 高 |
