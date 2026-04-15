# AI4Story Seedream Grid Test

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

## 2. Prepare input JSON

Copy `input.example.json` and replace the 9 object names.

The JSON must contain exactly 9 objects:

```json
{
  "objects": ["apple", "banana", "cat", "dog", "cup", "chair", "lamp", "book", "shoe"],
  "style": "hand-drawn illustration",
  "extra_prompt": "Make each object easy to isolate from the white background."
} 
```

## 3. Generate the 3x3 grid image

Set your Volcengine API key first:

```bash
set ARK_API_KEY=your_api_key
```

Then run:

```bash
python seedream_grid_test.py --input input.example.json --output outputs/grid.png
```

If your key belongs to the LAS operator side, run:

```bash
python seedream_grid_test.py --provider las --input input.example.json --output outputs/grid.png
```

## 4. Remove white background and export each object

```bash
python postprocess_grid.py --input outputs/grid.png --input-json input.example.json
```

Outputs:

- `outputs/grid_transparent.png`: full transparent-background grid
- `outputs/extracted/*.png`: each isolated object as transparent PNG
- `outputs/extracted/*.svg`: each isolated object as embedded-image SVG
- `outputs/extracted/manifest.json`: output manifest

## Notes

- `https://ark.cn-beijing.volces.com/api/v3` is only a base URL, so opening it directly and seeing `404` is expected.
- Use a real model ID such as `doubao-seedream-5-0-lite-260128`, not the display name `Doubao-Seedream-5.0-lite`.
- The SVG export currently wraps the transparent PNG inside an SVG container for compatibility and simplicity.
- If the model leaves too little spacing around an object, increase `--crop-padding` or make the prompt stricter.
- If some near-white strokes disappear, lower `--white-tolerance`.
