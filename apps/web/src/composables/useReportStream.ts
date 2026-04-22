import { ref } from "vue";
import type { ReportRequest, ReportResponse } from "@/api/types";

type StageName = "analyze" | "compose" | "render";
export interface StageState {
  name: StageName;
  state: "idle" | "running" | "done";
  label: string;
}
export interface PerSceneProgress {
  index: number;
  total: number;
  label: string;
}

export function useReportStream() {
  const stages = ref<StageState[]>([
    { name: "analyze", state: "idle", label: "分析互动记录" },
    { name: "compose", state: "idle", label: "撰写三份报告" },
    { name: "render",  state: "idle", label: "渲染结果" },
  ]);
  const perScene = ref<PerSceneProgress | null>(null);
  const chunks = ref<Array<{ kind: string; data: any }>>([]);
  const running = ref(false);
  const error = ref<string | null>(null);

  function markStage(name: StageName, state: "running" | "done", label?: string) {
    const s = stages.value.find((x) => x.name === name);
    if (!s) return;
    s.state = state;
    if (label) s.label = label;
    if (name === "compose" && state === "done") {
      const r = stages.value.find((x) => x.name === "render");
      if (r) r.state = "running";
    }
  }

  async function run(body: ReportRequest): Promise<ReportResponse> {
    running.value = true;
    error.value = null;
    perScene.value = null;
    chunks.value = [];
    stages.value = [
      { name: "analyze", state: "running", label: "分析互动记录" },
      { name: "compose", state: "idle",    label: "撰写三份报告" },
      { name: "render",  state: "idle",    label: "渲染结果" },
    ];

    let finalPayload: ReportResponse | null = null;
    try {
      const resp = await fetch("/api/report/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let sep;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const block = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          let eventName = "message";
          const dataLines: string[] = [];
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) eventName = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          let data: any = {};
          try { data = JSON.parse(dataLines.join("\n")); } catch { continue; }
          if (eventName === "stage") markStage(data.name, data.state, data.label);
          else if (eventName === "per_scene") perScene.value = {
            index: data.index || 0, total: data.total || 1, label: data.label || "",
          };
          else if (eventName === "chunk") chunks.value.push(data);
          else if (eventName === "error") { error.value = data.detail || "stream error"; break; }
          else if (eventName === "all_done") finalPayload = data.payload as ReportResponse;
        }
        if (error.value) break;
      }

      if (error.value) throw new Error(error.value);
      if (!finalPayload) throw new Error("stream ended without payload");
      markStage("render", "done");
      running.value = false;
      return finalPayload;
    } catch (e: any) {
      error.value = e?.message || String(e);
      running.value = false;
      throw e;
    }
  }

  return { stages, perScene, chunks, running, error, run };
}
