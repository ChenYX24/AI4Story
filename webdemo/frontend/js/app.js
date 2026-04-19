import { mountStoryPicker, mountStoryPickerAtStories } from "./story_picker.js";
import { state, clearInteractive } from "./state.js";
import { stopTTS } from "./tts.js";

mountStoryPicker();

document.getElementById("home-btn")?.addEventListener("click", async () => {
  if (state.stage === "picking") return;
  const ok = await confirmHome();
  if (!ok) return;
  stopTTS();
  state.stage = "picking";
  state.flow = [];
  state.cursor = 0;
  state.highestUnlocked = 0;
  state.story = null;
  state.storyId = null;
  clearInteractive();
  state.storyLog = { interactions: [] };
  document.getElementById("story-picker")?.remove();
  mountStoryPickerAtStories();
});

function confirmHome() {
  return new Promise((resolve) => {
    const m = document.createElement("div");
    m.className = "modal";
    m.innerHTML = `
      <div class="modal-box">
        <h3>换一个故事？</h3>
        <div class="modal-hint">当前故事的进度会清空，确定要回到选择页吗？</div>
        <div class="modal-actions">
          <button class="secondary" id="hm-no">继续当前</button>
          <button id="hm-yes">换故事</button>
        </div>
      </div>`;
    document.body.appendChild(m);
    document.getElementById("hm-no").onclick = () => { m.remove(); resolve(false); };
    document.getElementById("hm-yes").onclick = () => { m.remove(); resolve(true); };
  });
}
