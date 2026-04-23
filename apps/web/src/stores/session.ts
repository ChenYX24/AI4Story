// 本地会话历史 + 进行中 playState 快照。
// playState 让用户翻出去再回来、或下次再玩同一故事时，能选择"继续"在原进度上。
// 阶段 3 接入真账户后改为后端 sessions 表。
import { defineStore } from "pinia";
import { useLocalStorage } from "@vueuse/core";
import type { Operation, CustomProp, InteractResponse, Interaction } from "@/api/types";

export interface SessionRecord {
  id: string;
  story_id: string;
  story_title: string;
  started_at: string;
  finished_at?: string;
  report_ready?: boolean;
}

export interface FlowItem {
  type: "narrative" | "interactive" | "dynamic";
  sceneIdx: number;
  visited: boolean;
}

export interface SessionPlayState {
  story_id: string;
  story_title?: string;
  cursor: number;
  highestUnlocked: number;
  flow: FlowItem[];
  // Map 序列化为对象（key: sceneIdx.toString()）
  dynamicByScene: Record<string, {
    payload: InteractResponse;
    snapOps: Operation[];
    snapProps: CustomProp[];
  }>;
  interactByScene: Record<string, {
    placed: any[];
    ops: Operation[];
    customProps: CustomProp[];
  }>;
  interactions: Interaction[];
  comicUrls: string[];
  updatedAt: string;
}

export const useSessionStore = defineStore("session", () => {
  const list = useLocalStorage<SessionRecord[]>("mindshow_sessions", []);
  // 进行中的游玩状态 —— 每个 story 一份快照；完成或用户覆盖后清除
  const playStates = useLocalStorage<Record<string, SessionPlayState>>("mindshow_play_states", {});

  function start(story_id: string, story_title: string): string {
    const id = "s_" + Date.now().toString(36);
    list.value.unshift({ id, story_id, story_title, started_at: new Date().toISOString() });
    if (list.value.length > 100) list.value.length = 100;
    return id;
  }

  function markReportReady(id: string) {
    const r = list.value.find((s) => s.id === id);
    if (!r) return;
    r.report_ready = true;
    r.finished_at = new Date().toISOString();
  }

  function remove(id: string) {
    list.value = list.value.filter((s) => s.id !== id);
  }

  function clearAllForStory(storyId: string) {
    list.value = list.value.filter((s) => s.story_id !== storyId);
  }

  function clear() { list.value = []; }

  // ---- playState API ----
  function savePlayState(state: SessionPlayState) {
    playStates.value = { ...playStates.value, [state.story_id]: state };
  }
  function getPlayState(storyId: string): SessionPlayState | undefined {
    return playStates.value?.[storyId];
  }
  function clearPlayState(storyId: string) {
    const { [storyId]: _, ...rest } = playStates.value || {};
    playStates.value = rest;
  }
  function hasInProgress(storyId: string): boolean {
    const ps = getPlayState(storyId);
    return !!ps && ps.cursor < ps.flow.length - 1;
  }

  return {
    list, playStates,
    start, markReportReady, remove, clearAllForStory, clear,
    savePlayState, getPlayState, clearPlayState, hasInProgress,
  };
});
