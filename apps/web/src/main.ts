import { createApp } from "vue";
import { createPinia } from "pinia";
import "./style.css";
import App from "./App.vue";
import router from "./router";

const app = createApp(App);

// 全局错误捕获 — 记录 + 提示，避免单个组件报错掀翻整页
app.config.errorHandler = (err, _instance, info) => {
  console.error("[vue errorHandler]", err, info);
  // 动态 import toast 避免循环依赖（toast store 依赖 pinia）
  import("@/stores/toast").then((m) => {
    try {
      m.useToastStore().push(
        `内部错误：${(err as Error)?.message || "未知错误"}`,
        "error",
      );
    } catch { /* swallow */ }
  });
};

window.addEventListener("unhandledrejection", (e) => {
  console.warn("[unhandledrejection]", e.reason);
});

app.use(createPinia());
app.use(router);
app.mount("#app");

// 启动后尝试恢复账号会话（不阻塞 mount）
import("@/stores/user").then((m) => {
  try { void m.useUserStore().boot(); } catch { /* ignore */ }
});
