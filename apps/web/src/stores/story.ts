import { defineStore } from "pinia";
import { ref } from "vue";
import type { Scene, StoryCard, StoryDetail, Interaction, CustomProp, Operation, InteractResponse } from "@/api/types";
import { fetchStories, fetchStory, fetchScene } from "@/api/endpoints";

export interface DynamicNodeRecord {
  payload: InteractResponse;
  snapOps: Operation[];
  snapProps: CustomProp[];
}

export const useStoryStore = defineStore("story", () => {
  const list = ref<StoryCard[]>([]);
  const current = ref<StoryDetail | null>(null);
  const sceneCache = ref<Map<number, Scene>>(new Map());

  // 节点流：narrative + interactive 穿插；互动完成生成 dynamic 幕，splice 插入在 interactive 之后
  // 对 dynamic 类型，sceneIdx 等于其源 interactive 场景的 sceneIdx（作为 dynamicByScene 的 key）
  const flow = ref<Array<{ type: "narrative" | "interactive" | "dynamic"; sceneIdx: number; visited: boolean }>>([]);
  const cursor = ref(0);
  const highestUnlocked = ref(0);

  // 用户的交互快照 — 送给报告
  const interactions = ref<Interaction[]>([]);
  // 当前 story 内累计 custom props + comic urls（共享 + 分享面板用）
  const comicUrls = ref<string[]>([]);
  // 动态节点持久化：sceneIdx → 该 interactive 场景已生成的 dynamic 结果（可切换回看）
  const dynamicByScene = ref<Map<number, DynamicNodeRecord>>(new Map());

  function recordDynamic(sceneIdx: number, record: DynamicNodeRecord) {
    if (!dynamicByScene.value) dynamicByScene.value = new Map();
    dynamicByScene.value.set(sceneIdx, {
      payload: record.payload,
      snapOps: record.snapOps.map((o) => ({ ...o })),
      snapProps: record.snapProps.map((p) => ({ ...p })),
    });
  }

  // 把 dynamic 幕 splice 到当前 interactive 节点之后
  function insertDynamicAfter(afterIdx: number, sourceSceneIdx: number) {
    // 先移除该 source 的旧 dynamic（重玩时避免重复）
    flow.value = flow.value.filter(
      (f) => !(f.type === "dynamic" && f.sceneIdx === sourceSceneIdx),
    );
    // 插到 afterIdx 后面
    const insertAt = Math.min(afterIdx + 1, flow.value.length);
    flow.value.splice(insertAt, 0, { type: "dynamic", sceneIdx: sourceSceneIdx, visited: true });
    return insertAt;
  }

  // 顶栏跳转请求：StoryPage 在 mount 时注册自己的 loadCursor，TopBar 点击缩略图调 requestJump
  const _jumpHandler = ref<((idx: number) => void) | null>(null);
  function setJumpHandler(fn: ((idx: number) => void) | null) { _jumpHandler.value = fn; }
  function requestJump(idx: number) {
    if (_jumpHandler.value) _jumpHandler.value(idx);
  }

  function addInteraction(snap: {
    scene_idx: number;
    interaction_goal?: string;
    ops: Operation[];
    custom_props: CustomProp[];
    dynamic_summary?: string;
    comic_url?: string;
  }) {
    interactions.value.push({
      scene_idx: snap.scene_idx,
      interaction_goal: snap.interaction_goal,
      ops: snap.ops.map((o) => ({ ...o })),
      custom_props: snap.custom_props.map((c) => ({ ...c })),
      dynamic_summary: snap.dynamic_summary,
    });
    if (snap.comic_url && !comicUrls.value.includes(snap.comic_url)) {
      comicUrls.value.push(snap.comic_url);
    }
  }

  function trackComic(url?: string) {
    if (url && !comicUrls.value.includes(url)) comicUrls.value.push(url);
  }

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
    interactions.value = [];
    comicUrls.value = [];
    dynamicByScene.value.clear();
  }

  return {
    list, current, flow, cursor, highestUnlocked,
    sceneCache,
    interactions, comicUrls,
    dynamicByScene,
    loadList, loadStory, ensureScene, reset,
    addInteraction, trackComic, recordDynamic, insertDynamicAfter,
    setJumpHandler, requestJump,
  };
});
