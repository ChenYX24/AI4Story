<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router";
import BaseButton from "./BaseButton.vue";
import { useUserStore } from "@/stores/user";
import { computed } from "vue";

const route = useRoute();
const user = useUserStore();

const showTimeline = computed(() => route.name === "story");

interface TimelineItem {
  sceneIdx: number;
  type: "narrative" | "interactive";
  visited?: boolean;
}

const props = defineProps<{
  cursor?: number;
  highestUnlocked?: number;
  flowItems?: TimelineItem[];
}>();
const emit = defineEmits<{
  (e: "home"): void;
  (e: "jump", idx: number): void;
}>();

function thumbUrl(it: TimelineItem): string {
  const pad = String(it.sceneIdx).padStart(3, "0");
  return it.type === "narrative"
    ? `/assets/scenes/${pad}/comic/panel.png`
    : `/assets/scenes/${pad}/background/background.png`;
}

function onClick(i: number) {
  const unlocked = i <= (props.highestUnlocked ?? 0);
  if (!unlocked) return;
  emit("jump", i);
}
</script>

<template>
  <header
    class="sticky top-0 z-30 h-14 px-4 flex items-center gap-3 bg-white/85 backdrop-blur border-b border-paper-edge"
  >
    <button
      v-if="showTimeline"
      class="shrink-0 w-9 h-9 rounded-full bg-paper-deep hover:bg-gold-mute text-ink grid place-items-center transition"
      title="换一个故事"
      @click="emit('home')"
    >🏠</button>

    <RouterLink
      to="/"
      class="shrink-0 font-display text-xl font-extrabold tracking-wider bg-gradient-to-r from-accent-deep to-gold-deep bg-clip-text text-transparent"
    >漫秀 MindShow</RouterLink>

    <!-- Timeline with scene thumbnails -->
    <nav
      v-if="showTimeline && flowItems && flowItems.length > 0"
      class="flex-1 min-w-0 flex items-center justify-center gap-1.5 overflow-x-auto no-scrollbar"
    >
      <button
        v-for="(it, i) in flowItems"
        :key="i"
        class="relative shrink-0 w-11 h-8 rounded-md overflow-hidden transition border-2 bg-paper"
        :class="[
          i === cursor ? 'border-accent shadow-sm scale-110' : 'border-transparent opacity-80 hover:opacity-100',
          i > (highestUnlocked ?? 0) ? 'grayscale cursor-not-allowed opacity-40' : 'cursor-pointer',
        ]"
        :title="`${it.type === 'narrative' ? '叙事' : '互动'} · 第 ${it.sceneIdx} 幕${i > (highestUnlocked ?? 0) ? ' (未解锁)' : ''}`"
        @click="onClick(i)"
      >
        <img
          :src="thumbUrl(it)"
          loading="lazy"
          class="w-full h-full object-cover pointer-events-none"
          @error="(ev: any) => (ev.target.style.display = 'none')"
        />
        <!-- 已看过的标记 -->
        <div
          v-if="it.visited && i !== cursor"
          class="absolute inset-0 bg-good/20 grid place-items-center text-[10px] text-ink"
        >✓</div>
        <!-- 互动节点角标 -->
        <div
          v-if="it.type === 'interactive'"
          class="absolute bottom-0 right-0 px-1 py-0 text-[9px] bg-gold/90 text-ink rounded-tl"
        >🎭</div>
      </button>
    </nav>
    <div v-else class="flex-1" />

    <RouterLink
      v-if="!showTimeline"
      to="/library"
      custom
      v-slot="{ navigate, isActive }"
    >
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
