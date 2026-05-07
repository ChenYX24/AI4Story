<script setup lang="ts">
import type { RetellFeedback } from "@/api/types";
import BaseButton from "@/components/BaseButton.vue";

defineProps<{
  feedback: RetellFeedback;
  isLastScene: boolean;
}>();

const emit = defineEmits<{
  retry: [];
  next: [];
}>();
</script>

<template>
  <div class="flex flex-col gap-5">
    <!-- Encouragement -->
    <div class="text-center">
      <div class="text-3xl mb-2">🌟</div>
      <p class="text-xl font-bold text-ink leading-relaxed">
        {{ feedback.encouragement }}
      </p>
    </div>

    <!-- Covered points -->
    <div v-if="feedback.covered_points.length" class="bg-green-50 rounded-2xl p-4">
      <p class="text-sm font-semibold text-green-700 mb-2">✅ 你说对的地方</p>
      <ul class="space-y-1">
        <li
          v-for="(pt, i) in feedback.covered_points"
          :key="i"
          class="text-sm text-green-800 flex items-start gap-2"
        >
          <span class="text-green-500 mt-0.5">•</span>
          {{ pt }}
        </li>
      </ul>
    </div>

    <!-- Suggestion / missed -->
    <div v-if="feedback.suggestion" class="bg-amber-50 rounded-2xl p-4">
      <p class="text-sm font-semibold text-amber-700 mb-1">💡 还可以补充</p>
      <p class="text-sm text-amber-800">{{ feedback.suggestion }}</p>
    </div>

    <!-- Actions -->
    <div class="flex items-center justify-center gap-3 pt-2">
      <BaseButton variant="soft" size="lg" @click="emit('retry')">
        🔄 再说一次
      </BaseButton>
      <BaseButton size="lg" :pill="true" @click="emit('next')">
        {{ isLastScene ? '🏆 看总结' : '▶️ 下一页' }}
      </BaseButton>
    </div>
  </div>
</template>
