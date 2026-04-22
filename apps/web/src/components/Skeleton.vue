<script setup lang="ts">
defineProps<{
  /** css height like '120px' or 'h-24' class-ready */
  height?: string;
  rounded?: string;
}>();
</script>

<template>
  <div
    class="skeleton relative overflow-hidden bg-paper-deep"
    :class="rounded || 'rounded-xl'"
    :style="height ? { height } : undefined"
  >
    <div class="skeleton-shimmer"></div>
  </div>
</template>

<style scoped>
.skeleton-shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.45) 50%,
    transparent 100%
  );
  animation: shimmer 1.4s linear infinite;
}
@keyframes shimmer {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer { animation: none; opacity: 0.6; }
}
</style>
