<script setup lang="ts">
import type { RetellSummaryResponse } from "@/api/types";
import BaseButton from "@/components/BaseButton.vue";
import BaseCard from "@/components/BaseCard.vue";

defineProps<{
  summary: RetellSummaryResponse;
  storyTitle: string;
}>();

const emit = defineEmits<{
  goLibrary: [];
  restart: [];
}>();

function starChar(idx: number, starCount: number) {
  return idx < starCount ? "⭐" : "☆";
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <!-- Badge + Stars -->
    <div class="text-center">
      <div class="text-5xl mb-3">🏆</div>
      <h2 class="text-2xl font-bold text-ink mb-2">{{ summary.badge }}</h2>
      <div class="text-3xl tracking-wider">
        <span v-for="i in 5" :key="i">{{ starChar(i, summary.star_count) }}</span>
      </div>
      <p class="text-sm text-ink-soft mt-1">
        {{ summary.overall_score }} 分
      </p>
    </div>

    <!-- Encouragement -->
    <BaseCard class="text-center">
      <p class="text-lg font-semibold text-ink leading-relaxed">
        {{ summary.encouragement_summary }}
      </p>
    </BaseCard>

    <!-- Strengths -->
    <BaseCard v-if="summary.strengths.length">
      <h3 class="text-base font-semibold text-green-700 mb-2">🌟 你的优点</h3>
      <ul class="space-y-2">
        <li
          v-for="(s, i) in summary.strengths"
          :key="i"
          class="text-sm text-ink flex items-start gap-2"
        >
          <span class="text-green-500 mt-0.5">✨</span>
          {{ s }}
        </li>
      </ul>
    </BaseCard>

    <!-- Growth areas -->
    <BaseCard v-if="summary.growth_areas.length">
      <h3 class="text-base font-semibold text-amber-700 mb-2">🌱 下次可以试试</h3>
      <ul class="space-y-2">
        <li
          v-for="(g, i) in summary.growth_areas"
          :key="i"
          class="text-sm text-ink flex items-start gap-2"
        >
          <span class="text-amber-500 mt-0.5">💪</span>
          {{ g }}
        </li>
      </ul>
    </BaseCard>

    <!-- Scene-by-scene recap (expandable) -->
    <details v-if="summary.scene_results.length" class="bg-paper-deep rounded-2xl p-4">
      <summary class="text-sm font-semibold text-ink-soft cursor-pointer">
        查看每页详情
      </summary>
      <div class="mt-3 space-y-2">
        <div
          v-for="(r, i) in summary.scene_results"
          :key="i"
          class="flex items-center gap-3 text-sm"
        >
          <span class="w-8 h-8 rounded-full bg-gold-mute flex items-center justify-center text-xs font-semibold">
            {{ r.scene_index }}
          </span>
          <span class="flex-1 text-ink-soft truncate">"{{ r.child_text }}"</span>
          <span class="font-mono text-xs text-ink-soft">{{ r.correctness }}%</span>
        </div>
      </div>
    </details>

    <!-- Actions -->
    <div class="flex items-center justify-center gap-3 pt-2">
      <BaseButton variant="soft" size="lg" @click="emit('goLibrary')">
        📚 返回书架
      </BaseButton>
      <BaseButton size="lg" :pill="true" @click="emit('restart')">
        🔄 再讲一次
      </BaseButton>
    </div>
  </div>
</template>
