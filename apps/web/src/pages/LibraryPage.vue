<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import TopBar from "@/components/TopBar.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import { useStoryStore } from "@/stores/story";
import { useToastStore } from "@/stores/toast";
import { deleteCustomStory } from "@/api/endpoints";

const router = useRouter();
const store = useStoryStore();
const toast = useToastStore();
const loading = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

async function refresh() {
  loading.value = true;
  try { await store.loadList(); } catch (e: any) { toast.push(`加载失败：${e.message}`, "error"); }
  finally { loading.value = false; }
}

onMounted(async () => {
  await refresh();
  pollTimer = setInterval(() => {
    if (store.list.some((s) => s.status === "generating")) refresh();
  }, 4000);
});
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer); });

function pick(id: string, available: boolean, status?: string, errMsg?: string) {
  if (!available) {
    toast.push(status === "failed" ? (errMsg || "这个故事生成失败了") : "敬请期待", "warn");
    return;
  }
  router.push({ name: "story", params: { id } });
}

async function onDelete(id: string, e: MouseEvent) {
  e.stopPropagation();
  if (!confirm("确定删除这个故事吗？")) return;
  try {
    await deleteCustomStory(id);
    store.list = store.list.filter((s) => s.id !== id);
    toast.push("已删除", "success");
  } catch (e: any) {
    toast.push(`删除失败：${e.message}`, "error");
  }
}
</script>

<template>
  <div>
    <TopBar />
    <div class="max-w-[1100px] mx-auto px-5 py-8 fade-in">
      <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 class="font-display text-2xl sm:text-3xl font-bold m-0">📚 我的书架</h1>
          <p class="text-ink-soft text-sm mt-1">选一本书开始冒险，或者创造一本新的</p>
        </div>
        <div class="flex gap-2">
          <BaseButton variant="soft" size="sm" pill @click="refresh" :disabled="loading">
            {{ loading ? "加载中…" : "🔄 刷新" }}
          </BaseButton>
          <BaseButton size="sm" pill @click="router.push('/')">＋ 创建新故事</BaseButton>
        </div>
      </div>

      <div
        v-if="!loading && store.list.length === 0"
        class="text-center py-16"
      >
        <div class="text-5xl mb-3">📖</div>
        <div class="text-ink-soft">书架是空的 — 回到首页输入一段故事开始吧</div>
        <div class="mt-4">
          <BaseButton pill @click="router.push('/')">回首页创建</BaseButton>
        </div>
      </div>

      <div
        v-else
        class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-5"
      >
        <BaseCard
          v-for="story in store.list"
          :key="story.id"
          :hover="!!story.available"
          class="overflow-hidden relative group"
          @click="pick(story.id, !!story.available, story.status, story.error_message)"
        >
          <div
            class="h-36 grid place-items-center text-6xl relative overflow-hidden"
            :style="story.cover_url ? `background-image:url(${story.cover_url}); background-size:cover; background-position:center;` : ''"
            :class="!story.cover_url && 'bg-gradient-to-br from-paper-deep to-gold-mute'"
          >
            <span v-if="!story.cover_url">
              {{ story.status === "generating" ? "⏳" : story.status === "failed" ? "⚠️" : story.is_custom ? "📘" : "📖" }}
            </span>

            <!-- 标签 -->
            <div
              v-if="story.status === 'generating'"
              class="absolute top-2 right-2 px-2 py-0.5 rounded-full text-[11px] font-medium bg-white/90 text-ink-soft"
            >生成中</div>
            <div
              v-else-if="story.status === 'failed'"
              class="absolute top-2 right-2 px-2 py-0.5 rounded-full text-[11px] font-medium bg-warn/20 text-warn"
            >失败</div>
            <div
              v-else-if="story.is_custom"
              class="absolute top-2 right-2 px-2 py-0.5 rounded-full text-[11px] font-medium bg-gold/90 text-ink"
            >原创</div>

            <!-- 删除按钮（仅失败的自定义故事） -->
            <button
              v-if="story.status === 'failed' && story.is_custom"
              class="absolute top-2 left-2 w-7 h-7 rounded-full bg-white/90 text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center"
              @click="(e) => onDelete(story.id, e)"
            >✕</button>
          </div>
          <div class="p-4">
            <div class="font-bold text-ink leading-snug">{{ story.title }}</div>
            <div class="text-sm text-ink-soft mt-1 line-clamp-2 min-h-[2.5em]">{{ story.summary || "" }}</div>
            <div class="mt-2 text-xs text-ink-mute">
              {{ story.scene_count > 0 ? `${story.scene_count} 幕` : story.status === "generating" ? "后台生成中" : "" }}
            </div>
            <!-- 生成进度条 -->
            <div v-if="story.status === 'generating'" class="mt-2">
              <div class="h-1.5 bg-paper-deep rounded-full overflow-hidden">
                <div class="h-full bg-gradient-to-r from-accent-soft to-accent-deep transition-all" :style="{ width: `${story.progress || 0}%` }"></div>
              </div>
              <div class="text-[11px] text-ink-mute mt-1">{{ story.progress_label || "生成中" }}</div>
            </div>
          </div>
        </BaseCard>
      </div>
    </div>
  </div>
</template>
