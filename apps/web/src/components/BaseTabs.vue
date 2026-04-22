<script setup lang="ts">
defineProps<{
  tabs: Array<{ key: string; label: string; icon?: string }>;
  modelValue: string;
  variant?: "pill" | "underline";
}>();
const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();
</script>

<template>
  <div
    :class="[
      variant === 'underline'
        ? 'flex gap-6 border-b border-paper-edge'
        : 'inline-flex gap-1 p-1 bg-white rounded-full shadow-[var(--shadow-card)]',
    ]"
  >
    <button
      v-for="t in tabs"
      :key="t.key"
      type="button"
      :class="[
        'transition font-medium',
        variant === 'underline'
          ? modelValue === t.key
            ? 'text-accent-deep border-b-2 border-accent py-2'
            : 'text-ink-soft hover:text-ink py-2'
          : modelValue === t.key
          ? 'bg-gradient-to-br from-accent-soft to-accent-deep text-white shadow rounded-full px-4 py-2'
          : 'text-ink-soft hover:text-ink px-4 py-2 rounded-full',
      ]"
      @click="emit('update:modelValue', t.key)"
    >
      <span v-if="t.icon" class="mr-1">{{ t.icon }}</span>{{ t.label }}
    </button>
  </div>
</template>
