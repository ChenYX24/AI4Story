<!--
  MyAssetsModal —— 用户打开后可浏览账户下所有可用资产：
    · 本 session 造的 custom props (无服务器 id，用 url 兜底)
    · 服务端同步过来的 "我画的道具" (assetShelf.myAssets)
    · 收藏的官方/他人单件   (assetShelf.assetIds → 官方 assets 中查找)
    · 收藏的资产包           (assetShelf.bundleIds → 官方 bundles 展开)
    · 我创建的包            (fetchMyPacks，展开)
    · 官方默认单件           (public.assets 中「官方」category)
    · 官方默认资产包         (public.bundles 展开)
  所有条目按 unique id 去重（优先服务器 id，无则 url）。
  点击条目 → 调 emit("pick", asset) → 父组件直接落在舞台。
-->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import BaseModal from "./BaseModal.vue";
import {
  fetchPublicAssets,
  fetchMyPacks,
  type PackOut,
} from "@/api/endpoints";
import { useAssetShelfStore } from "@/stores/assetShelf";
import type { CustomProp, PublicAsset, PublicAssetBundle } from "@/api/types";

const props = defineProps<{
  open: boolean;
  sessionCustomProps: CustomProp[];
}>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "pick", asset: UnifiedAsset): void;
}>();

const assetShelf = useAssetShelfStore();

interface UnifiedAsset {
  id: string;                                // 去重 key
  name: string;
  url: string;
  kind: "character" | "object";
  origin: "mine" | "fav_single" | "fav_pack" | "my_pack" | "official_single" | "official_pack";
  pack_name?: string;                        // 来自资产包时显示所属包名
}

// ---- data sources ----
const publicAssets = ref<PublicAsset[]>([]);
const publicBundles = ref<PublicAssetBundle[]>([]);
const myPacks = ref<PackOut[]>([]);
const loading = ref(false);
const tab = ref<"all" | "character" | "object">("all");

async function load() {
  loading.value = true;
  try {
    const [pub, mine] = await Promise.allSettled([fetchPublicAssets(), fetchMyPacks()]);
    if (pub.status === "fulfilled") {
      publicAssets.value = pub.value.assets || [];
      publicBundles.value = pub.value.bundles || [];
    }
    if (mine.status === "fulfilled") {
      myPacks.value = mine.value.packs || [];
    }
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch(() => props.open, (o) => { if (o) load(); });

function guessKind(raw: any): "character" | "object" {
  const k = String(raw?.kind || "").toLowerCase();
  return k === "character" ? "character" : "object";
}

// 每类条目转成 UnifiedAsset —— 去重靠 id，下面会用 Map 合并
function fromSessionCustom(cp: CustomProp): UnifiedAsset {
  return {
    id: `custom-${cp.url}`,
    name: cp.name,
    url: cp.url,
    kind: "object",
    origin: "mine",
  };
}
function fromMyAsset(a: { id: string; name: string; url: string; kind: string }): UnifiedAsset {
  return { id: a.id, name: a.name, url: a.url, kind: guessKind(a), origin: "mine" };
}
function fromFavSingle(a: PublicAsset): UnifiedAsset {
  return { id: a.id, name: a.name, url: a.url, kind: guessKind(a), origin: "fav_single" };
}
function fromBundleItem(item: any, bundleName: string, origin: UnifiedAsset["origin"]): UnifiedAsset {
  const id = String(item.id || item.asset_id || `${item.name}-${item.url}`);
  return {
    id,
    name: String(item.name || ""),
    url: String(item.url || ""),
    kind: guessKind(item),
    origin,
    pack_name: bundleName,
  };
}

const allAssets = computed<UnifiedAsset[]>(() => {
  const merged = new Map<string, UnifiedAsset>();
  const urlSeen = new Set<string>();          // 二级去重：不同来源下同一 url 的资产视作同一件
  const put = (a: UnifiedAsset) => {
    if (!a.id || !a.url) return;
    if (urlSeen.has(a.url)) return;
    if (merged.has(a.id)) return;
    merged.set(a.id, a);
    urlSeen.add(a.url);
  };

  // 1. 本 session 造的 custom props —— 最高优先级
  for (const cp of props.sessionCustomProps || []) put(fromSessionCustom(cp));

  // 2. 我画的道具（跨 session、跨账号同步过来的）
  for (const a of assetShelf.myAssets) put(fromMyAsset(a));

  // 3. 我收藏的单件
  const favSingleIds = new Set(assetShelf.assetIds);
  for (const a of publicAssets.value) {
    if (favSingleIds.has(a.id)) put(fromFavSingle(a));
  }

  // 4. 我收藏的资产包 —— 展开成单件
  const favBundleIds = new Set(assetShelf.bundleIds);
  for (const b of publicBundles.value) {
    if (!favBundleIds.has(b.id)) continue;
    const items = (b as any).assets || (b as any).items || [];
    for (const it of items) put(fromBundleItem(it, b.name, "fav_pack"));
  }

  // 5. 我创建的资产包 —— 展开成单件
  for (const p of myPacks.value) {
    for (const it of p.assets || []) put(fromBundleItem(it, p.name, "my_pack"));
  }

  // 6. 官方默认单件（未收藏的也展示 —— 因为用户可能想直接拖用）
  for (const a of publicAssets.value) {
    if (!favSingleIds.has(a.id)) put({ ...fromFavSingle(a), origin: "official_single" });
  }

  // 7. 官方默认包（未收藏的）—— 展开
  for (const b of publicBundles.value) {
    if (favBundleIds.has(b.id)) continue;
    const items = (b as any).assets || (b as any).items || [];
    for (const it of items) put(fromBundleItem(it, b.name, "official_pack"));
  }

  return Array.from(merged.values());
});

const filtered = computed(() => {
  if (tab.value === "all") return allAssets.value;
  return allAssets.value.filter((a) => a.kind === tab.value);
});

const originLabel: Record<UnifiedAsset["origin"], string> = {
  mine: "我画的",
  fav_single: "已收藏",
  fav_pack: "收藏包",
  my_pack: "我的包",
  official_single: "官方",
  official_pack: "官方包",
};

function onPick(a: UnifiedAsset) {
  emit("pick", a);
  emit("close");
}
</script>

<template>
  <BaseModal :open="open" title="📦 我的资产" max-width="640px" @close="emit('close')">
    <div class="space-y-3">
      <div class="flex gap-2 text-xs">
        <button
          v-for="t in [{ k: 'all', label: '全部' }, { k: 'character', label: '人物' }, { k: 'object', label: '道具' }] as const"
          :key="t.k"
          class="px-3 py-1 rounded-full border border-paper-edge"
          :class="tab === t.k ? 'bg-accent text-white border-accent' : 'bg-paper hover:bg-paper-deep text-ink-soft'"
          @click="tab = t.k"
        >{{ t.label }}</button>
        <div class="ml-auto text-ink-mute text-xs self-center" v-if="!loading">共 {{ filtered.length }} 个</div>
        <div class="ml-auto text-ink-mute text-xs self-center animate-pulse" v-else>加载中…</div>
      </div>

      <div
        class="overflow-y-auto grid grid-cols-3 sm:grid-cols-4 gap-3 pr-1"
        style="max-height: 480px;"
      >
        <div v-if="!filtered.length && !loading" class="col-span-full text-center text-ink-mute text-sm py-12">
          还没有资产～先去收藏几件或自己画一个吧
        </div>
        <button
          v-for="a in filtered"
          :key="a.id"
          class="bg-paper-deep hover:bg-gold-mute/60 active:scale-95 rounded-lg p-2 flex flex-col items-center text-center border border-paper-edge hover:border-gold/40 transition"
          :title="`${a.name} —— 点击添加到舞台\n来源：${originLabel[a.origin]}${a.pack_name ? ` (${a.pack_name})` : ''}`"
          @click="onPick(a)"
        >
          <img v-if="a.url" :src="a.url" class="w-16 h-16 object-contain" :alt="a.name" />
          <div class="text-xs mt-1 text-ink truncate w-full">{{ a.name }}</div>
          <div class="text-[10px] text-ink-mute truncate w-full">
            {{ originLabel[a.origin] }}<template v-if="a.pack_name">·{{ a.pack_name }}</template>
          </div>
        </button>
      </div>
    </div>
  </BaseModal>
</template>
