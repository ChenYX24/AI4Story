<script setup lang="ts">
// 简易画板 — canvas 2D 指针事件，支持颜色 / 粗细 / 橡皮 / 撤销 / 清空
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import BaseButton from "./BaseButton.vue";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "submit", dataUrl: string): void;
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const color = ref("#3a2515");
const lineWidth = ref(4);
const eraser = ref(false);
const history = ref<ImageData[]>([]);

const COLORS = ["#3a2515", "#e35a1f", "#ffcb63", "#5bbf82", "#4e7fb8", "#e4605b", "#ffffff"];

function getCtx() {
  const c = canvasRef.value;
  if (!c) return null;
  return c.getContext("2d");
}

function initCanvas() {
  const c = canvasRef.value;
  if (!c) return;
  // 逻辑像素 × dpr
  const dpr = window.devicePixelRatio || 1;
  const rect = c.getBoundingClientRect();
  c.width = Math.round(rect.width * dpr);
  c.height = Math.round(rect.height * dpr);
  const ctx = c.getContext("2d");
  if (!ctx) return;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = "#fffaf0";
  ctx.fillRect(0, 0, rect.width, rect.height);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  history.value = [ctx.getImageData(0, 0, c.width, c.height)];
}

watch(() => props.open, (v) => {
  if (v) nextTick(initCanvas);
});

let drawing = false;
function onPointerDown(e: PointerEvent) {
  const c = canvasRef.value; const ctx = getCtx(); if (!c || !ctx) return;
  c.setPointerCapture(e.pointerId);
  drawing = true;
  ctx.strokeStyle = eraser.value ? "#fffaf0" : color.value;
  ctx.lineWidth = eraser.value ? Math.max(lineWidth.value * 3, 12) : lineWidth.value;
  const rect = c.getBoundingClientRect();
  ctx.beginPath();
  ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top);
}
function onPointerMove(e: PointerEvent) {
  if (!drawing) return;
  const c = canvasRef.value; const ctx = getCtx(); if (!c || !ctx) return;
  const rect = c.getBoundingClientRect();
  ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top);
  ctx.stroke();
}
function onPointerUp() {
  if (!drawing) return;
  drawing = false;
  const c = canvasRef.value; const ctx = getCtx(); if (!c || !ctx) return;
  history.value.push(ctx.getImageData(0, 0, c.width, c.height));
  if (history.value.length > 30) history.value.shift();
}

function undo() {
  const c = canvasRef.value; const ctx = getCtx(); if (!c || !ctx) return;
  if (history.value.length <= 1) return;
  history.value.pop();
  const last = history.value[history.value.length - 1];
  if (last) ctx.putImageData(last, 0, 0);
}
function clearAll() {
  const c = canvasRef.value; const ctx = getCtx(); if (!c || !ctx) return;
  const rect = c.getBoundingClientRect();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#fffaf0";
  ctx.fillRect(0, 0, c.width, c.height);
  const dpr = window.devicePixelRatio || 1;
  ctx.scale(dpr, dpr);
  history.value = [ctx.getImageData(0, 0, c.width, c.height)];
  void rect;
}

function submit() {
  const c = canvasRef.value;
  if (!c) return;
  const url = c.toDataURL("image/png");
  emit("submit", url);
}

onBeforeUnmount(() => { history.value = []; });
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        class="fixed inset-0 z-[60] bg-cinema/70 backdrop-blur-sm grid place-items-center p-4"
        @click.self="emit('close')"
      >
        <div class="bg-white rounded-2xl p-4 max-w-[700px] w-full">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-bold">🎨 画个新道具</h3>
            <button class="w-8 h-8 rounded-full bg-paper-deep hover:bg-gold-mute" @click="emit('close')">✕</button>
          </div>

          <!-- 工具条 -->
          <div class="flex items-center gap-2 mb-2 flex-wrap">
            <div class="flex gap-1">
              <button
                v-for="c in COLORS"
                :key="c"
                class="w-7 h-7 rounded-full border-2"
                :class="color === c && !eraser ? 'border-ink scale-110' : 'border-paper-edge'"
                :style="{ background: c }"
                @click="color = c; eraser = false"
              ></button>
            </div>
            <div class="flex items-center gap-1 ml-2">
              <span class="text-xs text-ink-mute">粗细</span>
              <input v-model.number="lineWidth" type="range" min="1" max="14" class="accent-accent" />
              <span class="text-xs w-6 text-ink-soft">{{ lineWidth }}</span>
            </div>
            <button
              class="ml-auto px-3 py-1 text-xs rounded-full transition"
              :class="eraser ? 'bg-gold text-ink' : 'bg-paper-deep text-ink-soft hover:bg-gold-mute'"
              @click="eraser = !eraser"
            >{{ eraser ? '橡皮✓' : '橡皮' }}</button>
            <button class="px-3 py-1 text-xs rounded-full bg-paper-deep text-ink-soft hover:bg-gold-mute" @click="undo">撤销</button>
            <button class="px-3 py-1 text-xs rounded-full bg-paper-deep text-ink-soft hover:bg-gold-mute" @click="clearAll">清空</button>
          </div>

          <!-- 画布 -->
          <canvas
            ref="canvasRef"
            class="w-full aspect-[4/3] border border-paper-edge rounded-xl touch-none select-none cursor-crosshair"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointerleave="onPointerUp"
          ></canvas>

          <div class="flex justify-end gap-2 mt-3">
            <BaseButton variant="soft" pill size="sm" @click="emit('close')">取消</BaseButton>
            <BaseButton pill size="sm" @click="submit">✨ 用这张图</BaseButton>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-enter-active, .modal-leave-active { transition: all 0.25s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; transform: scale(0.98); }
</style>
