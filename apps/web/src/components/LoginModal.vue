<script setup lang="ts">
import { ref, watch } from "vue";
import BaseButton from "./BaseButton.vue";
import BaseModal from "./BaseModal.vue";
import { useUserStore } from "@/stores/user";
import { useToastStore } from "@/stores/toast";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "success"): void;
}>();

const user = useUserStore();
const toast = useToastStore();

const authMode = ref<"login" | "register">("login");
const nick = ref("");
const password = ref("");
const busy = ref(false);

watch(() => props.open, (v) => {
  if (v) { nick.value = ""; password.value = ""; authMode.value = "login"; }
});

async function submit() {
  const n = nick.value.trim();
  if (!n) { toast.push("请输入昵称", "warn"); return; }
  if (!password.value || password.value.length < 4) {
    toast.push("密码至少 4 位", "warn"); return;
  }
  busy.value = true;
  try {
    if (authMode.value === "login") {
      await user.login(n, password.value);
      toast.push(`欢迎回来，${n}`, "success");
    } else {
      await user.register(n, password.value);
      toast.push(`${n}，账号创建成功`, "success");
    }
    nick.value = ""; password.value = "";
    emit("success");
  } catch (e: any) {
    toast.push(e?.message || "失败", "error");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <BaseModal :open="open" :title="authMode === 'login' ? '欢迎回来' : '创建新账号'" @close="emit('close')">
    <div class="flex gap-1 p-1 rounded-full bg-paper-deep mb-4 text-sm">
      <button
        class="flex-1 py-2 rounded-full transition font-medium"
        :class="authMode === 'login' ? 'bg-white shadow text-accent-deep' : 'text-ink-soft'"
        @click="authMode = 'login'"
      >登录</button>
      <button
        class="flex-1 py-2 rounded-full transition font-medium"
        :class="authMode === 'register' ? 'bg-white shadow text-accent-deep' : 'text-ink-soft'"
        @click="authMode = 'register'"
      >注册</button>
    </div>
    <input
      v-model="nick"
      type="text"
      maxlength="20"
      placeholder="昵称"
      class="w-full px-4 py-3 mb-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
      @keydown.enter="submit"
    />
    <input
      v-model="password"
      type="password"
      maxlength="40"
      placeholder="密码（至少 4 位）"
      class="w-full px-4 py-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
      @keydown.enter="submit"
    />
    <div class="text-xs text-ink-mute mt-2">
      {{ authMode === 'login' ? '后续资产、会话、报告都会记到你的账户下。' : '注册后昵称即账号名，请记住密码。' }}
    </div>
    <template #footer>
      <BaseButton variant="soft" pill @click="emit('close')">稍后</BaseButton>
      <BaseButton pill :disabled="busy" @click="submit">
        {{ busy ? "处理中…" : authMode === 'login' ? '登录' : '注册' }}
      </BaseButton>
    </template>
  </BaseModal>
</template>
