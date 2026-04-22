// 全局键盘快捷键 — 自动忽略在 input/textarea/contenteditable 中的按键
import { onBeforeUnmount, onMounted } from "vue";

export interface Binding {
  key: string;        // "ArrowLeft" | "ArrowRight" | " " | "Escape" | "1"..."9"
  handler: (e: KeyboardEvent) => void;
  description?: string;
}

function inEditable(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if ((t as HTMLElement).isContentEditable) return true;
  return false;
}

export function useKeyboardShortcuts(bindings: Binding[]) {
  const onKey = (e: KeyboardEvent) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (inEditable(e)) return;
    for (const b of bindings) {
      if (b.key === e.key) {
        b.handler(e);
        e.preventDefault();
        return;
      }
    }
  };
  onMounted(() => document.addEventListener("keydown", onKey));
  onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
}
