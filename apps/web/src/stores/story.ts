import { defineStore } from "pinia";
import { ref } from "vue";
import type { Scene, StoryCard, StoryDetail } from "@/api/types";
import { fetchStories, fetchStory, fetchScene } from "@/api/endpoints";

export const useStoryStore = defineStore("story", () => {
  const list = ref<StoryCard[]>([]);
  const current = ref<StoryDetail | null>(null);
  const sceneCache = ref<Map<number, Scene>>(new Map());

  // 节点流：narrative + interactive 穿插
  const flow = ref<Array<{ type: "narrative" | "interactive"; sceneIdx: number; visited: boolean }>>([]);
  const cursor = ref(0);
  const highestUnlocked = ref(0);

  async function loadList() {
    const r = await fetchStories();
    list.value = r.stories;
    return r.stories;
  }

  async function loadStory(id: string) {
    const s = await fetchStory(id);
    // 后端不回 id，前端手工补上以便后续判断 current.id === routeId
    s.id = id;
    if (!s.title) {
      const card = list.value.find((x) => x.id === id);
      if (card) s.title = card.title;
    }
    current.value = s;
    flow.value = (s.scenes || []).map((sc) => ({
      type: sc.type,
      sceneIdx: sc.index,
      visited: false,
    }));
    cursor.value = 0;
    highestUnlocked.value = 0;
    return s;
  }

  async function ensureScene(idx: number): Promise<Scene> {
    if (sceneCache.value.has(idx)) return sceneCache.value.get(idx)!;
    const sc = await fetchScene(idx);
    sceneCache.value.set(idx, sc);
    return sc;
  }

  function reset() {
    current.value = null;
    flow.value = [];
    cursor.value = 0;
    highestUnlocked.value = 0;
    sceneCache.value.clear();
  }

  return { list, current, flow, cursor, highestUnlocked, loadList, loadStory, ensureScene, reset };
});
