<script setup lang="ts">
defineProps<{
  total: number;
  current: number;
}>();
</script>

<template>
  <div class="flex items-center justify-center gap-2 py-3">
    <div
      v-for="i in total"
      :key="i"
      class="retell-dot"
      :class="{
        done: i - 1 < current,
        active: i - 1 === current,
        pending: i - 1 > current,
      }"
    >
      <span v-if="i - 1 < current" class="text-xs">✓</span>
      <span v-else class="text-xs">{{ i }}</span>
    </div>
  </div>
</template>

<style scoped>
.retell-dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  transition: all 0.3s ease;
}
.retell-dot.done {
  background: #34d399;
  color: white;
}
.retell-dot.active {
  background: linear-gradient(135deg, #fbbf24, #f59e0b);
  color: white;
  box-shadow: 0 0 12px rgba(251, 191, 36, 0.5);
  transform: scale(1.15);
}
.retell-dot.pending {
  background: #e5e7eb;
  color: #9ca3af;
}
</style>
