<script setup lang="ts">
// 互动场景：拖拽角色/道具到背景 → 选两个 + 输入动作 → 加入 ops 序列 → 完成 → /api/interact
// 保留与 web-legacy/js/interactive_view.js 一致的 contract，但用 Pointer Events + Vue reactivity 重写
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useToastStore } from "@/stores/toast";
import { useSessionStore } from "@/stores/session";
import { useAssetShelfStore } from "@/stores/assetShelf";
import { useInteractStore } from "@/stores/interact";
import { fetchPlacements, postInteract, createProp, uploadImage } from "@/api/endpoints";
import type {
  Scene, SceneCharacter, SceneProp,
  Transform, Operation, CustomProp,
  InteractResponse,
} from "@/api/types";
import BaseButton from "./BaseButton.vue";
import SketchPadModal from "./SketchPadModal.vue";
import CustomPropCreateModal from "./CustomPropCreateModal.vue";

// ---- 生图 loading hint 轮播 ----
const LOADING_HINTS = [
  "AI 正在调色盘里挑颜色…",
  "小画笔正在认真地画…",
  "把你说的故事变成画…",
  "再加一点点魔法…",
  "快完成啦，再等一下～",
];
const loadingHint = ref("");
let loadingTimer: ReturnType<typeof setInterval> | null = null;
function startLoadingHints() {
  stopLoadingHints();
  let i = 0;
  loadingHint.value = LOADING_HINTS[0];
  loadingTimer = setInterval(() => {
    i = (i + 1) % LOADING_HINTS.length;
    loadingHint.value = LOADING_HINTS[i];
  }, 2600);
}
function stopLoadingHints() {
  if (loadingTimer) { clearInterval(loadingTimer); loadingTimer = null; }
  loadingHint.value = "";
}

// nextComicUrl: 下一幕的叙事图，loading 时做背景图（后端未来会给"本幕对应的叙事补充图"，届时替换）
const props = defineProps<{ scene: Scene; storyId: string; nextComicUrl?: string }>();
const emit = defineEmits<{
  (e: "done", payload: InteractResponse, snap: {
    ops: Operation[];
    custom_props: CustomProp[];
  }): void;
}>();
// 双向绑定 ops，让父组件（StoryPage 右侧对话栏）也能展示 + 删除
const ops = defineModel<Operation[]>("ops", { default: () => [] });

const toast = useToastStore();
const sessions = useSessionStore();
const assetShelf = useAssetShelfStore();
const interactStore = useInteractStore();

interface PlacedItem {
  id: string;          // unique within this scene session
  name: string;
  kind: "character" | "object";
  url?: string;
  custom_url?: string;
  // 0..1 normalized coords
  x: number;
  y: number;
  scale: number;
  rotation: number;
  isCustom?: boolean;
  // 道具 AI 生成中：显示 spinner + 参考图占位
  loading?: boolean;
  refImage?: string;   // 占位期间展示的参考图（上传/画板/拍照的原图）
}

const placed = ref<PlacedItem[]>([]);
const customProps = ref<CustomProp[]>([]);
const generating = ref(false);

// 新造道具：作画中占位（在 aside "✨ 我造的道具" 区域显示 spinner），完成后搬到 customProps
interface PendingProp {
  tempId: string;
  name: string;
  refImage?: string;
}
const pendingProps = ref<PendingProp[]>([]);
// C7: 生成下一幕的二次确认
const confirmingComplete = ref(false);

// 选两个对象做交互
const selA = ref<PlacedItem | null>(null);
const selB = ref<PlacedItem | null>(null);
const actionText = ref("");
const freeformText = ref("");
const newPropName = ref("");

const sessionId = computed(() => {
  // 复用 sessions.list 中最近一次（StoryPage onMount 已 push）；找不到就生成一个
  const latest = sessions.list[0];
  if (latest && latest.story_id === props.storyId) return latest.id;
  return "s_" + Date.now().toString(36);
});

// 预置 placements (从后端读默认布局)；placement 不带 url，从 scene.characters / .props 里按 name 查
function findUrlByName(name: string, kind: "character" | "object"): string | undefined {
  if (kind === "character") {
    return props.scene.characters?.find((c) => c.name === name)?.url;
  }
  return props.scene.props?.find((p) => p.name === name)?.url;
}

async function loadInitialPlacements() {
  // 参考 legacy：初始只放角色 (character)，道具留在侧边栏让用户主动拖
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
  // 如果 placements 里没有角色（极端情况），按 scene.characters 的 default_x/y 铺开
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
  // 先尝试恢复本幕之前的摆放 / ops / customProps（翻页回看 or 重玩都不丢）
  const saved = interactStore.get(props.storyId, props.scene.index);
  if (saved && (saved.placed.length || saved.ops.length || saved.customProps.length)) {
    placed.value = saved.placed.map((p) => ({ ...p }));
    ops.value = saved.ops.map((o) => ({ ...o }));
    customProps.value = saved.customProps.map((c) => ({ ...c }));
  } else {
    void loadInitialPlacements();
  }
  document.addEventListener("keydown", onStageKey);
});
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onStageKey);
});

// 状态变化 → 持久化到 interact store（翻页离开再回来不丢）
watch(
  [placed, ops, customProps],
  () => {
    interactStore.save(props.storyId, props.scene.index, {
      placed: placed.value,
      ops: ops.value,
      customProps: customProps.value,
    });
  },
  { deep: true },
);

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
  dragSource = null;
}

function allowDrop(e: DragEvent) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
}

// ---- Multi-pointer gesture tracking ----
// 每个物体上当前活动的 pointers（pointerId → clientX/Y）
const itemActivePointers = new Map<string, Map<number, { clientX: number; clientY: number }>>();

interface PinchState {
  itemId: string;
  startDist: number;
  startAngle: number;
  startScale: number;
  startRotation: number;
}
let pinch: PinchState | null = null;

// 单指拖移（不在 pinch/corner resize 中时）
let activePointer: { id: string; pointerId: number; offX: number; offY: number } | null = null;

// 角落手柄：拖它同时缩放 + 旋转
interface CornerState {
  itemId: string;
  pointerId: number;
  centerPx: number;   // stage-relative px
  centerPy: number;
  startDist: number;
  startAngle: number;
  startScale: number;
  startRotation: number;
}
let cornerResize: CornerState | null = null;

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
  // 进入 pinch → 清单指移动
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
  // 单指 → drag 移动
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

  // 1. corner resize 优先
  if (cornerResize && cornerResize.pointerId === e.pointerId) {
    const item = placed.value.find((p) => p.id === cornerResize!.itemId);
    if (!item) return;
    const rect = stageRef.value.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const dx = px - cornerResize.centerPx;
    const dy = py - cornerResize.centerPy;
    const dist = Math.hypot(dx, dy);
    const angle = Math.atan2(dy, dx);
    item.scale = clamp(
      cornerResize.startScale * (dist / Math.max(8, cornerResize.startDist)),
      MIN_SCALE, MAX_SCALE,
    );
    item.rotation = wrapDeg(
      cornerResize.startRotation + ((angle - cornerResize.startAngle) * 180) / Math.PI,
    );
    return;
  }

  // 2. pinch（两指）更新
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
      return;
    }
  }

  // 3. 单指拖移
  if (activePointer && activePointer.pointerId === e.pointerId) {
    const rect = stageRef.value.getBoundingClientRect();
    const item = placed.value.find((p) => p.id === activePointer!.id);
    if (!item) return;
    item.x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width - activePointer.offX));
    item.y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height - activePointer.offY));
  }
}

function onStagePointerUp(e?: PointerEvent) {
  if (!e) { activePointer = null; pinch = null; cornerResize = null; itemActivePointers.clear(); return; }
  // 从所有 item maps 里移除这个 pointerId
  for (const map of itemActivePointers.values()) map.delete(e.pointerId);
  if (pinch) {
    const m = itemActivePointers.get(pinch.itemId);
    if (!m || m.size < 2) pinch = null;
  }
  if (cornerResize && cornerResize.pointerId === e.pointerId) cornerResize = null;
  if (activePointer && activePointer.pointerId === e.pointerId) activePointer = null;
}

// 角落手柄：pointerdown 独立处理
function onCornerPointerDown(e: PointerEvent, item: PlacedItem) {
  e.stopPropagation();
  if (!stageRef.value) return;
  (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  const stageRect = stageRef.value.getBoundingClientRect();
  const centerPx = item.x * stageRect.width;
  const centerPy = item.y * stageRect.height;
  const px = e.clientX - stageRect.left;
  const py = e.clientY - stageRect.top;
  const dx = px - centerPx;
  const dy = py - centerPy;
  cornerResize = {
    itemId: item.id,
    pointerId: e.pointerId,
    centerPx, centerPy,
    startDist: Math.hypot(dx, dy),
    startAngle: Math.atan2(dy, dx),
    startScale: item.scale,
    startRotation: item.rotation,
  };
}

// ---- 选两个做 op ----
function selectItem(item: PlacedItem) {
  if (!selA.value)             { selA.value = item; return; }
  if (selA.value.id === item.id){ selA.value = null;  selB.value = null; return; }
  if (!selB.value)             { selB.value = item; return; }
  if (selB.value.id === item.id){ selB.value = null;  return; }
  // 重选 A
  selA.value = item; selB.value = null;
}

function addPairOp() {
  if (!selA.value || !actionText.value.trim()) {
    toast.push("先选两个东西，再写动作", "warn");
    return;
  }
  ops.value.push({
    subject: selA.value.name,
    subject_kind: selA.value.kind,
    target: selB.value?.name,
    target_kind: selB.value?.kind,
    action: actionText.value.trim(),
  });
  actionText.value = "";
  selA.value = null;
  selB.value = null;
}

function addFreeformOp() {
  const t = freeformText.value.trim();
  if (!t) return;
  ops.value.push({ action: t });
  freeformText.value = "";
}

function removePlaced(id: string) {
  placed.value = placed.value.filter((p) => p.id !== id);
  if (selA.value?.id === id) selA.value = null;
  if (selB.value?.id === id) selB.value = null;
}

// ---- 选中后对物体做变换 ----
const MIN_SCALE = 0.3;
const MAX_SCALE = 3.0;
const ROT_STEP = 15;

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

function scaleItem(item: PlacedItem, factor: number) {
  item.scale = clamp(Number((item.scale * factor).toFixed(3)), MIN_SCALE, MAX_SCALE);
}
function rotateItem(item: PlacedItem, deg: number) {
  let r = (item.rotation + deg) % 360;
  if (r > 180) r -= 360;
  if (r < -180) r += 360;
  item.rotation = r;
}
function resetItem(item: PlacedItem) {
  item.scale = 1;
  item.rotation = 0;
}

// 当只有 A 选中（没有 B）时认为在单选编辑态，显示工具条
const editingItem = computed<PlacedItem | null>(() => {
  if (selA.value && !selB.value) return selA.value;
  return null;
});

// 舞台空白处点击 → 取消选中
function onStageBackgroundClick() {
  selA.value = null;
  selB.value = null;
}

// 键盘：Delete 删 / =+缩放 / -缩小 / r/R 旋转
function onStageKey(e: KeyboardEvent) {
  const target = e.target as HTMLElement | null;
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
  const item = editingItem.value;
  if (!item) return;
  switch (e.key) {
    case "Delete":
    case "Backspace":
      removePlaced(item.id);
      e.preventDefault();
      break;
    case "=":
    case "+":
      scaleItem(item, 1.1); e.preventDefault(); break;
    case "-":
    case "_":
      scaleItem(item, 1 / 1.1); e.preventDefault(); break;
    case "r":
      rotateItem(item, ROT_STEP); e.preventDefault(); break;
    case "R":
      rotateItem(item, -ROT_STEP); e.preventDefault(); break;
    case "0":
      resetItem(item); e.preventDefault(); break;
  }
}

// ---- 创建自定义道具 —— 后台生成：占位在 aside 道具栏（不自动上舞台），完成后可手动拖入 ----
async function addCustomProp() {
  const name = newPropName.value.trim();
  if (!name) return;
  newPropName.value = "";
  const tempId = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`;
  pendingProps.value.push({ tempId, name });
  toast.push(`🎨 「${name}」正在后台作画…`, "info");
  try {
    const r = await createProp({
      session_id: sessionId.value,
      scene_idx: props.scene.index,
      name,
    });
    // 完成：从 pendingProps 移除，加入 customProps（aside 展示 + API 发送）+ 写入 assetShelf 持久化
    pendingProps.value = pendingProps.value.filter((p) => p.tempId !== tempId);
    customProps.value.push({ name: r.name, url: r.url });
    assetShelf.addMyAsset({
      name: r.name,
      url: r.url,
      kind: "object",
      origin_story_id: props.storyId,
      origin_scene_idx: props.scene.index,
    });
    toast.push(`✨ 「${r.name}」画好啦，拖到舞台就能用～`, "success");
  } catch (e: any) {
    pendingProps.value = pendingProps.value.filter((p) => p.tempId !== tempId);
    toast.push(`新道具创建失败：${e?.message || e}`, "error");
  }
}

// ---- 完成 → /api/interact ----
// 入口：点"完成"按钮 → 弹确认框；确认后调 doComplete（C7）
function askComplete() {
  if (!ops.value.length) {
    toast.push("先安排至少一个动作", "warn");
    return;
  }
  confirmingComplete.value = true;
}

async function doComplete() {
  confirmingComplete.value = false;
  generating.value = true;
  startLoadingHints();
  try {
    const transforms: Transform[] = placed.value.map((p) => ({
      name: p.name, kind: p.kind, x: p.x, y: p.y, scale: p.scale, rotation: p.rotation,
      custom_url: p.custom_url,
    }));
    const resp = await postInteract({
      story_id: props.storyId,
      session_id: sessionId.value,
      scene_idx: props.scene.index,
      placements: transforms,
      ops: ops.value,
      custom_props: customProps.value,
    });
    emit("done", resp, {
      ops: ops.value.map((o) => ({ ...o })),
      custom_props: customProps.value.map((c) => ({ ...c })),
    });
  } catch (e: any) {
    toast.push(`生成失败：${e.message}`, "error");
  } finally {
    generating.value = false;
    stopLoadingHints();
  }
}

onBeforeUnmount(stopLoadingHints);

// ---- F: 上传 / 拍照 / 画板 作为自定义道具的"参考图" ----
const showSketchPad = ref(false);
const cameraOpen = ref(false);
const cameraStream = ref<MediaStream | null>(null);
const videoEl = ref<HTMLVideoElement | null>(null);

async function onUploadPick(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  (e.target as HTMLInputElement).value = ""; // 允许同名重选
  if (!file) return;
  if (!file.type.startsWith("image/")) { toast.push("请选择图片", "warn"); return; }
  if (file.size > 6 * 1024 * 1024) { toast.push("图片不能超过 6MB", "warn"); return; }
  const fr = new FileReader();
  fr.onload = async () => {
    const dataUrl = String(fr.result || "");
    await addCustomFromImage(dataUrl, file.name.replace(/\.[^.]+$/, "") || "我的图片");
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
  await addCustomFromImage(dataUrl, "拍的照片");
}

async function onSketchDone(dataUrl: string) {
  showSketchPad.value = false;
  await addCustomFromImage(dataUrl, "手绘道具");
}

// 上传/拍照/画板完成 → 先存盘 → 弹 CustomPropCreateModal 让用户填名称/描述 → 再决定 AI 画或直接用
const propModalOpen = ref(false);
const propModalRefUrl = ref("");
const propModalDefaultName = ref("");

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
  // skipAi：直接用原图，瞬间完成；加入 customProps + 持久化 myAssets，不自动上舞台
  if (payload.skipAi) {
    customProps.value.push({ name: payload.name, url: propModalRefUrl.value });
    assetShelf.addMyAsset({
      name: payload.name,
      url: propModalRefUrl.value,
      kind: "object",
      origin_story_id: props.storyId,
      origin_scene_idx: props.scene.index,
    });
    toast.push(`✅ 「${payload.name}」已加到道具库，拖到舞台即可使用`, "success");
    propModalOpen.value = false;
    return;
  }
  // AI 路径：立即关 modal + 占位进 aside，createProp 后台进行，完成后加入 customProps 并持久化
  const tempId = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`;
  const refImage = propModalRefUrl.value;
  const name = payload.name;
  const description = payload.description;
  propModalOpen.value = false;
  pendingProps.value.push({ tempId, name, refImage });
  toast.push(`🎨 「${name}」在后台作画，稍等片刻…`, "info");
  try {
    const r = await createProp({
      session_id: sessionId.value,
      scene_idx: props.scene.index,
      name,
      description: description || undefined,
      reference_image_url: refImage,
      skip_ai: false,
    });
    pendingProps.value = pendingProps.value.filter((p) => p.tempId !== tempId);
    customProps.value.push({ name: r.name, url: r.url });
    assetShelf.addMyAsset({
      name: r.name,
      url: r.url,
      kind: "object",
      origin_story_id: props.storyId,
      origin_scene_idx: props.scene.index,
    });
    toast.push(`✨ 「${r.name}」画好啦，拖到舞台就能用～`, "success");
  } catch (e: any) {
    pendingProps.value = pendingProps.value.filter((p) => p.tempId !== tempId);
    toast.push(`生成失败：${e?.message || e}`, "error");
  }
}

const sidebarChars = computed(() => props.scene.characters || []);
const sidebarProps = computed(() => props.scene.props || []);
</script>

<template>
  <div class="flex-1 flex flex-col relative">
    <!-- 互动目标提示 -->
    <div class="mb-3 text-xs text-ink-soft px-1 flex items-center gap-2 flex-wrap">
      <span class="inline-flex items-center gap-1 bg-gold/15 px-2 py-1 rounded-full border border-gold/30 text-ink">
        🎯 <span class="font-semibold">互动目标：</span><span class="text-ink-soft">{{ scene.interaction_goal || "把场景填满" }}</span>
      </span>
      <span class="hidden md:inline text-ink-mute">把侧边的道具拖进舞台 · 点选两个对象再写"做什么" · 多次安排后点完成</span>
    </div>

    <!-- 生图 loading 覆盖：显示下一幕叙事图原图（无蒙版），前景只叠一张小 loading 卡 -->
    <Transition name="modal">
      <div
        v-if="generating"
        class="absolute inset-0 z-30 rounded-xl overflow-hidden"
      >
        <img
          v-if="nextComicUrl || scene.comic_url"
          :src="nextComicUrl || scene.comic_url"
          class="absolute inset-0 w-full h-full object-cover"
          alt="下一幕预览"
        />
        <div v-else class="absolute inset-0 bg-paper"></div>
        <!-- 前景 loading 小卡（底部居中，不遮挡剧情图） -->
        <div class="absolute left-1/2 bottom-6 -translate-x-1/2 px-5 py-3 bg-white/92 rounded-full shadow-[var(--shadow-card-lg)] border border-paper-edge flex items-center gap-3 fade-in max-w-[90%]">
          <div class="w-6 h-6 border-[3px] border-gold-mute border-t-accent rounded-full animate-spin shrink-0"></div>
          <div class="min-w-0">
            <div class="font-display font-bold text-sm leading-tight">AI 正在作画…</div>
            <div class="text-[11px] text-ink-soft animate-pulse truncate">{{ loadingHint }}</div>
          </div>
        </div>
      </div>
    </Transition>

    <div class="flex-1 grid grid-cols-1 md:grid-cols-[1fr_180px] gap-3 min-h-0">
      <!-- 舞台 -->
      <div
        ref="stageRef"
        class="relative bg-paper rounded-xl overflow-hidden border border-paper-edge select-none"
        @drop="onStageDrop"
        @dragover="allowDrop"
        @pointermove="onStagePointerMove"
        @pointerup="(e) => onStagePointerUp(e)"
        @pointercancel="(e) => onStagePointerUp(e)"
        @pointerleave="() => onStagePointerUp()"
        @click.self="onStageBackgroundClick"
        style="touch-action: none;"
      >
        <img v-if="scene.background_url" :src="scene.background_url" class="absolute inset-0 w-full h-full object-cover pointer-events-none" alt="背景" />

        <!-- 已放置的物体 -->
        <div
          v-for="item in placed"
          :key="item.id"
          class="absolute -translate-x-1/2 -translate-y-1/2 cursor-grab active:cursor-grabbing transition-shadow"
          :class="[
            selA?.id === item.id && 'z-10',
            selB?.id === item.id && 'z-10',
          ]"
          :style="{
            left: `${item.x * 100}%`,
            top: `${item.y * 100}%`,
            width: `${72 * item.scale}px`,
          }"
          @pointerdown="(e) => onItemPointerDown(e, item)"
          @click.stop="selectItem(item)"
        >
          <!-- 选中外框（不随 rotate 翻转）-->
          <div
            v-if="selA?.id === item.id || selB?.id === item.id"
            class="absolute -inset-2 rounded-xl pointer-events-none"
            :class="selA?.id === item.id ? 'ring-[3px] ring-accent shadow-[0_0_16px_rgba(255,122,61,0.4)]' : 'ring-[3px] ring-good shadow-[0_0_16px_rgba(91,191,130,0.4)]'"
          ></div>

          <!-- 本体：旋转只作用到图片 / 标签，不动外框/工具条 -->
          <div :style="{ transform: `rotate(${item.rotation}deg)` }" class="relative">
            <!-- 完成：最终 url -->
            <img v-if="item.url && !item.loading" :src="item.url" :alt="item.name" class="w-full h-auto pointer-events-none drop-shadow-md" />
            <!-- AI 作画中占位 -->
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

          <!-- 右下角落手柄 — 拖动同时缩放 + 旋转（仅单选态） -->
          <button
            v-if="editingItem?.id === item.id"
            class="absolute -right-2 -bottom-2 w-6 h-6 rounded-full bg-accent text-white text-xs grid place-items-center shadow-[0_4px_10px_rgba(255,122,61,0.45)] cursor-nwse-resize hover:bg-accent-deep active:scale-95 transition"
            title="拖动缩放 / 旋转"
            @pointerdown.stop="(e) => onCornerPointerDown(e, item)"
            @click.stop
          >⇲</button>

          <!-- 选中工具条 — 单选（A 且无 B）时显示 -->
          <div
            v-if="editingItem?.id === item.id"
            class="absolute left-1/2 -translate-x-1/2 -top-11 flex gap-0.5 items-center bg-white/95 rounded-full border border-paper-edge shadow-[0_4px_14px_rgba(122,90,54,0.2)] px-1 py-0.5 fade-in"
            @click.stop
          >
            <button class="w-7 h-7 grid place-items-center rounded-full hover:bg-paper-deep" title="缩小" @click="scaleItem(item, 1/1.15)">−</button>
            <button class="w-7 h-7 grid place-items-center rounded-full hover:bg-paper-deep" title="放大" @click="scaleItem(item, 1.15)">+</button>
            <span class="w-px h-4 bg-paper-edge mx-0.5"></span>
            <button class="w-7 h-7 grid place-items-center rounded-full hover:bg-paper-deep" title="逆时针旋转 15°" @click="rotateItem(item, -ROT_STEP)">↺</button>
            <button class="w-7 h-7 grid place-items-center rounded-full hover:bg-paper-deep" title="顺时针旋转 15°" @click="rotateItem(item, ROT_STEP)">↻</button>
            <button class="w-7 h-7 grid place-items-center rounded-full hover:bg-paper-deep text-[11px]" title="复位" @click="resetItem(item)">⟳</button>
            <span class="w-px h-4 bg-paper-edge mx-0.5"></span>
            <button class="w-7 h-7 grid place-items-center rounded-full hover:bg-warn/15 text-warn" title="删除（Del）" @click="removePlaced(item.id)">✕</button>
          </div>
        </div>

        <!-- 选中提示 -->
        <div
          v-if="selA || selB"
          class="absolute top-2 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-white/95 text-xs text-ink-soft shadow pointer-events-none"
        >
          <template v-if="selA && selB">
            已选：<span class="text-accent-deep font-semibold">{{ selA.name }}</span>
            + <span class="text-good font-semibold">{{ selB.name }}</span>
            <span class="ml-2 text-ink-mute">下方写"做什么"</span>
          </template>
          <template v-else-if="selA">
            已选 <span class="text-accent-deep font-semibold">{{ selA.name }}</span>
            <span class="ml-2 text-ink-mute">拖右下 ⇲ 缩放旋转 · 双指捏合 · 再点一个对象可组合动作</span>
          </template>
        </div>
      </div>

      <!-- 侧边：可拖入的角色 / 道具 + 我造的道具（占位） -->
      <aside class="bg-white/60 border border-paper-edge rounded-xl p-3 overflow-y-auto no-scrollbar flex flex-col gap-3 min-h-0">
        <div class="text-xs font-bold text-ink-soft mb-2">👥 角色（拖到舞台）</div>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div
            v-for="c in sidebarChars"
            :key="c.name"
            draggable="true"
            class="bg-paper-deep rounded-lg p-2 grid place-items-center text-center cursor-grab active:cursor-grabbing"
            @dragstart="(e) => onSidebarDragStart(e, c, 'character')"
          >
            <img v-if="c.url" :src="c.url" class="w-12 h-12 object-contain" :alt="c.name" />
            <div class="text-[10px] mt-1 text-ink-soft truncate w-full">{{ c.name }}</div>
          </div>
        </div>
        <div class="text-xs font-bold text-ink-soft mb-2">🎁 道具</div>
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div
            v-for="p in sidebarProps"
            :key="p.name"
            draggable="true"
            class="bg-gold-mute/40 rounded-lg p-2 grid place-items-center text-center cursor-grab active:cursor-grabbing"
            @dragstart="(e) => onSidebarDragStart(e, p, 'object')"
          >
            <img v-if="p.url" :src="p.url" class="w-12 h-12 object-contain" :alt="p.name" />
            <div class="text-[10px] mt-1 text-ink truncate w-full">{{ p.name }}</div>
          </div>
        </div>
        <!-- 动作序列已挪到 StoryPage 右侧对话栏 -->

        <!-- ✨ 我造的道具（当前 session 造的 + 作画中占位） -->
        <div v-if="pendingProps.length || customProps.length" class="border-t border-paper-edge pt-2">
          <div class="text-xs font-bold text-ink-soft mb-2 flex items-center justify-between">
            <span>✨ 我造的道具</span>
            <span v-if="pendingProps.length" class="text-[10px] text-ink-mute font-normal">作画中 {{ pendingProps.length }}</span>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <!-- 已完成：可拖入舞台 -->
            <div
              v-for="cp in customProps"
              :key="cp.url"
              draggable="true"
              class="bg-gold-mute/40 rounded-lg p-1.5 grid place-items-center text-center cursor-grab active:cursor-grabbing relative border border-gold/30"
              :title="`${cp.name} —— 拖到舞台使用`"
              @dragstart="(e) => onSidebarDragStart(e, { name: cp.name, url: cp.url } as any, 'object')"
            >
              <img v-if="cp.url" :src="cp.url" class="w-10 h-10 object-contain" :alt="cp.name" />
              <div class="text-[10px] mt-0.5 text-ink truncate w-full">{{ cp.name }}</div>
            </div>
            <!-- 作画中：spinner 占位 -->
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

        <!-- 创建新道具 -->
        <div class="border-t border-paper-edge pt-2 space-y-2">
          <div class="text-xs font-bold text-ink-soft">✨ 造个新道具</div>
          <!-- AI 生成 -->
          <input
            v-model="newPropName"
            type="text"
            placeholder="AI 画：比如「会发光的画笔」"
            maxlength="16"
            class="w-full px-2 py-1.5 text-xs rounded border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
            @keydown.enter="addCustomProp"
          />
          <button
            class="w-full text-xs px-2 py-1 rounded bg-gradient-to-br from-accent-soft to-accent-deep text-white hover:brightness-110 disabled:opacity-50"
            :disabled="!newPropName.trim()"
            @click="addCustomProp"
          >＋ AI 生成</button>
          <!-- 上传 / 拍照 / 画板 -->
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
              class="flex flex-col items-center justify-center gap-1 text-[11px] px-1 py-2 rounded bg-paper hover:bg-gold-mute border border-paper-edge transition"
              title="摄像头拍照"
              @click="openCamera"
            >
              <span class="text-lg">📷</span>
              <span>拍照</span>
            </button>
            <button
              class="flex flex-col items-center justify-center gap-1 text-[11px] px-1 py-2 rounded bg-paper hover:bg-gold-mute border border-paper-edge transition"
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

    <!-- 操作输入区 —— 通过 Teleport 送到 StoryPage 右侧对话栏（左边免滚动） -->
    <Teleport to="#interact-inputs-slot" defer>
      <div class="space-y-3">
        <div>
          <div class="text-xs font-semibold text-ink-soft mb-1.5">📌 让两个对象做点什么</div>
          <div class="text-[11px] text-ink-mute mb-2 min-h-[14px]">
            {{ selA ? `主语：${selA.name}` : "先点舞台上一个对象作为主语" }}
            {{ selB ? `· 对象：${selB.name}` : (selA ? "（可选：再点一个作为对象）" : "") }}
          </div>
          <div class="flex gap-2">
            <input
              v-model="actionText"
              type="text"
              placeholder="例如：把鲜花送给"
              class="flex-1 px-3 py-2 text-sm rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
              @keydown.enter="addPairOp"
            />
            <button
              class="px-3 py-2 text-sm rounded-lg bg-paper-deep hover:bg-gold-mute disabled:opacity-50"
              :disabled="!selA || !actionText.trim()"
              @click="addPairOp"
            >＋</button>
          </div>
        </div>
        <div class="border-t border-dashed border-paper-edge pt-3">
          <div class="text-xs font-semibold text-ink-soft mb-1.5">💭 自由描述一件场景里发生的事</div>
          <div class="flex gap-2">
            <input
              v-model="freeformText"
              type="text"
              placeholder="例如：天上下起了花瓣雨"
              class="flex-1 px-3 py-2 text-sm rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
              @keydown.enter="addFreeformOp"
            />
            <button
              class="px-3 py-2 text-sm rounded-lg bg-paper-deep hover:bg-gold-mute disabled:opacity-50"
              :disabled="!freeformText.trim()"
              @click="addFreeformOp"
            >＋</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 完成（ops 序列已移到右侧 aside） -->
    <div class="mt-5 flex justify-end gap-2 pt-4 border-t border-dashed border-paper-edge">
      <BaseButton variant="soft" size="sm" pill :disabled="generating || !ops.length" @click="ops = []">清空动作</BaseButton>
      <BaseButton size="sm" pill :disabled="!ops.length || generating" @click="askComplete">
        {{ generating ? "AI 正在画…" : `✨ 完成 (${ops.length}) 并生成下一幕` }}
      </BaseButton>
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
              <button class="w-8 h-8 rounded-full bg-paper-deep hover:bg-gold-mute" @click="closeCamera">✕</button>
            </div>
            <div class="bg-cinema rounded-xl overflow-hidden aspect-video">
              <video ref="videoEl" class="w-full h-full object-contain" playsinline muted></video>
            </div>
            <div class="flex justify-end gap-2 mt-3">
              <BaseButton variant="soft" pill size="sm" @click="closeCamera">取消</BaseButton>
              <BaseButton pill size="sm" @click="snap">📸 拍下</BaseButton>
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

    <!-- 生成下一幕二次确认（C7） -->
    <Teleport to="body">
      <Transition name="modal">
        <div
          v-if="confirmingComplete"
          class="fixed inset-0 z-[70] bg-cinema/70 backdrop-blur-sm grid place-items-center p-4"
          @click.self="confirmingComplete = false"
        >
          <div class="bg-white rounded-2xl p-6 max-w-[440px] w-full shadow-[var(--shadow-card-lg)] fade-in">
            <div class="flex items-start gap-3">
              <div class="text-4xl">✨</div>
              <div class="flex-1">
                <h3 class="font-display font-bold text-lg m-0 mb-1">确认推进到下一幕？</h3>
                <p class="text-sm text-ink-soft m-0">
                  当前的 <span class="text-accent-deep font-semibold">{{ ops.length }}</span> 个动作
                  和所有道具摆放将被锁定，交给 AI 作画。稍后不能再修改这一幕。
                </p>
              </div>
            </div>
            <!-- ops 摘要 -->
            <div v-if="ops.length" class="mt-3 max-h-36 overflow-y-auto no-scrollbar bg-paper rounded-lg p-2 text-[11px] space-y-1">
              <div
                v-for="(o, i) in ops"
                :key="i"
                class="flex gap-1.5"
              >
                <span class="text-accent-deep font-semibold shrink-0">{{ i + 1 }}.</span>
                <span class="text-ink">
                  <template v-if="o.subject && o.target">「{{ o.subject }}」对「{{ o.target }}」：{{ o.action }}</template>
                  <template v-else-if="o.subject">「{{ o.subject }}」：{{ o.action }}</template>
                  <template v-else>{{ o.action }}</template>
                </span>
              </div>
            </div>
            <div class="mt-5 flex justify-end gap-2">
              <BaseButton variant="soft" size="sm" pill @click="confirmingComplete = false">再想想</BaseButton>
              <BaseButton size="sm" pill @click="doComplete">✨ 确认生成</BaseButton>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.modal-enter-active, .modal-leave-active { transition: all 0.25s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; transform: scale(0.98); }
</style>
