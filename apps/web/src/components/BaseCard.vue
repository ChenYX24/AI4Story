<script setup lang="ts">
defineProps<{
  hover?: boolean;
  glow?: boolean;
}>();
</script>

<template>
  <div
    :class="[
      'rounded-[var(--radius-card)] bg-white border border-paper-edge',
      'shadow-[var(--shadow-card)]',
      hover && 'transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-card-lg)] cursor-pointer',
      glow && 'ring-2 ring-gold/40 bg-gradient-to-br from-white to-gold-mute/40',
    ]"
  >
    <slot />
  </div>
</template>
