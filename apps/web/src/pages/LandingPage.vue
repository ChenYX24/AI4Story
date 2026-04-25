<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import CinemaHero from "@/components/CinemaHero.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import BaseModal from "@/components/BaseModal.vue";
import { useToastStore } from "@/stores/toast";
import { useShelfStore } from "@/stores/shelf";
import { useAssetShelfStore } from "@/stores/assetShelf";
import { useUserStore } from "@/stores/user";
import { useRoute } from "vue-router";
import {
  createCustomStory,
  createStoryFromVideo,
  fetchPublicStories,
  fetchPublicAssets,
  uploadImage,
  bookmarkStory,
  unbookmarkStory,
} from "@/api/endpoints";
import { useStoryStore } from "@/stores/story";
import type { PublicStoryCard, PublicAsset, PublicAssetBundle } from "@/api/types";

const router = useRouter();
const route = useRoute();
const toast = useToastStore();
const shelf = useShelfStore();
const assetShelf = useAssetShelfStore();
const userStore = useUserStore();
const storyStore = useStoryStore();

// 未登录时统一弹登录窗 —— 登录成功后回到当前页（用 ?login=1 触发 App.vue 里的 LoginModal）
function requireLogin(action: string): boolean {
  if (userStore.isAuthed) return true;
  toast.push(`${action}前请先登录`, "warn");
  router.push({ query: { ...route.query, login: "1", redirect: route.fullPath } });
  return false;
}

// 就绪的 tab 放前面（文字、手绘、视频已可用；语音开发中 🔒）—— P-L1
const landingTabs = [
  { key: "text",   label: "文字描述", icon: "✍️" },
  { key: "sketch", label: "手绘上传", icon: "🎨" },
  { key: "voice",  label: "语音讲述 🔒", icon: "🎙️" },
  { key: "video",  label: "视频导入", icon: "🎬" },
];
const activeTab = ref("text");
const title = ref("");
const textInput = ref("");
const submitting = ref(false);
const videoTitle = ref("");
const videoUrl = ref("");
const videoSubmitting = ref(false);

async function submitText() {
  const text = textInput.value.trim();
  if (!text) { toast.push("先输入一点故事内容吧", "warn"); return; }
  if (!requireLogin("创建故事")) return;
  submitting.value = true;
  try {
    await createCustomStory({ text, title: title.value.trim() || undefined });
    toast.push("故事已进入后台生成，去书架看进度", "success");
    textInput.value = ""; title.value = "";
    router.push("/library");
  } catch (e: any) {
    if (e?.status === 401) {
      router.push({ query: { ...route.query, login: "1", redirect: route.fullPath } });
      toast.push("登录已过期，请重新登录", "warn");
    } else {
      toast.push(`创建失败：${e.message}`, "error");
    }
  } finally {
    submitting.value = false;
  }
}

async function submitVideo() {
  const url = videoUrl.value.trim();
  if (!url) { toast.push("先粘贴一个公开 B 站视频链接", "warn"); return; }
  if (!requireLogin("导入视频故事")) return;
  videoSubmitting.value = true;
  try {
    await createStoryFromVideo({ url, title: videoTitle.value.trim() || undefined });
    toast.push("视频故事已进入后台生成，去书架看进度", "success");
    videoTitle.value = "";
    videoUrl.value = "";
    router.push("/library");
  } catch (e: any) {
    if (e?.status === 401) {
      router.push({ query: { ...route.query, login: "1", redirect: route.fullPath } });
      toast.push("登录已过期，请重新登录", "warn");
    } else {
      toast.push(`视频导入失败：${e.message}`, "error");
    }
  } finally {
    videoSubmitting.value = false;
  }
}

function scrollToCreate() {
  document.getElementById("landing-create")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// 公共平台 —— 真接入 /api/public/stories + /api/public/assets
const plazaTabs = [
  { key: "stories",  label: "热门故事" },
  { key: "assets",   label: "精选资产" },
];
const plazaTab = ref("stories");
const plazaStories = ref<PublicStoryCard[]>([]);
const plazaAssets  = ref<PublicAsset[]>([]);
const plazaBundles = ref<PublicAssetBundle[]>([]);
const plazaLoading = ref(false);

async function loadPlaza() {
  plazaLoading.value = true;
  try {
    const [s, a] = await Promise.allSettled([fetchPublicStories(), fetchPublicAssets()]);
    if (s.status === "fulfilled") plazaStories.value = s.value.stories;
    if (a.status === "fulfilled") {
      plazaAssets.value = a.value.assets;
      plazaBundles.value = a.value.bundles || [];
    }
  } finally {
    plazaLoading.value = false;
  }
}

// 把别人公开的故事加到 / 移出"我的故事"。同步刷新 storyStore.list 让其它页面同步显示。
const bookmarkBusyIds = ref<Set<string>>(new Set());
async function onToggleBookmark(s: PublicStoryCard, e: MouseEvent) {
  e.stopPropagation();
  if (s.official) return;
  if (!requireLogin("收藏故事")) return;
  if (bookmarkBusyIds.value.has(s.id)) return;
  const next = new Set(bookmarkBusyIds.value);
  next.add(s.id);
  bookmarkBusyIds.value = next;
  try {
    if (s.bookmarked) {
      await unbookmarkStory(s.id);
      s.bookmarked = false;
      toast.push("已从我的故事移除", "success");
    } else {
      await bookmarkStory(s.id);
      s.bookmarked = true;
      toast.push("已添加到我的故事", "success");
    }
    void storyStore.loadList?.().catch(() => {});
  } catch (err: any) {
    toast.push(`操作失败：${err?.message || err}`, "warn");
  } finally {
    const after = new Set(bookmarkBusyIds.value);
    after.delete(s.id);
    bookmarkBusyIds.value = after;
  }
}

onMounted(loadPlaza);

// Preview modal
type Preview =
  | { kind: "story"; data: PublicStoryCard }
  | { kind: "asset"; data: PublicAsset }
  | { kind: "bundle"; data: PublicAssetBundle }
  | null;
const preview = ref<Preview>(null);
function openStory(s: PublicStoryCard) { preview.value = { kind: "story", data: s }; }
function openAsset(a: PublicAsset) { preview.value = { kind: "asset", data: a }; }
function openBundle(b: PublicAssetBundle) {
  preview.value = { kind: "bundle", data: b };
  bundleSelected.value = new Set();
}

// 资产包下钻：multi-select 内部 asset
const bundleSelected = ref<Set<string>>(new Set());
function toggleBundleItem(aid: string) {
  const s = new Set(bundleSelected.value);
  if (s.has(aid)) s.delete(aid); else s.add(aid);
  bundleSelected.value = s;
}
function favSelectedFromBundle() {
  let count = 0;
  for (const aid of bundleSelected.value) {
    if (!assetShelf.hasAsset(aid)) { assetShelf.toggleAsset(aid); count++; }
  }
  toast.push(count ? `✨ 收藏了 ${count} 件` : "都已经在我的资产里了", "success");
  bundleSelected.value = new Set();
}

function playStory(id: string) { preview.value = null; router.push({ name: "story", params: { id } }); }

function toggleStoryShelf(id: string) {
  const wasIn = shelf.has(id);
  shelf.toggle(id);
  toast.push(wasIn ? "已从书架移除" : "已加到书架", "success");
}

function toggleAssetFav(id: string) {
  assetShelf.toggleAsset(id);
  toast.push(assetShelf.hasAsset(id) ? "已收藏到我的资产" : "已取消收藏", "success");
}
function toggleBundleFav(id: string) {
  assetShelf.toggleBundle(id);
  toast.push(assetShelf.hasBundle(id) ? "已收藏这个资产包" : "已取消收藏", "success");
}

// 通过 id 查单件资产（用于 bundle 预览展开）
const assetById = computed(() => {
  const m = new Map<string, PublicAsset>();
  for (const a of plazaAssets.value) m.set(a.id, a);
  return m;
});

// 手绘上传
// B5：手绘支持多图上传
interface SketchImage { dataUrl: string; name: string; size: number; }
const sketchImages = ref<SketchImage[]>([]);
const sketchTitle = ref("");
const sketchDesc = ref("");
const sketchUploading = ref(false);

function onSketchPick(e: Event) {
  const files = (e.target as HTMLInputElement).files;
  if (!files || !files.length) return;
  const MAX_TOTAL = 9;
  for (const f of Array.from(files)) {
    if (sketchImages.value.length >= MAX_TOTAL) { toast.push(`最多 ${MAX_TOTAL} 张`, "warn"); break; }
    if (!f.type.startsWith("image/")) { toast.push(`${f.name} 不是图片`, "warn"); continue; }
    if (f.size > 6 * 1024 * 1024) { toast.push(`${f.name} 超过 6MB`, "warn"); continue; }
    const fr = new FileReader();
    fr.onload = () => {
      sketchImages.value = [...sketchImages.value, { dataUrl: String(fr.result || ""), name: f.name, size: f.size }];
    };
    fr.readAsDataURL(f);
  }
  (e.target as HTMLInputElement).value = "";
}
function removeSketchImage(idx: number) {
  sketchImages.value = sketchImages.value.filter((_, i) => i !== idx);
}

async function submitSketch() {
  if (!sketchImages.value.length) { toast.push("先上传至少一张图", "warn"); return; }
  const desc = sketchDesc.value.trim();
  if (!desc) { toast.push("用几句话描述你画了什么，AI 才能接着往下编 ✏️", "warn"); return; }
  if (!requireLogin("生成手绘故事")) return;
  sketchUploading.value = true;
  try {
    // 所有图并行上传
    const uploaded = await Promise.all(sketchImages.value.map((img) =>
      uploadImage({ data: img.dataUrl, kind: "sketch" }),
    ));
    const urlLines = uploaded.map((u, i) => `  ${i + 1}. ${u.url}`).join("\n");
    const text = `${desc}\n（小朋友上传了 ${uploaded.length} 张参考图：\n${urlLines}\n）`;
    await createCustomStory({ text, title: sketchTitle.value.trim() || "我的手绘故事" });
    toast.push(`手绘故事已进入后台生成 ✨ (${uploaded.length} 张参考图)`, "success");
    sketchImages.value = []; sketchDesc.value = ""; sketchTitle.value = "";
    router.push("/library");
  } catch (e: any) {
    toast.push(`创建失败：${e.message}`, "error");
  } finally {
    sketchUploading.value = false;
  }
}
</script>

<template>
  <div class="fade-in">
    <!-- 胶片 hero（顶栏右侧已有"我的"，这里不再放 FAB） -->
    <CinemaHero @explore="scrollToCreate" />

    <!-- 创作入口 -->
    <section id="landing-create" class="max-w-[960px] mx-auto px-5 -mt-10 relative z-10">
      <BaseCard class="px-6 py-7 sm:px-10 sm:py-9">
        <div class="text-center mb-5">
          <span class="inline-block px-3 py-1 rounded-full bg-gold/20 text-ink-soft text-xs font-medium tracking-wide mb-3">
            ✨ 选一个方式开始
          </span>
          <h2 class="font-display text-2xl sm:text-3xl font-bold text-ink m-0">把灵感变成一本绘本故事</h2>
          <p class="text-ink-soft text-sm mt-2">漫秀会帮你拆分章节、生成角色与场景，把故事交给孩子去探索。</p>
        </div>

        <div class="flex justify-center mb-5 overflow-x-auto no-scrollbar">
          <BaseTabs v-model="activeTab" :tabs="landingTabs" />
        </div>

        <div v-if="activeTab === 'text'">
          <input
            v-model="title"
            type="text"
            placeholder="给故事取个名字（选填）"
            maxlength="32"
            class="w-full px-4 py-3 mb-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
          />
          <textarea
            v-model="textInput"
            rows="3"
            class="w-full px-4 py-3 rounded-xl border border-paper-edge bg-white resize-y focus:outline-none focus:border-accent-soft"
            placeholder="比如：有一只怕黑的小狐狸，为了找回掉进夜空里的画笔，和一群会发光的萤火虫一起穿过森林。"
            @keydown.meta.enter="submitText"
            @keydown.ctrl.enter="submitText"
          ></textarea>
          <div class="mt-4 flex flex-col-reverse sm:flex-row items-stretch sm:items-center gap-3 sm:justify-between">
            <div class="text-xs text-ink-mute">创作过程大约 1 分钟，请保持网络畅通</div>
            <BaseButton :disabled="submitting" size="lg" pill @click="submitText">
              {{ submitting ? "创建中…" : "开始创作" }} →
            </BaseButton>
          </div>
        </div>
        <!-- 手绘上传 —— MVP：上传 + 文字描述 -->
        <div v-else-if="activeTab === 'sketch'">
          <input
            v-model="sketchTitle"
            type="text"
            placeholder="给故事取个名字（选填）"
            maxlength="32"
            class="w-full px-4 py-3 mb-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
          />
          <div class="grid md:grid-cols-2 gap-3">
            <!-- B5：多图上传 -->
            <div>
              <div class="grid grid-cols-3 gap-2">
                <div
                  v-for="(img, i) in sketchImages"
                  :key="i"
                  class="aspect-square rounded-xl overflow-hidden relative bg-white border border-paper-edge group"
                >
                  <img :src="img.dataUrl" class="w-full h-full object-contain" alt="" />
                  <button
                    class="absolute top-1 right-1 w-6 h-6 bg-white/90 rounded-full text-warn opacity-0 group-hover:opacity-100 transition grid place-items-center text-xs"
                    title="移除"
                    @click="removeSketchImage(i)"
                  >✕</button>
                </div>
                <label
                  v-if="sketchImages.length < 9"
                  class="aspect-square border-2 border-dashed border-paper-edge rounded-xl cursor-pointer grid place-items-center bg-paper hover:bg-paper-deep/50 transition"
                >
                  <div class="text-center text-ink-soft p-2">
                    <div class="text-3xl mb-1">＋</div>
                    <div class="text-[11px]">添加图片</div>
                    <div class="text-[10px] text-ink-mute">最多 9 张</div>
                  </div>
                  <input type="file" accept="image/*" multiple class="hidden" @change="onSketchPick" />
                </label>
              </div>
              <div v-if="sketchImages.length" class="text-xs text-ink-mute mt-2">
                已添加 {{ sketchImages.length }} 张（AI 会同时参考所有图）
              </div>
            </div>
            <textarea
              v-model="sketchDesc"
              rows="7"
              class="w-full px-4 py-3 rounded-xl border border-paper-edge bg-white resize-y focus:outline-none focus:border-accent-soft"
              placeholder="描述一下你画的是什么：主角是谁、发生什么事？AI 会接着你的画编一段故事。"
              @keydown.meta.enter="submitSketch"
              @keydown.ctrl.enter="submitSketch"
            ></textarea>
          </div>
          <div class="mt-4 flex flex-col-reverse sm:flex-row items-stretch sm:items-center gap-3 sm:justify-between">
            <div class="text-xs text-ink-mute">上传的图会作为参考保留 · AI 依描述开展故事</div>
            <BaseButton :disabled="sketchUploading" size="lg" pill @click="submitSketch">
              {{ sketchUploading ? "上传中…" : "开始创作" }} →
            </BaseButton>
          </div>
        </div>

        <!-- 视频导入 —— B 站公开链接 -->
        <div v-else-if="activeTab === 'video'">
          <input
            v-model="videoTitle"
            type="text"
            placeholder="给视频故事取个名字（选填）"
            maxlength="32"
            class="w-full px-4 py-3 mb-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
          />
          <div class="bg-paper rounded-xl p-5 border border-paper-edge">
            <div class="flex items-start gap-4 flex-wrap">
              <div class="text-5xl animate-floaty">🎬</div>
              <div class="flex-1 min-w-[220px]">
                <div class="font-semibold text-ink mb-1">公开视频链接</div>
                <div class="text-sm text-ink-soft mb-3">
                  当前支持 B 站公开视频：优先读取字幕，没有字幕时会下载音频并转写，再改编成绘本故事。
                </div>
                <div class="flex flex-col sm:flex-row gap-2">
                  <input
                    v-model="videoUrl"
                    type="url"
                    placeholder="https://www.bilibili.com/video/..."
                    class="flex-1 px-3 py-2 text-sm rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
                    @keydown.meta.enter="submitVideo"
                    @keydown.ctrl.enter="submitVideo"
                  />
                  <BaseButton :disabled="videoSubmitting" size="sm" pill @click="submitVideo">
                    {{ videoSubmitting ? "导入中…" : "开始导入" }}
                  </BaseButton>
                </div>
                <div class="text-xs text-ink-mute mt-3">限制 10 分钟以内；会员、番剧、登录可见或合集视频暂不保证可用。</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 语音讲述 —— 精致占位 -->
        <div v-else-if="activeTab === 'voice'" class="py-8 px-4">
          <div class="bg-paper rounded-xl p-6 border-2 border-dashed border-paper-edge text-center">
            <div class="text-6xl mb-3 animate-floaty">🎙️</div>
            <div class="font-semibold text-ink mb-1">语音讲述</div>
            <div class="text-sm text-ink-soft mb-4">
              按住说话 · AI 识别成文本 · 自动拆成故事。iOS Safari 暂不可用。
            </div>
            <BaseButton variant="soft" pill disabled>按住说话（开发中）</BaseButton>
          </div>
        </div>
      </BaseCard>

      <div class="text-center mt-6">
        <BaseButton variant="ghost" pill @click="router.push('/library')">
          查看现有故事 →
        </BaseButton>
      </div>
    </section>

    <!-- 公共平台 -->
    <section class="max-w-[1100px] mx-auto px-5 mt-16 pb-16">
      <div class="text-center mb-6">
        <h2 class="font-display text-2xl font-bold m-0">公共平台</h2>
        <p class="text-ink-soft text-sm mt-1">来看看大家分享的故事和资产</p>
      </div>
      <div class="flex justify-center mb-6">
        <BaseTabs v-model="plazaTab" :tabs="plazaTabs" />
      </div>
      <!-- Loading skeletons -->
      <div v-if="plazaLoading && plazaStories.length === 0" class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
        <div v-for="i in 4" :key="i" class="bg-white border border-paper-edge rounded-[var(--radius-card)] overflow-hidden p-4">
          <div class="h-24 rounded-lg bg-paper-deep relative overflow-hidden mb-3">
            <div class="absolute inset-0 animate-shimmer"></div>
          </div>
          <div class="h-4 rounded bg-paper-deep w-3/4 mb-2 relative overflow-hidden">
            <div class="absolute inset-0 animate-shimmer"></div>
          </div>
          <div class="h-3 rounded bg-paper-deep w-1/2 relative overflow-hidden">
            <div class="absolute inset-0 animate-shimmer"></div>
          </div>
        </div>
      </div>

      <!-- Stories -->
      <div
        v-else-if="plazaTab === 'stories'"
        class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4"
      >
        <BaseCard
          v-for="s in [...plazaStories].sort((a, b) => (b.likes ?? 0) - (a.likes ?? 0))"
          :key="s.id"
          hover
          class="overflow-hidden cursor-pointer"
          @click="openStory(s)"
        >
          <div
            class="h-28 grid place-items-center text-5xl relative overflow-hidden"
            :class="s.official ? 'bg-gradient-to-br from-gold to-accent-soft' : 'bg-gradient-to-br from-paper-deep to-gold-mute'"
          >
            <img
              v-if="s.cover_url"
              :src="s.cover_url"
              loading="lazy"
              decoding="async"
              class="absolute inset-0 w-full h-full object-cover"
              alt=""
            />
            <span v-else>{{ s.emoji_cover || (s.official ? '📖' : '📘') }}</span>
          </div>
          <div class="p-4">
            <div class="font-bold text-ink leading-snug min-h-[2.7em]">{{ s.title }}</div>
            <div class="mt-1.5 flex items-center justify-between text-xs text-ink-soft">
              <span>@{{ s.author }}</span>
              <span class="text-warn">❤ {{ s.likes }}</span>
            </div>
            <div class="mt-2 flex items-center justify-between">
              <span class="text-[11px] text-ink-mute">{{ s.scene_count }} 幕</span>
              <div class="flex items-center gap-1.5">
                <span v-if="s.official" class="px-2 py-0.5 rounded-full text-[11px] bg-gradient-to-r from-gold to-accent text-white">官方</span>
                <!-- 自己发布的故事不展示"添加到我的故事"——已经在「我的原创」里了 -->
                <span
                  v-else-if="userStore.user && s.owner_user_id === userStore.user.id"
                  class="px-2 py-0.5 text-[11px] rounded-full bg-accent-soft/30 text-accent-deep"
                  title="这是你发布的故事"
                >📤 我发布的</span>
                <button
                  v-else
                  class="px-2 py-0.5 text-[11px] rounded-full transition"
                  :class="s.bookmarked
                    ? 'bg-good/20 text-good hover:bg-warn/20 hover:text-warn'
                    : 'bg-accent text-white hover:brightness-110'"
                  :disabled="bookmarkBusyIds.has(s.id)"
                  :title="s.bookmarked ? '点击取消，从我的故事里移除' : '加到我的故事里'"
                  @click="(e) => onToggleBookmark(s, e)"
                >{{ s.bookmarked ? '✓ 已添加' : '＋ 添加到我的故事' }}</button>
              </div>
            </div>
          </div>
        </BaseCard>
      </div>

      <!-- Assets：先打包后单件 -->
      <div v-else>
        <!-- 打包资产 -->
        <div v-if="plazaBundles.length" class="mb-6">
          <div class="text-sm font-semibold text-ink-soft mb-3 flex items-center gap-2">
            <span>📦 打包资产</span>
            <span class="text-xs text-ink-mute font-normal">一键拿全整套</span>
          </div>
          <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
            <BaseCard
              v-for="b in plazaBundles"
              :key="b.id"
              hover
              :glow="!!b.official"
              class="overflow-hidden cursor-pointer relative"
              @click="openBundle(b)"
            >
              <div class="h-32 relative grid place-items-center bg-gradient-to-br from-gold to-accent-soft overflow-hidden">
                <img v-if="b.cover_url" :src="b.cover_url" class="max-w-[55%] max-h-[80%] object-contain drop-shadow-md" alt="" />
                <div v-else class="text-6xl">{{ b.cover_emoji || "📦" }}</div>
                <div class="absolute bottom-1 right-2 px-2 py-0.5 text-[11px] rounded-full bg-white/90 text-ink font-semibold">
                  × {{ b.item_count }}
                </div>
              </div>
              <div class="p-3">
                <div class="font-semibold text-ink truncate">{{ b.name }}</div>
                <div class="text-xs text-ink-mute mt-0.5 line-clamp-1">{{ b.description }}</div>
                <div class="mt-2 flex items-center justify-between text-[11px]">
                  <span class="text-ink-soft">{{ b.kind === 'character_pack' ? '人物包' : b.kind === 'object_pack' ? '道具包' : '混合包' }}</span>
                  <span class="text-warn">❤ {{ b.likes ?? 0 }}</span>
                </div>
                <div v-if="assetShelf.hasBundle(b.id)" class="mt-1">
                  <span class="px-2 py-0.5 text-[11px] bg-good/15 text-good rounded-full">✓ 已收藏</span>
                </div>
              </div>
            </BaseCard>
          </div>
        </div>

        <!-- 单件资产 -->
        <div>
          <div class="text-sm font-semibold text-ink-soft mb-3 flex items-center gap-2">
            <span>🎭 单件资产</span>
            <span class="text-xs text-ink-mute font-normal">点击预览 / 收藏</span>
          </div>
          <div class="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
            <BaseCard
              v-for="a in plazaAssets"
              :key="a.id"
              hover
              class="overflow-hidden cursor-pointer relative group"
              @click="openAsset(a)"
            >
              <div class="h-28 grid place-items-center bg-gradient-to-br from-paper-deep to-gold-mute relative">
                <img :src="a.url" :alt="a.name" loading="lazy" class="max-w-[88%] max-h-[88%] object-contain drop-shadow-sm" />
                <!-- P-P2：悬浮快速收藏 -->
                <button
                  class="absolute top-1.5 right-1.5 w-7 h-7 rounded-full grid place-items-center backdrop-blur transition text-sm"
                  :class="assetShelf.hasAsset(a.id)
                    ? 'bg-accent text-white shadow-[0_2px_8px_rgba(255,122,61,0.45)] opacity-100'
                    : 'bg-white/85 text-ink-soft opacity-0 group-hover:opacity-100 hover:bg-gold-mute'"
                  :title="assetShelf.hasAsset(a.id) ? '从收藏移除' : '收藏到我的资产'"
                  @click.stop="toggleAssetFav(a.id)"
                >{{ assetShelf.hasAsset(a.id) ? "★" : "☆" }}</button>
              </div>
              <div class="p-3">
                <div class="font-semibold text-ink text-sm truncate">{{ a.name }}</div>
                <div class="text-xs text-ink-mute mt-0.5">
                  {{ a.kind === 'character' ? '人物' : '道具' }} · 官方
                </div>
              </div>
            </BaseCard>
            <div v-if="!plazaLoading && plazaAssets.length === 0" class="col-span-full text-center py-12 text-ink-mute text-sm">
              暂无资产
            </div>
          </div>
        </div>
      </div>

      <!-- "看更多" 在分享码 + 账号系统就绪前隐藏（P-L3） -->
      <div class="text-center mt-10 text-xs text-ink-mute">
        更多社区内容将在账号与分享码系统上线后开放 ✨
      </div>
    </section>

    <!-- Preview Modal -->
    <BaseModal
      :open="!!preview"
      :max-width="preview?.kind === 'story' ? '560px' : '440px'"
      @close="preview = null"
    >
      <template v-if="preview?.kind === 'story'">
        <div
          class="w-full h-48 rounded-xl overflow-hidden mb-3 bg-gradient-to-br from-paper-deep to-gold-mute grid place-items-center text-6xl"
        >
          <img
            v-if="preview.data.cover_url"
            :src="preview.data.cover_url"
            class="w-full h-full object-cover"
            alt=""
          />
          <span v-else>{{ preview.data.official ? '📖' : '📘' }}</span>
        </div>
        <h3 class="font-display text-xl font-bold m-0 mb-1">{{ preview.data.title }}</h3>
        <div class="text-xs text-ink-soft mb-2">
          @{{ preview.data.author }} · {{ preview.data.scene_count }} 幕 · ❤ {{ preview.data.likes }}
        </div>
        <p class="text-sm text-ink-soft leading-relaxed m-0">{{ preview.data.summary }}</p>
      </template>
      <template v-else-if="preview?.kind === 'asset'">
        <div class="w-full h-60 rounded-xl overflow-hidden mb-3 bg-gradient-to-br from-paper to-gold-mute grid place-items-center p-6">
          <img :src="preview.data.url" :alt="preview.data.name" class="max-w-full max-h-full object-contain drop-shadow-lg" />
        </div>
        <h3 class="font-display text-xl font-bold m-0 mb-1">{{ preview.data.name }}</h3>
        <div class="text-xs text-ink-soft">
          {{ preview.data.kind === 'character' ? '人物' : '道具' }} · 官方精选
        </div>
      </template>
      <template v-else-if="preview?.kind === 'bundle'">
        <div class="w-full h-48 rounded-xl overflow-hidden mb-3 bg-gradient-to-br from-gold to-accent-soft grid place-items-center relative">
          <img v-if="preview.data.cover_url" :src="preview.data.cover_url" class="max-w-[50%] max-h-[80%] object-contain drop-shadow-lg" alt="" />
          <div v-else class="text-7xl">{{ preview.data.cover_emoji || "📦" }}</div>
          <div class="absolute top-2 right-2 px-2.5 py-1 rounded-full bg-white/95 text-ink text-xs font-semibold">
            × {{ preview.data.item_count }} 件
          </div>
        </div>
        <h3 class="font-display text-xl font-bold m-0 mb-1">{{ preview.data.name }}</h3>
        <div class="text-xs text-ink-soft mb-3">
          {{ preview.data.kind === 'character_pack' ? '人物包' : preview.data.kind === 'object_pack' ? '道具包' : '混合包' }}
          · 官方精选 · ❤ {{ preview.data.likes ?? 0 }}
        </div>
        <p class="text-sm text-ink-soft leading-relaxed m-0 mb-2">{{ preview.data.description }}</p>
        <div class="text-xs text-ink-mute mb-2 flex items-center justify-between">
          <span>点击单件可多选收藏</span>
          <span v-if="bundleSelected.size" class="text-accent-deep font-semibold">已选 {{ bundleSelected.size }} / {{ preview.data.asset_ids.length }}</span>
        </div>
        <!-- bundle 包含的资产缩略 —— D1 可多选 -->
        <div class="grid grid-cols-5 gap-2">
          <button
            v-for="aid in preview.data.asset_ids"
            :key="aid"
            type="button"
            class="aspect-square rounded-lg grid place-items-center p-1 overflow-hidden relative border-2 transition"
            :class="bundleSelected.has(aid)
              ? 'border-accent bg-accent/10 shadow-[0_0_8px_rgba(255,122,61,0.25)]'
              : assetShelf.hasAsset(aid)
                ? 'border-good/50 bg-good/5'
                : 'border-transparent bg-paper-deep hover:border-paper-edge'"
            :title="assetById.get(aid)?.name"
            @click="toggleBundleItem(aid)"
          >
            <img
              v-if="assetById.get(aid)?.url"
              :src="assetById.get(aid)!.url"
              class="max-w-full max-h-full object-contain"
              alt=""
            />
            <span
              v-if="assetShelf.hasAsset(aid)"
              class="absolute top-0.5 right-0.5 text-[9px] text-good bg-white/90 rounded px-1"
            >★</span>
            <span
              v-if="bundleSelected.has(aid)"
              class="absolute inset-0 grid place-items-center bg-accent/20"
            >
              <span class="text-white bg-accent rounded-full w-5 h-5 grid place-items-center text-xs">✓</span>
            </span>
          </button>
        </div>
      </template>
      <template #footer>
        <template v-if="preview?.kind === 'story'">
          <BaseButton variant="soft" pill @click="preview = null">关闭</BaseButton>
          <BaseButton
            variant="soft"
            pill
            @click="toggleStoryShelf((preview as any).data.id)"
          >{{ shelf.has(preview.data.id) ? "★ 从书架移除" : "☆ 加到书架" }}</BaseButton>
          <BaseButton pill @click="playStory(preview.data.id)">开始玩 →</BaseButton>
        </template>
        <template v-else-if="preview?.kind === 'asset'">
          <BaseButton variant="soft" pill @click="preview = null">关闭</BaseButton>
          <BaseButton pill @click="toggleAssetFav((preview as any).data.id)">
            {{ assetShelf.hasAsset((preview as any).data.id) ? "★ 取消收藏" : "☆ 收藏" }}
          </BaseButton>
        </template>
        <template v-else-if="preview?.kind === 'bundle'">
          <BaseButton variant="soft" pill @click="preview = null">关闭</BaseButton>
          <BaseButton
            v-if="bundleSelected.size > 0"
            variant="soft"
            pill
            @click="favSelectedFromBundle"
          >☆ 收藏选中 ({{ bundleSelected.size }})</BaseButton>
          <BaseButton pill @click="toggleBundleFav((preview as any).data.id)">
            {{ assetShelf.hasBundle((preview as any).data.id) ? "★ 取消整包" : "☆ 收藏整包" }}
          </BaseButton>
        </template>
      </template>
    </BaseModal>
  </div>
</template>
