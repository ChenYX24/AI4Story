// 简易本地会话历史 — 用户每开一个故事就记录一条；玩到报告标 ready
// 阶段 2 接入真账户后改为后端 sessions 表
import { defineStore } from "pinia";
import { useLocalStorage } from "@vueuse/core";

export interface SessionRecord {
  id: string;
  story_id: string;
  story_title: string;
  started_at: string;
  finished_at?: string;
  report_ready?: boolean;
}

export const useSessionStore = defineStore("session", () => {
  const list = useLocalStorage<SessionRecord[]>("mindshow_sessions", []);

  function start(story_id: string, story_title: string): string {
    const id = "s_" + Date.now().toString(36);
    list.value.unshift({ id, story_id, story_title, started_at: new Date().toISOString() });
    // cap at 100 latest
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

  return { list, start, markReportReady, remove, clearAllForStory, clear };
});
