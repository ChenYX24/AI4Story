# AI4Story

## Structure

```text
scripts/
  image_generation/
  image_processing/
  story/
  workflow/
examples/
  image_generation/
  story/
outputs/
  images/
  story_scenes/
scenes/
  story_scenes.json
  global/
  001/
  002/
```

## Install

```bash
pip install -r requirements.txt
```

## Image generation

Set your Volcengine API key:

```bash
set ARK_API_KEY=your_api_key
```

Run the 3x3 grid generation script:

```bash
python scripts/image_generation/seedream_grid_test.py --input examples/image_generation/input.example.json --output outputs/images/grid.png
```

If your key belongs to the LAS side:

```bash
python scripts/image_generation/seedream_grid_test.py --provider las --input examples/image_generation/input.example.json --output outputs/images/grid.png
```

## Image post-processing

Default behavior:

- `rembg` background removal
- alpha matting enabled
- white sticker-like outline
- PNG and real vector SVG export
- tqdm progress bars enabled

Run:

```bash
python scripts/image_processing/postprocess_grid.py --input outputs/images/grid.png --input-json examples/image_generation/input.example.json
```

Optional examples:

```bash
python scripts/image_processing/postprocess_grid.py --input outputs/images/grid.png --input-json examples/image_generation/input.example.json --bg-removal-method threshold
python scripts/image_processing/postprocess_grid.py --input outputs/images/grid.png --input-json examples/image_generation/input.example.json --no-rembg-alpha-matting
python scripts/image_processing/postprocess_grid.py --input outputs/images/grid.png --input-json examples/image_generation/input.example.json --no-progress
```

Outputs:

- `outputs/images/grid_transparent.png`
- `outputs/images/extracted/*.png`
- `outputs/images/extracted/*.svg`
- `outputs/images/extracted/manifest.json`

## Story scene splitting

Set your Bailian API key:

```bash
set DASHSCOPE_API_KEY=your_api_key
```

Run with the example story:

```bash
python scripts/story/story_scene_splitter.py --input-file examples/story/story_input.example.txt --model qwen3.5-omni-flash
```

Recommended tighter split:

```bash
python scripts/story/story_scene_splitter.py --input-file examples/story/story_input.example.txt --model qwen3.5-omni-flash --target-total-scenes 7 --max-narrative-scenes 4
```

Run with direct text:

```bash
python scripts/story/story_scene_splitter.py --text "在这里直接放故事文本" --model qwen3.5-omni-flash
```

Current scene rules:

- The first scene must be a narrative scene.
- The last scene must be a narrative scene.
- Every interactive scene must be followed by a narrative scene.
- `event_summary` only describes the opening state and result of the scene.
- Interactive scenes must provide exactly 9 interactive props.
- `global_content` stores recurring characters and recurring objects for consistent asset generation.
- `characters[].related_objects` links character-object combinations that should be generated as one visual unit.
- One-off props in narrative scenes should usually be absorbed into `background_visual_description`.

Outputs:

- `outputs/story_scenes/story_scenes.json`
- `outputs/story_scenes/story_scenes_raw.json`
- `outputs/story_scenes/story_scenes_raw_text.txt`

## Full workflow

Set both API keys:

```bash
set DASHSCOPE_API_KEY=your_dashscope_key
set ARK_API_KEY=your_volcengine_key
```

Run the end-to-end workflow:

```bash
python scripts/workflow/story_asset_workflow.py --input-file examples/story/story_input.example.txt --qwen-model qwen3.5-omni-flash
```

Workflow defaults:

- foreground assets: `2048x2048`
- backgrounds: `2048x2048`

These defaults are intentionally above the current Seedream minimum total-pixel requirement.

Debug mode for interactive-scene image generation only:

```bash
python scripts/workflow/story_asset_workflow.py --use-existing-scenes --use-existing-global --interactive-only --scenes-json scenes/story_scenes.json
```

This mode:

- reuses the existing `scenes/story_scenes.json`
- reuses the existing `scenes/global/manifest.json` and global assets
- skips story splitting
- skips global asset generation
- only generates interactive-scene backgrounds, character images, and 3x3 object grids

Narrative-scene comic test mode:

```bash
python scripts/workflow/story_asset_workflow.py --use-existing-scenes --use-existing-global --narrative-only --scenes-json scenes/story_scenes.json
```

This mode:

- skips all interactive-scene image generation
- generates one text-free 4-panel comic image per narrative scene under `scenes/<scene_index>/comic/panel.png`
- first generates a 4-panel storyboard rewrite under `scenes/<scene_index>/comic/storyboard.txt`, then uses it to drive the final comic image
- uses global character and related-object references to keep style and identity consistent

If you want to reuse the existing `scenes/story_scenes.json`, add `--use-existing-scenes`.
If you omit `--use-existing-scenes`, the workflow will still run the full scene-splitting flow first, then generate only the narrative-scene comics.

What it does:

- Splits the story and saves only `scenes/story_scenes.json`
- Generates global recurring characters and recurring objects into `scenes/global`
- Generates global characters in 3x3 grids and then post-processes them into individual full-body PNG/SVG assets
- Generates global objects in 3x3 grids and then post-processes them into individual PNG/SVG assets
- Creates one folder per chapter under `scenes/<scene_index>`
- Saves each scene payload to `scenes/<scene_index>/scene.json`
- Generates one text-free 4-panel comic image for every narrative scene under `scenes/<scene_index>/comic/panel.png`
- For interactive scenes:
  - generates `image/characters/*.png` and `image/characters/*.svg`
  - generates scene props in 3x3 grids and then post-processes them into `image/objects/*.png` and `image/objects/*.svg`
  - conditions scene props on each scene's `background_visual_description` so the isolated props still match that scene world
  - generates a consistent-size background at `background/background.png`
- For narrative scenes:
  - only creates the chapter folders and `scene.json` for now, without generating any images

Important notes:

- Interactive character generation will compose a temporary local reference board from matching global PNG assets and send it as the Seedream reference input.
- This reference-image wiring is implemented based on the official Seedream image-editing capability documentation and related Volcengine docs; if your endpoint requires a slightly different reference-image field shape, adjust the payload in `scripts/image_generation/seedream_client.py`.
- When an object batch has fewer than 9 items, the workflow pads the remaining cells as explicit blank slots and deletes those placeholder outputs after post-processing.
- Global character grids use the same blank-slot padding strategy when the final batch has fewer than 9 characters.

## Notes

- `https://ark.cn-beijing.volces.com/api/v3` is only a base URL, so opening it directly and seeing `404` is expected.
- Use a real Volcengine model ID such as `doubao-seedream-5-0-lite-260128` instead of the display name.
- The story splitter uses Bailian's OpenAI-compatible Chat API at `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`.
- `response_format={"type":"json_object"}` is enabled, but the script still includes a repair pass for malformed or structurally invalid JSON.
