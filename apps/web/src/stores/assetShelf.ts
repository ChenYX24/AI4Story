// 资产收藏 —— 独立于故事书架 (useShelfStore)。
// 三条独立 list：
//   assetIds / bundleIds — 收藏的公共资产（id 指向公共库）
//   myAssets — 用户自创道具（互动页生成的 AI 道具、上传/拍照/画板做的道具）
// 登录后自动与后端 /api/user/assets 双向同步（未登录时仅 localStorage）。
import { defineStore } from "pinia";
import { computed } from "vue";
import { useLocalStorage } from "@vueuse/core";
import { createMyAsset, deleteMyAsset, syncMyAssets } from "@/api/endpoints";
import { getAuthToken } from "@/api/client";

export interface MyAsset {
  id: string;          // 客户端生成的稳定 id（时间戳 + 随机）
  name: string;
  url: string;
  kind: "character" | "object";
  origin_story_id?: string;
  origin_scene_idx?: number;
  created_at: number;
}

export const useAssetShelfStore = defineStore("assetShelf", () => {
  // 单件资产（公共库收藏）
  const assetIds = useLocalStorage<string[]>("mindshow_asset_shelf", []);
  // 打包资产（公共库收藏）
  const bundleIds = useLocalStorage<string[]>("mindshow_bundle_shelf", []);
  // 我自己创造的道具（互动页 AI 生成 / 上传 / 画板）
  const myAssets = useLocalStorage<MyAsset[]>("mindshow_my_assets", []);

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

  function addMyAsset(a: Omit<MyAsset, "id" | "created_at"> & { id?: string }): MyAsset {
    const full: MyAsset = {
      id: a.id || `my-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: a.name,
      url: a.url,
      kind: a.kind,
      origin_story_id: a.origin_story_id,
      origin_scene_idx: a.origin_scene_idx,
      created_at: Date.now(),
    };
    myAssets.value = [full, ...myAssets.value];
    // 后台同步到服务端（登录态），失败不阻塞本地
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

  // 登录后调用：把本地未上传的 push 给服务端并 pull 全量回来合并
  async function pullFromServer() {
    if (!getAuthToken()) return;
    try {
      const resp = await syncMyAssets(myAssets.value.map((a) => ({
        id: a.id, name: a.name, url: a.url, kind: a.kind,
        origin_story_id: a.origin_story_id, origin_scene_idx: a.origin_scene_idx,
      })));
      // 合并结果（服务端是权威）
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
    pullFromServer,
  };
});
