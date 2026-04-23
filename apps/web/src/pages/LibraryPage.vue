<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useLocalStorage } from "@vueuse/core";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseModal from "@/components/BaseModal.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import Skeleton from "@/components/Skeleton.vue";
import { useStoryStore } from "@/stores/story";
import { useShelfStore } from "@/stores/shelf";
import { useToastStore } from "@/stores/toast";
import { deleteCustomStory, patchCustomStory } from "@/api/endpoints";
import type { StoryCard } from "@/api/types";

const router = useRouter();
const store = useStoryStore();
const shelf = useShelfStore();
const toast = useToastStore();
const loading = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

// Filter: 全部 / 我的书架 / 我的原创
const filterTabs = [
  { key: "all",     label: "全部", icon: "📚" },
  { key: "shelf",   label: "我的书架", icon: "🔖" },
  { key: "custom",  label: "我的原创", icon: "📘" },
];
const filter = ref<"all" | "shelf" | "custom">("all");

const filteredList = computed(() => {
  if (filter.value === "shelf") return store.list.filter((s) => shelf.has(s.id));
  if (filter.value === "custom") return store.list.filter((s) => s.is_custom);
  return store.list;
});

function toggleShelf(s: StoryCard, e: MouseEvent) {
  e.stopPropagation();
  shelf.toggle(s.id);
  toast.push(shelf.has(s.id) ? `已加到书架` : `已从书架移除`, "success");
}

// 已看过的自定义故事 id — 用来显示红点 new-indicator
const seenIds = useLocalStorage<string[]>("mindshow_seen_stories", []);
const seenSet = computed(() => new Set(seenIds.value));

function markSeen(id: string) {
  if (!seenSet.value.has(id)) seenIds.value = [...seenIds.value, id];
}

// 编辑标题 modal
const editing = ref<StoryCard | null>(null);
const editTitleInput = ref("");
function openEdit(s: StoryCard, e: MouseEvent) {
  e.stopPropagation();
  editing.value = s;
  editTitleInput.value = s.title;
}
async function saveTitle() {
  const s = editing.value;
  if (!s) return;
  const newT = editTitleInput.value.trim();
  if (!newT) { toast.push("标题不能为空", "warn"); return; }
  try {
    await patchCustomStory(s.id, { title: newT });
    const target = store.list.find((x) => x.id === s.id);
    if (target) target.title = newT;
    toast.push("标题已更新", "success");
    editing.value = null;
  } catch (e: any) {
    toast.push(`更新失败：${e.message}`, "error");
  }
}

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
    <div class="max-w-[1100px] mx-auto px-5 py-8 fade-in">
      <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 class="font-display text-2xl sm:text-3xl font-bold m-0">📚 我的书架</h1>
          <p class="text-ink-soft text-sm mt-1">选一本书开始冒险，或者创造一本新的</p>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-ink-mute mr-1">共 {{ filteredList.length }} 个</span>
          <BaseButton variant="soft" size="sm" pill @click="refresh" :disabled="loading">
            {{ loading ? "加载中…" : "🔄 刷新" }}
          </BaseButton>
          <BaseButton size="sm" pill @click="router.push('/')">＋ 创建新故事</BaseButton>
        </div>
      </div>

      <!-- 筛选 tabs -->
      <div class="mb-5">
        <BaseTabs v-model="filter" :tabs="filterTabs" />
      </div>

      <!-- 骨架屏：首次加载（list 还没来 + loading=true） -->
      <div
        v-if="loading && store.list.length === 0"
        class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-5"
      >
        <div v-for="i in 6" :key="i" class="bg-white border border-paper-edge rounded-[var(--radius-card)] overflow-hidden shadow-[var(--shadow-card)]">
          <Skeleton height="144px" rounded="" />
          <div class="p-4 space-y-2">
            <Skeleton height="18px" />
            <Skeleton height="14px" />
            <Skeleton height="14px" />
          </div>
        </div>
      </div>

      <div
        v-else-if="!loading && filteredList.length === 0"
        class="text-center py-20"
      >
        <div class="text-6xl mb-4">📖</div>
        <div class="font-display text-xl sm:text-2xl font-bold text-ink mb-1">
          {{ filter === "shelf" ? "书架空空的" :
             filter === "custom" ? "还没有原创故事" :
             "书架空空的" }}
        </div>
        <div class="text-ink-soft text-sm">
          {{ filter === "shelf" ? "去首页公共平台加几本吧" :
             filter === "custom" ? "回首页写点什么，AI 会帮你生成" :
             "回首页写点什么开始" }}
        </div>
        <div class="mt-5 flex gap-2 justify-center">
          <BaseButton v-if="filter === 'shelf'" variant="soft" pill @click="router.push('/')">去首页发现</BaseButton>
          <BaseButton pill @click="router.push('/')">回首页创建</BaseButton>
        </div>
      </div>

      <div
        v-else
        class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-5"
      >
        <BaseCard
          v-for="story in filteredList"
          :key="story.id"
          :hover="!!story.available"
          class="overflow-hidden relative group"
          @click="pick(story.id, !!story.available, story.status, story.error_message)"
        >
          <div
            class="h-36 grid place-items-center text-6xl relative overflow-hidden"
            :class="!story.cover_url && 'bg-gradient-to-br from-paper-deep to-gold-mute'"
          >
            <img
              v-if="story.cover_url"
              :src="story.cover_url"
              loading="lazy"
              decoding="async"
              class="absolute inset-0 w-full h-full object-cover"
              alt=""
            />
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

            <!-- 编辑标题按钮（仅自定义且可用） -->
            <button
              v-if="story.is_custom && story.available"
              class="absolute top-2 left-2 w-7 h-7 rounded-full bg-white/90 text-ink-soft opacity-0 group-hover:opacity-100 transition grid place-items-center hover:bg-gold-mute"
              title="修改标题"
              @click="(e) => openEdit(story, e)"
            >✎</button>

            <!-- 新故事红点 -->
            <div
              v-if="story.is_custom && story.available && !seenSet.has(story.id)"
              class="absolute top-3 left-3 w-2.5 h-2.5 rounded-full bg-accent shadow"
              style="box-shadow: 0 0 0 3px rgba(255, 122, 61, 0.25);"
              @mouseenter="markSeen(story.id)"
            ></div>

            <!-- 收藏 ☆/★ 切换（右下角）-->
            <button
              v-if="story.available"
              class="absolute bottom-2 right-2 w-8 h-8 rounded-full grid place-items-center transition backdrop-blur text-base"
              :class="shelf.has(story.id)
                ? 'bg-accent text-white shadow-[0_4px_12px_rgba(255,122,61,0.45)]'
                : 'bg-white/90 text-ink-soft hover:bg-gold-mute'"
              :title="shelf.has(story.id) ? '从书架移除' : '加到书架'"
              @click="(e) => toggleShelf(story, e)"
            >{{ shelf.has(story.id) ? "★" : "☆" }}</button>
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

    <!-- 编辑标题 Modal -->
    <BaseModal :open="!!editing" title="修改故事标题" @close="editing = null">
      <input
        v-model="editTitleInput"
        maxlength="32"
        type="text"
        class="w-full px-3 py-2 rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
        @keydown.enter="saveTitle"
      />
      <template #footer>
        <BaseButton variant="soft" pill @click="editing = null">取消</BaseButton>
        <BaseButton pill @click="saveTitle">保存</BaseButton>
      </template>
    </BaseModal>
  </div>
</template>
