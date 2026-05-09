<script setup lang="ts">
// 互动场景：拖拽角色/道具到舞台 → 自由摆放 → 和讲故事的人聊天
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useToastStore } from "@/stores/toast";
import { useSessionStore } from "@/stores/session";
import { useAssetShelfStore } from "@/stores/assetShelf";
import { useInteractStore } from "@/stores/interact";
import { useStoryStore } from "@/stores/story";
import { fetchPlacements, createProp, uploadImage } from "@/api/endpoints";
import { thumbUrl } from "@/api/client";
import type { Scene, SceneCharacter, SceneProp, CustomProp } from "@/api/types";
import SketchPadModal from "./SketchPadModal.vue";
import CustomPropCreateModal from "./CustomPropCreateModal.vue";
import MyAssetsModal from "./MyAssetsModal.vue";

const props = defineProps<{ scene: Scene; storyId: string; sessionId: string }>();

const toast = useToastStore();
const sessions = useSessionStore();
const assetShelf = useAssetShelfStore();
const interactStore = useInteractStore();
const storyStore = useStoryStore();

// 缩略图宽度 — 按使用场景分档，避免加载全尺寸 PNG
const TW_SIDEBAR = 128;
const TW_STAGE = 320;
const TW_BG = 900;

interface PlacedItem {
  id: string;
  name: string;
  kind: "character" | "object";
  url?: string;
  custom_url?: string;
  x: number;
  y: number;
  scale: number;
  rotation: number;
  isCustom?: boolean;
  loading?: boolean;
  refImage?: string;
}

const placed = ref<PlacedItem[]>([]);
const customProps = ref<CustomProp[]>([]);

interface PendingProp {
  tempId: string;
  name: string;
  refImage?: string;
}
const pendingProps = ref<PendingProp[]>([]);

const selectedId = ref<string | null>(null);
const newPropName = ref("");
const sessionId = computed(() => props.sessionId);

// ---- 渐进式引导 ----
const hasDragged = ref(false);
const hasSelected = ref(false);
const hasScaled = ref(false);
const dragHintDismissed = ref(false);
const guideStep = ref<"drag" | "select" | "manipulate" | "done">("drag");
const tipIndex = ref(0);
const tips = [
  "把角色拖到舞台上开始创作",
  "点击角色可以选中它",
  "选中后拖拽移动 · 双指缩放 · Delete 删除",
  "试试「造个新道具」AI 帮你画！",
];
let tipTimer: ReturnType<typeof setInterval> | null = null;

function updateGuideStep() {
  if (placed.value.length === 0 && !dragHintDismissed.value) {
    guideStep.value = "drag";
  } else if (!hasSelected.value) {
    guideStep.value = "select";
  } else if (!hasScaled.value && selectedId.value) {
    guideStep.value = "manipulate";
  } else {
    guideStep.value = "done";
  }
}

function onItemInteraction(kind: "drag" | "select" | "scale") {
  if (kind === "drag") hasDragged.value = true;
  if (kind === "select") hasSelected.value = true;
  if (kind === "scale") hasScaled.value = true;
  updateGuideStep();
}

function findUrlByName(name: string, kind: "character" | "object"): string | undefined {
  if (kind === "character") {
    return props.scene.characters?.find((c) => c.name === name)?.url;
  }
  return props.scene.props?.find((p) => p.name === name)?.url;
}

async function loadInitialPlacements() {
  try {
    const r = await fetchPlacements(props.storyId, props.scene.index);
    for (const p of r.placements) {
      if (p.kind !== "character") continue;
      placed.value.push({
        id: `${p.kind}-${p.name}-${Math.random().toString(36).slice(2, 6)}`,
        name: p.name,
        kind: p.kind,
        url: p.url || findUrlByName(p.name, p.kind),
        x: p.x, y: p.y,
        scale: p.scale ?? 1,
        rotation: p.rotation ?? 0,
      });
    }
  } catch { /* no initial placements = ok */ }
  if (placed.value.length === 0 && props.scene.characters?.length) {
    props.scene.characters.forEach((c, i) => {
      placed.value.push({
        id: `character-${c.name}-fallback-${i}`,
        name: c.name,
        kind: "character",
        url: c.url,
        x: c.default_x ?? (0.3 + i * 0.2),
        y: c.default_y ?? 0.7,
        scale: c.default_scale ?? 1,
        rotation: 0,
      });
    });
  }
}

onMounted(() => {
  const saved = interactStore.get(sessionId.value, props.scene.index);
  if (saved && saved.placed.length) {
    placed.value = saved.placed.map((p) => ({ ...p }));
    customProps.value = [...(saved.customProps || [])];
    hasDragged.value = true;
  } else {
    void loadInitialPlacements();
  }
  document.addEventListener("keydown", onStageKey);
  tipTimer = setInterval(() => {
    tipIndex.value = (tipIndex.value + 1) % tips.length;
  }, 6000);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onStageKey);
  _cleanupTouchDrag();
  dragSource = null;
  if (tipTimer) { clearInterval(tipTimer); tipTimer = null; }
});

watch(
  [placed, customProps],
  () => {
    interactStore.save(sessionId.value, props.scene.index, {
      placed: placed.value,
      customProps: customProps.value,
    });
  },
  { deep: true },
);

function persistSceneState() {
  interactStore.save(sessionId.value, props.scene.index, {
    placed: placed.value,
    customProps: customProps.value,
  });
}

// ---- Drag from sidebar onto stage ----
const stageRef = ref<HTMLDivElement | null>(null);
let dragSource: { name: string; kind: "character" | "object"; url?: string } | null = null;

function onSidebarDragStart(e: DragEvent, item: SceneCharacter | SceneProp, kind: "character" | "object") {
  dragSource = { name: item.name, kind, url: item.url };
  e.dataTransfer?.setData("text/plain", item.name);
  e.dataTransfer && (e.dataTransfer.effectAllowed = "copy");
}

function onStageDrop(e: DragEvent) {
  e.preventDefault();
  if (!dragSource || !stageRef.value) return;
  const rect = stageRef.value.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;
  placed.value.push({
    id: `${dragSource.kind}-${dragSource.name}-${Date.now()}`,
    name: dragSource.name,
    kind: dragSource.kind,
    url: dragSource.url,
    x, y,
    scale: 1, rotation: 0,
  });
  onItemInteraction("drag");
  dragSource = null;
}

function allowDrop(e: DragEvent) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
}

// ---- Touch drag (iPad / mobile) ----
let touchDragGhost: HTMLElement | null = null;
function _positionGhost(x: number, y: number) {
  if (!touchDragGhost) return;
  touchDragGhost.style.left = `${x}px`;
  touchDragGhost.style.top = `${y}px`;
}
function _cleanupTouchDrag() {
  document.removeEventListener("touchmove", _onTouchMove);
  document.removeEventListener("touchend", _onTouchEnd);
  document.removeEventListener("touchcancel", _onTouchEnd);
  if (touchDragGhost) {
    touchDragGhost.remove();
    touchDragGhost = null;
  }
}
function _onTouchMove(e: TouchEvent) {
  if (!touchDragGhost || e.touches.length !== 1) return;
  e.preventDefault();
  const t = e.touches[0];
  _positionGhost(t.clientX, t.clientY);
}
function _onTouchEnd(e: TouchEvent) {
  const t = e.changedTouches?.[0];
  _cleanupTouchDrag();
  if (!dragSource || !stageRef.value || !t) {
    dragSource = null;
    return;
  }
  const rect = stageRef.value.getBoundingClientRect();
  const inside = t.clientX >= rect.left && t.clientX <= rect.right
    && t.clientY >= rect.top && t.clientY <= rect.bottom;
  if (inside) {
    const x = (t.clientX - rect.left) / rect.width;
    const y = (t.clientY - rect.top) / rect.height;
    placed.value.push({
      id: `${dragSource.kind}-${dragSource.name}-${Date.now()}`,
      name: dragSource.name,
      kind: dragSource.kind,
      url: dragSource.url,
      x, y,
      scale: 1, rotation: 0,
    });
    onItemInteraction("drag");
  }
  dragSource = null;
}
function onSidebarTouchStart(
  e: TouchEvent,
  item: { name: string; url?: string },
  kind: "character" | "object",
) {
  if (e.touches.length !== 1) return;
  dragSource = { name: item.name, kind, url: item.url };
  const t = e.touches[0];
  const ghost = document.createElement("div");
  ghost.style.cssText = [
    "position:fixed", "left:0", "top:0", "pointer-events:none", "z-index:9999",
    "width:64px", "height:64px", "background:#fff", "border-radius:14px",
    "box-shadow:0 10px 28px rgba(0,0,0,0.22)",
    "display:flex", "align-items:center", "justify-content:center",
    "transform:translate(-50%,-50%)", "opacity:0.95",
  ].join(";");
  if (item.url) {
    const img = document.createElement("img");
    img.src = thumbUrl(item.url, 72);
    img.style.cssText = "width:48px;height:48px;object-fit:contain;pointer-events:none;";
    ghost.appendChild(img);
  } else {
    ghost.textContent = item.name || "•";
    ghost.style.fontSize = "12px";
    ghost.style.color = "#3d2b1f";
  }
  document.body.appendChild(ghost);
  touchDragGhost = ghost;
  _positionGhost(t.clientX, t.clientY);
  document.addEventListener("touchmove", _onTouchMove, { passive: false });
  document.addEventListener("touchend", _onTouchEnd);
  document.addEventListener("touchcancel", _onTouchEnd);
}

// ---- Pointer interaction on stage (single-finger move + two-finger pinch/rotate) ----
const itemActivePointers = new Map<string, Map<number, { clientX: number; clientY: number }>>();

interface PinchState {
  itemId: string;
  startDist: number;
  startAngle: number;
  startScale: number;
  startRotation: number;
}
let pinch: PinchState | null = null;
let activePointer: { id: string; pointerId: number; offX: number; offY: number } | null = null;

function pointerDist(a: { clientX: number; clientY: number }, b: { clientX: number; clientY: number }) {
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
}
function pointerAngle(a: { clientX: number; clientY: number }, b: { clientX: number; clientY: number }) {
  return Math.atan2(b.clientY - a.clientY, b.clientX - a.clientX);
}
function wrapDeg(d: number) {
  let r = d % 360;
  if (r > 180) r -= 360;
  if (r < -180) r += 360;
  return r;
}

function enterPinchIfPossible(item: PlacedItem) {
  const map = itemActivePointers.get(item.id);
  if (!map || map.size !== 2) return;
  const [p1, p2] = [...map.values()];
  pinch = {
    itemId: item.id,
    startDist: pointerDist(p1, p2),
    startAngle: pointerAngle(p1, p2),
    startScale: item.scale,
    startRotation: item.rotation,
  };
  if (activePointer?.id === item.id) activePointer = null;
}

function onItemPointerDown(e: PointerEvent, item: PlacedItem) {
  if (!stageRef.value) return;
  (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  let map = itemActivePointers.get(item.id);
  if (!map) { map = new Map(); itemActivePointers.set(item.id, map); }
  map.set(e.pointerId, { clientX: e.clientX, clientY: e.clientY });

  if (map.size >= 2) {
    enterPinchIfPossible(item);
    return;
  }
  const rect = stageRef.value.getBoundingClientRect();
  activePointer = {
    id: item.id,
    pointerId: e.pointerId,
    offX: (e.clientX - rect.left) / rect.width - item.x,
    offY: (e.clientY - rect.top) / rect.height - item.y,
  };
}

function onStagePointerMove(e: PointerEvent) {
  if (!stageRef.value) return;

  if (pinch) {
    const map = itemActivePointers.get(pinch.itemId);
    if (!map) { pinch = null; return; }
    if (map.has(e.pointerId)) {
      map.set(e.pointerId, { clientX: e.clientX, clientY: e.clientY });
    }
    if (map.size >= 2) {
      const item = placed.value.find((p) => p.id === pinch!.itemId);
      if (!item) return;
      const [p1, p2] = [...map.values()];
      const dist = pointerDist(p1, p2);
      const angle = pointerAngle(p1, p2);
      item.scale = clamp(
        pinch.startScale * (dist / Math.max(8, pinch.startDist)),
        MIN_SCALE, MAX_SCALE,
      );
      item.rotation = wrapDeg(
        pinch.startRotation + ((angle - pinch.startAngle) * 180) / Math.PI,
      );
      if (Math.abs(item.scale - (pinch.startScale)) > 0.05) {
        onItemInteraction("scale");
      }
      return;
    }
  }

  if (activePointer && activePointer.pointerId === e.pointerId) {
    const rect = stageRef.value.getBoundingClientRect();
    const item = placed.value.find((p) => p.id === activePointer!.id);
    if (!item) return;
    item.x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width - activePointer.offX));
    item.y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height - activePointer.offY));
  }
}

function onStagePointerUp(e?: PointerEvent) {
  if (!e) { activePointer = null; pinch = null; itemActivePointers.clear(); return; }
  for (const map of itemActivePointers.values()) map.delete(e.pointerId);
  if (pinch) {
    const m = itemActivePointers.get(pinch.itemId);
    if (!m || m.size < 2) pinch = null;
  }
  if (activePointer && activePointer.pointerId === e.pointerId) activePointer = null;
}

const MIN_SCALE = 0.3;
const MAX_SCALE = 3.0;

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

// ---- Select / Delete ----
function toggleSelect(item: PlacedItem) {
  const wasSelected = selectedId.value === item.id;
  selectedId.value = wasSelected ? null : item.id;
  if (!wasSelected) onItemInteraction("select");
}

function onStageBackgroundClick() {
  selectedId.value = null;
}

function removePlaced(id: string) {
  const item = placed.value.find((p) => p.id === id);
  placed.value = placed.value.filter((p) => p.id !== id);
  if (item?.custom_url) {
    customProps.value = customProps.value.filter((c) => c.url !== item.custom_url);
  }
  if (selectedId.value === id) selectedId.value = null;
}

function onStageKey(e: KeyboardEvent) {
  const target = e.target as HTMLElement | null;
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
  if (e.key === "Delete" || e.key === "Backspace") {
    if (selectedId.value) {
      removePlaced(selectedId.value);
      e.preventDefault();
    }
  }
}

// ---- Create custom prop ----
async function addCustomProp() {
  const name = newPropName.value.trim();
  if (!name) return;
  newPropName.value = "";
  const tempId = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`;
  pendingProps.value.push({ tempId, name });
  storyStore.startPendingProp(props.storyId);
  toast.push(`「${name}」正在后台作画…`, "info");
  try {
    const r = await createProp({
      session_id: sessionId.value,
      scene_idx: props.scene.index,
      name,
    });
    pendingProps.value = pendingProps.value.filter((p) => p.tempId !== tempId);
    customProps.value.push({ name: r.name, url: r.url });
    persistSceneState();
    assetShelf.addMyAsset({
      name: r.name,
      url: r.url,
      kind: "object",
      origin_story_id: props.storyId,
      origin_scene_idx: props.scene.index,
    });
    sessions.markGeneratedNotice(props.storyId);
    toast.push(`「${r.name}」画好啦，拖到舞台就能用～`, "success");
  } catch (e: any) {
    pendingProps.value = pendingProps.value.filter((p) => p.tempId !== tempId);
    toast.push(`新道具创建失败：${e?.message || e}`, "error");
  } finally {
    storyStore.finishPendingProp(props.storyId);
  }
}

// ---- Upload / Camera / Sketch ----
const showSketchPad = ref(false);
const cameraOpen = ref(false);
const cameraStream = ref<MediaStream | null>(null);
const videoEl = ref<HTMLVideoElement | null>(null);

async function onUploadPick(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  (e.target as HTMLInputElement).value = "";
  if (!file) return;
  if (!file.type.startsWith("image/")) { toast.push("请选择图片", "warn"); return; }
  if (file.size > 6 * 1024 * 1024) { toast.push("图片不能超过 6MB", "warn"); return; }
  const fr = new FileReader();
  fr.onload = async () => {
    const dataUrl = String(fr.result || "");
    await addCustomFromImage(dataUrl, "");
  };
  fr.readAsDataURL(file);
}

async function openCamera() {
  try {
    const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    cameraStream.value = s;
    cameraOpen.value = true;
    await new Promise((r) => setTimeout(r, 80));
    if (videoEl.value) {
      videoEl.value.srcObject = s;
      await videoEl.value.play().catch(() => {});
    }
  } catch (e: any) {
    toast.push(`摄像头不可用：${e?.message || e}`, "warn");
  }
}
function closeCamera() {
  cameraStream.value?.getTracks().forEach((t) => t.stop());
  cameraStream.value = null;
  cameraOpen.value = false;
}
async function snap() {
  if (!videoEl.value) return;
  const v = videoEl.value;
  const cvs = document.createElement("canvas");
  cvs.width = v.videoWidth; cvs.height = v.videoHeight;
  const ctx = cvs.getContext("2d");
  if (!ctx) return;
  ctx.drawImage(v, 0, 0);
  const dataUrl = cvs.toDataURL("image/png");
  closeCamera();
  await addCustomFromImage(dataUrl, "");
}

async function onSketchDone(dataUrl: string) {
  showSketchPad.value = false;
  await addCustomFromImage(dataUrl, "");
}

const propModalOpen = ref(false);
const propModalRefUrl = ref("");
const propModalDefaultName = ref("");

const myAssetsOpen = ref(false);
function addAssetToStage(asset: {
  id: string;
  name: string;
  url: string;
  kind: "character" | "object";
  origin: string;
}) {
  const isCustom = asset.origin === "mine";
  placed.value.push({
    id: `${asset.kind}-${asset.name}-${Date.now()}`,
    name: asset.name,
    kind: asset.kind,
    url: asset.url,
    custom_url: isCustom ? asset.url : undefined,
    isCustom,
    x: 0.5,
    y: 0.55,
    scale: 1,
    rotation: 0,
  });
  if (isCustom && !customProps.value.some((c) => c.url === asset.url)) {
    customProps.value = [...customProps.value, { name: asset.name, url: asset.url }];
  }
  onItemInteraction("drag");
  toast.push(`已添加「${asset.name}」到舞台`, "info");
}

async function addCustomFromImage(dataUrl: string, defaultName: string) {
  try {
    const up = await uploadImage({ data: dataUrl, kind: "prop" });
    propModalRefUrl.value = up.url;
    propModalDefaultName.value = defaultName;
    propModalOpen.value = true;
  } catch (e: any) {
    toast.push(`上传失败：${e?.message || e}`, "error");
  }
}

async function onPropModalSubmit(payload: { name: string; description: string; skipAi: boolean }) {
  if (payload.skipAi) {
    customProps.value.push({ name: payload.name, url: propModalRefUrl.value });
    persistSceneState();
    assetShelf.addMyAsset({
      name: payload.name,
      url: propModalRefUrl.value,
      kind: "object",
      origin_story_id: props.storyId,
      origin_scene_idx: props.scene.index,
    });
    toast.push(`「${payload.name}」已加到道具库，拖到舞台即可使用`, "success");
    propModalOpen.value = false;
    return;
  }
  const tempId = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`;
  const refImage = propModalRefUrl.value;
  const name = payload.name;
  propModalOpen.value = false;
  pendingProps.value.push({ tempId, name, refImage });
  storyStore.startPendingProp(props.storyId);
  toast.push(`「${name}」在后台作画，稍等片刻…`, "info");
  try {
    const r = await createProp({
      session_id: sessionId.value,
      scene_idx: props.scene.index,
      name,
      description: payload.description || undefined,
      reference_image_url: refImage,
      skip_ai: false,
    });
    pendingProps.value = pendingProps.value.filter((p) => p.tempId !== tempId);
    customProps.value.push({ name: r.name, url: r.url });
    persistSceneState();
    assetShelf.addMyAsset({
      name: r.name,
      url: r.url,
      kind: "object",
      origin_story_id: props.storyId,
      origin_scene_idx: props.scene.index,
    });
    sessions.markGeneratedNotice(props.storyId);
    toast.push(`「${r.name}」画好啦，拖到舞台就能用～`, "success");
  } catch (e: any) {
    pendingProps.value = pendingProps.value.filter((p) => p.tempId !== tempId);
    toast.push(`生成失败：${e?.message || e}`, "error");
  } finally {
    storyStore.finishPendingProp(props.storyId);
  }
}

const sidebarChars = computed(() => props.scene.characters || []);
const sidebarProps = computed(() => props.scene.props || []);

const showDragHint = computed(() => !hasDragged.value && !dragHintDismissed.value && placed.value.length === 0);
const showCreateHighlight = computed(() => hasDragged.value && customProps.value.length === 0);
</script>

<template>
  <div class="flex-1 flex flex-col relative min-h-0">
    <!-- 渐进式引导栏 -->
    <div class="mb-3 text-xs px-1 flex items-center gap-2 flex-wrap">
      <span class="inline-flex items-center gap-1 bg-gold/15 px-2 py-1 rounded-full border border-gold/30 text-ink shrink-0">
        <span class="font-semibold">互动目标：</span><span class="text-ink-soft">{{ scene.interaction_goal || "把场景填满" }}</span>
      </span>
      <Transition name="hint" mode="out-in">
        <span v-if="guideStep === 'drag'" key="drag" class="hidden md:inline text-ink-mute">
          👆 把侧边的角色拖到舞台上开始创作
        </span>
        <span v-else-if="guideStep === 'select'" key="select" class="hidden md:inline text-ink-mute">
          💡 点击舞台上的角色或道具可以选中它
        </span>
        <span v-else-if="guideStep === 'manipulate'" key="manipulate" class="hidden md:inline text-ink-mute">
          ✋ 拖拽移动位置 · 🤏 双指缩放旋转 · ⌨️ 按 Delete 删除
        </span>
        <span v-else key="done" class="hidden md:inline text-ink-mute opacity-70">
          {{ tips[tipIndex] }}
        </span>
      </Transition>
    </div>

    <div class="flex-1 grid grid-cols-1 md:grid-cols-[1fr_180px] gap-3 min-h-0" style="grid-template-rows: minmax(0, 1fr);">
      <!-- 舞台 -->
      <div
        ref="stageRef"
        class="relative bg-paper rounded-xl overflow-hidden border border-paper-edge select-none h-full w-full min-h-0"
        style="touch-action: none;"
        @drop="onStageDrop"
        @dragover="allowDrop"
        @pointermove="onStagePointerMove"
        @pointerup="(e) => onStagePointerUp(e)"
        @pointercancel="(e) => onStagePointerUp(e)"
        @pointerleave="() => onStagePointerUp()"
        @click.self="onStageBackgroundClick"
      >
        <img
          v-if="scene.background_url"
          :src="thumbUrl(scene.background_url, TW_BG)"
          loading="eager"
          decoding="async"
          class="absolute inset-0 w-full h-full object-contain object-top pointer-events-none"
          alt="背景"
        />

        <!-- 空舞台拖拽引导 -->
        <Transition name="hint">
          <div
            v-if="showDragHint"
            class="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 pointer-events-none"
          >
            <div class="text-5xl animate-floaty">👆</div>
            <div class="px-5 py-3 rounded-2xl bg-white/92 shadow-[var(--shadow-card)] border-2 border-dashed border-gold/60 text-center">
              <div class="text-sm font-bold text-ink mb-1">把侧边的角色拖到这里吧！</div>
              <div class="text-xs text-ink-mute">按住角色或道具，拖到舞台上</div>
            </div>
            <button
              class="pointer-events-auto text-xs text-ink-mute underline hover:text-ink transition cursor-pointer"
              @click.stop="dragHintDismissed = true"
            >知道了</button>
          </div>
        </Transition>

        <!-- 已放置物体 -->
        <div
          v-for="item in placed"
          :key="item.id"
          class="absolute -translate-x-1/2 -translate-y-1/2 cursor-grab active:cursor-grabbing transition-shadow"
          :class="[selectedId === item.id && 'z-10']"
          :style="{
            left: `${item.x * 100}%`,
            top: `${item.y * 100}%`,
            width: `${72 * item.scale}px`,
          }"
          @pointerdown="(e) => onItemPointerDown(e, item)"
          @click.stop="toggleSelect(item)"
        >
          <!-- 选中外框 + 操作提示 -->
          <div
            v-if="selectedId === item.id"
            class="absolute -inset-2 rounded-xl pointer-events-none ring-[3px] ring-accent shadow-[0_0_16px_rgba(255,122,61,0.4)]"
          >
            <div class="absolute -bottom-7 left-1/2 -translate-x-1/2 bg-accent text-white text-[10px] px-2 py-0.5 rounded-full whitespace-nowrap shadow-md">
              拖拽移动 · 双指缩放 · Delete 删除
            </div>
          </div>

          <div :style="{ transform: `rotate(${item.rotation}deg)` }" class="relative">
            <img
              v-if="item.url && !item.loading"
              :src="thumbUrl(item.url, TW_STAGE)"
              :alt="item.name"
              loading="lazy"
              decoding="async"
              class="w-full h-auto pointer-events-none drop-shadow-md"
            />
            <div v-else-if="item.loading" class="w-full aspect-square relative rounded-xl overflow-hidden bg-white/80 shadow-md">
              <img
                v-if="item.refImage"
                :src="item.refImage"
                class="absolute inset-0 w-full h-full object-cover"
                style="filter: blur(3px) saturate(0.5) opacity(0.6);"
                alt=""
              />
              <div class="absolute inset-0 bg-white/50"></div>
              <div class="absolute inset-0 grid place-items-center">
                <div class="w-8 h-8 border-[3px] border-gold-mute border-t-accent rounded-full animate-spin"></div>
              </div>
              <div class="absolute bottom-0 inset-x-0 text-[9px] text-center text-ink-soft bg-white/80 py-0.5">AI 作画中…</div>
            </div>
            <div v-else class="w-full aspect-square grid place-items-center text-3xl bg-white/80 rounded-full">
              {{ item.kind === "character" ? "🧑" : "🎁" }}
            </div>
          </div>

          <div class="text-[10px] text-center text-ink-soft mt-0.5 px-1 bg-white/70 rounded pointer-events-none">{{ item.name }}</div>

          <!-- 选中删除按钮 -->
          <button
            v-if="selectedId === item.id"
            class="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-warn text-white text-xs grid place-items-center shadow-md hover:bg-warn/80 active:scale-95 transition cursor-pointer z-20"
            title="移除"
            @click.stop="removePlaced(item.id)"
          >✕</button>
        </div>
      </div>

      <!-- 侧边栏 -->
      <aside class="interact-aside bg-white/60 border border-paper-edge rounded-xl p-3 overflow-y-scroll flex flex-col gap-3 h-full min-h-0">
        <!-- 角色 -->
        <div class="text-xs font-bold text-ink-soft mb-1 flex items-center gap-1.5">
          <span>👥 角色</span>
          <span class="text-[10px] font-normal text-ink-mute bg-gold/20 px-1.5 py-0.5 rounded-full drag-badge-pulse">拖到舞台</span>
        </div>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div
            v-for="c in sidebarChars"
            :key="c.name"
            draggable="true"
            class="sidebar-item bg-paper-deep rounded-lg p-2 grid place-items-center text-center cursor-grab active:cursor-grabbing select-none hover:bg-gold-mute/60 hover:shadow-md active:scale-95 transition-all"
            style="touch-action: none;"
            @dragstart="(e) => onSidebarDragStart(e, c, 'character')"
            @touchstart="(e) => onSidebarTouchStart(e, c, 'character')"
          >
            <img v-if="c.url" :src="thumbUrl(c.url, TW_SIDEBAR)" loading="lazy" decoding="async" class="w-12 h-12 object-contain" :alt="c.name" />
            <div class="text-[10px] mt-1 text-ink-soft truncate w-full">{{ c.name }}</div>
          </div>
        </div>

        <!-- 道具 -->
        <div class="text-xs font-bold text-ink-soft mb-1 flex items-center gap-1.5">
          <span>🎁 道具</span>
          <span class="text-[10px] font-normal text-ink-mute bg-gold/20 px-1.5 py-0.5 rounded-full drag-badge-pulse">拖到舞台</span>
        </div>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div
            v-for="p in sidebarProps"
            :key="p.name"
            draggable="true"
            class="sidebar-item bg-gold-mute/40 rounded-lg p-2 grid place-items-center text-center cursor-grab active:cursor-grabbing select-none hover:bg-gold-mute/70 hover:shadow-md active:scale-95 transition-all"
            style="touch-action: none;"
            @dragstart="(e) => onSidebarDragStart(e, p, 'object')"
            @touchstart="(e) => onSidebarTouchStart(e, p, 'object')"
          >
            <img v-if="p.url" :src="thumbUrl(p.url, TW_SIDEBAR)" loading="lazy" decoding="async" class="w-12 h-12 object-contain" :alt="p.name" />
            <div class="text-[10px] mt-1 text-ink truncate w-full">{{ p.name }}</div>
          </div>
          <button
            class="sidebar-item bg-paper-deep hover:bg-gold-mute/60 active:scale-95 rounded-lg p-2 grid place-items-center text-center border border-dashed border-paper-edge hover:border-gold/40 transition cursor-pointer"
            title="浏览账户下所有已有资产"
            @click="myAssetsOpen = true"
          >
            <div class="w-12 h-12 grid place-items-center text-2xl text-ink-soft">＋</div>
            <div class="text-[10px] mt-1 text-ink-soft truncate w-full">我的资产</div>
          </button>
        </div>

        <!-- 我造的道具 -->
        <div v-if="pendingProps.length || customProps.length" class="border-t border-paper-edge pt-2">
          <div class="text-xs font-bold text-ink-soft mb-2 flex items-center justify-between">
            <span>✨ 我造的道具</span>
            <span v-if="pendingProps.length" class="text-[10px] text-ink-mute font-normal">作画中 {{ pendingProps.length }}</span>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div
              v-for="cp in customProps"
              :key="cp.url"
              draggable="true"
              class="sidebar-item bg-gold-mute/40 rounded-lg p-1.5 grid place-items-center text-center cursor-grab active:cursor-grabbing relative border border-gold/30 select-none hover:shadow-md active:scale-95 transition-all"
              style="touch-action: none;"
              :title="`${cp.name} —— 拖到舞台使用`"
              @dragstart="(e) => onSidebarDragStart(e, { name: cp.name, url: cp.url } as any, 'object')"
              @touchstart="(e) => onSidebarTouchStart(e, { name: cp.name, url: cp.url } as any, 'object')"
            >
              <img v-if="cp.url" :src="thumbUrl(cp.url, TW_SIDEBAR)" loading="lazy" decoding="async" class="w-10 h-10 object-contain" :alt="cp.name" />
              <div class="text-[10px] mt-0.5 text-ink truncate w-full">{{ cp.name }}</div>
            </div>
            <div
              v-for="p in pendingProps"
              :key="p.tempId"
              class="bg-white/80 rounded-lg p-1.5 grid place-items-center text-center relative border border-paper-edge overflow-hidden"
              :title="`${p.name} —— 正在后台 AI 作画`"
            >
              <div class="relative w-10 h-10">
                <img
                  v-if="p.refImage"
                  :src="p.refImage"
                  class="absolute inset-0 w-full h-full object-cover rounded"
                  style="filter: blur(2px) saturate(0.4) opacity(0.5);"
                  alt=""
                />
                <div class="absolute inset-0 grid place-items-center">
                  <div class="w-5 h-5 border-[2px] border-gold-mute border-t-accent rounded-full animate-spin"></div>
                </div>
              </div>
              <div class="text-[10px] mt-0.5 text-ink-soft truncate w-full">{{ p.name }}</div>
              <div class="text-[9px] text-accent animate-pulse">作画中…</div>
            </div>
          </div>
        </div>

        <!-- 创建新道具 —— 首次无道具时高亮提示 -->
        <div class="border-t border-paper-edge pt-2 space-y-2" :class="{ 'create-section-glow': showCreateHighlight }">
          <div class="text-xs font-bold text-ink-soft flex items-center gap-2">
            <span>✨ 造个新道具</span>
            <span v-if="showCreateHighlight" class="text-[10px] text-accent animate-pulse font-normal">试试看！</span>
          </div>
          <div class="flex gap-2">
            <input
              v-model="newPropName"
              type="text"
              placeholder="AI 画：比如「会发光的画笔」"
              maxlength="16"
              class="flex-1 min-w-0 px-2 py-1.5 text-xs rounded border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
              @keydown.enter="addCustomProp"
            />
          </div>
          <button
            class="w-full text-xs px-2 py-1 rounded bg-gradient-to-br from-accent-soft to-accent-deep text-white hover:brightness-110 disabled:opacity-50 transition cursor-pointer"
            :disabled="!newPropName.trim()"
            @click="addCustomProp"
          >＋ AI 生成</button>
          <div class="grid grid-cols-3 gap-1">
            <label
              class="flex flex-col items-center justify-center gap-1 text-[11px] px-1 py-2 rounded bg-paper hover:bg-gold-mute border border-paper-edge cursor-pointer transition"
              title="上传图片"
            >
              <span class="text-lg">📁</span>
              <span>上传</span>
              <input type="file" accept="image/*" class="hidden" @change="onUploadPick" />
            </label>
            <button
              class="flex flex-col items-center justify-center gap-1 text-[11px] px-1 py-2 rounded bg-paper hover:bg-gold-mute border border-paper-edge transition cursor-pointer"
              title="摄像头拍照"
              @click="openCamera"
            >
              <span class="text-lg">📷</span>
              <span>拍照</span>
            </button>
            <button
              class="flex flex-col items-center justify-center gap-1 text-[11px] px-1 py-2 rounded bg-paper hover:bg-gold-mute border border-paper-edge transition cursor-pointer"
              title="画板绘制"
              @click="showSketchPad = true"
            >
              <span class="text-lg">🎨</span>
              <span>画板</span>
            </button>
          </div>
        </div>
      </aside>
    </div>

    <!-- 摄像头 modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div
          v-if="cameraOpen"
          class="fixed inset-0 z-[60] bg-cinema/70 backdrop-blur-sm grid place-items-center p-4"
          @click.self="closeCamera"
        >
          <div class="bg-white rounded-2xl p-4 max-w-[520px] w-full">
            <div class="flex items-center justify-between mb-2">
              <h3 class="font-bold">📷 摄像头拍照</h3>
              <button class="w-8 h-8 rounded-full bg-paper-deep hover:bg-gold-mute cursor-pointer" @click="closeCamera">✕</button>
            </div>
            <div class="bg-cinema rounded-xl overflow-hidden aspect-video">
              <video ref="videoEl" class="w-full h-full object-contain" playsinline muted></video>
            </div>
            <div class="flex justify-end gap-2 mt-3">
              <button class="px-4 py-1.5 text-sm rounded-full bg-paper-deep hover:bg-gold-mute cursor-pointer transition" @click="closeCamera">取消</button>
              <button class="px-4 py-1.5 text-sm rounded-full bg-accent text-white hover:brightness-110 cursor-pointer transition" @click="snap">📸 拍下</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 画板 modal -->
    <SketchPadModal :open="showSketchPad" @close="showSketchPad = false" @submit="onSketchDone" />

    <!-- 自定义道具创建 modal -->
    <CustomPropCreateModal
      :open="propModalOpen"
      :image-url="propModalRefUrl"
      :default-name="propModalDefaultName"
      @close="propModalOpen = false"
      @submit="onPropModalSubmit"
    />

    <!-- 我的资产 modal -->
    <MyAssetsModal
      :open="myAssetsOpen"
      :session-custom-props="customProps"
      @close="myAssetsOpen = false"
      @pick="addAssetToStage"
    />
  </div>
</template>

<style scoped>
.modal-enter-active, .modal-leave-active { transition: all 0.25s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; transform: scale(0.98); }

.hint-enter-active, .hint-leave-active { transition: all 0.35s ease; }
.hint-enter-from, .hint-leave-to { opacity: 0; transform: scale(0.95); }

.interact-aside {
  scrollbar-width: thin;
  scrollbar-color: rgba(213, 147, 57, 0.45) transparent;
}
.interact-aside::-webkit-scrollbar { width: 8px; }
.interact-aside::-webkit-scrollbar-track { background: rgba(247, 231, 201, 0.3); border-radius: 4px; }
.interact-aside::-webkit-scrollbar-thumb {
  background: rgba(213, 147, 57, 0.55);
  border-radius: 4px;
}
.interact-aside::-webkit-scrollbar-thumb:hover { background: rgba(213, 147, 57, 0.85); }

.sidebar-item {
  will-change: transform;
  animation: item-settle 0.3s ease-out;
}
@keyframes item-settle {
  from { transform: translateY(2px); opacity: 0.7; }
  to { transform: translateY(0); opacity: 1; }
}

.drag-badge-pulse {
  animation: badge-breathe 2s ease-in-out infinite;
}
@keyframes badge-breathe {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 1; }
}

/* "造个新道具" 首次引导高亮 */
.create-section-glow {
  animation: create-glow 2.5s ease-in-out infinite;
  border-radius: 12px;
  box-shadow: 0 0 0 2px rgba(255, 122, 61, 0.18);
}
@keyframes create-glow {
  0%, 100% { box-shadow: 0 0 0 2px rgba(255, 122, 61, 0.12); }
  50% { box-shadow: 0 0 0 3px rgba(255, 122, 61, 0.32), 0 0 18px rgba(255, 169, 82, 0.18); }
}
</style>
