<script setup lang="ts">
defineProps<{
  variant?: "primary" | "soft" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  pill?: boolean;
}>();
</script>

<template>
  <button
    :disabled="disabled"
    :class="[
      'inline-flex items-center justify-center gap-2 font-semibold transition select-none',
      'disabled:opacity-50 disabled:cursor-not-allowed',
      pill ? 'rounded-full' : 'rounded-xl',
      size === 'sm' ? 'px-3 py-1.5 text-sm' : size === 'lg' ? 'px-6 py-3 text-base' : 'px-4 py-2 text-sm',
      (!variant || variant === 'primary') && 'bg-gradient-to-br from-accent-soft to-accent-deep text-white shadow-card hover:brightness-110 active:scale-[0.98]',
      variant === 'soft' && 'bg-paper-deep text-ink border border-paper-edge hover:bg-gold-mute',
      variant === 'ghost' && 'bg-transparent text-ink-soft hover:text-ink hover:bg-paper-deep/50',
      variant === 'danger' && 'bg-warn/15 text-warn border border-warn/40 hover:bg-warn/25',
    ]"
  >
    <slot />
  </button>
</template>
