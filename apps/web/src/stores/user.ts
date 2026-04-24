// 真·账号 store —— 后端 /api/auth/{register,login,me,logout}
// token 存 localStorage（'mindshow_token'，由 api/client 自动读出加 header）
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { authLogin, authLogout, authMe, authRegister } from "@/api/endpoints";
import { getAuthToken, setAuthToken } from "@/api/client";
import { useAssetShelfStore } from "@/stores/assetShelf";
import { useSessionStore } from "@/stores/session";

export interface User {
  id: string;
  nickname: string;
  created_at?: number | string;
}

export const useUserStore = defineStore("user", () => {
  const user = ref<User | null>(null);
  const booting = ref(false);

  const isAuthed = computed(() => user.value !== null);

  async function boot() {
    // 启动时尝试用 localStorage token 恢复会话
    if (!getAuthToken()) { user.value = null; return; }
    booting.value = true;
    try {
      const me = await authMe();
      user.value = { id: me.id, nickname: me.nickname, created_at: me.created_at };
      const assets = useAssetShelfStore();
      assets.loadScope(me.id);
      useSessionStore().loadScope(me.id);
      void assets.pullFromServer();
    } catch {
      user.value = null;
      setAuthToken(null);
      useAssetShelfStore().loadScope(null);
      useSessionStore().loadScope(null);
    } finally {
      booting.value = false;
    }
  }

  async function login(nickname: string, password: string) {
    const r = await authLogin(nickname, password);
    setAuthToken(r.token);
    user.value = { id: r.id, nickname: r.nickname };
    const assets = useAssetShelfStore();
    assets.loadScope(r.id);
    useSessionStore().loadScope(r.id);
    await assets.pullFromServer();
  }

  async function register(nickname: string, password: string) {
    const r = await authRegister(nickname, password);
    setAuthToken(r.token);
    user.value = { id: r.id, nickname: r.nickname };
    const assets = useAssetShelfStore();
    assets.loadScope(r.id);
    useSessionStore().loadScope(r.id);
    await assets.pullFromServer();
  }

  async function logout() {
    try { await authLogout(); } catch { /* ignore */ }
    setAuthToken(null);
    user.value = null;
    useAssetShelfStore().loadScope(null);
    useSessionStore().loadScope(null);
  }

  return { user, isAuthed, booting, boot, login, register, logout };
});
