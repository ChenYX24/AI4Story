<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import TopBar from "@/components/TopBar.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseCard from "@/components/BaseCard.vue";
import InteractiveView from "@/components/InteractiveView.vue";
import { useStoryStore } from "@/stores/story";
import { useToastStore } from "@/stores/toast";
import { useASR } from "@/composables/useASR";
import { useTTSPreload } from "@/composables/useTTSPreload";
import { postChat } from "@/api/endpoints";
import type { Scene, InteractResponse } from "@/api/types";

const props = defineProps<{ id: string }>();
const router = useRouter();
const store = useStoryStore();
const toast = useToastStore();
const asr = useASR({ lang: "zh-CN" });
const tts = useTTSPreload();

const loading = ref(true);
const scene = ref<Scene | null>(null);
const flipping = ref<"next" | "prev" | null>(null);
const flipIn = ref(true);
const lineCursor = ref(0);
const inputText = ref("");

// 聊天记录 — 单幕内的对话（切换幕时重置）
interface ChatMsg { role: "user" | "assistant"; text: string; }
const chatLog = ref<ChatMsg[]>([]);
const chatBusy = ref(false);

// 互动场景生成的动态 narrative payload — 在切换到下一节点时插入到 flow
const dynamicNode = ref<InteractResponse | null>(null);

async function loadCursor(idx: number) {
  if (idx < 0 || idx >= store.flow.length) return;
  loading.value = true;
  try {
    const node = store.flow[idx];
    const sc = await store.ensureScene(node.sceneIdx);
    scene.value = sc;
    store.trackComic(sc.comic_url);
    store.cursor = idx;
    store.highestUnlocked = Math.max(store.highestUnlocked, idx);
    node.visited = true;
    lineCursor.value = 0;
    chatLog.value = [];
    // narrative 幕：并发预载 TTS audio
    if (sc.type === "narrative" && sc.storyboard?.length) {
      tts.preload(sc.storyboard.map((l) => ({ text: l.text, speaker: l.speaker, tone: l.tone })));
    } else {
      tts.stop();
    }
    // 进入动画
    flipIn.value = false;
    requestAnimationFrame(() => { flipIn.value = true; });
    // 下一幕预取（scene + 图片）
    prefetchNode(idx + 1);
  } finally { loading.value = false; flipping.value = null; }
}

async function prefetchNode(idx: number) {
  if (idx < 0 || idx >= store.flow.length) return;
  const node = store.flow[idx];
  try {
    const sc = await store.ensureScene(node.sceneIdx);
    const urls: string[] = [];
    if (sc.comic_url) urls.push(sc.comic_url);
    if (sc.background_url) urls.push(sc.background_url);
    (sc.characters || []).forEach((c) => c.url && urls.push(c.url));
    (sc.props || []).forEach((p) => p.url && urls.push(p.url));
    urls.forEach((u) => { const img = new Image(); img.src = u; });
  } catch { /* silent */ }
}

async function turnPage(direction: "next" | "prev") {
  // 在 dynamic narrative 上点 next → 先清 dynamic 再走真正的 flow 推进
  if (dynamicNode.value && direction === "next") {
    dynamicNode.value = null;
    flipping.value = "next";
    setTimeout(() => loadCursor(Math.min(store.cursor + 1, store.flow.length - 1)), 420);
    return;
  }
  if (dynamicNode.value && direction === "prev") {
    dynamicNode.value = null;
    return;
  }
  const to = store.cursor + (direction === "next" ? 1 : -1);
  if (to < 0) return;
  if (to >= store.flow.length) {
    router.push({ name: "report", params: { id: props.id } });
    return;
  }
  // 顺序推进永远允许；跳转（timeline）才检查 highestUnlocked
  stopAudio();
  flipping.value = direction;
  setTimeout(() => loadCursor(to), 420);
}

function stopAudio() { tts.stop(); }

async function advanceLine() {
  const sb = scene.value?.storyboard || [];
  if (lineCursor.value >= sb.length) { toast.push("这一幕讲完啦", "info"); return; }
  const idx = lineCursor.value;
  lineCursor.value += 1;
  // 同时：文字展示 + 预载音频播放（音频已 preload, 这里立即 play）
  await tts.play(idx);
}

// 点击已显示的旁白气泡重播
function replayLine(idx: number) { tts.play(idx); }

async function sendChat(textOverride?: string) {
  const v = (textOverride ?? inputText.value).trim();
  if (!v || chatBusy.value) return;
  inputText.value = "";
  chatLog.value.push({ role: "user", text: v });
  chatBusy.value = true;
  try {
    const r = await postChat({
      story_id: props.id,
      scene_idx: (scene.value?.index ?? 0),
      user_text: v,
    });
    chatLog.value.push({ role: "assistant", text: r.reply });
    // 朗读 reply
    tts.stop();
    tts.playOne({ text: r.reply, tone: "温柔" });
  } catch (e: any) {
    toast.push(`聊天失败：${e.message}`, "error");
  } finally {
    chatBusy.value = false;
  }
}

async function startMic() {
  if (!asr.supported) { toast.push("浏览器不支持语音识别，建议使用 Chrome", "warn"); return; }
  try {
    const t = await asr.listenOnce();
    if (t) await sendChat(t);
  } catch (e: any) {
    toast.push(`没听清：${e.message}`, "warn");
  }
}

// 互动完成回调 — dynamic narrative 替代当前 scene 渲染（不动 flow）+ 记录 interaction 供报告用
async function onInteractDone(
  payload: InteractResponse,
  snap: { ops: any[]; custom_props: any[] },
) {
  // 写入 store 供 ReportPage 取
  store.addInteraction({
    scene_idx: scene.value?.index ?? 0,
    interaction_goal: scene.value?.interaction_goal,
    ops: snap.ops,
    custom_props: snap.custom_props,
    dynamic_summary: payload.summary,
    comic_url: payload.comic_url,
  });

  flipping.value = "next";
  setTimeout(() => {
    dynamicNode.value = payload;
    lineCursor.value = 0;
    chatLog.value = [];
    flipping.value = null;
    flipIn.value = false;
    requestAnimationFrame(() => { flipIn.value = true; });
    // dynamic 段落的 storyboard 也预载音频（虽然用户不点下一句，但聊天可能需要 tts）
    if (payload.storyboard?.length) {
      tts.preload(payload.storyboard.map((l) => ({ text: l.text, speaker: l.speaker, tone: l.tone })));
    }
    toast.push("✨ 你的故事段落已经画好了", "success");
  }, 420);
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
      :highest-unlocked="store.highestUnlocked"
      :flow-items="store.flow"
      @home="() => router.push('/library')"
      @jump="(idx: number) => loadCursor(idx)"
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
                  第 {{ (node?.sceneIdx ?? 0) }} 页 · {{ node?.type === "narrative" ? "叙事" : "互动" }}
                </div>
                <div class="text-xs text-ink-mute">{{ store.cursor + 1 }} / {{ store.flow.length }}</div>
              </div>

              <!-- ✨ Dynamic narrative（互动后生成的新段落）优先 -->
              <template v-if="dynamicNode">
                <div class="flex-1 grid place-items-center rounded-xl overflow-hidden bg-paper">
                  <img :src="dynamicNode.comic_url" class="w-full h-full object-contain" alt="新段落" />
                </div>
                <div class="mt-3 px-3 py-2 bg-gold/10 rounded-lg text-sm text-ink-soft border border-gold/30">
                  ✨ 这是你创造的新段落 — <span class="font-medium">{{ dynamicNode.summary }}</span>
                </div>
              </template>

              <!-- 叙事：只显示 comic，旁白在右侧 aside -->
              <template v-else-if="node?.type === 'narrative'">
                <div class="flex-1 grid place-items-center rounded-xl overflow-hidden bg-paper">
                  <img
                    v-if="scene.comic_url"
                    :src="scene.comic_url"
                    alt="场景连环画"
                    class="w-full h-full object-contain"
                  />
                  <div v-else class="py-20 text-ink-mute">（此幕无图）</div>
                </div>
              </template>

              <!-- 互动：拖拽 + ops + 调 /api/interact -->
              <template v-else>
                <InteractiveView
                  :scene="scene"
                  :story-id="props.id"
                  @done="onInteractDone"
                />
              </template>

              <!-- 底部操作条 — interactive 场景时由 InteractiveView 自带按钮，外层不再重复 -->
              <div
                v-if="dynamicNode || node?.type === 'narrative'"
                class="mt-6 flex flex-wrap gap-2 justify-between items-center pt-4 border-t border-dashed border-paper-edge"
              >
                <div class="flex gap-2">
                  <BaseButton variant="soft" size="sm" pill :disabled="store.cursor === 0 && !dynamicNode" @click="turnPage('prev')">⬅ 上一页</BaseButton>
                  <BaseButton
                    v-if="!dynamicNode && node?.type === 'narrative'"
                    variant="ghost"
                    size="sm"
                    pill
                    @click="advanceLine"
                  >🔊 下一句</BaseButton>
                </div>
                <BaseButton size="sm" pill @click="turnPage('next')">
                  {{ dynamicNode ? "继续 ⏭" : isLast ? "📊 查看报告" : "翻下一页 ⏭" }}
                </BaseButton>
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <!-- 右侧：摘要 + 旁白流 + 聊天 -->
      <aside class="space-y-4 lg:max-h-[calc(100vh-6rem)] lg:sticky lg:top-20 lg:overflow-y-auto no-scrollbar">
        <BaseCard class="p-5">
          <h2 class="font-display text-lg font-bold m-0 mb-1">{{ scene?.title || store.current?.title || "故事" }}</h2>
          <p class="text-sm text-ink-soft leading-relaxed m-0">
            {{ scene?.summary || scene?.narration || store.current?.story_summary || "" }}
          </p>
        </BaseCard>

        <!-- 旁白流（narrative / dynamic 时才显示） -->
        <BaseCard
          v-if="(node?.type === 'narrative' || dynamicNode) && (visibleLines.length || (dynamicNode?.storyboard?.length ?? 0) > 0)"
          class="p-5"
        >
          <div class="text-sm font-semibold mb-3 flex items-center gap-2">
            <span>📖 旁白</span>
            <span v-if="node?.type === 'narrative' && !dynamicNode" class="text-xs text-ink-mute font-normal">
              {{ lineCursor }} / {{ (scene?.storyboard || []).length }}
            </span>
          </div>
          <div class="space-y-2">
            <!-- 动态段落的所有 storyboard 一次性显示 -->
            <template v-if="dynamicNode">
              <div
                v-for="(ln, i) in (dynamicNode.storyboard || [])"
                :key="'d-' + i"
                class="fade-in bg-paper-deep rounded-xl px-3 py-2 text-sm leading-relaxed"
              >
                <span class="text-ink-soft font-semibold">{{ ln.speaker }}：</span>{{ ln.text }}
              </div>
            </template>
            <!-- 预置叙事：点"下一句"逐条展开，已展开的可点击重播 -->
            <template v-else>
              <div
                v-for="(ln, i) in visibleLines"
                :key="'v-' + i"
                class="fade-in bg-paper-deep rounded-xl px-3 py-2 text-sm leading-relaxed cursor-pointer hover:bg-gold-mute transition"
                :class="i === visibleLines.length - 1 && 'ring-1 ring-gold/40'"
                title="点击重播"
                @click="replayLine(i)"
              >
                <span class="text-ink-soft font-semibold">{{ ln.speaker }}：</span>{{ ln.text }}
              </div>
            </template>
          </div>
        </BaseCard>
        <BaseCard class="p-5 flex flex-col" style="min-height: 280px;">
          <div class="text-sm font-semibold mb-3 flex items-center justify-between">
            <span>🗣️ 和讲故事的人聊聊</span>
            <span v-if="chatBusy" class="text-xs text-ink-mute animate-pulse">回复中…</span>
          </div>
          <div class="flex-1 overflow-y-auto space-y-2 mb-3 pr-1 no-scrollbar" style="max-height: 320px;">
            <div v-if="!chatLog.length" class="text-xs text-ink-mute text-center py-6">
              { 想问什么、想说什么、按下面输入框开始 }
            </div>
            <div
              v-for="(m, i) in chatLog"
              :key="i"
              class="fade-in rounded-2xl px-3 py-2 text-sm max-w-[85%]"
              :class="m.role === 'user'
                ? 'bg-accent-soft/20 ml-auto text-ink'
                : 'bg-paper-deep mr-auto text-ink'"
            >
              <span v-if="m.role !== 'user'" class="text-xs text-ink-soft font-semibold block mb-0.5">讲故事的人</span>
              {{ m.text }}
            </div>
          </div>
          <div class="flex gap-2 mt-auto">
            <button
              :disabled="!asr.supported || asr.listening.value || chatBusy"
              class="w-9 h-9 rounded-full bg-paper-deep hover:bg-gold-mute text-ink-soft grid place-items-center disabled:opacity-40 transition"
              :class="asr.listening.value && 'bg-warn/30'"
              :title="asr.supported ? '语音输入' : '当前浏览器不支持语音'"
              @click="startMic"
            >🎤</button>
            <input
              v-model="inputText"
              placeholder="想问点什么？"
              :disabled="chatBusy"
              class="flex-1 px-3 py-2 rounded-lg border border-paper-edge bg-white text-sm focus:outline-none focus:border-accent-soft disabled:opacity-60"
              @keydown.enter="sendChat()"
            />
            <BaseButton size="sm" :disabled="chatBusy" @click="sendChat()">发送</BaseButton>
          </div>
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
