<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";
import BaseButton from "@/components/BaseButton.vue";
import BaseCard from "@/components/BaseCard.vue";
import InteractiveView from "@/components/InteractiveView.vue";
import { useStoryStore } from "@/stores/story";
import { useSessionStore } from "@/stores/session";
import { useInteractStore } from "@/stores/interact";
import { useToastStore } from "@/stores/toast";
import BaseModal from "@/components/BaseModal.vue";
import { useASR } from "@/composables/useASR";
import { useTTSPreload } from "@/composables/useTTSPreload";
import { useKeyboardShortcuts } from "@/composables/useKeyboardShortcuts";
import { postChat, postInteract, postReport } from "@/api/endpoints";
import type { Scene, InteractRequest, InteractResponse, Operation } from "@/api/types";

const props = defineProps<{ id: string }>();
const router = useRouter();
const store = useStoryStore();
const sess = useSessionStore();
const interactStore = useInteractStore();
const toast = useToastStore();
const asr = useASR({ lang: "zh-CN" });
const tts = useTTSPreload();

const loading = ref(true);
const scene = ref<Scene | null>(null);
const flipping = ref<"next" | "prev" | null>(null);
const flipIn = ref(true);
const lineCursor = ref(0);
const inputText = ref("");

// 聊天记录 — 按场景持久化
interface ChatMsg { role: "user" | "assistant"; text: string; }
const chatLog = ref<ChatMsg[]>([]);
const chatBusy = ref(false);
const chatLogByScene = ref<Record<string, ChatMsg[]>>({});

// 互动场景生成的动态 narrative payload — 在切换到下一节点时插入到 flow
const dynamicNode = ref<InteractResponse | null>(null);
const pendingDynamicPreview = ref<string | null>(null);
const pendingDynamicError = ref<string | null>(null);

async function loadCursor(idx: number) {
  if (idx < 0 || idx >= store.flow.length) return;
  loading.value = true;
  try {
    const node = store.flow[idx];
    store.cursor = idx;
    store.highestUnlocked = Math.max(store.highestUnlocked, idx);
    node.visited = true;
    // 保存当前场景的聊天记录，再切换
    if (scene.value && chatLog.value.length) {
      chatLogByScene.value = { ...chatLogByScene.value, [String(scene.value.index)]: [...chatLog.value] };
    }
    lineCursor.value = 0;
    chatLog.value = [];

    // 恢复该场景的聊天记录
    const savedChat = chatLogByScene.value[String(node.sceneIdx)];
    if (savedChat?.length) chatLog.value = [...savedChat];

    if (node.type === "dynamic") {
      // 独立的 dynamic 幕（互动后生成，已插入 flow）
      const dyn = store.dynamicByScene.get(node.sceneIdx);
      const pending = store.pendingDynamicByScene.get(node.sceneIdx);
      if (!dyn) {
        scene.value = await store.ensureScene(node.sceneIdx).catch(() => null as any);
        dynamicNode.value = null;
        pendingDynamicPreview.value = pending?.previewUrl || null;
        pendingDynamicError.value = pending?.error || null;
        interactiveOps.value = [];
      } else {
        // 源 interactive 场景的 meta 仍然作为 scene.value 背景（供 summary 卡用），但 type 在模板分支里按 dynamicNode 优先
        scene.value = await store.ensureScene(node.sceneIdx).catch(() => null as any);
        dynamicNode.value = dyn.payload;
        pendingDynamicPreview.value = null;
        pendingDynamicError.value = null;
        interactiveOps.value = [];
        store.trackComic(dyn.payload.comic_url);
        if (dyn.payload.storyboard?.length) {
          tts.preload(dyn.payload.storyboard.map((l) => ({ text: l.text, speaker: l.speaker, tone: l.tone })));
        } else {
          tts.stop();
        }
      }
    } else {
      // narrative / interactive 正常路径
      const sc = await store.ensureScene(node.sceneIdx);
      scene.value = sc;
      store.trackComic(sc.comic_url);
      dynamicNode.value = null;
      pendingDynamicPreview.value = null;
      pendingDynamicError.value = null;
      const savedInteract = sc.type === "interactive" ? interactStore.get(props.id, sc.index) : undefined;
      interactiveOps.value = savedInteract?.ops?.map((o) => ({ ...o })) || [];
      if (sc.type === "narrative" && sc.storyboard?.length) {
        tts.preload(sc.storyboard.map((l) => ({ text: l.text, speaker: l.speaker, tone: l.tone })));
      } else {
        tts.stop();
      }
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

function currentSessionId(): string {
  return sess.ensure(props.id, store.current?.title || props.id);
}

function startReportInBackground() {
  const sessionId = currentSessionId();
  const current = sess.getById(sessionId);
  if (current?.report_payload || current?.report_status === "generating" || sess.getReportPromise(sessionId)) return;
  sess.markReportGenerating(sessionId);
  const p = postReport({
    session_id: sessionId,
    story_id: props.id,
    interactions: store.interactions,
  }).then((payload) => {
    sess.saveReport(sessionId, payload);
    return payload;
  }).catch((e: any) => {
    sess.failReport(sessionId, e?.message || String(e));
    throw e;
  });
  sess.setReportPromise(sessionId, p);
  p.catch(() => {});
}

function goReport() {
  const sid = currentSessionId();
  startReportInBackground();
  router.push({ name: "report", params: { id: props.id }, query: { sid } });
}

function isLastInteractiveScene(sceneIdx: number): boolean {
  const scenes = store.current?.scenes || [];
  return !scenes.some((s) => s.type === "interactive" && s.index > sceneIdx);
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
    flipping.value = "prev";
    setTimeout(() => loadCursor(Math.max(0, store.cursor - 1)), 420);
    return;
  }
  const to = store.cursor + (direction === "next" ? 1 : -1);
  if (to < 0) return;
  if (to >= store.flow.length) {
    goReport();
    return;
  }
  // 顺序推进永远允许；跳转（timeline）才检查 highestUnlocked
  stopAudio();
  flipping.value = direction;
  setTimeout(() => loadCursor(to), 420);
}

function stopAudio() { tts.stop(); }

// 当前幕的 storyboard —— dynamic 优先（也需要逐句播放）
const activeStoryboard = computed(() =>
  dynamicNode.value?.storyboard || scene.value?.storyboard || [],
);

async function advanceLine() {
  const sb = activeStoryboard.value;
  // 讲完所有句子后再点"下一句" → 自动翻页（C3b：v2.1 α）
  if (lineCursor.value >= sb.length) {
    if (!isLast.value) {
      turnPage("next");
    } else {
      goReport();
    }
    return;
  }
  const idx = lineCursor.value;
  lineCursor.value += 1;
  await tts.play(idx);
}

// 上一句：把最后一条藏起来，并播放"新的最后一条"（真正意义上的上一句）
function retreatLine() {
  // cursor <= 1 时只有 [0] 可见，回退会隐藏当前仅有的一句，不做
  if (lineCursor.value <= 1) return;
  tts.stop();
  lineCursor.value -= 1;
  // 新 visible = slice(0, lineCursor)，最后一条索引 = lineCursor - 1
  tts.play(lineCursor.value - 1);
}

// 点击已显示的旁白气泡重播（narrative）或动态段落任意行重播
function replayLine(idx: number) { tts.stop(); tts.play(idx); }

// 聊天空态预设问题（P-S3；等 A4 动态推荐落地后替换）
const presetQuestions = [
  "他为什么这么做？",
  "如果我是他，我会怎么办？",
  "可不可以换一个结局？",
];
function fillPreset(q: string) {
  inputText.value = q;
  // 自动发送 vs 只填入 —— 这里只填入，让小朋友有机会改。
}

// ---- 键盘快捷键 ----
useKeyboardShortcuts([
  { key: "ArrowRight", handler: () => turnPage("next") },
  { key: "ArrowLeft",  handler: () => turnPage("prev") },
  { key: " ",          handler: () => advanceLine() },
  { key: "Escape",     handler: () => router.push("/library") },
  ...Array.from({ length: 9 }, (_, i) => ({
    key: String(i + 1),
    handler: () => {
      if (i <= store.highestUnlocked && i < store.flow.length) loadCursor(i);
    },
  })),
]);

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

// 互动完成回调 — dynamic 幕 splice 到 flow 中（当前 interactive 之后），cursor 前进到新幕
async function onInteractDone(
  payload: InteractResponse,
  snap: { ops: any[]; custom_props: any[] },
) {
  const sourceSceneIdx = scene.value?.index;
  if (sourceSceneIdx === undefined) return;
  store.addInteraction({
    scene_idx: sourceSceneIdx,
    interaction_goal: scene.value?.interaction_goal,
    ops: snap.ops,
    custom_props: snap.custom_props,
    dynamic_summary: payload.summary,
    comic_url: payload.comic_url,
  });
  store.recordDynamic(sourceSceneIdx, {
    payload,
    snapOps: snap.ops,
    snapProps: snap.custom_props,
  });
  // splice 到 flow：已有同源 dynamic 会先被清除
  const insertedAt = store.insertDynamicAfter(store.cursor, sourceSceneIdx);
  flipping.value = "next";
  setTimeout(() => {
    flipping.value = null;
    toast.push("✨ 你的故事段落已经画好了", "success");
    // 跳到新插入的 dynamic 幕
    loadCursor(insertedAt);
  }, 420);
}

function onInteractGenerate(request: InteractRequest) {
  const sourceSceneIdx = scene.value?.index;
  if (sourceSceneIdx === undefined) return;
  const sourceGoal = scene.value?.interaction_goal;
  const previewUrl = nextPreviewComicUrl.value;
  store.recordPendingDynamic(sourceSceneIdx, {
    previewUrl,
    snapOps: request.ops,
    snapProps: request.custom_props,
    startedAt: new Date().toISOString(),
  });
  const insertedAt = store.insertDynamicAfter(store.cursor, sourceSceneIdx);
  flipping.value = "next";
  setTimeout(() => {
    flipping.value = null;
    void loadCursor(insertedAt);
  }, 420);

  void postInteract(request).then((payload) => {
    store.addInteraction({
      scene_idx: sourceSceneIdx,
      interaction_goal: sourceGoal,
      ops: request.ops,
      custom_props: request.custom_props,
      dynamic_summary: payload.summary,
      comic_url: payload.comic_url,
    });
    store.recordDynamic(sourceSceneIdx, {
      payload,
      snapOps: request.ops,
      snapProps: request.custom_props,
    });
    sess.markGeneratedNotice(props.id);
    toast.push("Generated new story scene", "success");
    if (isLastInteractiveScene(sourceSceneIdx)) startReportInBackground();
    const active = store.flow[store.cursor];
    if (active?.type === "dynamic" && active.sceneIdx === sourceSceneIdx) {
      void loadCursor(store.cursor);
    }
  }).catch((e: any) => {
    const msg = e?.message || String(e);
    store.failPendingDynamic(sourceSceneIdx, msg);
    pendingDynamicError.value = msg;
    toast.push(`Generate failed: ${msg}`, "error");
  });
}

void onInteractDone;


// E3：进行中 session 恢复弹窗
const resumeModalOpen = ref(false);
function onResumeContinue() {
  const ps = sess.getPlayState(props.id);
  if (!ps) { resumeModalOpen.value = false; return; }
  // 恢复 flow / dynamicByScene / interactStore.states
  store.flow = ps.flow.map((f) => ({ ...f }));
  store.cursor = ps.cursor;
  store.highestUnlocked = ps.highestUnlocked;
  store.interactions = ps.interactions.map((i) => ({ ...i, ops: i.ops.map((o) => ({ ...o })), custom_props: i.custom_props.map((c) => ({ ...c })) }));
  store.comicUrls = [...ps.comicUrls];
  // dynamicByScene
  const dynMap = new Map();
  for (const k in ps.dynamicByScene) dynMap.set(Number(k), ps.dynamicByScene[k]);
  store.dynamicByScene = dynMap;
  const pendingDynMap = new Map();
  for (const k in (ps.pendingDynamicByScene || {})) pendingDynMap.set(Number(k), ps.pendingDynamicByScene![k]);
  store.pendingDynamicByScene = pendingDynMap;
  // interactByScene
  interactStore.clearAll();
  for (const k in ps.interactByScene) {
    interactStore.save(props.id, Number(k), ps.interactByScene[k] as any);
  }
  // chatLogByScene
  if (ps.chatLogByScene) {
    chatLogByScene.value = { ...ps.chatLogByScene };
  }
  resumeModalOpen.value = false;
  toast.push("已恢复上次进度", "success");
  loadCursor(ps.cursor);
}
function onResumeOverwrite() {
  sess.clearPlayState(props.id);
  interactStore.clearAll();
  store.reset();
  resumeModalOpen.value = false;
  (async () => {
    await store.loadStory(props.id);
    if (store.flow.length > 0) loadCursor(0);
  })();
}
function onResumeCancel() {
  resumeModalOpen.value = false;
  router.push("/library");
}

onMounted(async () => {
  sess.clearGeneratedNotice(props.id);
  store.setJumpHandler((idx: number) => { loadCursor(idx); });
  try {
    // 先判断有没有"进行中"快照（本地 + 远程）
    let inProgress = sess.hasInProgress(props.id);
    if (!inProgress) {
      const remote = await sess.fetchRemoteSession(props.id);
      if (remote && remote.cursor < remote.flow.length - 1) inProgress = true;
    }
    if (inProgress) {
      if (!store.current || store.current.id !== props.id) {
        if (store.current && store.current.id !== props.id) store.reset();
        await store.loadStory(props.id);
      }
      if (store.flow.length === 0) {
        toast.push("这个故事暂未准备好", "error");
        router.push("/library");
        return;
      }
      currentSessionId();
      resumeModalOpen.value = true;
      return;
    }

    if (!store.current || store.current.id !== props.id) {
      if (store.current && store.current.id !== props.id) store.reset();
      await store.loadStory(props.id);
    }
    if (store.flow.length === 0) {
      toast.push("这个故事暂未准备好", "error");
      router.push("/library");
      return;
    }
    currentSessionId();
    await loadCursor(0);
  } catch (e: any) {
    toast.push(`加载失败：${e.message}`, "error");
    router.push("/library");
  }
});

// 自动快照：cursor / flow / dynamicByScene / interactByScene / chatLog 变 → 写 session playState
watch(
  [
    () => store.cursor,
    () => store.flow,
    () => store.dynamicByScene,
    () => store.pendingDynamicByScene,
    () => interactStore.states,
    () => store.interactions,
    () => store.comicUrls,
    chatLog,
  ],
  () => {
    if (!store.current || store.current.id !== props.id) return;
    if (store.cursor >= store.flow.length) return;
    // 保存当前场景的聊天到 chatLogByScene
    if (scene.value && chatLog.value.length) {
      chatLogByScene.value = { ...chatLogByScene.value, [String(scene.value.index)]: [...chatLog.value] };
    }
    const dynObj: Record<string, any> = {};
    store.dynamicByScene?.forEach?.((v, k) => { dynObj[String(k)] = v; });
    const pendingDynObj: Record<string, any> = {};
    store.pendingDynamicByScene?.forEach?.((v, k) => { pendingDynObj[String(k)] = v; });
    const interactObj: Record<string, any> = {};
    interactStore.states?.forEach?.((v, k) => {
      const [sid, sidxStr] = k.split(":");
      if (sid !== props.id) return;
      interactObj[sidxStr] = v;
    });
    sess.savePlayState({
      story_id: props.id,
      story_title: store.current.title,
      cursor: store.cursor,
      highestUnlocked: store.highestUnlocked,
      flow: store.flow.map((f) => ({ ...f })),
      dynamicByScene: dynObj,
      pendingDynamicByScene: pendingDynObj,
      interactByScene: interactObj,
      interactions: store.interactions.map((i) => ({ ...i })),
      comicUrls: [...store.comicUrls],
      chatLogByScene: { ...chatLogByScene.value },
      updatedAt: new Date().toISOString(),
    });
  },
  { deep: true, flush: "post" },
);

onBeforeUnmount(() => { store.setJumpHandler(null); });

watch(() => props.id, async (v) => {
  if (store.current?.id !== v) {
    await store.loadStory(v);
    currentSessionId();
    await loadCursor(0);
  }
});

const node = computed(() => store.flow[store.cursor]);
const isLast = computed(() => store.cursor === store.flow.length - 1);
const visibleLines = computed(() => activeStoryboard.value.slice(0, lineCursor.value));
const isPendingDynamic = computed(() => node.value?.type === "dynamic" && !dynamicNode.value);

// TopBar 现在自读 store，无需传 timelineItems

// 下一幕的 comic_url —— 传给互动页 loading 做背景图（用户 #6）
const nextPreviewComicUrl = computed<string | undefined>(() => {
  const nextIdx = store.cursor + 1;
  if (nextIdx >= store.flow.length) return undefined;
  const nextNode = store.flow[nextIdx];
  const cached = store.sceneCache?.get?.(nextNode.sceneIdx);
  if (cached?.comic_url) return cached.comic_url;
  const pad = String(nextNode.sceneIdx).padStart(3, "0");
  return nextNode.type === "narrative"
    ? `/assets/scenes/${pad}/comic/panel.png`
    : `/assets/scenes/${pad}/background/background.png`;
});

// 互动场景的 ops —— 与 InteractiveView 双向绑定（defineModel），在右侧对话栏展示 + 删除
const interactiveOps = ref<Operation[]>([]);
function removeInteractiveOp(i: number) {
  interactiveOps.value.splice(i, 1);
}

// ref 拿到 InteractiveView 以调用暴露方法（完成/清空）
const interactiveRef = ref<{ askComplete: () => void; clearOps: () => void; isGenerating: () => boolean } | null>(null);
function callInteractiveComplete() { interactiveRef.value?.askComplete(); }
function callInteractiveClear() { interactiveRef.value?.clearOps(); }
const interactiveGenerating = computed(() => interactiveRef.value?.isGenerating?.() ?? false);
</script>

<template>
  <!-- 宽屏（lg+）：严格 viewport 高度免整体滚动；窄屏：让页面自然滚动 -->
  <div class="min-h-[calc(100vh-3.5rem)] lg:h-[calc(100vh-3.5rem)] lg:overflow-hidden">
    <!-- E3：进行中 session 恢复弹窗（取消 / 覆盖 / 继续） -->
    <BaseModal :open="resumeModalOpen" title="继续上次的玩法？" :max-width="'460px'" @close="onResumeCancel">
      <p class="text-sm text-ink-soft m-0 mb-2">
        你之前玩这个故事到
        <span class="font-semibold text-ink">第 {{ ((sess.getPlayState(props.id)?.cursor ?? 0) + 1) }} / {{ sess.getPlayState(props.id)?.flow.length ?? 0 }} 页</span>
        ，所有摆放、道具和已生成的段落都保留了。
      </p>
      <p class="text-xs text-ink-mute m-0">选「覆盖」会清空上次进度从头开始。</p>
      <template #footer>
        <BaseButton variant="soft" pill @click="onResumeCancel">取消（回书架）</BaseButton>
        <BaseButton variant="soft" pill @click="onResumeOverwrite">覆盖重玩</BaseButton>
        <BaseButton pill @click="onResumeContinue">继续 →</BaseButton>
      </template>
    </BaseModal>

    <div class="max-w-[1400px] mx-auto h-full px-4 sm:px-6 py-4 grid gap-4 lg:grid-cols-[1fr_360px]">
      <!-- 书本区：占满可用高度，永不溢出 -->
      <div
        class="relative h-full min-h-0"
        :style="{ perspective: '1800px' }"
      >
        <!-- 骨架（scene 未加载时） -->
        <div
          v-if="!scene"
          class="bg-gradient-to-br from-white to-paper-deep border border-paper-edge rounded-l-xl rounded-r-[32px] p-4 sm:p-6 flex flex-col h-full"
          style="box-shadow: var(--shadow-book);"
        >
          <div class="flex justify-between mb-4">
            <div class="w-24 h-4 rounded bg-paper-deep relative overflow-hidden">
              <div class="absolute inset-0 animate-shimmer"></div>
            </div>
            <div class="w-12 h-4 rounded bg-paper-deep relative overflow-hidden">
              <div class="absolute inset-0 animate-shimmer"></div>
            </div>
          </div>
          <div class="flex-1 rounded-xl bg-paper-deep relative overflow-hidden">
            <div class="absolute inset-0 animate-shimmer"></div>
          </div>
          <div class="mt-6 pt-4 border-t border-dashed border-paper-edge flex justify-between">
            <div class="w-20 h-8 rounded-full bg-paper-deep"></div>
            <div class="w-24 h-8 rounded-full bg-paper-deep"></div>
          </div>
        </div>

        <Transition name="book" mode="out-in">
          <div
            v-if="scene"
            :key="store.cursor"
            class="relative bg-gradient-to-br from-white to-paper-deep border border-paper-edge rounded-l-xl rounded-r-[32px] overflow-hidden h-full"
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

            <!-- grid 3 行：header(auto) / main(1fr) / footer(auto)；footer 永不被截 -->
            <div class="p-4 sm:p-6 grid h-full min-h-0 gap-0" style="grid-template-rows: auto minmax(0,1fr) auto;">
              <div class="flex items-center justify-between mb-3">
                <div class="text-xs tracking-wider text-ink-mute">
                  第 {{ (node?.sceneIdx ?? 0) }} 页 · {{ node?.type === "narrative" ? "叙事" : "互动" }}
                </div>
                <div class="text-xs text-ink-mute">{{ store.cursor + 1 }} / {{ store.flow.length }}</div>
              </div>

              <!-- 中间主区：占满剩余 1fr；内部 flex-col 让各分支填满 -->
              <div class="min-h-0 flex flex-col overflow-hidden">
                <!-- ✨ Dynamic narrative -->
                <template v-if="dynamicNode">
                  <div class="flex-1 min-h-0 relative rounded-xl overflow-hidden bg-paper narrative-magic">
                    <img
                      :src="dynamicNode.comic_url"
                      class="absolute inset-0 w-full h-full object-contain z-10"
                      alt="新段落"
                    />
                  </div>
                  <div class="mt-2 px-3 py-2 bg-gold/10 rounded-lg text-sm text-ink-soft border border-gold/30 shrink-0">
                    ✨ 这是你创造的新段落 — <span class="font-medium">{{ dynamicNode.summary }}</span>
                  </div>
                </template>

                <!-- 叙事 -->
                <template v-else-if="isPendingDynamic">
                  <div class="flex-1 min-h-0 relative rounded-xl overflow-hidden bg-paper">
                    <img
                      v-if="pendingDynamicPreview"
                      :src="pendingDynamicPreview"
                      class="absolute inset-0 w-full h-full object-contain"
                      alt="Generating scene preview"
                    />
                    <div v-else class="absolute inset-0 bg-gradient-to-br from-paper-deep to-gold-mute"></div>
                    <div class="absolute inset-x-0 bottom-4 mx-auto w-fit max-w-[86%] rounded-2xl bg-white/90 border border-gold/40 px-4 py-3 shadow-[var(--shadow-card)] text-center">
                      <div class="mx-auto mb-2 w-8 h-8 rounded-full border-[3px] border-gold-mute border-t-accent animate-spin"></div>
                      <div class="text-sm font-semibold text-ink">AI is generating your new scene</div>
                      <div class="text-xs text-ink-soft mt-1">
                        {{ pendingDynamicError ? `Generate failed: ${pendingDynamicError}` : "You can switch pages; generation will keep running in the background." }}
                      </div>
                    </div>
                  </div>
                </template>

                <template v-else-if="node?.type === 'narrative'">
                  <div class="flex-1 min-h-0 relative rounded-xl overflow-hidden bg-paper">
                    <img
                      v-if="scene.comic_url"
                      :src="scene.comic_url"
                      alt="场景连环画"
                      class="absolute inset-0 w-full h-full object-contain"
                    />
                    <div v-else class="absolute inset-0 grid place-items-center text-ink-mute">（此幕无图）</div>
                  </div>
                </template>

                <!-- 互动 -->
                <template v-else>
                  <InteractiveView
                    ref="interactiveRef"
                    v-model:ops="interactiveOps"
                    :scene="scene"
                    :story-id="props.id"
                    :next-comic-url="nextPreviewComicUrl"
                    @generate="onInteractGenerate"
                  />
                </template>
              </div>

              <!-- 底部操作条 —— 永远渲染，保证"完成"按钮在视口底部不被 overflow 截 -->
              <div class="mt-3 flex flex-wrap gap-2 justify-between items-center pt-3 border-t border-dashed border-paper-edge">
                <div class="flex gap-2 flex-wrap">
                  <BaseButton variant="soft" size="sm" pill :disabled="store.cursor === 0" @click="turnPage('prev')">⬅ 上一页</BaseButton>
                  <BaseButton
                    v-if="activeStoryboard.length > 0"
                    variant="ghost"
                    size="sm"
                    pill
                    :disabled="lineCursor <= 1"
                    @click="retreatLine"
                  >◀ 上一句</BaseButton>
                  <BaseButton
                    v-if="activeStoryboard.length > 0"
                    variant="ghost"
                    size="sm"
                    pill
                    @click="advanceLine"
                  >🔊 下一句</BaseButton>
                </div>
                <template v-if="node?.type === 'interactive' && !dynamicNode && !isPendingDynamic">
                  <BaseButton
                    size="sm"
                    pill
                    :disabled="interactiveOps.length === 0 || interactiveGenerating"
                    @click="callInteractiveComplete"
                  >
                    {{ interactiveGenerating ? "AI 正在画…" : `✨ 完成 (${interactiveOps.length}) 并生成下一幕` }}
                  </BaseButton>
                </template>
                <template v-else>
                  <BaseButton size="sm" pill @click="turnPage('next')">
                    {{ isLast ? "📊 查看报告" : "翻下一页 ⏭" }}
                  </BaseButton>
                </template>
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <!-- 右侧：摘要 + 旁白流 + 聊天 —— 占满 grid cell 高度，内部自滚动 -->
      <aside class="space-y-3 h-full min-h-0 overflow-y-auto no-scrollbar pr-1">
        <BaseCard class="p-5">
          <h2 class="font-display text-lg font-bold m-0 mb-1">{{ scene?.title || store.current?.title || "故事" }}</h2>
          <p class="text-sm text-ink-soft leading-relaxed m-0">
            {{ scene?.summary || scene?.narration || store.current?.story_summary || "" }}
          </p>
        </BaseCard>

        <!-- 互动节点：操作输入区（Teleport 自 InteractiveView） -->
        <BaseCard v-show="node?.type === 'interactive' && !dynamicNode && !isPendingDynamic" class="p-4">
          <div id="interact-inputs-slot"></div>
        </BaseCard>

        <!-- 互动节点：动作序列卡（从舞台侧挪过来，方便和对话一起看） -->
        <BaseCard v-if="node?.type === 'interactive' && !dynamicNode && !isPendingDynamic" class="p-4">
          <div class="text-sm font-semibold mb-2 flex items-center justify-between">
            <span>🎬 动作序列<span v-if="interactiveOps.length" class="text-xs text-ink-mute font-normal ml-1">· 共 {{ interactiveOps.length }}</span></span>
            <button
              v-if="interactiveOps.length > 0"
              class="text-[11px] px-2 py-0.5 rounded-full bg-paper-deep hover:bg-warn/15 text-ink-soft hover:text-warn transition"
              :disabled="interactiveGenerating"
              title="清空所有动作"
              @click="callInteractiveClear"
            >🗑 清空</button>
          </div>
          <div v-if="!interactiveOps.length" class="text-xs text-ink-mute text-center py-3 border border-dashed border-paper-edge rounded">
            还没安排动作<br />选两个对象 → 写"做什么"
          </div>
          <div v-else class="space-y-1.5 max-h-48 overflow-y-auto no-scrollbar pr-1">
            <div
              v-for="(o, i) in interactiveOps"
              :key="i"
              class="flex items-start gap-1.5 px-2 py-1.5 rounded-lg bg-accent/10 border border-accent/25 text-xs leading-snug"
            >
              <span class="font-semibold text-accent-deep shrink-0">{{ i + 1 }}.</span>
              <span class="flex-1 text-ink break-words">
                <template v-if="o.subject && o.target">「{{ o.subject }}」对「{{ o.target }}」：{{ o.action }}</template>
                <template v-else-if="o.subject">「{{ o.subject }}」：{{ o.action }}</template>
                <template v-else>{{ o.action }}</template>
              </span>
              <button class="text-warn hover:text-warn/70 shrink-0" title="移除" @click="removeInteractiveOp(i)">×</button>
            </div>
          </div>
        </BaseCard>

        <!-- 旁白流（narrative / dynamic 都用同一套逐句展开） -->
        <BaseCard
          v-if="activeStoryboard.length > 0 && (node?.type === 'narrative' || dynamicNode)"
          class="p-5"
        >
          <div class="text-sm font-semibold mb-3 flex items-center gap-2">
            <span>📖 旁白</span>
            <span class="text-xs text-ink-mute font-normal">
              {{ lineCursor }} / {{ activeStoryboard.length }}
            </span>
          </div>
          <div class="space-y-2">
            <div
              v-for="(ln, i) in visibleLines"
              :key="'v-' + i"
              class="fade-in bg-paper-deep rounded-xl px-3 py-2 text-sm leading-relaxed cursor-pointer hover:bg-gold-mute transition"
              :class="[
                tts.playingIdx.value === i
                  ? 'ring-2 ring-gold/70 shadow-[0_0_16px_rgba(224,178,95,0.45)] bg-gold/10 tts-pulse'
                  : i === visibleLines.length - 1 ? 'ring-1 ring-gold/40' : '',
              ]"
              title="点击重播"
              @click="replayLine(i)"
            >
              <span class="text-ink-soft font-semibold">{{ ln.speaker }}：</span>{{ ln.text }}
              <span v-if="tts.playingIdx.value === i" class="ml-1 text-gold">🔊</span>
            </div>
          </div>
        </BaseCard>
        <BaseCard class="p-5 flex flex-col" style="min-height: 280px;">
          <div class="text-sm font-semibold mb-3 flex items-center justify-between">
            <span>🗣️ 和讲故事的人聊聊</span>
            <span v-if="chatBusy" class="text-xs text-ink-mute animate-pulse">回复中…</span>
          </div>
          <div class="flex-1 overflow-y-auto space-y-2 mb-3 pr-1 no-scrollbar" style="max-height: 320px;">
            <div v-if="!chatLog.length" class="py-4">
              <div class="text-xs text-ink-mute text-center mb-3">
                💡 试试问点什么：
              </div>
              <div class="flex flex-col gap-2">
                <button
                  v-for="q in presetQuestions"
                  :key="q"
                  class="text-left px-3 py-2 text-sm rounded-xl bg-paper-deep hover:bg-gold-mute border border-paper-edge/50 hover:border-gold/40 transition text-ink-soft hover:text-ink"
                  @click="fillPreset(q)"
                >{{ q }}</button>
              </div>
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

/* P-S5 动态段落 — 极淡金色光晕 + 星点漂浮 */
.narrative-magic::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 18% 22%, rgba(255,203,99,0.35), transparent 40%),
    radial-gradient(circle at 82% 78%, rgba(255,169,82,0.28), transparent 42%);
  pointer-events: none;
  opacity: 0.75;
}
.narrative-magic::after {
  content: "✨ · ✧ · ✨";
  position: absolute;
  top: 8px; left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  letter-spacing: 4px;
  color: rgba(213, 147, 57, 0.55);
  pointer-events: none;
  animation: sparkle-drift 3.6s ease-in-out infinite alternate;
}
@keyframes sparkle-drift {
  from { opacity: 0.4; transform: translate(-50%, 0); }
  to   { opacity: 0.95; transform: translate(-50%, 3px); }
}

/* P-S4 侧栏顶底渐隐遮罩（暗示可滚动） */
.aside-fade-mask {
  -webkit-mask-image: linear-gradient(to bottom, transparent 0, #000 12px, #000 calc(100% - 12px), transparent 100%);
          mask-image: linear-gradient(to bottom, transparent 0, #000 12px, #000 calc(100% - 12px), transparent 100%);
}
@media (prefers-reduced-motion: reduce) {
  .narrative-magic::after { animation: none; }
}
</style>
