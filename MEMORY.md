# MEMORY

## 当前稳定记忆

- 2026-04-18 11:20 +08：项目依赖入口是 [requirements.txt](requirements.txt)，新增 [environment.yml](environment.yml) 作为 Conda 环境声明，环境名固定为 `ai4story`，Python 版本固定为 `3.11`。
- 2026-04-18 11:20 +08：当前 shell 为 `zsh`，本机已有 `/Users/cyx/miniconda3`，但 `conda` 尚未注入 `~/.zshrc`。
- 2026-04-18 11:20 +08：工作区已有用户变更 `scenes/story_scenes.json` 删除态，后续操作不得回滚或覆盖。
- 2026-04-18 11:27 +08：`ai4story` 环境已创建，`rembg`、`onnxruntime`、`Pillow`、`requests`、`tqdm`、`vtracer` 在正常用户权限下导入成功。
- 2026-04-18 11:27 +08：若在受限沙箱里导入 `rembg`，`pymatting/numba` 可能因无法写缓存目录而报 `no locator available`；这不是环境损坏，普通终端下可正常使用。
