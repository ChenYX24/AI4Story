// 本地会话历史 + 进行中 playState 快照 + 后端持久化（混合存储）。
import { defineStore } from "pinia";
import { useLocalStorage } from "@vueuse/core";
import { ref } from "vue";
import type { Operation, CustomProp, InteractResponse, Interaction } from "@/api/types";
import type { FlowNode, PendingDynamicRecord } from "@/stores/story";
import { getAuthToken } from "@/api/client";
import {
  createSessionApi, updateSessionApi, fetchSessionsApi,
} from "@/api/endpoints";

export interface SessionRecord {
  id: string;
  story_id: string;
  story_title: string;
  started_at: string;
  finished_at?: string;
  report_ready?: boolean;
}

export type FlowItem = FlowNode;

export interface ChatMsg { role: "user" | "assistant"; text: string; }

export interface SessionPlayState {
  story_id: string;
  story_title?: string;
  cursor: number;
  highestUnlocked: number;
  flow: FlowItem[];
  dynamicByScene: Record<string, {
    payload: InteractResponse;
    snapOps: Operation[];
    snapProps: CustomProp[];
  }>;
  pendingDynamicByScene?: Record<string, PendingDynamicRecord>;
  interactByScene: Record<string, {
    placed: any[];
    ops: Operation[];
    customProps: CustomProp[];
  }>;
  interactions: Interaction[];
  comicUrls: string[];
  chatLogByScene?: Record<string, ChatMsg[]>;
  updatedAt: string;
}

export const useSessionStore = defineStore("session", () => {
  const list = useLocalStorage<SessionRecord[]>("mindshow_sessions", []);
  const playStates = useLocalStorage<Record<string, SessionPlayState>>("mindshow_play_states", {});
  const generatedNotices = useLocalStorage<Record<string, boolean>>("mindshow_generated_notices", {});
  // 后端 session id 映射：story_id → backend session id
  const backendIds = ref<Record<string, string>>({});
  // 防抖定时器
  const _syncTimers = new Map<string, ReturnType<typeof setTimeout>>();

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

  function markGeneratedNotice(storyId: string) {
    generatedNotices.value = { ...generatedNotices.value, [storyId]: true };
  }

  function clearGeneratedNotice(storyId: string) {
    const { [storyId]: _, ...rest } = generatedNotices.value || {};
    generatedNotices.value = rest;
  }

  function hasGeneratedNotice(storyId: string): boolean {
    return !!generatedNotices.value?.[storyId];
  }

  // ---- playState API (localStorage 立即写 + 后端防抖同步) ----
  function savePlayState(state: SessionPlayState) {
    playStates.value = { ...playStates.value, [state.story_id]: state };
    _debouncedSync(state.story_id, state);
  }

  function getPlayState(storyId: string): SessionPlayState | undefined {
    return playStates.value?.[storyId];
  }

  function clearPlayState(storyId: string) {
    const { [storyId]: _, ...rest } = playStates.value || {};
    playStates.value = rest;
    // 后端也标记完成
    const bid = backendIds.value[storyId];
    if (bid && getAuthToken()) {
      updateSessionApi(bid, { play_state: {}, status: "finished" }).catch(() => {});
    }
    delete backendIds.value[storyId];
  }

  function hasInProgress(storyId: string): boolean {
    const ps = getPlayState(storyId);
    return !!ps && ps.cursor < ps.flow.length - 1;
  }

  // 后端防抖同步（5s）
  function _debouncedSync(storyId: string, state: SessionPlayState) {
    if (!getAuthToken()) return;
    const existing = _syncTimers.get(storyId);
    if (existing) clearTimeout(existing);
    _syncTimers.set(storyId, setTimeout(() => {
      _syncTimers.delete(storyId);
      _syncToBackend(storyId, state);
    }, 5000));
  }

  async function _syncToBackend(storyId: string, state: SessionPlayState) {
    try {
      const bid = backendIds.value[storyId];
      if (bid) {
        await updateSessionApi(bid, { play_state: state as any });
      } else {
        const r = await createSessionApi({ story_id: storyId, play_state: state as any });
        backendIds.value = { ...backendIds.value, [storyId]: r.id };
      }
    } catch { /* 后端不可用时静默失败，localStorage 仍有数据 */ }
  }

  // 从后端拉取未完成会话（登录后 + 进入故事时调用）
  async function fetchRemoteSession(storyId: string): Promise<SessionPlayState | null> {
    if (!getAuthToken()) return null;
    try {
      const { sessions } = await fetchSessionsApi(storyId);
      const playing = sessions.find((s) => s.status === "playing");
      if (!playing) return null;
      backendIds.value = { ...backendIds.value, [storyId]: playing.id };
      const ps = playing.play_state as unknown as SessionPlayState;
      if (ps && ps.flow?.length) {
        playStates.value = { ...playStates.value, [storyId]: ps };
        return ps;
      }
    } catch { /* silent */ }
    return null;
  }

  return {
    list, playStates, backendIds, generatedNotices,
    start, markReportReady, remove, clearAllForStory, clear,
    markGeneratedNotice, clearGeneratedNotice, hasGeneratedNotice,
    savePlayState, getPlayState, clearPlayState, hasInProgress,
    fetchRemoteSession,
  };
});
