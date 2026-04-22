// 收藏：从公共平台"加到书架"的 story ids（MVP 本地持久，阶段 2 入账户 DB）
import { defineStore } from "pinia";
import { computed } from "vue";
import { useLocalStorage } from "@vueuse/core";

export const useShelfStore = defineStore("shelf", () => {
  const ids = useLocalStorage<string[]>("mindshow_shelf", []);
  const set = computed(() => new Set(ids.value));

  function add(id: string) {
    if (!set.value.has(id)) ids.value = [...ids.value, id];
  }
  function remove(id: string) {
    ids.value = ids.value.filter((x) => x !== id);
  }
  function has(id: string) { return set.value.has(id); }
  function toggle(id: string) { has(id) ? remove(id) : add(id); }

  return { ids, set, add, remove, has, toggle };
});
