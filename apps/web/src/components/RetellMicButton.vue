<script setup lang="ts">
import { ref } from "vue";
import { useASR } from "@/composables/useASR";

const emit = defineEmits<{
  transcript: [text: string];
  error: [err: Error];
}>();

const asr = useASR();
const showTextFallback = ref(false);
const typedText = ref("");

async function onMicTap() {
  try {
    const text = await asr.listenOnce();
    emit("transcript", text);
  } catch (e: any) {
    // iOS Safari or permission denied — show text fallback
    if (!asr.supported || e?.message?.includes("not allowed")) {
      showTextFallback.value = true;
    }
    emit("error", e instanceof Error ? e : new Error(String(e)));
  }
}

function onSubmitText() {
  const text = typedText.value.trim();
  if (!text) return;
  emit("transcript", text);
  typedText.value = "";
}
</script>

<template>
  <div class="flex flex-col items-center gap-4">
    <!-- Mic button -->
    <button
      v-if="!showTextFallback"
      :disabled="asr.listening.value"
      class="retell-mic-btn"
      :class="{ listening: asr.listening.value }"
      @click="onMicTap"
    >
      <span class="mic-icon text-4xl">🎤</span>
      <span class="mic-label text-sm font-semibold text-ink-soft mt-1">
        {{ asr.listening.value ? "正在听..." : "点我说话" }}
      </span>
    </button>

    <!-- Text input fallback -->
    <div v-else class="w-full max-w-md flex flex-col gap-3">
      <textarea
        v-model="typedText"
        rows="3"
        class="w-full rounded-xl border border-paper-edge bg-paper p-3 text-ink placeholder:text-ink-soft/50 resize-none focus:outline-none focus:ring-2 focus:ring-accent-soft text-base"
        placeholder="在这里输入你想说的话..."
      />
      <button
        class="self-end px-5 py-2 rounded-full bg-gradient-to-br from-accent-soft to-accent-deep text-white font-semibold shadow-card hover:brightness-110 active:scale-[0.98] transition"
        :disabled="!typedText.trim()"
        @click="onSubmitText"
      >
        提交
      </button>
    </div>

    <button
      v-if="!asr.supported && !showTextFallback"
      class="text-sm text-ink-soft underline"
      @click="showTextFallback = true"
    >
      用文字输入
    </button>
  </div>
</template>

<style scoped>
.retell-mic-btn {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border: 3px solid #fbbf24;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 20px rgba(251, 191, 36, 0.25);
}
.retell-mic-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 6px 24px rgba(251, 191, 36, 0.4);
}
.retell-mic-btn:active {
  transform: scale(0.97);
}
.retell-mic-btn.listening {
  background: linear-gradient(135deg, #fca5a5, #f87171);
  border-color: #ef4444;
  animation: mic-pulse 1.2s ease-in-out infinite;
}
.retell-mic-btn:disabled {
  cursor: default;
  opacity: 0.9;
}
@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
  50% { box-shadow: 0 0 0 20px rgba(239, 68, 68, 0); }
}
</style>
