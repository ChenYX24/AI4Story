import { ref, computed } from "vue";
import type {
  RetellSceneItem,
  RetellFeedback,
  RetellSummaryResponse,
} from "@/api/types";
import {
  postRetellStart,
  postRetellSubmit,
  postRetellSummary,
} from "@/api/endpoints";

export type RetellPhase = "loading" | "telling" | "feedback" | "summary" | "error";

export function useRetell() {
  const sessionId = ref("");
  const storyTitle = ref("");
  const scenes = ref<RetellSceneItem[]>([]);
  const cursor = ref(0);
  const results = ref<Map<number, RetellFeedback>>(new Map());
  const summary = ref<RetellSummaryResponse | null>(null);
  const phase = ref<RetellPhase>("loading");
  const error = ref<string | null>(null);
  const childText = ref("");
  const submitting = ref(false);

  const currentScene = computed(() => scenes.value[cursor.value] ?? null);
  const totalScenes = computed(() => scenes.value.length);
  const isLastScene = computed(() => cursor.value >= scenes.value.length - 1);
  const progress = computed(() =>
    totalScenes.value > 0 ? Math.round(((cursor.value + 1) / totalScenes.value) * 100) : 0,
  );

  async function start(storyId: string) {
    phase.value = "loading";
    error.value = null;
    try {
      const res = await postRetellStart({ story_id: storyId });
      sessionId.value = res.session_id;
      storyTitle.value = res.story_title;
      scenes.value = res.scenes;
      cursor.value = 0;
      results.value = new Map();
      summary.value = null;
      childText.value = "";
      phase.value = res.scenes.length > 0 ? "telling" : "error";
    } catch (e: any) {
      error.value = e?.message || "加载失败";
      phase.value = "error";
    }
  }

  async function submit(text: string) {
    if (!currentScene.value || submitting.value) return;
    submitting.value = true;
    childText.value = text;
    try {
      const res = await postRetellSubmit({
        session_id: sessionId.value,
        scene_index: currentScene.value.scene_index,
        child_text: text,
      });
      results.value.set(currentScene.value.scene_index, res.feedback);
      phase.value = "feedback";
    } catch (e: any) {
      error.value = e?.message || "提交失败，请重试";
      // stay in telling phase so child can retry
    } finally {
      submitting.value = false;
    }
  }

  async function requestSummary() {
    phase.value = "loading";
    try {
      const res = await postRetellSummary({ session_id: sessionId.value });
      summary.value = res;
      phase.value = "summary";
    } catch (e: any) {
      error.value = e?.message || "获取总结失败";
      phase.value = "error";
    }
  }

  function advance() {
    if (cursor.value < scenes.value.length - 1) {
      cursor.value++;
      childText.value = "";
      phase.value = "telling";
    } else {
      requestSummary();
    }
  }

  function retry() {
    childText.value = "";
    phase.value = "telling";
  }

  function restart() {
    cursor.value = 0;
    results.value = new Map();
    summary.value = null;
    childText.value = "";
    phase.value = "telling";
  }

  return {
    sessionId,
    storyTitle,
    scenes,
    cursor,
    results,
    summary,
    phase,
    error,
    childText,
    submitting,
    currentScene,
    totalScenes,
    isLastScene,
    progress,
    start,
    submit,
    advance,
    retry,
    restart,
    requestSummary,
  };
}
