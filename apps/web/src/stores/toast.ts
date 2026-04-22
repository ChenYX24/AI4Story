import { defineStore } from "pinia";
import { ref } from "vue";

export interface ToastMsg {
  id: number;
  text: string;
  kind?: "info" | "success" | "warn" | "error";
}

let seq = 0;
export const useToastStore = defineStore("toast", () => {
  const list = ref<ToastMsg[]>([]);

  function push(text: string, kind: ToastMsg["kind"] = "info", ms = 2400) {
    const id = ++seq;
    list.value.push({ id, text, kind });
    window.setTimeout(() => {
      list.value = list.value.filter((t) => t.id !== id);
    }, ms);
  }

  return { list, push };
});

// 便利函数
export function toast(text: string, kind: ToastMsg["kind"] = "info") {
  useToastStore().push(text, kind);
}
