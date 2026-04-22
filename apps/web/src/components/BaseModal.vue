<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";

const props = defineProps<{
  open: boolean;
  title?: string;
  maxWidth?: string;
}>();
const emit = defineEmits<{ (e: "close"): void }>();

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape" && props.open) emit("close");
}
onMounted(() => document.addEventListener("keydown", onKey));
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        class="fixed inset-0 z-50 bg-cinema/50 backdrop-blur-sm grid place-items-center px-4"
        @click.self="emit('close')"
      >
        <div
          class="bg-white rounded-[var(--radius-card)] shadow-[var(--shadow-card-lg)] w-full fade-in"
          :style="{ maxWidth: maxWidth || '420px' }"
        >
          <header v-if="title || $slots.header" class="px-5 pt-5 pb-2 flex items-center justify-between">
            <slot name="header">
              <h3 class="text-lg font-bold text-ink m-0">{{ title }}</h3>
            </slot>
            <button
              class="w-8 h-8 rounded-full bg-paper text-ink-soft hover:bg-paper-deep grid place-items-center"
              @click="emit('close')"
            >✕</button>
          </header>
          <div class="px-5 pb-5 pt-2">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="px-5 pb-5 flex justify-end gap-2">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-enter-active, .modal-leave-active { transition: all 0.25s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; transform: scale(0.98); }
</style>
