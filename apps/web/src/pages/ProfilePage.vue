<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import BaseCard from "@/components/BaseCard.vue";
import { createPack, fetchPack } from "@/api/endpoints";
import type { PackOut } from "@/api/endpoints";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import BaseModal from "@/components/BaseModal.vue";
import { useUserStore } from "@/stores/user";
import { useStoryStore } from "@/stores/story";
import { useSessionStore } from "@/stores/session";
import { useShelfStore } from "@/stores/shelf";
import { useAssetShelfStore } from "@/stores/assetShelf";
import { useToastStore } from "@/stores/toast";
import { fetchPublicAssets } from "@/api/endpoints";
import type { PublicAsset, PublicAssetBundle } from "@/api/types";

const router = useRouter();
const user = useUserStore();
const store = useStoryStore();
const sess = useSessionStore();
const shelf = useShelfStore();
const assetShelf = useAssetShelfStore();
const toast = useToastStore();

const showLogin = ref(false);
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

void submitAuth;

async function logout() {
  await user.logout();
  toast.push("已登出", "info");
  router.push("/");
}

const tabs = [
  { key: "stories", label: "我的故事", icon: "📖" },
  { key: "sessions", label: "历史会话", icon: "🎮" },
  { key: "assets", label: "资产", icon: "🎨" },
  { key: "growth", label: "成长报告", icon: "📈" },
];
const tab = ref("stories");
const sessionsLoading = ref(false);

async function syncRemoteSessions() {
  if (!user.isAuthed || sessionsLoading.value) return;
  sessionsLoading.value = true;
  try {
    await sess.fetchRemoteSessionsAll();
  } finally {
    sessionsLoading.value = false;
  }
}

watch(tab, (value) => {
  if (value === "sessions") void syncRemoteSessions();
});

const assetSubs = [
  { key: "mine",      label: "我的创作" },
  { key: "favorites", label: "我的收藏" },
  { key: "official",  label: "官方资产库" },
];
const assetSub = ref<"mine" | "favorites" | "official">("mine");

// 真资产数据 — 从 /api/public/assets 拿
const publicAssets = ref<PublicAsset[]>([]);
const publicBundles = ref<PublicAssetBundle[]>([]);
const assetsLoading = ref(false);

async function loadPublicAssets() {
  if (publicAssets.value.length) return;
  assetsLoading.value = true;
  try {
    const r = await fetchPublicAssets();
    publicAssets.value = r.assets;
    publicBundles.value = r.bundles || [];
  } catch (e: any) {
    toast.push(`加载资产失败：${e?.message || e}`, "error");
  } finally {
    assetsLoading.value = false;
  }
}

const assetById = computed(() => {
  const m = new Map<string, PublicAsset>();
  for (const a of publicAssets.value) m.set(a.id, a);
  return m;
});
const bundleById = computed(() => {
  const m = new Map<string, PublicAssetBundle>();
  for (const b of publicBundles.value) m.set(b.id, b);
  return m;
});

const favAssets = computed(() =>
  assetShelf.assetIds.filter((id) => assetById.value.has(id))
    .map((id) => assetById.value.get(id)!),
);
const favBundles = computed(() =>
  assetShelf.bundleIds.filter((id) => bundleById.value.has(id))
    .map((id) => bundleById.value.get(id)!),
);

function onRemoveAssetFav(id: string, e: MouseEvent) {
  e.stopPropagation();
  assetShelf.removeAsset(id);
  toast.push("已取消收藏", "success");
}
function onRemoveBundleFav(id: string, e: MouseEvent) {
  e.stopPropagation();
  assetShelf.removeBundle(id);
  toast.push("已取消收藏", "success");
}
function onToggleAssetFav(id: string, e: MouseEvent) {
  e.stopPropagation();
  assetShelf.toggleAsset(id);
}
function onToggleBundleFav(id: string, e: MouseEvent) {
  e.stopPropagation();
  assetShelf.toggleBundle(id);
}

// 真数据：自定义故事 = stories.list 里 is_custom=true；书架 = shelf ids 在 store.list 中的
const myStories = computed(() => store.list.filter((s) => s.is_custom));
const shelfStories = computed(() => store.list.filter((s) => shelf.has(s.id)));
// 历史会话按 story 分组
// 取该 session 对应的缩略图：进行中 → 最近一张 comic；已完成 → 故事 cover（从 store.list 找）
function storyCover(storyId: string): string | undefined {
  return store.list.find((x) => x.id === storyId)?.cover_url;
}
function sessionThumb(s: { id: string; story_id: string; comic_urls?: string[]; report_comics?: string[] }): string | undefined {
  const ps = sess.getSessionState(s.id);
  if (ps?.comicUrls?.length) return ps.comicUrls[ps.comicUrls.length - 1];
  if (s.report_comics?.length) return s.report_comics[s.report_comics.length - 1];
  if (s.comic_urls?.length) return s.comic_urls[s.comic_urls.length - 1];
  return storyCover(s.story_id);
}
function sessionProgress(sessionId: string): number {
  const ps = sess.getSessionState(sessionId);
  if (!ps || ps.flow.length === 0) return 0;
  const baseFlow = ps.flow.filter((f) => f.type !== "dynamic");
  const baseTotal = baseFlow.length || ps.flow.length;
  const currentBase = ps.flow.slice(0, ps.cursor + 1).filter((f) => f.type !== "dynamic").length || 1;
  return Math.round((currentBase / baseTotal) * 100);
}
function sessionProgressText(sessionId: string): string {
  const ps = sess.getSessionState(sessionId);
  if (!ps || ps.flow.length === 0) return "? / ?";
  const baseFlow = ps.flow.filter((f) => f.type !== "dynamic");
  const baseTotal = baseFlow.length || ps.flow.length;
  const currentBase = ps.flow.slice(0, ps.cursor + 1).filter((f) => f.type !== "dynamic").length || 1;
  return `${currentBase} / ${baseTotal}`;
}
const profileSessions = computed(() => {
  const merged = [...sess.list];
  const known = new Set(merged.map((s) => s.id));
  for (const [sessionId, ps] of Object.entries(sess.playStates || {})) {
    if (known.has(sessionId)) continue;
    if (ps.cursor >= ps.flow.length - 1) continue;
    const story = store.list.find((s) => s.id === ps.story_id);
    merged.push({
      id: sessionId,
      story_id: ps.story_id,
      story_title: ps.story_title || story?.title || ps.story_id,
      started_at: ps.updatedAt,
      report_ready: false,
    });
  }
  return merged.sort((a, b) => Number(Boolean(a.report_ready)) - Number(Boolean(b.report_ready)));
});

// D4/D5 我的资产 —— 多选 + 打包分享 + 分享码导入
const mineSelected = ref<Set<string>>(new Set());
function toggleMineSelect(id: string) {
  const s = new Set(mineSelected.value);
  if (s.has(id)) s.delete(id); else s.add(id);
  mineSelected.value = s;
}
function clearMineSelect() { mineSelected.value = new Set(); }

const shareModalOpen = ref(false);
const sharePackName = ref("");
const sharePackDesc = ref("");
const sharePackPublic = ref(false);
const sharePackBusy = ref(false);
const createdPack = ref<PackOut | null>(null);

function openShareModal() {
  if (!mineSelected.value.size) { toast.push("先选几件要打包的道具", "warn"); return; }
  sharePackName.value = `我的道具包 · ${new Date().toLocaleDateString()}`;
  sharePackDesc.value = "";
  sharePackPublic.value = false;
  createdPack.value = null;
  shareModalOpen.value = true;
}

async function doCreatePack() {
  if (!sharePackName.value.trim()) { toast.push("给包取个名字", "warn"); return; }
  sharePackBusy.value = true;
  try {
    const p = await createPack({
      name: sharePackName.value.trim(),
      description: sharePackDesc.value.trim(),
      asset_ids: Array.from(mineSelected.value),
      public: sharePackPublic.value,
    });
    createdPack.value = p;
    clearMineSelect();
    toast.push(`✨ 分享码 ${p.code} 已生成`, "success");
  } catch (e: any) {
    toast.push(e?.message || "打包失败", "error");
  } finally {
    sharePackBusy.value = false;
  }
}

function copyShareCode() {
  if (!createdPack.value) return;
  const code = createdPack.value.code;
  try {
    navigator.clipboard.writeText(code);
    toast.push(`码 ${code} 已复制`, "success");
  } catch {
    toast.push(`码：${code}`, "info");
  }
}

// 分享码导入（Profile 我的资产页的入口，和 StorePage 独立）
const importCodeInput = ref("");
const importBusy = ref(false);
const importedPackInProfile = ref<PackOut | null>(null);
async function doImportByCode() {
  const code = importCodeInput.value.trim().toUpperCase();
  if (code.length !== 6) { toast.push("分享码是 6 位", "warn"); return; }
  importBusy.value = true;
  try {
    importedPackInProfile.value = await fetchPack(code);
  } catch (e: any) {
    toast.push(e?.message || "找不到这个分享码", "error");
  } finally { importBusy.value = false; }
}
function importPackToMine() {
  if (!importedPackInProfile.value) return;
  let count = 0;
  for (const a of importedPackInProfile.value.assets) {
    if (assetShelf.myAssets.find((m) => m.id === a.id)) continue;
    assetShelf.addMyAsset({
      id: a.id, name: a.name, url: a.url,
      kind: (a.kind as "character" | "object"),
      origin_story_id: a.origin_story_id,
      origin_scene_idx: a.origin_scene_idx,
    });
    count++;
  }
  toast.push(count ? `✨ 导入了 ${count} 件` : "全部已经在我的资产里了", "success");
  importCodeInput.value = "";
  importedPackInProfile.value = null;
}

// E4 成长报告 —— 硬编码 + 轻量启发式（阶段 3 接后端 AI 聚合分析）
const growthKeys = [
  { key: "imagination", label: "\u60f3\u8c61" },
  { key: "expression", label: "\u8868\u8fbe" },
  { key: "logic", label: "\u903b\u8f91" },
  { key: "aesthetic", label: "\u5ba1\u7f8e" },
  { key: "innovation", label: "\u521b\u65b0" },
];
function metricValue(report: any, label: string): number {
  const metrics = report?.parent_section?.metrics || [];
  const found = metrics.find((m: any) => String(m.name || "").includes(label));
  const n = Number(found?.value);
  return Number.isFinite(n) ? Math.max(0, Math.min(100, Math.round(n))) : 60;
}
const completedGrowthReports = computed(() => sess.completedReports);
const latestGrowthReport = computed(() => completedGrowthReports.value[0]?.report_payload || null);
const growthDims = computed(() => {
  const reports = completedGrowthReports.value.map((r) => r.report_payload).filter(Boolean);
  return growthKeys.map((d) => {
    const latest = latestGrowthReport.value ? metricValue(latestGrowthReport.value, d.label) : 0;
    const average = reports.length ? Math.round(reports.reduce((sum, r) => sum + metricValue(r, d.label), 0) / reports.length) : latest;
    return { ...d, latest, average };
  });
});
const growthAdvice = computed(() => {
  if (!latestGrowthReport.value) return "\u5b8c\u6210\u4e00\u6b21\u6545\u4e8b\u4e92\u52a8\u540e\uff0c\u8fd9\u91cc\u4f1a\u5c55\u793a\u6700\u8fd1\u4e00\u6b21\u548c\u5386\u53f2\u5e73\u5747\u7684\u5bf9\u6bd4\u3002";
  const dims = growthDims.value;
  const improved = [...dims].sort((a, b) => (b.latest - b.average) - (a.latest - a.average))[0];
  const focus = [...dims].sort((a, b) => a.latest - b.latest)[0];
  const same = dims.every((d) => d.latest === d.average);
  if (same) return `\u8fd9\u662f\u7b2c\u4e00\u6b21\u5b8c\u6574\u62a5\u544a\uff0c${improved.label}\u76ee\u524d\u8868\u73b0\u6700\u9c9c\u660e\u3002\u540e\u7eed\u591a\u73a9\u51e0\u6b21\u540e\uff0c\u8fd9\u91cc\u4f1a\u663e\u793a\u548c\u5386\u53f2\u5e73\u5747\u7684\u53d8\u5316\u3002`;
  return `\u6700\u8fd1\u4e00\u6b21\u5728\u300c${improved.label}\u300d\u4e0a\u9ad8\u4e8e\u5e73\u5747\uff0c\u8bf4\u660e\u8fd9\u6b21\u4e92\u52a8\u91cc\u6709\u65b0\u7684\u4eae\u70b9\uff1b\u300c${focus.label}\u300d\u53ef\u4ee5\u7ee7\u7eed\u901a\u8fc7\u8bb2\u8ff0\u539f\u56e0\u3001\u8865\u5145\u7ec6\u8282\u548c\u5c1d\u8bd5\u4e0d\u540c\u7ed3\u5c40\u6765\u7ec3\u4e60\u3002`;
});

function hexPoints(radius: number): string[] {
  const pts: string[] = [];
  for (let i = 0; i < growthKeys.length; i++) {
    const a = (Math.PI * 2 * i) / growthKeys.length - Math.PI / 2;
    pts.push(`${(Math.cos(a) * radius).toFixed(1)},${(Math.sin(a) * radius).toFixed(1)}`);
  }
  return pts;
}
function labelPoint(i: number, radius: number): { x: number; y: number } {
  const a = (Math.PI * 2 * i) / growthKeys.length - Math.PI / 2;
  return { x: Math.cos(a) * radius, y: Math.sin(a) * radius + 4 };
}
function radarPoints(which: "latest" | "average" = "latest"): string[] {
  return growthDims.value.map((d, i) => {
    const a = (Math.PI * 2 * i) / growthKeys.length - Math.PI / 2;
    const r = ((which === "latest" ? d.latest : d.average) / 100) * 100;
    return `${(Math.cos(a) * r).toFixed(1)},${(Math.sin(a) * r).toFixed(1)}`;
  });
}

const sessionsByStory = computed(() => {
  const g: Record<string, typeof profileSessions.value> = {};
  for (const s of profileSessions.value) {
    const card = store.list.find((x) => x.id === s.story_id);
    const title = s.story_title && s.story_title !== s.story_id ? s.story_title : (card?.title || s.story_title || s.story_id);
    (g[title] ??= []).push(s);
  }
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
  sess.deleteSession(id);
  toast.push("已删除", "success");
}

onMounted(() => {
  if (store.list.length === 0) { void store.loadList().catch(() => {}); }
  void loadPublicAssets();
  void syncRemoteSessions();
});

function backHome() { router.push("/"); }
function openStory(id: string, sid?: string) {
  router.push({ name: "story", params: { id }, query: sid ? { sid } : {} });
}
function openReport(storyId: string, sid?: string) { router.push({ name: "report", params: { id: storyId }, query: sid ? { sid } : {} }); }
</script>

<template>
  <div class="min-h-screen">

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
        <template v-if="profileSessions.length === 0">
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
            <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
              <BaseCard
                v-for="s in items"
                :key="s.id"
                hover
                class="p-0 relative group cursor-pointer overflow-hidden"
                @click="s.report_ready || s.report_status === 'generating' ? openReport(s.story_id, s.id) : openStory(s.story_id, s.id)"
              >
                <span
                  v-if="sess.hasGeneratedNotice(s.story_id)"
                  class="absolute top-1.5 right-1.5 z-10 w-2.5 h-2.5 rounded-full bg-warn shadow-[0_0_0_2px_white]"
                  title="有新的场景或道具生成"
                ></span>
                <!-- 缩略图（优先 playState 最近 comic，回落故事 cover） -->
                <div class="h-24 bg-gradient-to-br from-paper-deep to-gold-mute grid place-items-center overflow-hidden relative">
                  <img
                    v-if="sessionThumb(s)"
                    :src="sessionThumb(s) || ''"
                    class="absolute inset-0 w-full h-full object-cover"
                    alt=""
                  />
                  <span v-else class="text-4xl">🎬</span>
                  <!-- 状态胶囊 -->
                  <span
                    v-if="s.report_ready"
                    class="absolute top-1.5 right-4 px-2 py-0.5 text-[10px] rounded-full bg-good/90 text-white"
                  >✓ 已完成</span>
                  <span
                    v-else-if="s.report_status === 'generating'"
                    class="absolute top-1.5 right-4 px-2 py-0.5 text-[10px] rounded-full bg-gold/90 text-ink"
                  >生成中</span>
                  <span
                    v-else-if="!!sess.getSessionState(s.id)"
                    class="absolute top-1.5 right-4 px-2 py-0.5 text-[10px] rounded-full bg-accent/90 text-white"
                  >进行中</span>
                </div>
                <div class="p-3">
                  <div class="text-xs text-ink-mute mb-0.5">
                    {{ new Date(s.started_at).toLocaleDateString() }}
                    {{ new Date(s.started_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }}
                  </div>
                  <div v-if="sessionsLoading" class="text-center py-6 text-xs text-ink-mute">正在同步历史会话…</div>
                  <div v-if="!s.report_ready && !!sess.getSessionState(s.id)" class="mt-1">
                    <div class="h-1.5 bg-paper-deep rounded-full overflow-hidden">
                      <div
                        class="h-full bg-gradient-to-r from-accent-soft to-accent-deep transition-all"
                        :style="{ width: sessionProgress(s.id) + '%' }"
                      ></div>
                    </div>
                    <div class="text-[11px] text-ink-mute mt-1">
                      第 {{ sessionProgressText(s.id) }} 页
                    </div>
                  </div>
                  <div v-else-if="s.report_status === 'generating'" class="text-xs text-accent-deep">点击查看生成进度</div>
                  <div v-else-if="s.report_ready" class="text-xs text-good">点击查看报告</div>
                  <div v-else class="text-xs text-ink-mute">点击继续</div>
                </div>
                <button
                  class="absolute top-1.5 left-1.5 w-6 h-6 rounded-full bg-white/90 text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center text-xs"
                  title="删除会话"
                  @click="(e) => onRemoveSession(s.id, e)"
                >✕</button>
                <div
                  class="absolute right-2 bottom-2 max-w-[70%] truncate rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-mono text-ink-mute border border-paper-edge"
                  :title="`会话 ID：${s.id}`"
                >
                  {{ s.id }}
                </div>
              </BaseCard>
            </div>
          </div>
        </template>
      </div>

      <div v-else-if="tab === 'assets'">
        <div class="mb-4 flex items-center justify-between flex-wrap gap-3">
          <BaseTabs v-model="assetSub" :tabs="assetSubs" variant="underline" />
          <div class="text-xs text-ink-mute">
            共 <span class="font-semibold text-ink">{{ assetShelf.total }}</span> 件
          </div>
        </div>

        <!-- Loading skeleton -->
        <div v-if="assetsLoading && publicAssets.length === 0" class="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
          <div v-for="i in 6" :key="i" class="bg-white rounded-[var(--radius-card)] border border-paper-edge p-3">
            <div class="h-24 rounded-lg bg-paper-deep relative overflow-hidden mb-2">
              <div class="absolute inset-0 animate-shimmer"></div>
            </div>
            <div class="h-4 w-2/3 bg-paper-deep rounded relative overflow-hidden">
              <div class="absolute inset-0 animate-shimmer"></div>
            </div>
          </div>
        </div>

        <!-- 我的创作（自创道具 + 多选打包分享 + 分享码导入） -->
        <template v-else-if="assetSub === 'mine'">
          <!-- 工具栏：分享选中 + 分享码导入 -->
          <div class="mb-4 flex items-center gap-3 flex-wrap">
            <BaseButton
              size="sm"
              pill
              :disabled="mineSelected.size === 0"
              @click="openShareModal"
            >📤 打包分享 ({{ mineSelected.size }})</BaseButton>
            <BaseButton
              v-if="mineSelected.size > 0"
              variant="soft"
              size="sm"
              pill
              @click="clearMineSelect"
            >清空选择</BaseButton>
            <div class="flex-1"></div>
            <input
              v-model="importCodeInput"
              type="text"
              maxlength="6"
              placeholder="分享码导入"
              class="px-3 py-1.5 text-sm rounded-lg border border-paper-edge bg-white w-28 font-mono uppercase tracking-wider focus:outline-none focus:border-accent-soft"
              @keydown.enter="doImportByCode"
            />
            <BaseButton size="sm" pill variant="soft" :disabled="importBusy || importCodeInput.length !== 6" @click="doImportByCode">
              {{ importBusy ? "查找…" : "查找" }}
            </BaseButton>
          </div>

          <div v-if="assetShelf.myAssets.length === 0" class="text-center py-16 bg-white rounded-[var(--radius-card)] border border-paper-edge">
            <div class="text-5xl mb-2">🎨</div>
            <div class="font-bold text-ink">还没有自创道具</div>
            <div class="text-sm text-ink-soft mt-1">在互动页"造个新道具"里，AI 画好的 / 上传的道具都会出现在这里</div>
          </div>
          <div v-else>
            <div class="text-sm font-semibold text-ink-soft mb-2">
              ✨ 我画的道具 · {{ assetShelf.myAssets.length }}
              <span v-if="mineSelected.size" class="text-accent-deep font-normal ml-2">已选 {{ mineSelected.size }}</span>
            </div>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3">
              <BaseCard
                v-for="a in assetShelf.myAssets"
                :key="a.id"
                hover
                class="overflow-hidden cursor-pointer relative group border-2"
                :class="mineSelected.has(a.id) ? '!border-accent shadow-[0_0_12px_rgba(255,122,61,0.3)]' : '!border-transparent'"
                @click="toggleMineSelect(a.id)"
              >
                <div class="h-24 grid place-items-center bg-gradient-to-br from-paper to-gold-mute relative">
                  <img :src="a.url" :alt="a.name" loading="lazy" class="max-w-[88%] max-h-[88%] object-contain drop-shadow-sm" />
                  <span
                    v-if="mineSelected.has(a.id)"
                    class="absolute top-1.5 left-1.5 w-6 h-6 grid place-items-center bg-accent text-white rounded-full text-xs shadow"
                  >✓</span>
                </div>
                <div class="p-2.5">
                  <div class="font-semibold text-ink text-sm truncate">{{ a.name }}</div>
                  <div class="text-[11px] text-ink-mute mt-0.5 truncate">
                    {{ a.kind === 'character' ? '人物' : '道具' }} · {{ new Date(a.created_at).toLocaleDateString() }}
                  </div>
                </div>
                <button
                  class="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-white/90 text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center text-xs"
                  title="删除"
                  @click.stop="assetShelf.removeMyAsset(a.id); toast.push('已删除', 'success')"
                >✕</button>
              </BaseCard>
            </div>
          </div>
        </template>

        <!-- 我的收藏 -->
        <template v-else-if="assetSub === 'favorites'">
          <!-- 收藏的 bundle -->
          <div v-if="favBundles.length" class="mb-6">
            <div class="text-sm font-semibold text-ink-soft mb-2">📦 收藏的资产包 · {{ favBundles.length }}</div>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
              <BaseCard
                v-for="b in favBundles"
                :key="b.id"
                hover
                class="overflow-hidden relative group cursor-pointer"
              >
                <div class="h-28 relative grid place-items-center bg-gradient-to-br from-gold to-accent-soft">
                  <img v-if="b.cover_url" :src="b.cover_url" class="max-w-[55%] max-h-[80%] object-contain drop-shadow-md" alt="" />
                  <div v-else class="text-5xl">{{ b.cover_emoji || "📦" }}</div>
                  <div class="absolute bottom-1 right-2 px-2 py-0.5 text-[11px] rounded-full bg-white/90 text-ink font-semibold">
                    × {{ b.item_count }}
                  </div>
                </div>
                <div class="p-3">
                  <div class="font-semibold text-sm truncate">{{ b.name }}</div>
                  <div class="text-xs text-ink-mute line-clamp-1 mt-0.5">{{ b.description }}</div>
                </div>
                <button
                  class="absolute top-2 right-2 w-7 h-7 rounded-full bg-white/90 text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center"
                  title="取消收藏"
                  @click="(e) => onRemoveBundleFav(b.id, e)"
                >✕</button>
              </BaseCard>
            </div>
          </div>

          <!-- 收藏的单件 -->
          <div v-if="favAssets.length">
            <div class="text-sm font-semibold text-ink-soft mb-2">🎭 收藏的单件 · {{ favAssets.length }}</div>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3">
              <BaseCard
                v-for="a in favAssets"
                :key="a.id"
                hover
                class="overflow-hidden relative group cursor-pointer"
              >
                <div class="h-24 grid place-items-center bg-gradient-to-br from-paper-deep to-gold-mute">
                  <img :src="a.url" :alt="a.name" loading="lazy" class="max-w-[78%] max-h-[80%] object-contain drop-shadow-sm" />
                </div>
                <div class="p-2 text-center">
                  <div class="font-semibold text-xs truncate">{{ a.name }}</div>
                  <div class="text-[10px] text-ink-mute">{{ a.kind === 'character' ? '人物' : '道具' }}</div>
                </div>
                <button
                  class="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-white/90 text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center text-xs"
                  title="取消收藏"
                  @click="(e) => onRemoveAssetFav(a.id, e)"
                >✕</button>
              </BaseCard>
            </div>
          </div>

          <!-- 空态 -->
          <div
            v-if="favBundles.length === 0 && favAssets.length === 0"
            class="text-center py-16 bg-white rounded-[var(--radius-card)] shadow-[var(--shadow-card)] border border-paper-edge"
          >
            <div class="text-5xl mb-3">🎨</div>
            <div class="font-bold text-ink">还没有收藏的资产</div>
            <div class="text-sm text-ink-soft mt-1">去首页"公共平台 · 精选资产"里 ☆ 收藏喜欢的角色/道具/资产包</div>
            <div class="mt-4"><BaseButton pill @click="router.push('/')">去公共平台 →</BaseButton></div>
          </div>
        </template>

        <!-- 官方资产库 -->
        <template v-else>
          <!-- 官方 bundles -->
          <div v-if="favBundles.length" class="mb-6">
            <div class="text-sm font-semibold text-ink-soft mb-2">📦 官方资产包</div>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
              <BaseCard
                v-for="b in favBundles"
                :key="b.id"
                hover
                :glow="true"
                class="overflow-hidden relative cursor-pointer"
              >
                <div class="h-28 relative grid place-items-center bg-gradient-to-br from-gold to-accent-soft">
                  <img v-if="b.cover_url" :src="b.cover_url" class="max-w-[55%] max-h-[80%] object-contain drop-shadow-md" alt="" />
                  <div v-else class="text-5xl">{{ b.cover_emoji || "📦" }}</div>
                  <div class="absolute bottom-1 right-2 px-2 py-0.5 text-[11px] rounded-full bg-white/90 text-ink font-semibold">
                    × {{ b.item_count }}
                  </div>
                </div>
                <div class="p-3">
                  <div class="font-semibold text-sm truncate">{{ b.name }}</div>
                  <div class="text-xs text-ink-mute line-clamp-1 mt-0.5">{{ b.description }}</div>
                </div>
                <button
                  class="absolute top-2 right-2 w-7 h-7 rounded-full grid place-items-center transition text-base"
                  :class="assetShelf.hasBundle(b.id)
                    ? 'bg-accent text-white shadow'
                    : 'bg-white/90 text-ink-soft hover:bg-gold-mute'"
                  :title="assetShelf.hasBundle(b.id) ? '取消收藏' : '收藏'"
                  @click="(e) => onToggleBundleFav(b.id, e)"
                >{{ assetShelf.hasBundle(b.id) ? "★" : "☆" }}</button>
              </BaseCard>
            </div>
          </div>

          <!-- 官方单件 -->
          <div>
            <div class="text-sm font-semibold text-ink-soft mb-2">🎭 官方单件</div>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3">
              <BaseCard
                v-for="a in favAssets"
                :key="a.id"
                hover
                class="overflow-hidden relative cursor-pointer"
              >
                <div class="h-24 grid place-items-center bg-gradient-to-br from-paper-deep to-gold-mute">
                  <img :src="a.url" :alt="a.name" loading="lazy" class="max-w-[78%] max-h-[80%] object-contain" />
                </div>
                <div class="p-2 text-center">
                  <div class="font-semibold text-xs truncate">{{ a.name }}</div>
                  <div class="text-[10px] text-ink-mute">{{ a.kind === 'character' ? '人物' : '道具' }}</div>
                </div>
                <button
                  class="absolute top-1.5 right-1.5 w-6 h-6 rounded-full grid place-items-center transition text-xs"
                  :class="assetShelf.hasAsset(a.id)
                    ? 'bg-accent text-white shadow'
                    : 'bg-white/90 text-ink-soft hover:bg-gold-mute'"
                  :title="assetShelf.hasAsset(a.id) ? '取消收藏' : '收藏'"
                  @click="(e) => onToggleAssetFav(a.id, e)"
                >{{ assetShelf.hasAsset(a.id) ? "★" : "☆" }}</button>
              </BaseCard>
            </div>
          </div>
        </template>
      </div>

      <!-- E4 成长报告 Tab —— 维度雷达图（占位实现：基于 sess.list 计算近似值；阶段 3 接后端聚合） -->
      <div v-else-if="tab === 'growth'">
        <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div>
            <div class="font-bold text-ink text-lg">📈 成长报告</div>
            <div class="text-xs text-ink-mute mt-0.5">基于你玩过的 {{ sess.list.length }} 次会话，AI 会分析小朋友在每个维度的表现</div>
          </div>
          <BaseButton variant="soft" size="sm" pill @click="toast.push('深度分析接入后端聚合后可用（阶段 3）', 'info')">
            🔄 立即分析与建议
          </BaseButton>
        </div>
        <BaseCard class="p-6">
          <div class="grid md:grid-cols-[260px_1fr] gap-6 items-center">
            <!-- SVG 六维雷达图 -->
            <div class="grid place-items-center">
              <svg viewBox="-130 -130 260 260" class="w-56 h-56">
                <!-- 背景同心六边形 -->
                <g v-for="(r, i) in [0.25, 0.5, 0.75, 1]" :key="i"
                   :stroke-opacity="i === 3 ? 0.5 : 0.2" stroke="#d59339" fill="none">
                  <polygon :points="hexPoints(100 * r).join(' ')" />
                </g>
                <!-- 轴线 -->
                <g stroke="#d59339" stroke-opacity="0.25">
                  <line v-for="(p, i) in hexPoints(100)" :key="i" :x1="0" :y1="0" :x2="p.split(',')[0]" :y2="p.split(',')[1]" />
                </g>
                <!-- 数据多边形 -->
                <polygon
                  :points="radarPoints('average').join(' ')"
                  fill="rgba(82, 126, 164, 0.18)"
                  stroke="#527ea4"
                  stroke-width="2"
                  stroke-dasharray="4 4"
                />
                <polygon
                  :points="radarPoints('latest').join(' ')"
                  fill="rgba(255, 203, 99, 0.35)"
                  stroke="#e35a1f"
                  stroke-width="2"
                />
                <!-- 维度标签 -->
                <g font-size="11" fill="#7a5f40" text-anchor="middle">
                  <text v-for="(d, i) in growthDims" :key="i"
                        :x="labelPoint(i, 116).x" :y="labelPoint(i, 116).y">{{ d.label }}</text>
                </g>
              </svg>
            </div>
            <!-- 维度列表 + 得分 -->
            <div class="space-y-2">
              <div
                v-for="d in growthDims"
                :key="d.key"
                class="flex items-center gap-3"
              >
                <div class="w-20 text-sm text-ink font-semibold">{{ d.label }}</div>
                <div class="flex-1 h-2 bg-paper-deep rounded-full overflow-hidden">
                  <div class="h-full bg-gradient-to-r from-gold to-accent-deep transition-all"
                       :style="{ width: d.latest + '%' }"></div>
                </div>
                <div class="w-20 text-right text-sm text-ink-soft">{{ d.latest }} / {{ d.average }}</div>
              </div>
            </div>
          </div>
          <div class="mt-6 p-3 bg-paper rounded-lg text-sm text-ink-soft border border-dashed border-paper-edge">
            💡 <span class="font-medium">小建议：</span>{{ growthAdvice }}
          </div>
        </BaseCard>
      </div>
    </div>

    <!-- D4/D5 打包分享 modal -->
    <BaseModal :open="shareModalOpen" :title="createdPack ? '✨ 分享码已生成' : '📤 打包分享道具'" :max-width="'460px'" @close="shareModalOpen = false; createdPack = null">
      <template v-if="!createdPack">
        <p class="text-sm text-ink-soft m-0 mb-3">把你画的 {{ mineSelected.size }} 件道具打包，生成一个 6 位码发给朋友。</p>
        <label class="block mb-3">
          <span class="text-xs text-ink-soft block mb-1">包名</span>
          <input v-model="sharePackName" maxlength="30" type="text"
                 class="w-full px-3 py-2 rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft" />
        </label>
        <label class="block mb-3">
          <span class="text-xs text-ink-soft block mb-1">描述（可选）</span>
          <textarea v-model="sharePackDesc" rows="2" maxlength="120"
                    class="w-full px-3 py-2 rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft resize-y"></textarea>
        </label>
        <label class="flex items-center gap-2 text-sm text-ink-soft">
          <input type="checkbox" v-model="sharePackPublic" class="accent-accent" />
          同时发布到公共资产商城（其他人能看到）
        </label>
      </template>
      <template v-else>
        <div class="text-center py-4">
          <div class="text-ink-soft text-sm mb-1">把这个码发给朋友</div>
          <div class="font-mono text-3xl font-bold text-accent-deep tracking-[0.3em] my-3">{{ createdPack.code }}</div>
          <div class="text-xs text-ink-mute">包含 {{ createdPack.asset_ids.length }} 件道具 · {{ createdPack.public ? '公共可见' : '仅靠码访问' }}</div>
        </div>
      </template>
      <template #footer>
        <template v-if="!createdPack">
          <BaseButton variant="soft" pill @click="shareModalOpen = false">取消</BaseButton>
          <BaseButton pill :disabled="sharePackBusy" @click="doCreatePack">{{ sharePackBusy ? '生成中…' : '生成分享码' }}</BaseButton>
        </template>
        <template v-else>
          <BaseButton variant="soft" pill @click="copyShareCode">📋 复制码</BaseButton>
          <BaseButton pill @click="shareModalOpen = false; createdPack = null">完成</BaseButton>
        </template>
      </template>
    </BaseModal>

    <!-- 分享码导入结果 modal（Profile 我的资产入口） -->
    <BaseModal :open="!!importedPackInProfile" :title="'分享包内容'" :max-width="'480px'" @close="importedPackInProfile = null">
      <template v-if="importedPackInProfile">
        <div class="font-bold text-ink">{{ importedPackInProfile.name }}</div>
        <div class="text-xs text-ink-mute mt-0.5">
          码 <span class="font-mono text-accent-deep">{{ importedPackInProfile.code }}</span>
          · {{ importedPackInProfile.asset_ids.length }} 件
        </div>
        <p v-if="importedPackInProfile.description" class="text-sm text-ink-soft mt-2 mb-2">{{ importedPackInProfile.description }}</p>
        <div class="grid grid-cols-5 gap-2 mt-2">
          <div v-for="a in importedPackInProfile.assets" :key="a.id"
               class="aspect-square rounded-lg bg-paper-deep p-1 grid place-items-center overflow-hidden"
               :title="a.name">
            <img :src="a.url" class="max-w-full max-h-full object-contain" alt="" />
          </div>
        </div>
      </template>
      <template #footer>
        <BaseButton variant="soft" pill @click="importedPackInProfile = null">取消</BaseButton>
        <BaseButton pill @click="importPackToMine">全部加到我的资产 →</BaseButton>
      </template>
    </BaseModal>

  </div>
</template>
