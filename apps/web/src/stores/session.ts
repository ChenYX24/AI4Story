// 本地会话历史 + 进行中 playState 快照 + 后端持久化（混合存储）。
import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import type { Operation, CustomProp, InteractResponse, Interaction } from "@/api/types";
import type { FlowNode, PendingDynamicRecord } from "@/stores/story";
import { getAuthToken } from "@/api/client";
import {
  createSessionApi, updateSessionApi, fetchSessionsApi, deleteSessionApi,
} from "@/api/endpoints";

export interface SessionRecord {
  id: string;
  backend_session_id?: string;
  story_id: string;
  story_title: string;
  started_at: string;
  finished_at?: string;
  report_ready?: boolean;
  report_status?: "idle" | "generating" | "ready" | "failed";
  report_payload?: any;
  report_error?: string;
  play_state?: SessionPlayState;
  comic_urls?: string[];
  custom_props?: CustomProp[];
  interactions?: Interaction[];
  report_comics?: string[];
  report_props?: CustomProp[];
}

export type FlowItem = FlowNode;

export interface ChatMsg { role: "user" | "assistant"; text: string; }

export interface SessionPlayState {
  session_id: string;
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

function readJson<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) || "") as T; }
  catch { return fallback; }
}

export const useSessionStore = defineStore("session", () => {
  const scope = ref("guest");
  const list = ref<SessionRecord[]>([]);
  // playStates 按 session_id 存；同一 story_id 可以有多个互不污染的历史会话。
  const playStates = ref<Record<string, SessionPlayState>>({});
  const generatedNotices = ref<Record<string, boolean>>({});
  // 后端 session id 映射：local session_id → backend session id
  const backendIds = ref<Record<string, string>>({});
  // 防抖定时器
  const _syncTimers = new Map<string, ReturnType<typeof setTimeout>>();
  const reportPromises = new Map<string, Promise<any>>();
  // 待写入 list 的"占位"会话 — 用户没翻过第一页就不会真的写进历史。
  const pendingStarts = new Map<string, { story_id: string; story_title: string; started_at: string }>();

  const key = (name: string) => `mindshow_${scope.value}_${name}`;

  function hasValidFlow(ps?: SessionPlayState): ps is SessionPlayState {
    return !!ps && !!ps.story_id && Array.isArray(ps.flow) && ps.flow.length > 0;
  }

  function loadScope(userId?: string | null) {
    for (const timer of _syncTimers.values()) clearTimeout(timer);
    _syncTimers.clear();
    reportPromises.clear();
    pendingStarts.clear();
    backendIds.value = {};
    scope.value = userId || "guest";
    const rawList = readJson<SessionRecord[]>(key("sessions"), []);
    list.value = rawList.filter((record) => !record.play_state || hasValidFlow(record.play_state));
    const rawStates = readJson<Record<string, SessionPlayState>>(key("play_states"), {});
    playStates.value = Object.fromEntries(
      Object.entries(rawStates).filter(([sid, state]) => state?.session_id === sid && hasValidFlow(state)),
    );
    generatedNotices.value = readJson<Record<string, boolean>>(key("generated_notices"), {});
    normalizeOpenSessions();
  }

  function persistScope() {
    localStorage.setItem(key("sessions"), JSON.stringify(list.value));
    localStorage.setItem(key("play_states"), JSON.stringify(playStates.value));
    localStorage.setItem(key("generated_notices"), JSON.stringify(generatedNotices.value));
  }

  loadScope(null);
  watch([list, playStates, generatedNotices], persistScope, { deep: true });

  function start(story_id: string, story_title: string): string {
    pruneOpenSessionsForStory(story_id);
    const id = "s_" + Date.now().toString(36);
    pendingStarts.set(id, { story_id, story_title, started_at: new Date().toISOString() });
    return id;
  }

  function ensure(story_id: string, story_title: string): string {
    const active = list.value.find((s) => (
      s.story_id === story_id
      && !s.finished_at
      && !s.report_ready
      && !!getSessionState(s.id)
    ));
    if (active) {
      if (story_title && active.story_title !== story_title) active.story_title = story_title;
      return active.id;
    }
    return start(story_id, story_title);
  }

  function currentForStory(storyId: string): SessionRecord | undefined {
    return list.value.find((s) => s.story_id === storyId && !s.finished_at && !s.report_ready)
      || list.value.find((s) => s.story_id === storyId);
  }

  function getById(id?: string | null): SessionRecord | undefined {
    if (!id) return undefined;
    return list.value.find((s) => s.id === id);
  }

  function getSessionState(sessionId?: string | null): SessionPlayState | undefined {
    if (!sessionId) return undefined;
    return playStates.value?.[sessionId] || list.value.find((s) => s.id === sessionId)?.play_state;
  }

  function isOpenState(ps?: SessionPlayState): ps is SessionPlayState {
    return hasValidFlow(ps) && ps.cursor > 0 && ps.cursor < ps.flow.length - 1;
  }

  function markReportReady(id: string) {
    const r = list.value.find((s) => s.id === id);
    if (!r) return;
    r.report_ready = true;
    r.report_status = "ready";
    r.finished_at = new Date().toISOString();
  }

  function markReportGenerating(id: string) {
    const r = list.value.find((s) => s.id === id);
    if (!r) return;
    r.report_status = "generating";
  }

  function snapshotFromState(state?: SessionPlayState) {
    if (!state) return {};
    const customMap = new Map<string, CustomProp>();
    for (const it of state.interactions || []) {
      for (const cp of it.custom_props || []) {
        customMap.set(`${cp.name}:${cp.url}`, { ...cp });
      }
    }
    for (const key of Object.keys(state.interactByScene || {})) {
      for (const cp of state.interactByScene[key]?.customProps || []) {
        customMap.set(`${cp.name}:${cp.url}`, { ...cp });
      }
    }
    return {
      play_state: state,
      comic_urls: [...(state.comicUrls || [])],
      report_comics: [...(state.comicUrls || [])],
      custom_props: Array.from(customMap.values()),
      report_props: Array.from(customMap.values()),
      interactions: (state.interactions || []).map((i) => ({ ...i })),
    };
  }

  function updateSnapshot(id: string, state?: SessionPlayState) {
    const r = list.value.find((s) => s.id === id);
    if (!r) return;
    Object.assign(r, snapshotFromState(state));
  }

  function saveReport(id: string, payload: any, state?: SessionPlayState) {
    const r = list.value.find((s) => s.id === id);
    if (!r) return;
    Object.assign(r, snapshotFromState(state || r.play_state));
    r.report_payload = payload;
    r.report_error = undefined;
    markReportReady(id);
  }

  function failReport(id: string, error: string) {
    const r = list.value.find((s) => s.id === id);
    if (!r) return;
    r.report_status = "failed";
    r.report_error = error;
  }

  function setReportPromise(id: string, p: Promise<any>) {
    reportPromises.set(id, p);
    p.finally(() => reportPromises.delete(id)).catch(() => {});
  }

  function getReportPromise(id: string) {
    return reportPromises.get(id);
  }

  function remove(id: string) {
    list.value = list.value.filter((s) => s.id !== id);
  }

  function pruneOpenSessionsForStory(storyId: string, keepId?: string) {
    const toRemove = list.value.filter((s) => (
      s.story_id === storyId
      && s.id !== keepId
      && !s.finished_at
      && !s.report_ready
      && s.report_status !== "generating"
    ));
    for (const s of toRemove) {
      deleteSession(s.id, { remote: false });
    }
    const nextStates = { ...playStates.value };
    let changed = false;
    for (const [sid, ps] of Object.entries(nextStates)) {
      if (ps.story_id !== storyId || sid === keepId) continue;
      delete nextStates[sid];
      changed = true;
    }
    if (changed) playStates.value = nextStates;
  }

  function normalizeOpenSessions() {
    const storyIds = new Set([
      ...list.value.map((s) => s.story_id),
      ...Object.values(playStates.value || {}).map((ps) => ps.story_id),
    ]);
    for (const storyId of storyIds) {
      const candidates = openStateCandidates(storyId);
      pruneOpenSessionsForStory(storyId, candidates[0]?.sessionId);
    }
  }

  function deleteSession(sessionId: string, opts: { remote?: boolean } = {}) {
    const record = list.value.find((s) => s.id === sessionId);
    const timer = _syncTimers.get(sessionId);
    if (timer) {
      clearTimeout(timer);
      _syncTimers.delete(sessionId);
    }
    const bid = backendIds.value[sessionId] || record?.backend_session_id;
    if (opts.remote !== false && bid && getAuthToken()) {
      deleteSessionApi(bid).catch(() => {});
    }
    const { [sessionId]: _, ...restStates } = playStates.value || {};
    playStates.value = restStates;
    delete backendIds.value[sessionId];
    reportPromises.delete(sessionId);
    pendingStarts.delete(sessionId);
    list.value = list.value.filter((s) => s.id !== sessionId);
    return record;
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
    // 第一页（cursor === 0）= 仅打开了故事但还没真的开始玩，不算"进行中"。
    // 跳过持久化 + 不进历史会话列表，避免：
    //   (a) 下次重新进入这个故事时弹"继续上次的玩法？"
    //   (b) 历史会话里堆一堆 0 进度的空记录
    if (!hasValidFlow(state) || state.cursor === 0) return;
    let record = list.value.find((s) => s.id === state.session_id && s.story_id === state.story_id);
    if (!record) {
      // 用户翻过第一页 → 把先前 start() 占位的会话真正写入 list。
      const pending = pendingStarts.get(state.session_id);
      if (pending && pending.story_id !== state.story_id) return;
      record = {
        id: state.session_id,
        story_id: state.story_id,
        story_title: state.story_title || pending?.story_title || state.story_id,
        started_at: pending?.started_at || state.updatedAt || new Date().toISOString(),
      };
      list.value.unshift(record);
      if (list.value.length > 100) list.value.length = 100;
      pendingStarts.delete(state.session_id);
    }
    if (record.finished_at) return;
    playStates.value = { ...playStates.value, [state.session_id]: state };
    record.story_title = state.story_title || record.story_title;
    Object.assign(record, snapshotFromState(state));
    _debouncedSync(state.session_id, state);
  }

  function getPlayState(sessionId: string): SessionPlayState | undefined {
    return playStates.value?.[sessionId];
  }

  function clearPlayState(sessionId: string) {
    const timer = _syncTimers.get(sessionId);
    if (timer) {
      clearTimeout(timer);
      _syncTimers.delete(sessionId);
    }
    const finishedState = getSessionState(sessionId);
    const { [sessionId]: _, ...rest } = playStates.value || {};
    playStates.value = rest;
    const record = list.value.find((s) => s.id === sessionId);
    const bid = backendIds.value[sessionId] || record?.backend_session_id;
    if (bid && getAuthToken()) {
      updateSessionApi(bid, { play_state: finishedState || {}, status: "finished" }).catch(() => {});
    }
    delete backendIds.value[sessionId];
  }

  function hasInProgress(storyId: string): boolean {
    return !!getInProgressForStory(storyId);
  }

  function getInProgressForStory(storyId: string): { sessionId: string; state: SessionPlayState } | null {
    const candidates = openStateCandidates(storyId);
    const found = candidates[0];
    if (found) pruneOpenSessionsForStory(storyId, found.sessionId);
    else pruneOpenSessionsForStory(storyId);
    return found ? { sessionId: found.sessionId, state: found.state } : null;
  }

  function completeSession(sessionId: string, state?: SessionPlayState) {
    const record = list.value.find((s) => s.id === sessionId);
    const finalState = state || getSessionState(sessionId);
    if (record) {
      Object.assign(record, snapshotFromState(finalState));
      record.finished_at = record.finished_at || new Date().toISOString();
    }
    clearPlayState(sessionId);
  }

  const completedReports = computed(() => list.value.filter((s) => s.report_ready && s.report_payload));

  function openStateCandidates(storyId: string): Array<{ sessionId: string; state: SessionPlayState; updatedAt: string }> {
    const byId = new Map<string, { sessionId: string; state: SessionPlayState; updatedAt: string }>();
    for (const [sessionId, state] of Object.entries(playStates.value || {})) {
      if (state.story_id !== storyId || !isOpenState(state)) continue;
      byId.set(sessionId, { sessionId, state, updatedAt: state.updatedAt || "" });
    }
    for (const record of list.value) {
      if (record.story_id !== storyId || record.finished_at || record.report_ready || record.report_status === "generating") continue;
      const state = record.play_state;
      if (!isOpenState(state)) continue;
      byId.set(record.id, {
        sessionId: record.id,
        state,
        updatedAt: state.updatedAt || record.started_at || "",
      });
    }
    return Array.from(byId.values())
      .sort((a, b) => Date.parse(b.updatedAt || "") - Date.parse(a.updatedAt || ""));
  }

  // 后端防抖同步（5s）
  function _debouncedSync(sessionId: string, state: SessionPlayState) {
    if (!getAuthToken()) return;
    const existing = _syncTimers.get(sessionId);
    if (existing) clearTimeout(existing);
    _syncTimers.set(sessionId, setTimeout(() => {
      _syncTimers.delete(sessionId);
      _syncToBackend(sessionId, state);
    }, 5000));
  }

  async function _syncToBackend(sessionId: string, state: SessionPlayState) {
    try {
      const record = list.value.find((s) => s.id === sessionId);
      const bid = backendIds.value[sessionId] || record?.backend_session_id;
      if (bid) {
        await updateSessionApi(bid, { play_state: state as any });
        backendIds.value = { ...backendIds.value, [sessionId]: bid };
      } else {
        const r = await createSessionApi({ story_id: state.story_id, play_state: state as any });
        backendIds.value = { ...backendIds.value, [sessionId]: r.id };
        if (record) record.backend_session_id = r.id;
      }
    } catch { /* 后端不可用时静默失败，localStorage 仍有数据 */ }
  }

  // 从后端拉取未完成会话（登录后 + 进入故事时调用）
  function mergeRemoteSession(remote: any): { sessionId: string; state?: SessionPlayState } | null {
    const ps = remote.play_state as SessionPlayState | undefined;
    const storyId = String(remote.story_id || ps?.story_id || "");
    if (!storyId) return null;
    const hasFlow = hasValidFlow(ps);
    if (!hasFlow && remote.status !== "finished") return null;
    const sessionId = String((hasFlow && ps?.session_id) || remote.id);
    const state = hasFlow ? { ...ps, session_id: sessionId, story_id: storyId } : undefined;
    const started = state?.updatedAt || (remote.created_at ? new Date(remote.created_at * 1000).toISOString() : new Date().toISOString());
    const existing = list.value.find((s) => s.id === sessionId || s.backend_session_id === remote.id);
    const snapshot = snapshotFromState(state);
    const record: SessionRecord = existing || {
      id: sessionId,
      story_id: storyId,
      story_title: state?.story_title || storyId,
      started_at: started,
    };
    record.backend_session_id = remote.id;
    record.story_id = storyId;
    record.story_title = state?.story_title || record.story_title || storyId;
    record.started_at = record.started_at || started;
    record.finished_at = remote.status === "finished" ? (record.finished_at || started) : record.finished_at;
    Object.assign(record, snapshot);
    if (state && isOpenState(state) && remote.status === "playing") {
      backendIds.value = { ...backendIds.value, [sessionId]: remote.id };
      playStates.value = { ...playStates.value, [sessionId]: state };
    }
    if (!existing) list.value.unshift(record);
    return { sessionId, state };
  }

  async function fetchRemoteSessionsAll(): Promise<void> {
    if (!getAuthToken()) return;
    try {
      const { sessions } = await fetchSessionsApi();
      for (const remote of sessions) mergeRemoteSession(remote);
      list.value = [...list.value]
        .sort((a, b) => Date.parse(b.play_state?.updatedAt || b.started_at || "") - Date.parse(a.play_state?.updatedAt || a.started_at || ""))
        .slice(0, 100);
      normalizeOpenSessions();
    } catch { /* silent */ }
  }

  async function fetchRemoteSession(storyId: string): Promise<{ sessionId: string; state: SessionPlayState } | null> {
    if (!getAuthToken()) return null;
    try {
      const { sessions } = await fetchSessionsApi(storyId);
      const playing = sessions.find((s) => s.status === "playing" && s.play_state?.story_id === storyId);
      if (!playing) return null;
      const merged = mergeRemoteSession(playing);
      if (merged?.state && isOpenState(merged.state)) {
        pruneOpenSessionsForStory(storyId, merged.sessionId);
        return { sessionId: merged.sessionId, state: merged.state };
      }
    } catch { /* silent */ }
    return null;
  }

  return {
    list, playStates, backendIds, generatedNotices,
    loadScope,
    start, ensure, currentForStory, getById,
    markReportReady, markReportGenerating, saveReport, failReport, setReportPromise, getReportPromise, updateSnapshot,
    remove, deleteSession, pruneOpenSessionsForStory, normalizeOpenSessions, clearAllForStory, clear,
    markGeneratedNotice, clearGeneratedNotice, hasGeneratedNotice,
    savePlayState, getPlayState, getSessionState, clearPlayState, hasInProgress, getInProgressForStory, completeSession,
    fetchRemoteSession, fetchRemoteSessionsAll, completedReports,
  };
});
