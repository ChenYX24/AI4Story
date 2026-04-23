<script setup lang="ts">
import { RouterLink, useRoute, useRouter } from "vue-router";
import BaseButton from "./BaseButton.vue";
import { useUserStore } from "@/stores/user";
import { useToastStore } from "@/stores/toast";
import { computed } from "vue";

const route = useRoute();
const router = useRouter();
const user = useUserStore();
const toast = useToastStore();

const showTimeline = computed(() => route.name === "story");

interface TimelineItem {
  sceneIdx: number;
  type: "narrative" | "interactive";
  visited?: boolean;
  dynamicThumb?: string; // 已生成 dynamic 节点的缩略图（覆盖默认 thumbUrl）
}

const props = defineProps<{
  cursor?: number;
  highestUnlocked?: number;
  flowItems?: TimelineItem[];
}>();
const emit = defineEmits<{
  (e: "jump", idx: number): void;
}>();

function thumbUrl(it: TimelineItem): string {
  if (it.dynamicThumb) return it.dynamicThumb;
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

function onStoreClick() {
  if (route.name === "library") return;
  // 资产商城 MVP：跳到 library 书架页（资产 tab 在 profile 里）；后续会有独立 /store
  toast.push("资产商城即将上线，暂跳转到书架", "info");
  router.push("/library");
}
</script>

<template>
  <header
    class="fixed top-0 left-0 right-0 z-40 h-14 px-4 flex items-center gap-3 bg-white/90 backdrop-blur border-b border-paper-edge"
  >
    <!-- 左：logo 点击回首页 -->
    <RouterLink
      to="/"
      class="shrink-0 font-display text-xl font-extrabold tracking-wider bg-gradient-to-r from-accent-deep to-gold-deep bg-clip-text text-transparent flex items-center gap-2"
    >
      <span class="text-lg">🎞️</span>
      <span>漫秀 MindShow</span>
    </RouterLink>

    <!-- 中：Timeline with scene thumbnails — 仅 story 页显示；其他页占位以保证三段布局稳定 -->
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
        :title="`${it.type === 'narrative' ? '叙事' : '互动'} · 第 ${it.sceneIdx} 幕${i > (highestUnlocked ?? 0) ? ' (未解锁)' : ''}${it.dynamicThumb ? ' · 已玩过' : ''}`"
        @click="onClick(i)"
      >
        <img
          :src="thumbUrl(it)"
          loading="lazy"
          class="w-full h-full object-cover pointer-events-none"
          @error="(ev: any) => (ev.target.style.display = 'none')"
        />
        <!-- 已玩过生成了 dynamic 的标记 -->
        <div
          v-if="it.dynamicThumb && i !== cursor"
          class="absolute inset-0 ring-2 ring-gold/60 rounded-md pointer-events-none"
        ></div>
        <!-- 已看过的标记 -->
        <div
          v-else-if="it.visited && i !== cursor"
          class="absolute inset-0 bg-good/20 grid place-items-center text-[10px] text-ink"
        >✓</div>
        <!-- 互动节点角标 -->
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
