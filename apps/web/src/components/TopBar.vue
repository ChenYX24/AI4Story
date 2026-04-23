<script setup lang="ts">
import { RouterLink, useRoute, useRouter } from "vue-router";
import BaseButton from "./BaseButton.vue";
import { useUserStore } from "@/stores/user";
import { useStoryStore } from "@/stores/story";
import { useToastStore } from "@/stores/toast";
import { computed } from "vue";

const route = useRoute();
const router = useRouter();
const user = useUserStore();
const story = useStoryStore();
const toast = useToastStore();

const showTimeline = computed(() => route.name === "story" && story.flow?.length > 0);

interface TimelineItem {
  sceneIdx: number;
  type: "narrative" | "interactive";
  visited?: boolean;
  dynamicThumb?: string;
}

const timelineItems = computed<TimelineItem[]>(() =>
  (story.flow || []).map((f) => {
    const dyn = story.dynamicByScene?.get?.(f.sceneIdx);
    return {
      sceneIdx: f.sceneIdx,
      type: f.type,
      visited: f.visited,
      dynamicThumb: dyn?.payload.thumbnail_url || dyn?.payload.comic_url,
    };
  }),
);

function thumbUrl(it: TimelineItem): string {
  if (it.dynamicThumb) return it.dynamicThumb;
  const pad = String(it.sceneIdx).padStart(3, "0");
  return it.type === "narrative"
    ? `/assets/scenes/${pad}/comic/panel.png`
    : `/assets/scenes/${pad}/background/background.png`;
}

function onJump(i: number) {
  const unlocked = i <= (story.highestUnlocked ?? 0);
  if (!unlocked) return;
  story.requestJump(i);
}

function onStoreClick() {
  if (route.name === "library") return;
  toast.push("资产商城即将上线，暂跳转到书架", "info");
  router.push("/library");
}
</script>

<template>
  <header
    class="fixed top-0 left-0 right-0 z-50 h-14 px-4 flex items-center gap-3 bg-white/90 backdrop-blur border-b border-paper-edge"
  >
    <!-- 左：logo 点击回首页 -->
    <RouterLink
      to="/"
      class="shrink-0 font-display text-xl font-extrabold tracking-wider bg-gradient-to-r from-accent-deep to-gold-deep bg-clip-text text-transparent flex items-center gap-2"
    >
      <span class="text-lg">🎞️</span>
      <span>漫秀 MindShow</span>
    </RouterLink>

    <!-- 中：timeline 缩略条（仅 story 页） -->
    <nav
      v-if="showTimeline"
      class="flex-1 min-w-0 flex items-center justify-center gap-1.5 overflow-x-auto no-scrollbar"
    >
      <button
        v-for="(it, i) in timelineItems"
        :key="i"
        class="relative shrink-0 w-11 h-8 rounded-md overflow-hidden transition border-2 bg-paper"
        :class="[
          i === story.cursor ? 'border-accent shadow-sm scale-110' : 'border-transparent opacity-80 hover:opacity-100',
          i > (story.highestUnlocked ?? 0) ? 'grayscale cursor-not-allowed opacity-40' : 'cursor-pointer',
        ]"
        :title="`${it.type === 'narrative' ? '叙事' : '互动'} · 第 ${it.sceneIdx} 幕${i > (story.highestUnlocked ?? 0) ? ' (未解锁)' : ''}${it.dynamicThumb ? ' · 已玩过' : ''}`"
        @click="onJump(i)"
      >
        <img
          :src="thumbUrl(it)"
          loading="lazy"
          class="w-full h-full object-cover pointer-events-none"
          @error="(ev: any) => (ev.target.style.display = 'none')"
        />
        <div
          v-if="it.dynamicThumb && i !== story.cursor"
          class="absolute inset-0 ring-2 ring-gold/60 rounded-md pointer-events-none"
        ></div>
        <div
          v-else-if="it.visited && i !== story.cursor"
          class="absolute inset-0 bg-good/20 grid place-items-center text-[10px] text-ink"
        >✓</div>
        <div
          v-if="it.type === 'interactive' && !it.dynamicThumb"
          class="absolute bottom-0 right-0 px-1 py-0 text-[9px] bg-gold/90 text-ink rounded-tl"
        >🎭</div>
      </button>
    </nav>
    <div v-else class="flex-1" />

    <!-- 右：资产商城 + 书架 + 我的 -->
    <nav class="flex items-center gap-1 sm:gap-2 shrink-0">
      <BaseButton
        variant="ghost"
        size="sm"
        pill
        title="资产商城（即将上线）"
        @click="onStoreClick"
      >
        <span class="text-base">🛒</span>
        <span class="hidden sm:inline ml-1">资产商城</span>
      </BaseButton>

      <RouterLink to="/library" custom v-slot="{ navigate, isActive }">
        <BaseButton variant="ghost" size="sm" pill @click="navigate">
          <span :class="isActive ? 'text-accent-deep' : ''">
            <span class="text-base">📚</span>
            <span class="hidden sm:inline ml-1">书架</span>
          </span>
        </BaseButton>
      </RouterLink>

      <RouterLink to="/profile" custom v-slot="{ navigate, isActive }">
        <BaseButton variant="soft" size="sm" pill @click="navigate">
          <span :class="isActive ? 'text-accent-deep' : ''">
            <span class="text-base">👤</span>
            <span class="hidden sm:inline ml-1">{{ user.isAuthed ? user.user?.nickname : "我的" }}</span>
          </span>
        </BaseButton>
      </RouterLink>
    </nav>
  </header>
</template>
