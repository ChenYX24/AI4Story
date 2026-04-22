<script setup lang="ts">
import { useToastStore } from "@/stores/toast";
const toasts = useToastStore();
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-6 right-6 z-50 flex flex-col gap-2 pointer-events-none">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts.list"
          :key="t.id"
          class="pointer-events-auto rounded-xl px-4 py-2.5 shadow-card text-sm font-medium fade-in"
          :class="{
            'bg-paper-deep text-ink border border-paper-edge': t.kind === 'info',
            'bg-good/15 text-ink border border-good/40':       t.kind === 'success',
            'bg-gold/20 text-ink border border-gold/60':       t.kind === 'warn',
            'bg-warn/15 text-warn border border-warn/40':      t.kind === 'error',
          }"
        >{{ t.text }}</div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.25s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(12px); }
</style>
