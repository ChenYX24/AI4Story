<script setup lang="ts">
import { RouterLink, useRoute, useRouter } from "vue-router";
import BaseButton from "./BaseButton.vue";
import { useUserStore } from "@/stores/user";
import { useStoryStore } from "@/stores/story";
import { computed } from "vue";

const route = useRoute();
const router = useRouter();
const user = useUserStore();
const story = useStoryStore();

const showTimeline = computed(() => route.name === "story" && story.flow?.length > 0);

interface TimelineItem {
  sceneIdx: number;
  type: "narrative" | "interactive" | "dynamic";
  visited?: boolean;
  dynamicThumb?: string;
  pendingThumb?: string;
  pending?: boolean;
  generated?: boolean;
}

const timelineItems = computed<TimelineItem[]>(() =>
  (story.flow || []).map((f) => {
    const dyn = story.dynamicByScene?.get?.(f.sceneIdx);
    const pending = story.pendingDynamicByScene?.get?.(f.sceneIdx);
    // 只有 dynamic type 的节点才用 dyn 缩略图覆盖；interactive 保留默认 bg，仅金色描边表示已玩过
    const isDynamicNode = f.type === "dynamic";
    return {
      sceneIdx: f.sceneIdx,
      type: f.type,
      visited: f.visited,
      dynamicThumb: isDynamicNode ? (dyn?.payload.thumbnail_url || dyn?.payload.comic_url) : undefined,
      pendingThumb: isDynamicNode ? pending?.previewUrl : undefined,
      pending: isDynamicNode && !!pending && !dyn,
      generated: isDynamicNode && !!dyn,
    };
  }),
);

function thumbUrl(it: TimelineItem): string {
  if (it.pendingThumb) return it.pendingThumb;
  if (it.dynamicThumb) return it.dynamicThumb;
  const storyId = story.current?.id || String(route.params.id || "");
  const cached = story.sceneCache?.get?.(`${storyId}:` + it.sceneIdx);
  if (cached?.comic_url) return cached.comic_url;
  if (cached?.background_url) return cached.background_url;
  if (storyId && storyId !== "little_red_riding_hood") return "";
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
  if (route.name === "store") return;
  router.push("/store");
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
          v-if="thumbUrl(it)"
          :src="thumbUrl(it)"
          loading="lazy"
          class="w-full h-full object-cover pointer-events-none"
          @error="(ev: any) => (ev.target.style.display = 'none')"
        />
        <div v-else class="absolute inset-0 grid place-items-center text-[10px] font-semibold text-ink-mute">
          {{ it.sceneIdx }}
        </div>
        <div
          v-if="it.generated"
          class="absolute inset-0 ring-2 ring-gold/60 rounded-md pointer-events-none"
        ></div>
        <div
          v-if="it.generated"
          class="absolute top-0 left-0 px-1 py-0 text-[9px] bg-accent/95 text-white rounded-br"
        >AI</div>
        <div
          v-if="it.pending"
          class="absolute inset-0 bg-white/45 grid place-items-center pointer-events-none"
        >
          <div class="w-4 h-4 rounded-full border-2 border-gold-mute border-t-accent animate-spin"></div>
        </div>
        <div
          v-else-if="it.visited && i !== story.cursor && !it.generated"
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
