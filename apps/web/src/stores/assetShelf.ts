// 资产收藏 —— 独立于故事书架 (useShelfStore)。
// 存在 localStorage；既收单件 (asset.id) 也收打包 (bundle.id)；
// 阶段 2 接账号后改为后端 user_assets / user_asset_bundles 表。
import { defineStore } from "pinia";
import { computed } from "vue";
import { useLocalStorage } from "@vueuse/core";

export const useAssetShelfStore = defineStore("assetShelf", () => {
  // 单件资产
  const assetIds = useLocalStorage<string[]>("mindshow_asset_shelf", []);
  // 打包资产
  const bundleIds = useLocalStorage<string[]>("mindshow_bundle_shelf", []);

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

  const total = computed(() => assetIds.value.length + bundleIds.value.length);

  return {
    assetIds, bundleIds, assetSet, bundleSet, total,
    hasAsset, hasBundle,
    toggleAsset, toggleBundle,
    removeAsset, removeBundle,
  };
});
