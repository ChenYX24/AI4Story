// 每个 interactive scene 的操作快照：placed 摆放 / ops 动作 / customProps 自创道具。
// 让用户来回翻页、回看已玩过的幕时，之前的摆放和道具不丢失。
import { defineStore } from "pinia";
import { ref } from "vue";
import type { Operation, CustomProp } from "@/api/types";

export interface PlacedItemSnap {
  id: string;
  name: string;
  kind: "character" | "object";
  url?: string;
  custom_url?: string;
  x: number;
  y: number;
  scale: number;
  rotation: number;
  isCustom?: boolean;
}

export interface InteractSceneState {
  placed: PlacedItemSnap[];
  ops: Operation[];
  customProps: CustomProp[];
}

export const useInteractStore = defineStore("interact", () => {
  const states = ref<Map<string, InteractSceneState>>(new Map());
  const k = (sessionId: string, sceneIdx: number) => `${sessionId}:${sceneIdx}`;

  function get(sessionId: string, sceneIdx: number): InteractSceneState | undefined {
    return states.value?.get?.(k(sessionId, sceneIdx));
  }
  function save(sessionId: string, sceneIdx: number, s: InteractSceneState) {
    if (!states.value) states.value = new Map();
    states.value.set(k(sessionId, sceneIdx), {
      placed: s.placed.map((p) => ({ ...p })),
      ops: s.ops.map((o) => ({ ...o })),
      customProps: s.customProps.map((c) => ({ ...c })),
    });
  }
  function clear(sessionId: string, sceneIdx: number) {
    states.value?.delete?.(k(sessionId, sceneIdx));
  }
  function clearSession(sessionId: string) {
    states.value = new Map([...states.value].filter(([key]) => !key.startsWith(`${sessionId}:`)));
  }
  function clearAll() { states.value = new Map(); }

  return { states, get, save, clear, clearSession, clearAll };
});
