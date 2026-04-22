<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import CinemaHero from "@/components/CinemaHero.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import BaseModal from "@/components/BaseModal.vue";
import { useUserStore } from "@/stores/user";
import { useToastStore } from "@/stores/toast";
import { useShelfStore } from "@/stores/shelf";
import {
  createCustomStory,
  fetchPublicStories,
  fetchPublicAssets,
  uploadImage,
} from "@/api/endpoints";
import type { PublicStoryCard, PublicAsset } from "@/api/types";

const router = useRouter();
const user = useUserStore();
const toast = useToastStore();
const shelf = useShelfStore();

const landingTabs = [
  { key: "text",   label: "文字描述", icon: "✍️" },
  { key: "video",  label: "视频导入", icon: "🎬" },
  { key: "voice",  label: "语音讲述", icon: "🎙️" },
  { key: "sketch", label: "手绘上传", icon: "🎨" },
];
const activeTab = ref("text");
const title = ref("");
const textInput = ref("");
const submitting = ref(false);

async function submitText() {
  const text = textInput.value.trim();
  if (!text) { toast.push("先输入一点故事内容吧", "warn"); return; }
  submitting.value = true;
  try {
    await createCustomStory({ text, title: title.value.trim() || undefined });
    toast.push("故事已进入后台生成，去书架看进度", "success");
    textInput.value = ""; title.value = "";
    router.push("/library");
  } catch (e: any) {
    toast.push(`创建失败：${e.message}`, "error");
  } finally {
    submitting.value = false;
  }
}

function scrollToCreate() {
  document.getElementById("landing-create")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// 公共平台 —— 真接入 /api/public/stories + /api/public/assets
const plazaTabs = [
  { key: "stories",  label: "热门故事" },
  { key: "assets",   label: "精选资产" },
  { key: "official", label: "官方精选" },
];
const plazaTab = ref("stories");
const plazaStories = ref<PublicStoryCard[]>([]);
const plazaAssets  = ref<PublicAsset[]>([]);
const plazaLoading = ref(false);

async function loadPlaza() {
  plazaLoading.value = true;
  try {
    const [s, a] = await Promise.allSettled([fetchPublicStories(), fetchPublicAssets()]);
    if (s.status === "fulfilled") plazaStories.value = s.value.stories;
    if (a.status === "fulfilled") plazaAssets.value = a.value.assets;
  } finally {
    plazaLoading.value = false;
  }
}

onMounted(loadPlaza);

// Preview modal
type Preview =
  | { kind: "story"; data: PublicStoryCard }
  | { kind: "asset"; data: PublicAsset }
  | null;
const preview = ref<Preview>(null);
function openStory(s: PublicStoryCard) { preview.value = { kind: "story", data: s }; }
function openAsset(a: PublicAsset) { preview.value = { kind: "asset", data: a }; }

function playStory(id: string) { preview.value = null; router.push({ name: "story", params: { id } }); }

function addToShelf(id: string) {
  shelf.add(id);
  toast.push("已加到书架", "success");
}

function shareAssetHint() { toast.push("资产导入/收藏在账号系统后补上 🎨", "info"); }

// 手绘上传
const sketchFile = ref<File | null>(null);
const sketchDataUrl = ref<string>("");
const sketchTitle = ref("");
const sketchDesc = ref("");
const sketchUploading = ref(false);

function onSketchPick(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  if (!f.type.startsWith("image/")) { toast.push("请选择图片", "warn"); return; }
  if (f.size > 6 * 1024 * 1024) { toast.push("图片不能超过 6MB", "warn"); return; }
  sketchFile.value = f;
  const fr = new FileReader();
  fr.onload = () => { sketchDataUrl.value = String(fr.result || ""); };
  fr.readAsDataURL(f);
}

async function submitSketch() {
  if (!sketchDataUrl.value) { toast.push("先选一张图片", "warn"); return; }
  const desc = sketchDesc.value.trim();
  if (!desc) { toast.push("用几句话描述你画了什么，AI 才能接着往下编 ✏️", "warn"); return; }
  sketchUploading.value = true;
  try {
    const up = await uploadImage({ data: sketchDataUrl.value, kind: "sketch" });
    // 把描述 + 图 URL 打包送给 create custom story
    const text = `${desc}\n（参考一张小朋友自己画的图：${up.url}）`;
    await createCustomStory({ text, title: sketchTitle.value.trim() || "我的手绘故事" });
    toast.push("手绘故事已进入后台生成 ✨", "success");
    sketchFile.value = null; sketchDataUrl.value = ""; sketchDesc.value = ""; sketchTitle.value = "";
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
    <!-- 胶片 hero -->
    <CinemaHero @explore="scrollToCreate">
      <template #overlay>
        <!-- 右上 FAB：进入 profile -->
        <button
          class="absolute top-14 right-6 px-4 py-2 rounded-full text-sm font-semibold text-gold-mute border border-gold/60 bg-gold/10 hover:bg-gold/25 hover:text-white backdrop-blur transition z-10"
          @click="router.push('/profile')"
        >👤 {{ user.isAuthed ? user.user?.nickname : "我的" }}</button>
      </template>
    </CinemaHero>

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
            <div>
              <label
                class="block aspect-square border-2 border-dashed border-paper-edge rounded-xl cursor-pointer grid place-items-center bg-paper hover:bg-paper-deep/50 transition overflow-hidden relative"
              >
                <img v-if="sketchDataUrl" :src="sketchDataUrl" class="absolute inset-0 w-full h-full object-contain bg-white" alt="" />
                <div v-else class="text-center text-ink-soft p-4">
                  <div class="text-5xl mb-2">🎨</div>
                  <div class="text-sm">点这里上传一张图</div>
                  <div class="text-xs text-ink-mute mt-1">照片 / 截图 / 扫描 都可以</div>
                </div>
                <input type="file" accept="image/*" class="hidden" @change="onSketchPick" />
              </label>
              <div v-if="sketchFile" class="text-xs text-ink-mute mt-1 truncate">
                {{ sketchFile.name }} · {{ Math.round(sketchFile.size / 1024) }} KB
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

        <!-- 视频导入 —— 精致占位 -->
        <div v-else-if="activeTab === 'video'" class="py-8 px-4">
          <div class="bg-paper rounded-xl p-6 border-2 border-dashed border-paper-edge">
            <div class="flex items-start gap-4 flex-wrap">
              <div class="text-5xl animate-floaty">🎬</div>
              <div class="flex-1 min-w-[220px]">
                <div class="font-semibold text-ink mb-1">视频导入</div>
                <div class="text-sm text-ink-soft mb-3">
                  粘贴 B 站 / 抖音 / YouTube 链接或上传 .mp4 → AI 抽关键帧 + 字幕 → 拆成绘本。
                </div>
                <div class="flex gap-2">
                  <input
                    type="url"
                    placeholder="https://www.bilibili.com/video/..."
                    disabled
                    class="flex-1 px-3 py-2 text-sm rounded-lg border border-paper-edge bg-white/60 text-ink-mute"
                  />
                  <BaseButton variant="soft" size="sm" pill disabled>开发中</BaseButton>
                </div>
                <div class="text-xs text-ink-mute mt-3">预计阶段 3 开放；骨架在 <code class="px-1 bg-paper-deep rounded">agent-docs/plan/</code></div>
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

      <!-- Stories / Official -->
      <div
        v-else-if="plazaTab === 'stories' || plazaTab === 'official'"
        class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4"
      >
        <BaseCard
          v-for="s in (plazaTab === 'official'
            ? plazaStories.filter((x) => x.official)
            : plazaStories.filter((x) => !x.official))"
          :key="s.id"
          hover
          :glow="!!s.official"
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
              <span v-if="s.official" class="px-2 py-0.5 rounded-full text-[11px] bg-gradient-to-r from-gold to-accent text-white">官方</span>
              <span v-else-if="shelf.has(s.id)" class="px-2 py-0.5 rounded-full text-[11px] bg-good/20 text-good">✓ 在书架</span>
            </div>
          </div>
        </BaseCard>
      </div>

      <!-- Assets grid -->
      <div
        v-else
        class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4"
      >
        <BaseCard
          v-for="a in plazaAssets"
          :key="a.id"
          hover
          class="overflow-hidden cursor-pointer"
          @click="openAsset(a)"
        >
          <div class="h-32 grid place-items-center bg-gradient-to-br from-paper-deep to-gold-mute">
            <img :src="a.url" :alt="a.name" loading="lazy" class="max-w-[80%] max-h-[80%] object-contain drop-shadow-sm" />
          </div>
          <div class="p-3">
            <div class="font-semibold text-ink truncate">{{ a.name }}</div>
            <div class="text-xs text-ink-mute mt-0.5">
              {{ a.kind === 'character' ? '人物' : '道具' }} · 官方
            </div>
          </div>
        </BaseCard>
        <div v-if="!plazaLoading && plazaAssets.length === 0" class="col-span-full text-center py-12 text-ink-mute text-sm">
          暂无资产
        </div>
      </div>

      <div class="text-center mt-8">
        <BaseButton variant="soft" pill @click="toast.push('完整社区功能依赖账号 + 分享码系统，阶段 2 开放 ')">
          看更多 →
        </BaseButton>
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
      <template #footer>
        <template v-if="preview?.kind === 'story'">
          <BaseButton variant="soft" pill @click="preview = null">关闭</BaseButton>
          <BaseButton
            variant="soft"
            pill
            :disabled="shelf.has(preview.data.id)"
            @click="addToShelf(preview.data.id)"
          >{{ shelf.has(preview.data.id) ? "✓ 已在书架" : "加到书架" }}</BaseButton>
          <BaseButton pill @click="playStory(preview.data.id)">开始玩 →</BaseButton>
        </template>
        <template v-else-if="preview?.kind === 'asset'">
          <BaseButton variant="soft" pill @click="preview = null">关闭</BaseButton>
          <BaseButton pill @click="shareAssetHint">收藏（开发中）</BaseButton>
        </template>
      </template>
    </BaseModal>
  </div>
</template>
