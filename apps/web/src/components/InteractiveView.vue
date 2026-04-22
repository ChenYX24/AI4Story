<script setup lang="ts">
// 互动场景：拖拽角色/道具到背景 → 选两个 + 输入动作 → 加入 ops 序列 → 完成 → /api/interact
// 保留与 web-legacy/js/interactive_view.js 一致的 contract，但用 Pointer Events + Vue reactivity 重写
import { computed, onMounted, ref } from "vue";
import { useToastStore } from "@/stores/toast";
import { useSessionStore } from "@/stores/session";
import { fetchPlacements, postInteract, createProp } from "@/api/endpoints";
import type {
  Scene, SceneCharacter, SceneProp,
  Transform, Operation, CustomProp,
  InteractResponse,
} from "@/api/types";
import BaseButton from "./BaseButton.vue";

const props = defineProps<{ scene: Scene; storyId: string; }>();
const emit = defineEmits<{
  (e: "done", payload: InteractResponse, snap: {
    ops: Operation[];
    custom_props: CustomProp[];
  }): void;
}>();

const toast = useToastStore();
const sessions = useSessionStore();

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
}

const placed = ref<PlacedItem[]>([]);
const ops = ref<Operation[]>([]);
const customProps = ref<CustomProp[]>([]);
const generating = ref(false);

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
  try {
    const r = await fetchPlacements(props.storyId, props.scene.index);
    for (const p of r.placements) {
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
  } catch { /* 没有初始 placements 也 OK */ }
}

onMounted(loadInitialPlacements);

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

// ---- Drag-to-move on stage ----
let activePointer: { id: string; offX: number; offY: number } | null = null;

function onItemPointerDown(e: PointerEvent, item: PlacedItem) {
  if (!stageRef.value) return;
  (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  const rect = stageRef.value.getBoundingClientRect();
  activePointer = {
    id: item.id,
    offX: (e.clientX - rect.left) / rect.width - item.x,
    offY: (e.clientY - rect.top) / rect.height - item.y,
  };
}
function onStagePointerMove(e: PointerEvent) {
  if (!activePointer || !stageRef.value) return;
  const rect = stageRef.value.getBoundingClientRect();
  const item = placed.value.find((p) => p.id === activePointer!.id);
  if (!item) return;
  item.x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width  - activePointer.offX));
  item.y = Math.max(0, Math.min(1, (e.clientY - rect.top)  / rect.height - activePointer.offY));
}
function onStagePointerUp() { activePointer = null; }

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

function removeOp(i: number) { ops.value.splice(i, 1); }
function removePlaced(id: string) {
  placed.value = placed.value.filter((p) => p.id !== id);
  if (selA.value?.id === id) selA.value = null;
  if (selB.value?.id === id) selB.value = null;
}

// ---- 创建自定义道具 ----
async function addCustomProp() {
  const name = newPropName.value.trim();
  if (!name) return;
  newPropName.value = "";
  try {
    const r = await createProp({
      session_id: sessionId.value,
      scene_idx: props.scene.index,
      name,
    });
    customProps.value.push({ name: r.name, url: r.url });
    placed.value.push({
      id: `custom-${r.name}-${Date.now()}`,
      name: r.name,
      kind: "object",
      url: r.url,
      custom_url: r.url,
      x: 0.5, y: 0.5,
      scale: 1, rotation: 0,
      isCustom: true,
    });
    toast.push(`✨ 「${r.name}」造好啦`, "success");
  } catch (e: any) {
    toast.push(`新道具创建失败：${e.message}`, "error");
  }
}

// ---- 完成 → /api/interact ----
async function complete() {
  if (!ops.value.length) {
    toast.push("先安排至少一个动作", "warn");
    return;
  }
  generating.value = true;
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
  }
}

const sidebarChars = computed(() => props.scene.characters || []);
const sidebarProps = computed(() => props.scene.props || []);
</script>

<template>
  <div class="flex-1 flex flex-col">
    <!-- 互动目标提示 -->
    <div class="mb-3 text-xs text-ink-soft px-1">
      🎯 把角色和道具拖到背景里，点选两个对象再说一句"做什么"，多次安排后点完成
    </div>

    <div class="flex-1 grid grid-cols-1 md:grid-cols-[1fr_180px] gap-3 min-h-[420px]">
      <!-- 舞台 -->
      <div
        ref="stageRef"
        class="relative bg-paper rounded-xl overflow-hidden border border-paper-edge select-none"
        @drop="onStageDrop"
        @dragover="allowDrop"
        @pointermove="onStagePointerMove"
        @pointerup="onStagePointerUp"
        @pointerleave="onStagePointerUp"
        style="touch-action: none;"
      >
        <img v-if="scene.background_url" :src="scene.background_url" class="absolute inset-0 w-full h-full object-cover pointer-events-none" alt="背景" />

        <!-- 已放置的物体 -->
        <div
          v-for="item in placed"
          :key="item.id"
          class="absolute -translate-x-1/2 -translate-y-1/2 cursor-grab active:cursor-grabbing"
          :class="[
            selA?.id === item.id && 'ring-4 ring-accent rounded-full',
            selB?.id === item.id && 'ring-4 ring-good rounded-full',
          ]"
          :style="{
            left: `${item.x * 100}%`,
            top: `${item.y * 100}%`,
            width: `${72 * item.scale}px`,
            transform: `translate(-50%, -50%) rotate(${item.rotation}deg)`,
          }"
          @pointerdown="(e) => onItemPointerDown(e, item)"
          @click.stop="selectItem(item)"
        >
          <img v-if="item.url" :src="item.url" :alt="item.name" class="w-full h-auto pointer-events-none drop-shadow-md" />
          <div v-else class="w-full aspect-square grid place-items-center text-3xl bg-white/80 rounded-full">
            {{ item.kind === "character" ? "🧑" : "🎁" }}
          </div>
          <div class="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-warn/90 text-white grid place-items-center text-xs opacity-0 group-hover:opacity-100 hover:opacity-100 cursor-pointer"
            @click.stop="removePlaced(item.id)"
          >×</div>
          <div class="text-[10px] text-center text-ink-soft mt-0.5 px-1 bg-white/70 rounded">{{ item.name }}</div>
        </div>

        <!-- 选中提示 -->
        <div
          v-if="selA || selB"
          class="absolute top-2 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-white/90 text-xs text-ink-soft shadow"
        >
          已选：
          <span v-if="selA" class="text-accent-deep font-semibold">{{ selA.name }}</span>
          <span v-if="selB"> + <span class="text-good font-semibold">{{ selB.name }}</span></span>
        </div>
      </div>

      <!-- 侧边：可拖入的角色 / 道具 -->
      <aside class="bg-white/60 border border-paper-edge rounded-xl p-3 max-h-[440px] overflow-y-auto no-scrollbar">
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
        <!-- 创建新道具 -->
        <div class="border-t border-paper-edge pt-2">
          <div class="text-xs font-bold text-ink-soft mb-1">✨ 造个新道具</div>
          <input
            v-model="newPropName"
            type="text"
            placeholder="比如：会发光的画笔"
            maxlength="16"
            class="w-full px-2 py-1.5 text-xs rounded border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
            @keydown.enter="addCustomProp"
          />
          <button
            class="mt-1 w-full text-xs px-2 py-1 rounded bg-gradient-to-br from-accent-soft to-accent-deep text-white hover:brightness-110 disabled:opacity-50"
            :disabled="!newPropName.trim()"
            @click="addCustomProp"
          >＋ 创建</button>
        </div>
      </aside>
    </div>

    <!-- 操作输入区 -->
    <div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
      <div class="bg-white/70 border border-paper-edge rounded-xl p-3">
        <div class="text-xs font-semibold text-ink-soft mb-2">📌 让两个对象做点什么</div>
        <div class="text-xs text-ink-mute mb-2">
          {{ selA ? `主语：${selA.name}` : "先点一个对象作为主语" }}
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
      <div class="bg-white/70 border border-paper-edge rounded-xl p-3">
        <div class="text-xs font-semibold text-ink-soft mb-2">💭 自由描述一件场景里发生的事</div>
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

    <!-- ops 序列 -->
    <div v-if="ops.length" class="mt-3 flex flex-wrap gap-2">
      <div
        v-for="(o, i) in ops"
        :key="i"
        class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent/10 text-ink text-xs border border-accent/30"
      >
        <span class="font-semibold text-accent-deep">{{ i + 1 }}.</span>
        <span>
          <template v-if="o.subject && o.target">让「{{ o.subject }}」对「{{ o.target }}」: {{ o.action }}</template>
          <template v-else-if="o.subject">让「{{ o.subject }}」: {{ o.action }}</template>
          <template v-else>{{ o.action }}</template>
        </span>
        <button class="text-warn hover:text-warn/70" @click="removeOp(i)">×</button>
      </div>
    </div>

    <!-- 完成 -->
    <div class="mt-5 flex justify-end gap-2 pt-4 border-t border-dashed border-paper-edge">
      <BaseButton variant="soft" size="sm" pill :disabled="generating" @click="ops = []">清空动作</BaseButton>
      <BaseButton size="sm" pill :disabled="!ops.length || generating" @click="complete">
        {{ generating ? "AI 正在画…" : `✨ 完成 (${ops.length}) 并生成下一幕` }}
      </BaseButton>
    </div>
  </div>
</template>
