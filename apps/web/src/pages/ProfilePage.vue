<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import TopBar from "@/components/TopBar.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import BaseModal from "@/components/BaseModal.vue";
import { useUserStore } from "@/stores/user";
import { useStoryStore } from "@/stores/story";
import { useSessionStore } from "@/stores/session";
import { useShelfStore } from "@/stores/shelf";
import { useToastStore } from "@/stores/toast";

const router = useRouter();
const user = useUserStore();
const store = useStoryStore();
const sess = useSessionStore();
const shelf = useShelfStore();
const toast = useToastStore();

const showLogin = ref(!user.isAuthed);
const authMode = ref<"login" | "register">("login");
const nick = ref("");
const password = ref("");
const authBusy = ref(false);

async function submitAuth() {
  const n = nick.value.trim();
  if (!n) { toast.push("请输入昵称", "warn"); return; }
  if (!password.value || password.value.length < 4) {
    toast.push("密码至少 4 位", "warn"); return;
  }
  authBusy.value = true;
  try {
    if (authMode.value === "login") {
      await user.login(n, password.value);
      toast.push(`欢迎回来，${n}`, "success");
    } else {
      await user.register(n, password.value);
      toast.push(`${n}，账号创建成功 ✨`, "success");
    }
    showLogin.value = false;
    nick.value = ""; password.value = "";
  } catch (e: any) {
    toast.push(e?.message || "失败", "error");
  } finally {
    authBusy.value = false;
  }
}

async function logout() {
  await user.logout();
  showLogin.value = true;
  toast.push("已登出", "info");
}

const tabs = [
  { key: "stories", label: "我的故事", icon: "📖" },
  { key: "sessions", label: "历史会话", icon: "🎮" },
  { key: "assets", label: "资产", icon: "🎨" },
];
const tab = ref("stories");

const assetSubs = [
  { key: "mine", label: "我生成的" },
  { key: "imported", label: "导入的" },
  { key: "official", label: "官方共享库" },
];
const assetSub = ref("mine");

const MOCK_OFFICIAL = [
  { name: "经典童话角色包", cover: "🎭", kind: "人物" },
  { name: "魔法道具 × 20", cover: "🗝️", kind: "道具" },
  { name: "森林 / 城堡 / 海底背景", cover: "🌲", kind: "背景" },
  { name: "节日场景包", cover: "🎉", kind: "场景" },
];

// 真数据：自定义故事 = stories.list 里 is_custom=true；书架 = shelf ids 在 store.list 中的
const myStories = computed(() => store.list.filter((s) => s.is_custom));
const shelfStories = computed(() => store.list.filter((s) => shelf.has(s.id)));
// 历史会话按 story 分组
const sessionsByStory = computed(() => {
  const g: Record<string, typeof sess.list> = {};
  for (const s of sess.list) (g[s.story_title] ??= []).push(s);
  return g;
});

async function onDeleteCustom(id: string, e: MouseEvent) {
  e.stopPropagation();
  if (!confirm("确定删除这个故事吗？")) return;
  try {
    const { deleteCustomStory } = await import("@/api/endpoints");
    await deleteCustomStory(id);
    store.list = store.list.filter((s) => s.id !== id);
    shelf.remove(id);
    toast.push("已删除", "success");
  } catch (e: any) {
    toast.push(`删除失败：${e?.message || e}`, "error");
  }
}

function onRemoveFromShelf(id: string, e: MouseEvent) {
  e.stopPropagation();
  shelf.remove(id);
  toast.push("已从书架移除", "success");
}

function onRemoveSession(id: string, e: MouseEvent) {
  e.stopPropagation();
  if (!confirm("删除这次会话记录？")) return;
  sess.remove(id);
  toast.push("已删除", "success");
}

onMounted(() => {
  if (store.list.length === 0) { void store.loadList().catch(() => {}); }
});

function backHome() { router.push("/"); }
function openStory(id: string) { router.push({ name: "story", params: { id } }); }
function openReport(storyId: string) { router.push({ name: "report", params: { id: storyId } }); }
</script>

<template>
  <div class="min-h-screen">
    <TopBar />

    <div v-if="user.isAuthed" class="max-w-[960px] mx-auto px-5 py-8 fade-in">
      <!-- 用户头部 -->
      <div class="flex items-center gap-4 mb-6 flex-wrap">
        <div
          class="w-16 h-16 rounded-full grid place-items-center text-2xl font-extrabold text-white shadow-card"
          style="background: linear-gradient(135deg, #ffcb63, #ff7a3d);"
        >{{ (user.user?.nickname || "?").slice(0, 1).toUpperCase() }}</div>
        <div class="flex-1 min-w-0">
          <div class="text-xl font-bold">{{ user.user?.nickname }}</div>
          <div class="text-xs text-ink-mute">
            加入于 {{ user.user?.created_at ? new Date(Number(user.user.created_at) * 1000).toLocaleDateString() : "" }}
          </div>
        </div>
        <BaseButton variant="danger" size="sm" pill @click="logout">登出</BaseButton>
      </div>

      <!-- Tabs -->
      <div class="mb-5">
        <BaseTabs v-model="tab" :tabs="tabs" />
      </div>

      <!-- 内容 -->
      <div v-if="tab === 'stories'">
        <!-- 🔖 我的书架 -->
        <section class="mb-6">
          <div class="flex items-center justify-between mb-2">
            <div class="font-bold text-ink flex items-center gap-2">
              <span>🔖 我的书架</span>
              <span class="text-xs text-ink-mute font-normal">{{ shelfStories.length }} 本</span>
            </div>
          </div>
          <template v-if="shelfStories.length === 0">
            <div class="text-center py-10 bg-white rounded-[var(--radius-card)] border border-paper-edge text-sm text-ink-soft">
              书架还是空的 · 去首页公共平台把喜欢的故事 ★ 一下
            </div>
          </template>
          <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
            <BaseCard
              v-for="s in shelfStories"
              :key="s.id"
              hover
              class="overflow-hidden relative group cursor-pointer"
              @click="openStory(s.id)"
            >
              <div
                class="h-28 grid place-items-center text-4xl"
                :class="!s.cover_url && 'bg-gradient-to-br from-paper-deep to-gold-mute'"
              >
                <img v-if="s.cover_url" :src="s.cover_url" loading="lazy" class="w-full h-full object-cover" alt="" />
                <span v-else>{{ s.is_custom ? "📘" : "📖" }}</span>
              </div>
              <div class="p-3">
                <div class="font-semibold text-sm text-ink truncate">{{ s.title }}</div>
                <div class="text-xs text-ink-mute mt-0.5">{{ s.scene_count }} 幕</div>
              </div>
              <button
                class="absolute top-2 right-2 w-7 h-7 rounded-full bg-white/90 text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center"
                title="从书架移除"
                @click="(e) => onRemoveFromShelf(s.id, e)"
              >✕</button>
            </BaseCard>
          </div>
        </section>

        <!-- 📘 我创建的 -->
        <section>
          <div class="font-bold text-ink mb-2 flex items-center gap-2">
            <span>📘 我的原创</span>
            <span class="text-xs text-ink-mute font-normal">{{ myStories.length }} 本</span>
          </div>
          <template v-if="myStories.length === 0">
            <div class="text-center py-10 bg-white rounded-[var(--radius-card)] border border-paper-edge">
              <div class="text-4xl mb-2">✍️</div>
              <div class="font-semibold">还没创建过故事</div>
              <div class="text-xs text-ink-soft mt-1">首页输入一段描述 / 视频 / 手绘开始创作</div>
              <div class="mt-3"><BaseButton pill size="sm" @click="backHome">去首页创作 →</BaseButton></div>
            </div>
          </template>
          <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
            <BaseCard
              v-for="s in myStories"
              :key="s.id"
              hover
              class="overflow-hidden relative group cursor-pointer"
              @click="s.available && openStory(s.id)"
            >
              <div
                class="h-28 grid place-items-center text-4xl"
                :class="!s.cover_url && 'bg-gradient-to-br from-paper-deep to-gold-mute'"
              >
                <img v-if="s.cover_url" :src="s.cover_url" loading="lazy" class="w-full h-full object-cover" alt="" />
                <span v-else>{{ s.status === "generating" ? "⏳" : s.status === "failed" ? "⚠️" : "📘" }}</span>
              </div>
              <div class="p-3">
                <div class="font-semibold text-sm text-ink truncate">{{ s.title }}</div>
                <div class="text-xs text-ink-mute mt-0.5">
                  {{ s.scene_count > 0 ? `${s.scene_count} 幕` : (s.status === "generating" ? "生成中" : "—") }}
                </div>
                <div v-if="s.status === 'generating'" class="mt-1.5 h-1 bg-paper-deep rounded-full overflow-hidden">
                  <div class="h-full bg-gradient-to-r from-accent-soft to-accent-deep" :style="{ width: `${s.progress || 0}%` }"></div>
                </div>
              </div>
              <button
                class="absolute top-2 right-2 w-7 h-7 rounded-full bg-white/90 text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center"
                title="删除"
                @click="(e) => onDeleteCustom(s.id, e)"
              >✕</button>
            </BaseCard>
          </div>
        </section>
      </div>

      <div v-else-if="tab === 'sessions'">
        <template v-if="sess.list.length === 0">
          <div class="text-center py-16 bg-white rounded-[var(--radius-card)] shadow-[var(--shadow-card)] border border-paper-edge">
            <div class="text-5xl mb-3">🎮</div>
            <div class="font-bold text-ink">还没玩过的会话</div>
            <div class="text-sm text-ink-soft mt-1">玩完一遍故事后，这里会按故事归档每次的记录和报告</div>
            <div class="mt-4">
              <BaseButton variant="soft" pill @click="router.push('/library')">去书架选一本 →</BaseButton>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-for="(items, title) in sessionsByStory" :key="title" class="mb-6">
            <div class="flex items-center justify-between mb-2">
              <div class="font-bold text-ink">{{ title }} <span class="text-ink-mute text-sm font-normal">· {{ items.length }} 次</span></div>
            </div>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
              <BaseCard
                v-for="s in items"
                :key="s.id"
                hover
                class="p-4 relative group cursor-pointer"
                @click="s.report_ready ? openReport(s.story_id) : openStory(s.story_id)"
              >
                <div class="flex items-center gap-2 mb-1">
                  <div class="text-2xl">🎬</div>
                  <div class="text-sm font-medium truncate">{{ new Date(s.started_at).toLocaleString() }}</div>
                </div>
                <div class="text-xs" :class="s.report_ready ? 'text-good' : 'text-ink-mute'">
                  {{ s.report_ready ? "✓ 报告已生成 — 点查看" : "进行中 — 点继续" }}
                </div>
                <button
                  class="absolute top-2 right-2 w-6 h-6 rounded-full bg-white/90 text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center text-xs"
                  title="删除会话"
                  @click="(e) => onRemoveSession(s.id, e)"
                >✕</button>
              </BaseCard>
            </div>
          </div>
        </template>
      </div>

      <div v-else>
        <div class="mb-3">
          <BaseTabs v-model="assetSub" :tabs="assetSubs" variant="underline" />
        </div>
        <div class="flex gap-2 flex-wrap mb-4">
          <BaseButton variant="soft" size="sm" pill @click="toast.push('分享码导入：阶段 2 打通真正后端 CRUD 后可用')">
            ＋ 输入分享码导入
          </BaseButton>
          <BaseButton variant="soft" size="sm" pill @click="toast.push('多选打包分享：阶段 2 可用')">
            📦 打包分享（多选）
          </BaseButton>
        </div>
        <div v-if="assetSub === 'official'" class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
          <BaseCard v-for="(a, i) in MOCK_OFFICIAL" :key="i" hover class="overflow-hidden">
            <div class="h-24 grid place-items-center text-4xl bg-gradient-to-br from-gold to-accent-soft">{{ a.cover }}</div>
            <div class="p-3">
              <div class="font-semibold text-ink text-sm">{{ a.name }}</div>
              <div class="text-xs text-ink-mute">{{ a.kind }} · 官方</div>
            </div>
          </BaseCard>
        </div>
        <div v-else class="text-center py-16 bg-white rounded-[var(--radius-card)] shadow-[var(--shadow-card)] border border-paper-edge">
          <div class="text-5xl mb-3">{{ assetSub === 'imported' ? '📥' : '🎨' }}</div>
          <div class="font-bold text-ink">
            {{ assetSub === 'imported' ? '还没有导入的资产' : '还没有生成过资产' }}
          </div>
          <div class="text-sm text-ink-soft mt-1">
            {{ assetSub === 'imported' ? '让朋友给你一个分享码，粘贴后就能导入他们的角色 / 道具' : '每次创作都会自动把新角色和道具存进来' }}
          </div>
        </div>
      </div>
    </div>

    <!-- 登录 / 注册 Modal -->
    <BaseModal :open="showLogin" :title="authMode === 'login' ? '👋 欢迎回来' : '✨ 创建新账号'" @close="router.push('/')">
      <div class="flex gap-1 p-1 rounded-full bg-paper-deep mb-4 text-sm">
        <button
          class="flex-1 py-2 rounded-full transition font-medium"
          :class="authMode === 'login' ? 'bg-white shadow text-accent-deep' : 'text-ink-soft'"
          @click="authMode = 'login'"
        >登录</button>
        <button
          class="flex-1 py-2 rounded-full transition font-medium"
          :class="authMode === 'register' ? 'bg-white shadow text-accent-deep' : 'text-ink-soft'"
          @click="authMode = 'register'"
        >注册</button>
      </div>
      <input
        v-model="nick"
        type="text"
        maxlength="20"
        placeholder="昵称"
        class="w-full px-4 py-3 mb-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
        @keydown.enter="submitAuth"
      />
      <input
        v-model="password"
        type="password"
        maxlength="40"
        placeholder="密码（至少 4 位）"
        class="w-full px-4 py-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
        @keydown.enter="submitAuth"
      />
      <div class="text-xs text-ink-mute mt-2">
        {{ authMode === 'login' ? '后续资产、会话、报告都会记到你的账户下。' : '注册后昵称即账号名，请记住密码。' }}
      </div>
      <template #footer>
        <BaseButton variant="soft" pill @click="router.push('/')">稍后</BaseButton>
        <BaseButton pill :disabled="authBusy" @click="submitAuth">
          {{ authBusy ? "处理中…" : authMode === 'login' ? '登录' : '注册' }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>
