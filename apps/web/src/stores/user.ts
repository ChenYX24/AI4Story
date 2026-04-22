// F1 骨架：localStorage 假登录，阶段 2 换真正后端 auth
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { useLocalStorage } from "@vueuse/core";

export interface User {
  id: string;
  nick: string;
  created_at: string;
}

export const useUserStore = defineStore("user", () => {
  const user = useLocalStorage<User | null>("mindshow_user", null, {
    serializer: {
      read: (v: string) => (v ? JSON.parse(v) : null),
      write: (v: User | null) => JSON.stringify(v),
    },
  });

  const isAuthed = computed(() => user.value !== null);

  const pendingLogin = ref(false);

  function login(nick: string) {
    const trimmed = nick.trim();
    if (!trimmed) throw new Error("昵称不能为空");
    user.value = {
      id: "u_" + Math.random().toString(36).slice(2, 10),
      nick: trimmed,
      created_at: new Date().toISOString(),
    };
  }

  function logout() {
    user.value = null;
  }

  return { user, isAuthed, pendingLogin, login, logout };
});
