<script setup lang="ts">
// 上传 / 拍照 / 画板 的图拿到后弹这个 Modal：
// 让用户填 名称 + 描述，然后选：
//   ✨ AI 再画一个（Seedream + 参考图提示 + 描述）
//   📌 直接用这张图（不调 AI，保留原图作为道具）
import { ref, watch } from "vue";
import BaseButton from "./BaseButton.vue";

const props = defineProps<{
  open: boolean;
  imageUrl: string;      // 上传/画板/拍照 完成后存盘的 URL（/outputs/... 或绝对）
  defaultName?: string;
}>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "submit", payload: { name: string; description: string; skipAi: boolean }): void;
}>();

const name = ref("");
const description = ref("");
const mode = ref<"ai" | "raw">("ai");
const submitting = ref(false);

watch(() => props.open, (v) => {
  if (v) {
    name.value = props.defaultName || "";
    description.value = "";
    mode.value = "ai";
    submitting.value = false;
  }
});

function submit() {
  const n = name.value.trim();
  if (!n) return;
  submitting.value = true;
  emit("submit", {
    name: n,
    description: description.value.trim(),
    skipAi: mode.value === "raw",
  });
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        class="fixed inset-0 z-[65] bg-cinema/70 backdrop-blur-sm grid place-items-center p-4"
        @click.self="emit('close')"
      >
        <div class="bg-white rounded-2xl p-5 max-w-[540px] w-full shadow-[var(--shadow-card-lg)] fade-in">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-display text-lg font-bold m-0">✨ 把这张图变成道具</h3>
            <button class="w-8 h-8 rounded-full bg-paper-deep hover:bg-gold-mute" @click="emit('close')">✕</button>
          </div>

          <div class="grid md:grid-cols-[180px_1fr] gap-4">
            <!-- 原图预览 -->
            <div class="bg-paper rounded-xl border border-paper-edge grid place-items-center p-3 aspect-square overflow-hidden">
              <img :src="imageUrl" class="max-w-full max-h-full object-contain" alt="参考图" />
            </div>

            <!-- 表单 -->
            <div class="flex flex-col gap-3">
              <div>
                <label class="text-xs font-semibold text-ink-soft">道具名</label>
                <input
                  v-model="name"
                  maxlength="16"
                  placeholder="比如：发光的画笔"
                  class="mt-1 w-full px-3 py-2 rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
                  @keydown.enter.prevent
                />
              </div>
              <div>
                <label class="text-xs font-semibold text-ink-soft">描述（可选）</label>
                <textarea
                  v-model="description"
                  rows="3"
                  placeholder="例如：这是小朋友想象的会发光的画笔，给 AI 补一些细节"
                  class="mt-1 w-full px-3 py-2 rounded-lg border border-paper-edge bg-white resize-y focus:outline-none focus:border-accent-soft"
                ></textarea>
              </div>
              <div>
                <label class="text-xs font-semibold text-ink-soft mb-1 block">怎么用这张图</label>
                <div class="grid grid-cols-2 gap-2">
                  <button
                    class="flex flex-col items-start gap-1 px-3 py-2 rounded-xl border-2 transition text-left"
                    :class="mode === 'ai' ? 'border-accent bg-gold/10' : 'border-paper-edge hover:border-gold'"
                    @click="mode = 'ai'"
                  >
                    <span class="font-semibold">✨ AI 再画一个</span>
                    <span class="text-xs text-ink-soft">Seedream 参考原图 + 描述, 风格统一</span>
                  </button>
                  <button
                    class="flex flex-col items-start gap-1 px-3 py-2 rounded-xl border-2 transition text-left"
                    :class="mode === 'raw' ? 'border-accent bg-gold/10' : 'border-paper-edge hover:border-gold'"
                    @click="mode = 'raw'"
                  >
                    <span class="font-semibold">📌 直接用这张</span>
                    <span class="text-xs text-ink-soft">不调 AI, 保留原图作为道具（省时）</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-end gap-2 mt-4">
            <BaseButton variant="soft" pill size="sm" :disabled="submitting" @click="emit('close')">取消</BaseButton>
            <BaseButton pill size="sm" :disabled="!name.trim() || submitting" @click="submit">
              {{ submitting ? "生成中…" : mode === 'ai' ? "✨ 开始生成" : "📌 用这张" }}
            </BaseButton>
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
