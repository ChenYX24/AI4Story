<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router";
import BaseButton from "./BaseButton.vue";
import { useUserStore } from "@/stores/user";
import { computed } from "vue";

const route = useRoute();
const user = useUserStore();

const showTimeline = computed(() => route.name === "story");

defineProps<{
  /** 当前激活的时间线节点索引（仅 StoryPage 有用） */
  cursor?: number;
  total?: number;
}>();
const emit = defineEmits<{
  (e: "home"): void;
  (e: "jump", idx: number): void;
}>();
</script>

<template>
  <header
    class="sticky top-0 z-30 h-14 px-4 flex items-center gap-3 bg-white/80 backdrop-blur border-b border-paper-edge"
  >
    <button
      v-if="showTimeline"
      class="w-9 h-9 rounded-full bg-paper-deep hover:bg-gold-mute text-ink grid place-items-center transition"
      title="换一个故事"
      @click="emit('home')"
    >🏠</button>

    <RouterLink to="/" class="font-display text-xl font-extrabold tracking-wider bg-gradient-to-r from-accent-deep to-gold-deep bg-clip-text text-transparent">
      漫秀 MindShow
    </RouterLink>

    <nav v-if="showTimeline && total && total > 0" class="flex-1 flex justify-center gap-1 overflow-x-auto no-scrollbar">
      <button
        v-for="i in total"
        :key="i"
        class="w-7 h-7 text-xs rounded-full transition"
        :class="[
          (i - 1) === cursor
            ? 'bg-accent text-white shadow-sm'
            : (i - 1) < (cursor ?? 0)
            ? 'bg-gold-mute text-ink-soft'
            : 'bg-paper text-ink-mute',
        ]"
        @click="emit('jump', i - 1)"
      >{{ i }}</button>
    </nav>
    <div v-else class="flex-1" />

    <RouterLink v-if="!showTimeline || route.name !== 'story'" to="/library" custom v-slot="{ navigate, isActive }">
      <BaseButton variant="ghost" size="sm" @click="navigate">
        <span :class="isActive ? 'text-accent-deep' : ''">📚 书架</span>
      </BaseButton>
    </RouterLink>

    <RouterLink to="/profile" custom v-slot="{ navigate }">
      <BaseButton variant="soft" size="sm" pill @click="navigate">
        <span>{{ user.isAuthed ? `👤 ${user.user?.nick}` : "👤 我的" }}</span>
      </BaseButton>
    </RouterLink>
  </header>
</template>
