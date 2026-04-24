// Asset shelf is scoped per account so one browser profile cannot leak assets between users.
import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import { createMyAsset, deleteMyAsset, fetchMyAssets } from "@/api/endpoints";
import { getAuthToken } from "@/api/client";

export interface MyAsset {
  id: string;
  name: string;
  url: string;
  kind: "character" | "object";
  origin_story_id?: string;
  origin_scene_idx?: number;
  created_at: number;
}

function readJson<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) || "") as T; }
  catch { return fallback; }
}

export const useAssetShelfStore = defineStore("assetShelf", () => {
  const scope = ref("guest");
  const assetIds = ref<string[]>([]);
  const bundleIds = ref<string[]>([]);
  const myAssets = ref<MyAsset[]>([]);

  const key = (name: string) => `mindshow_${scope.value}_${name}`;
  function loadScope(userId?: string | null) {
    scope.value = userId || "guest";
    assetIds.value = readJson<string[]>(key("asset_shelf"), []);
    bundleIds.value = readJson<string[]>(key("bundle_shelf"), []);
    myAssets.value = readJson<MyAsset[]>(key("my_assets"), []);
  }
  function persist() {
    localStorage.setItem(key("asset_shelf"), JSON.stringify(assetIds.value));
    localStorage.setItem(key("bundle_shelf"), JSON.stringify(bundleIds.value));
    localStorage.setItem(key("my_assets"), JSON.stringify(myAssets.value));
  }
  loadScope(null);
  watch([assetIds, bundleIds, myAssets], persist, { deep: true });

  const assetSet = computed(() => new Set(assetIds.value));
  const bundleSet = computed(() => new Set(bundleIds.value));

  function hasAsset(id: string) { return assetSet.value.has(id); }
  function hasBundle(id: string) { return bundleSet.value.has(id); }

  function toggleAsset(id: string) {
    if (hasAsset(id)) assetIds.value = assetIds.value.filter((x) => x !== id);
    else assetIds.value = [...assetIds.value, id];
  }
  function toggleBundle(id: string) {
    if (hasBundle(id)) bundleIds.value = bundleIds.value.filter((x) => x !== id);
    else bundleIds.value = [...bundleIds.value, id];
  }

  function removeAsset(id: string) { assetIds.value = assetIds.value.filter((x) => x !== id); }
  function removeBundle(id: string) { bundleIds.value = bundleIds.value.filter((x) => x !== id); }

  function addMyAsset(a: Omit<MyAsset, "id" | "created_at"> & { id?: string; created_at?: number }): MyAsset {
    const full: MyAsset = {
      id: a.id || `my-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: a.name,
      url: a.url,
      kind: a.kind,
      origin_story_id: a.origin_story_id,
      origin_scene_idx: a.origin_scene_idx,
      created_at: a.created_at || Date.now(),
    };
    myAssets.value = [full, ...myAssets.value.filter((x) => x.id !== full.id)];
    if (getAuthToken()) {
      createMyAsset({
        id: full.id,
        name: full.name,
        url: full.url,
        kind: full.kind,
        origin_story_id: full.origin_story_id,
        origin_scene_idx: full.origin_scene_idx,
      }).catch((e) => console.warn("[assetShelf] sync add failed:", e?.message || e));
    }
    return full;
  }
  function removeMyAsset(id: string) {
    myAssets.value = myAssets.value.filter((x) => x.id !== id);
    if (getAuthToken()) {
      deleteMyAsset(id).catch((e) => console.warn("[assetShelf] sync delete failed:", e?.message || e));
    }
  }

  async function pullFromServer() {
    if (!getAuthToken()) return;
    try {
      const resp = await fetchMyAssets();
      myAssets.value = resp.assets.map((s) => ({
        id: s.id,
        name: s.name,
        url: s.url,
        kind: (s.kind as "character" | "object"),
        origin_story_id: s.origin_story_id,
        origin_scene_idx: s.origin_scene_idx,
        created_at: s.created_at,
      }));
    } catch (e) {
      console.warn("[assetShelf] pullFromServer failed:", (e as any)?.message || e);
    }
  }

  const total = computed(() => assetIds.value.length + bundleIds.value.length + myAssets.value.length);

  return {
    assetIds, bundleIds, assetSet, bundleSet, myAssets, total,
    hasAsset, hasBundle,
    toggleAsset, toggleBundle,
    removeAsset, removeBundle,
    addMyAsset, removeMyAsset,
    loadScope, pullFromServer,
  };
});
