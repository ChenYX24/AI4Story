<script setup lang="ts">
// D8 资产商城 —— 公共资产库 + 公共分享包
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import BaseModal from "@/components/BaseModal.vue";
import { fetchPublicAssets, fetchPublicPacks, fetchPack, fetchMyPacks, deletePack } from "@/api/endpoints";
import type { PublicAsset, PublicAssetBundle } from "@/api/types";
import type { PackOut } from "@/api/endpoints";
import { useAssetShelfStore } from "@/stores/assetShelf";
import { useToastStore } from "@/stores/toast";
import { useUserStore } from "@/stores/user";
import PackEditModal from "@/components/PackEditModal.vue";

const router = useRouter();
const assetShelf = useAssetShelfStore();
const toast = useToastStore();
const user = useUserStore();

const tabs = [
  { key: "assets",  label: "单件资产", icon: "🎭" },
  { key: "bundles", label: "资产包",   icon: "📦" },
  { key: "shared",  label: "用户分享", icon: "✨" },
  { key: "mine",    label: "我的资产包", icon: "📁" },
];
const tab = ref<"assets" | "bundles" | "shared" | "mine">("assets");

const assets  = ref<PublicAsset[]>([]);
const bundles = ref<PublicAssetBundle[]>([]);
const shared  = ref<PackOut[]>([]);
const loading = ref(false);

// 输入分享码导入
const codeInput = ref("");
const codeBusy = ref(false);
const importedPack = ref<PackOut | null>(null);
async function importByCode() {
  const code = codeInput.value.trim().toUpperCase();
  if (code.length !== 6) { toast.push("分享码是 6 位字符", "warn"); return; }
  codeBusy.value = true;
  try {
    const p = await fetchPack(code);
    importedPack.value = p;
  } catch (e: any) {
    toast.push(e?.message || "找不到这个分享码", "error");
  } finally {
    codeBusy.value = false;
  }
}
function addPackAssetsToMine() {
  if (!importedPack.value) return;
  let count = 0;
  for (const a of importedPack.value.assets) {
    // 避免重复
    if (assetShelf.myAssets.find((m) => m.id === a.id)) continue;
    assetShelf.addMyAsset({
      id: a.id,
      name: a.name,
      url: a.url,
      kind: (a.kind as "character" | "object"),
      origin_story_id: a.origin_story_id,
      origin_scene_idx: a.origin_scene_idx,
    });
    count++;
  }
  toast.push(count ? `✨ 导入了 ${count} 件道具到我的资产` : "全部已经在我的资产里了", "success");
  codeInput.value = "";
  importedPack.value = null;
}

async function loadAll() {
  loading.value = true;
  try {
    const [a, p] = await Promise.allSettled([fetchPublicAssets(), fetchPublicPacks()]);
    if (a.status === "fulfilled") {
      assets.value = a.value.assets;
      bundles.value = a.value.bundles || [];
    }
    if (p.status === "fulfilled") shared.value = p.value.packs;
  } finally { loading.value = false; }
}
onMounted(loadAll);

// ---- 我的资产包 ----
const myPacks = ref<PackOut[]>([]);
const myPacksLoading = ref(false);
const selectedPack = ref<PackOut | null>(null);
const packModalOpen = ref(false);
const editingPack = ref<PackOut | null>(null);

async function loadMyPacks() {
  if (!user.isAuthed) return;
  myPacksLoading.value = true;
  try {
    const r = await fetchMyPacks();
    myPacks.value = r.packs;
  } catch { /* silent */ }
  finally { myPacksLoading.value = false; }
}

function openCreatePack() {
  editingPack.value = null;
  packModalOpen.value = true;
}
function openEditPack(p: PackOut) {
  editingPack.value = p;
  packModalOpen.value = true;
}
function onPackSaved() {
  packModalOpen.value = false;
  loadMyPacks();
}
async function onDeletePack(p: PackOut) {
  if (!confirm(`确定删除「${p.name}」？`)) return;
  try {
    await deletePack(p.code);
    myPacks.value = myPacks.value.filter((x) => x.code !== p.code);
    if (selectedPack.value?.code === p.code) selectedPack.value = null;
    toast.push("已删除", "success");
  } catch (e: any) {
    toast.push(e?.message || "删除失败", "error");
  }
}
function copyCode(code: string) {
  try { navigator.clipboard.writeText(code); toast.push(`码 ${code} 已复制`, "success"); }
  catch { toast.push(`码：${code}`, "info"); }
}

const filteredAssets = computed(() => assets.value);

watch(tab, (v) => { if (v === "mine" && myPacks.value.length === 0) loadMyPacks(); });
</script>

<template>
  <div class="max-w-[1100px] mx-auto px-5 py-8 fade-in">
    <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
      <div>
        <h1 class="font-display text-2xl sm:text-3xl font-bold m-0">🛒 资产商城</h1>
        <p class="text-ink-soft text-sm mt-1">官方精选 · 用户共享 · 输入分享码一键导入</p>
      </div>
      <BaseButton variant="soft" size="sm" pill @click="router.push('/profile')">
        查看我的资产 →
      </BaseButton>
    </div>

    <!-- 分享码输入 -->
    <BaseCard class="p-4 mb-6">
      <div class="flex items-center gap-3 flex-wrap">
        <div class="font-semibold text-ink">🔑 输入分享码</div>
        <input
          v-model="codeInput"
          type="text"
          placeholder="例如 A3K9PQ"
          maxlength="6"
          class="px-3 py-2 text-sm rounded-lg border border-paper-edge bg-white w-32 font-mono uppercase tracking-widest focus:outline-none focus:border-accent-soft"
          @keydown.enter="importByCode"
        />
        <BaseButton size="sm" pill :disabled="codeBusy || codeInput.length !== 6" @click="importByCode">
          {{ codeBusy ? "查找中…" : "查找" }}
        </BaseButton>
        <span class="text-xs text-ink-mute">朋友把码发给你，粘到这里</span>
      </div>
    </BaseCard>

    <div class="flex justify-center mb-6">
      <BaseTabs v-model="tab" :tabs="tabs" />
    </div>

    <!-- Loading skeletons -->
    <div v-if="loading && assets.length === 0 && bundles.length === 0 && shared.length === 0"
         class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
      <div v-for="i in 8" :key="i" class="bg-white border border-paper-edge rounded-[var(--radius-card)] overflow-hidden p-3">
        <div class="h-24 rounded bg-paper-deep relative overflow-hidden mb-2">
          <div class="absolute inset-0 animate-shimmer"></div>
        </div>
        <div class="h-4 w-2/3 bg-paper-deep rounded"></div>
      </div>
    </div>

    <!-- 单件资产 -->
    <template v-else-if="tab === 'assets'">
      <div v-if="filteredAssets.length === 0" class="text-center py-16 text-ink-mute">暂无单件资产</div>
      <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
        <BaseCard
          v-for="a in filteredAssets"
          :key="a.id"
          hover
          class="overflow-hidden relative group"
        >
          <div class="h-24 grid place-items-center bg-gradient-to-br from-paper-deep to-gold-mute relative">
            <img :src="a.url" :alt="a.name" loading="lazy" class="max-w-[88%] max-h-[88%] object-contain" />
            <button
              class="absolute top-1.5 right-1.5 w-7 h-7 rounded-full grid place-items-center transition backdrop-blur text-sm"
              :class="assetShelf.hasAsset(a.id)
                ? 'bg-accent text-white shadow-[0_2px_8px_rgba(255,122,61,0.45)]'
                : 'bg-white/85 text-ink-soft opacity-0 group-hover:opacity-100 hover:bg-gold-mute'"
              :title="assetShelf.hasAsset(a.id) ? '从收藏移除' : '收藏'"
              @click="assetShelf.toggleAsset(a.id)"
            >{{ assetShelf.hasAsset(a.id) ? "★" : "☆" }}</button>
          </div>
          <div class="p-3">
            <div class="font-semibold text-ink text-sm truncate">{{ a.name }}</div>
            <div class="text-[11px] text-ink-mute mt-0.5">
              {{ a.kind === 'character' ? '人物' : '道具' }} · 官方
            </div>
          </div>
        </BaseCard>
      </div>
    </template>

    <!-- 官方资产包 -->
    <template v-else-if="tab === 'bundles'">
      <div v-if="bundles.length === 0" class="text-center py-16 text-ink-mute">暂无资产包</div>
      <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
        <BaseCard
          v-for="b in bundles"
          :key="b.id"
          hover
          class="overflow-hidden cursor-pointer relative"
        >
          <div class="h-32 relative grid place-items-center bg-gradient-to-br from-gold to-accent-soft overflow-hidden">
            <img v-if="b.cover_url" :src="b.cover_url" class="max-w-[55%] max-h-[80%] object-contain drop-shadow-md" alt="" />
            <div v-else class="text-6xl">{{ b.cover_emoji || "📦" }}</div>
            <div class="absolute bottom-1 right-2 px-2 py-0.5 text-[11px] rounded-full bg-white/90 text-ink font-semibold">× {{ b.item_count }}</div>
          </div>
          <div class="p-3">
            <div class="font-semibold text-ink truncate">{{ b.name }}</div>
            <div class="text-xs text-ink-mute mt-0.5 line-clamp-1">{{ b.description }}</div>
            <div class="mt-2 flex items-center justify-between text-[11px]">
              <span class="text-ink-soft">{{ b.kind === 'character_pack' ? '人物包' : b.kind === 'object_pack' ? '道具包' : '混合包' }}</span>
              <button
                class="px-2 py-0.5 rounded-full text-[11px]"
                :class="assetShelf.hasBundle(b.id) ? 'bg-accent text-white' : 'bg-paper-deep hover:bg-gold-mute text-ink-soft'"
                @click.stop="assetShelf.toggleBundle(b.id)"
              >{{ assetShelf.hasBundle(b.id) ? '★ 已收藏' : '☆ 收藏' }}</button>
            </div>
          </div>
        </BaseCard>
      </div>
    </template>

    <!-- 用户分享（后端 /packs/ public） -->
    <template v-else-if="tab === 'shared'">
      <div v-if="shared.length === 0" class="text-center py-16 text-ink-mute">
        <div class="text-5xl mb-3">✨</div>
        <div>还没有用户分享的资产包<br />在"我的资产"多选后点"打包分享到公共库"</div>
      </div>
      <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
        <BaseCard
          v-for="p in shared"
          :key="p.code"
          hover
          class="overflow-hidden relative"
        >
          <div class="h-28 grid place-items-center bg-gradient-to-br from-paper-deep to-gold-mute relative overflow-hidden">
            <div v-if="p.assets.length" class="grid grid-cols-3 gap-1 p-2">
              <div v-for="a in p.assets.slice(0, 6)" :key="a.id"
                   class="w-8 h-8 bg-white/70 rounded overflow-hidden grid place-items-center">
                <img :src="a.url" class="max-w-full max-h-full object-contain" alt="" />
              </div>
            </div>
            <div v-else class="text-4xl">📦</div>
            <div class="absolute bottom-1 right-2 px-2 py-0.5 text-[11px] rounded-full bg-white/90 text-ink font-semibold">× {{ p.asset_ids.length }}</div>
          </div>
          <div class="p-3">
            <div class="font-semibold text-ink truncate">{{ p.name }}</div>
            <div class="text-xs text-ink-mute mt-0.5 line-clamp-1">{{ p.description || "没有描述" }}</div>
            <div class="mt-2 flex items-center justify-between text-[11px]">
              <span class="font-mono text-accent-deep">{{ p.code }}</span>
              <BaseButton size="sm" pill @click="codeInput = p.code; importByCode()">导入</BaseButton>
            </div>
          </div>
        </BaseCard>
      </div>
    </template>

    <!-- 我的资产包 -->
    <template v-else-if="tab === 'mine'">
      <div v-if="!user.isAuthed" class="text-center py-16 text-ink-mute">
        请先登录后查看我的资产包
      </div>
      <template v-else>
        <div class="flex items-center justify-between mb-4">
          <div class="text-sm text-ink-soft">共 {{ myPacks.length }} 个包</div>
          <BaseButton size="sm" pill @click="openCreatePack">+ 创建资产包</BaseButton>
        </div>

        <!-- 包详情展开 -->
        <BaseCard v-if="selectedPack" class="p-5 mb-4">
          <div class="flex items-center justify-between mb-3">
            <div>
              <div class="font-bold text-ink text-lg">{{ selectedPack.name }}</div>
              <div class="text-xs text-ink-mute mt-0.5">
                码 <span class="font-mono text-accent-deep cursor-pointer" @click="copyCode(selectedPack.code)">{{ selectedPack.code }}</span>
                · {{ selectedPack.asset_ids.length }} 件
                · {{ selectedPack.public ? '公开' : '私有' }}
              </div>
              <div v-if="selectedPack.description" class="text-sm text-ink-soft mt-1">{{ selectedPack.description }}</div>
            </div>
            <div class="flex gap-2">
              <BaseButton variant="soft" size="sm" pill @click="openEditPack(selectedPack!)">编辑</BaseButton>
              <BaseButton variant="soft" size="sm" pill @click="onDeletePack(selectedPack!)">删除</BaseButton>
              <BaseButton variant="soft" size="sm" pill @click="selectedPack = null">收起</BaseButton>
            </div>
          </div>
          <div class="grid grid-cols-[repeat(auto-fill,minmax(100px,1fr))] gap-2">
            <div v-for="a in selectedPack.assets" :key="a.id"
                 class="aspect-square rounded-lg bg-paper-deep p-1.5 grid place-items-center overflow-hidden" :title="a.name">
              <img :src="a.url" class="max-w-full max-h-full object-contain" :alt="a.name" />
              <div class="text-[10px] text-ink-mute truncate w-full text-center mt-0.5">{{ a.name }}</div>
            </div>
          </div>
        </BaseCard>

        <div v-if="myPacksLoading" class="text-center py-8 text-ink-mute">加载中…</div>
        <div v-else-if="myPacks.length === 0" class="text-center py-16 bg-white rounded-[var(--radius-card)] border border-paper-edge">
          <div class="text-5xl mb-2">📁</div>
          <div class="font-bold text-ink">还没有资产包</div>
          <div class="text-sm text-ink-soft mt-1">创建资产包来整理你的道具，还能分享给朋友</div>
        </div>
        <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
          <BaseCard
            v-for="p in myPacks"
            :key="p.code"
            hover
            class="overflow-hidden cursor-pointer relative group"
            :class="selectedPack?.code === p.code && 'ring-2 ring-accent'"
            @click="selectedPack = selectedPack?.code === p.code ? null : p"
          >
            <div class="h-24 grid place-items-center bg-gradient-to-br from-paper-deep to-gold-mute relative overflow-hidden">
              <div v-if="p.assets.length" class="grid grid-cols-3 gap-1 p-2">
                <div v-for="a in p.assets.slice(0, 6)" :key="a.id"
                     class="w-7 h-7 bg-white/70 rounded overflow-hidden grid place-items-center">
                  <img :src="a.url" class="max-w-full max-h-full object-contain" alt="" />
                </div>
              </div>
              <div v-else class="text-4xl">📁</div>
              <div class="absolute bottom-1 right-2 px-2 py-0.5 text-[11px] rounded-full bg-white/90 text-ink font-semibold">× {{ p.asset_ids.length }}</div>
              <span v-if="p.public" class="absolute top-1 left-1 px-1.5 py-0.5 text-[10px] rounded-full bg-good/90 text-white">公开</span>
            </div>
            <div class="p-3">
              <div class="font-semibold text-ink text-sm truncate">{{ p.name }}</div>
              <div class="text-xs text-ink-mute mt-0.5 flex items-center justify-between">
                <span class="font-mono text-accent-deep">{{ p.code }}</span>
                <span>{{ p.asset_ids.length }} 件</span>
              </div>
            </div>
          </BaseCard>
        </div>
      </template>
    </template>

    <PackEditModal :open="packModalOpen" :edit-pack="editingPack" @close="packModalOpen = false" @saved="onPackSaved" />

    <!-- 分享码查询结果 modal -->
    <BaseModal :open="!!importedPack" title="分享包内容" :max-width="'520px'" @close="importedPack = null">
      <template v-if="importedPack">
        <div class="font-bold text-ink text-lg">{{ importedPack.name }}</div>
        <div class="text-xs text-ink-mute mt-0.5">
          码 <span class="font-mono text-accent-deep">{{ importedPack.code }}</span>
          · {{ importedPack.asset_ids.length }} 件
        </div>
        <p v-if="importedPack.description" class="text-sm text-ink-soft mt-2 mb-3">{{ importedPack.description }}</p>
        <div class="grid grid-cols-5 gap-2 mt-3">
          <div v-for="a in importedPack.assets" :key="a.id"
               class="aspect-square rounded-lg bg-paper-deep p-1 grid place-items-center overflow-hidden"
               :title="a.name">
            <img :src="a.url" class="max-w-full max-h-full object-contain" alt="" />
          </div>
        </div>
      </template>
      <template #footer>
        <BaseButton variant="soft" pill @click="importedPack = null">取消</BaseButton>
        <BaseButton pill @click="addPackAssetsToMine">全部加到我的资产 →</BaseButton>
      </template>
    </BaseModal>
  </div>
</template>
