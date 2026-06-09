<script setup lang="ts">
// 语音输入实时波形 — 从共享麦克风 AnalyserNode 读时域数据，canvas 居中绘制竖条
import { ref, watch, onBeforeUnmount } from "vue";
import { getMicAnalyser } from "@/composables/useMicLevel";

const props = defineProps<{ active: boolean }>();

const canvas = ref<HTMLCanvasElement | null>(null);
const BARS = 28;
let raf = 0;

function draw() {
  raf = requestAnimationFrame(draw);
  const cv = canvas.value;
  if (!cv) return;
  const ctx = cv.getContext("2d");
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const analyser = getMicAnalyser();
  const gap = 3;
  const bw = (w - gap * (BARS - 1)) / BARS;
  const mid = h / 2;
  const r = bw / 2;

  const buf = analyser ? new Uint8Array(analyser.fftSize) : null;
  if (analyser && buf) analyser.getByteTimeDomainData(buf);
  const step = buf ? Math.floor(buf.length / BARS) : 0;

  for (let i = 0; i < BARS; i++) {
    let amp = 0;
    if (buf && step) {
      let sum = 0;
      for (let j = 0; j < step; j++) { const v = (buf[i * step + j] - 128) / 128; sum += v * v; }
      const rms = Math.sqrt(sum / step);
      // 噪声门限滤掉环境底噪，再用大增益 + 非线性曲线放大，让正常说话音量也清晰可见
      amp = Math.min(1, Math.pow(Math.max(0, rms - 0.004) * 20, 0.6));
    }
    const bh = Math.max(bw, amp * (h - 4)); // 静音时为一个小圆点
    const x = i * (bw + gap);
    const y = mid - bh / 2;
    ctx.fillStyle = `rgba(224, 178, 95, ${0.45 + amp * 0.55})`;
    ctx.beginPath();
    // 圆角竖条
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + bw, y, x + bw, y + bh, r);
    ctx.arcTo(x + bw, y + bh, x, y + bh, r);
    ctx.arcTo(x, y + bh, x, y, r);
    ctx.arcTo(x, y, x + bw, y, r);
    ctx.fill();
  }
}

function stop() {
  if (raf) { cancelAnimationFrame(raf); raf = 0; }
  const cv = canvas.value;
  const ctx = cv?.getContext("2d");
  if (cv && ctx) ctx.clearRect(0, 0, cv.width, cv.height);
}

watch(() => props.active, (a) => {
  if (a) { if (!raf) raf = requestAnimationFrame(draw); }
  else stop();
}, { immediate: true });

onBeforeUnmount(stop);
</script>

<template>
  <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-paper-deep/90 border border-gold/40 shadow-[0_2px_10px_rgba(224,178,95,0.25)]">
    <span class="text-base leading-none animate-pulse">🎙️</span>
    <canvas ref="canvas" class="h-7 w-40"></canvas>
    <span class="text-[11px] text-ink-soft whitespace-nowrap">正在聆听…</span>
  </div>
</template>
