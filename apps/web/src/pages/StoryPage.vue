<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import TopBar from "@/components/TopBar.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseCard from "@/components/BaseCard.vue";
import { useStoryStore } from "@/stores/story";
import { useToastStore } from "@/stores/toast";
import type { Scene } from "@/api/types";

const props = defineProps<{ id: string }>();
const router = useRouter();
const store = useStoryStore();
const toast = useToastStore();

const loading = ref(true);
const scene = ref<Scene | null>(null);
const flipping = ref<"next" | "prev" | null>(null);
const flipIn = ref(true);
const lineCursor = ref(0);
const audio = ref<HTMLAudioElement | null>(null);
const inputText = ref("");

async function loadCursor(idx: number) {
  if (idx < 0 || idx >= store.flow.length) return;
  loading.value = true;
  try {
    const node = store.flow[idx];
    const sc = await store.ensureScene(node.sceneIdx);
    scene.value = sc;
    store.cursor = idx;
    store.highestUnlocked = Math.max(store.highestUnlocked, idx);
    node.visited = true;
    lineCursor.value = 0;
    // 进入动画
    flipIn.value = false;
    requestAnimationFrame(() => { flipIn.value = true; });
  } finally { loading.value = false; flipping.value = null; }
}

async function turnPage(direction: "next" | "prev") {
  const to = store.cursor + (direction === "next" ? 1 : -1);
  if (to < 0) return;
  if (to >= store.flow.length) {
    // 到达末尾 → 看报告
    router.push({ name: "report", params: { id: props.id } });
    return;
  }
  if (to > store.highestUnlocked) { toast.push("还没解锁哦～", "warn"); return; }
  stopAudio();
  flipping.value = direction;
  // 等翻页动画过一半，再换页
  setTimeout(() => loadCursor(to), 420);
}

function stopAudio() {
  if (audio.value) { audio.value.pause(); audio.value = null; }
}

async function playLine(idx: number) {
  stopAudio();
  const sb = scene.value?.storyboard || [];
  const line = sb[idx];
  if (!line) return;
  try {
    const q = new URLSearchParams({ text: line.text, tone: line.tone || "" });
    if (line.speaker) q.set("speaker", line.speaker);
    const a = new Audio(`/api/tts?${q.toString()}`);
    audio.value = a;
    a.play().catch(() => {});
  } catch {
    /* fallback: ignore */
  }
}

function advanceLine() {
  const sb = scene.value?.storyboard || [];
  if (lineCursor.value >= sb.length) { toast.push("这一幕讲完啦", "info"); return; }
  const idx = lineCursor.value;
  lineCursor.value += 1;
  playLine(idx);
}

async function sendChat() {
  const v = inputText.value.trim();
  if (!v) return;
  inputText.value = "";
  toast.push("聊天功能迁移中 — 下一轮接入", "warn");
}

onMounted(async () => {
  try {
    if (!store.current || store.current.id !== props.id) {
      await store.loadStory(props.id);
    }
    if (store.flow.length === 0) {
      toast.push("这个故事暂未准备好", "error");
      router.push("/library");
      return;
    }
    await loadCursor(0);
  } catch (e: any) {
    toast.push(`加载失败：${e.message}`, "error");
    router.push("/library");
  }
});

watch(() => props.id, async (v) => {
  if (store.current?.id !== v) {
    await store.loadStory(v);
    await loadCursor(0);
  }
});

const node = computed(() => store.flow[store.cursor]);
const isLast = computed(() => store.cursor === store.flow.length - 1);
const visibleLines = computed(() => (scene.value?.storyboard || []).slice(0, lineCursor.value));
</script>

<template>
  <div class="min-h-screen">
    <TopBar
      :cursor="store.cursor"
      :total="store.flow.length"
      @home="() => router.push('/library')"
      @jump="(idx: number) => idx <= store.highestUnlocked && loadCursor(idx)"
    />

    <div class="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 grid gap-6 lg:grid-cols-[1fr_360px]">
      <!-- 书本区 -->
      <div
        class="relative"
        :style="{ perspective: '1800px' }"
      >
        <Transition name="book" mode="out-in">
          <div
            v-if="scene"
            :key="store.cursor"
            class="relative bg-gradient-to-br from-white to-paper-deep border border-paper-edge rounded-l-xl rounded-r-[32px] overflow-hidden"
            :style="{
              boxShadow: 'var(--shadow-book)',
              transformOrigin: 'left center',
              transition: 'transform 0.7s var(--ease-book), opacity 0.6s ease',
              transform: flipping === 'next' ? 'rotateY(-160deg)' : flipping === 'prev' ? 'rotateY(160deg)' : 'rotateY(0)',
              opacity: flipping ? 0.25 : 1,
            }"
          >
            <!-- 书脊阴影 -->
            <div class="absolute left-0 top-0 bottom-0 w-6 pointer-events-none"
              style="background: linear-gradient(90deg, rgba(122,90,54,.35), transparent);"
            ></div>

            <div class="p-6 sm:p-10 min-h-[420px] sm:min-h-[520px] flex flex-col">
              <div class="flex items-center justify-between mb-4">
                <div class="text-xs tracking-wider text-ink-mute">
                  第 {{ (node?.sceneIdx ?? 0) }} 页 · {{ node?.kind === "narrative" ? "叙事" : "互动" }}
                </div>
                <div class="text-xs text-ink-mute">{{ store.cursor + 1 }} / {{ store.flow.length }}</div>
              </div>

              <!-- 叙事：显示 comic + 逐句 -->
              <template v-if="node?.kind === 'narrative'">
                <div class="flex-1 grid place-items-center rounded-xl overflow-hidden bg-paper">
                  <img
                    v-if="scene.comic_url"
                    :src="scene.comic_url"
                    alt="场景连环画"
                    class="w-full h-full object-contain"
                  />
                  <div v-else class="py-20 text-ink-mute">（此幕无图）</div>
                </div>

                <!-- 旁白气泡流 -->
                <div v-if="visibleLines.length" class="mt-4 space-y-2">
                  <div
                    v-for="(ln, i) in visibleLines"
                    :key="i"
                    class="fade-in bg-paper-deep rounded-xl px-4 py-2 text-sm"
                  >
                    <span class="text-ink-soft font-semibold">{{ ln.speaker }}：</span>{{ ln.text }}
                  </div>
                </div>
              </template>

              <!-- 互动：最小占位版 -->
              <template v-else>
                <div class="flex-1 grid place-items-center rounded-xl overflow-hidden bg-paper relative">
                  <img v-if="scene.background_url" :src="scene.background_url" class="w-full h-full object-cover" alt="背景" />
                  <div v-else class="py-20 text-ink-mute">（此幕无背景图）</div>
                  <div class="absolute inset-0 flex items-end justify-center pointer-events-none">
                    <div class="mb-4 px-4 py-2 rounded-full bg-white/90 text-xs text-ink-soft">
                      🎭 互动玩法（拖拽+动作）在下一轮接入
                    </div>
                  </div>
                </div>
                <div class="mt-4 flex flex-wrap gap-2">
                  <span
                    v-for="c in scene.characters"
                    :key="c.id"
                    class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-paper-deep text-ink-soft text-xs"
                  >
                    <img v-if="c.url" :src="c.url" class="w-5 h-5 object-contain" alt="" />
                    {{ c.name }}
                  </span>
                  <span
                    v-for="p in scene.props"
                    :key="p.id"
                    class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gold-mute/60 text-ink text-xs"
                  >
                    <img v-if="p.url" :src="p.url" class="w-5 h-5 object-contain" alt="" />
                    {{ p.name }}
                  </span>
                </div>
              </template>

              <!-- 底部操作条 -->
              <div class="mt-6 flex flex-wrap gap-2 justify-between items-center pt-4 border-t border-dashed border-paper-edge">
                <div class="flex gap-2">
                  <BaseButton variant="soft" size="sm" pill :disabled="store.cursor === 0" @click="turnPage('prev')">⬅ 上一页</BaseButton>
                  <BaseButton
                    v-if="node?.kind === 'narrative'"
                    variant="ghost"
                    size="sm"
                    pill
                    @click="advanceLine"
                  >🔊 下一句</BaseButton>
                </div>
                <BaseButton size="sm" pill @click="turnPage('next')">
                  {{ isLast ? "📊 查看报告" : "翻下一页 ⏭" }}
                </BaseButton>
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <!-- 右侧：摘要 + 聊天 -->
      <aside>
        <BaseCard class="p-5 mb-4">
          <h2 class="font-display text-lg font-bold m-0 mb-1">{{ scene?.title || store.current?.title || "故事" }}</h2>
          <p class="text-sm text-ink-soft leading-relaxed m-0">
            {{ scene?.summary || scene?.narration || store.current?.story_summary || "" }}
          </p>
        </BaseCard>
        <BaseCard class="p-5">
          <div class="text-sm font-semibold mb-2">🗣️ 和讲故事的人聊聊</div>
          <div class="flex gap-2">
            <input
              v-model="inputText"
              placeholder="想问点什么？"
              class="flex-1 px-3 py-2 rounded-lg border border-paper-edge bg-white text-sm focus:outline-none focus:border-accent-soft"
              @keydown.enter="sendChat"
            />
            <BaseButton size="sm" @click="sendChat">发送</BaseButton>
          </div>
          <div class="text-xs text-ink-mute mt-2">下一轮接入语音 + LLM 实时回复</div>
        </BaseCard>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.book-enter-active, .book-leave-active {
  transition: opacity 0.4s ease, transform 0.7s var(--ease-book);
}
.book-enter-from { opacity: 0; transform: rotateY(-160deg); }
.book-leave-to   { opacity: 0; }
</style>
