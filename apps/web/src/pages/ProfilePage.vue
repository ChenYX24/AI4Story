<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import TopBar from "@/components/TopBar.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import BaseModal from "@/components/BaseModal.vue";
import { useUserStore } from "@/stores/user";
import { useToastStore } from "@/stores/toast";

const router = useRouter();
const user = useUserStore();
const toast = useToastStore();

const showLogin = ref(!user.isAuthed);
const nick = ref("");

function login() {
  try { user.login(nick.value); showLogin.value = false; nick.value = ""; }
  catch (e: any) { toast.push(e.message, "warn"); }
}
function logout() { user.logout(); showLogin.value = true; }

const tabs = [
  { key: "stories", label: "我的故事", icon: "📖" },
  { key: "sessions", label: "历史会话", icon: "🎮" },
  { key: "assets", label: "资产", icon: "🎨" },
];
const tab = ref("stories");

const assetSubs = [
  { key: "mine", label: "我生成的" },
  { key: "imported", label: "导入的" },
  { key: "official", label: "官方共享库" },
];
const assetSub = ref("mine");

const MOCK_OFFICIAL = [
  { name: "经典童话角色包", cover: "🎭", kind: "人物" },
  { name: "魔法道具 × 20", cover: "🗝️", kind: "道具" },
  { name: "森林 / 城堡 / 海底背景", cover: "🌲", kind: "背景" },
  { name: "节日场景包", cover: "🎉", kind: "场景" },
];

function backHome() { router.push("/"); }
</script>

<template>
  <div class="min-h-screen">
    <TopBar />

    <div v-if="user.isAuthed" class="max-w-[960px] mx-auto px-5 py-8 fade-in">
      <!-- 用户头部 -->
      <div class="flex items-center gap-4 mb-6 flex-wrap">
        <div
          class="w-16 h-16 rounded-full grid place-items-center text-2xl font-extrabold text-white shadow-card"
          style="background: linear-gradient(135deg, #ffcb63, #ff7a3d);"
        >{{ user.user?.nick.slice(0, 1).toUpperCase() }}</div>
        <div class="flex-1 min-w-0">
          <div class="text-xl font-bold">{{ user.user?.nick }}</div>
          <div class="text-xs text-ink-mute">
            加入于 {{ user.user ? new Date(user.user.created_at).toLocaleDateString() : "" }} · MVP 假登录
          </div>
        </div>
        <BaseButton variant="danger" size="sm" pill @click="logout">登出</BaseButton>
      </div>

      <!-- Tabs -->
      <div class="mb-5">
        <BaseTabs v-model="tab" :tabs="tabs" />
      </div>

      <!-- 内容 -->
      <div v-if="tab === 'stories'">
        <div class="text-center py-16 bg-white rounded-[var(--radius-card)] shadow-[var(--shadow-card)] border border-paper-edge">
          <div class="text-5xl mb-3">📖</div>
          <div class="font-bold text-ink">还没有创建过故事</div>
          <div class="text-sm text-ink-soft mt-1">去首页输入一段描述 / 视频 / 音频，或手绘上传开始创作</div>
          <div class="mt-4"><BaseButton pill @click="backHome">返回首页创作 →</BaseButton></div>
        </div>
      </div>

      <div v-else-if="tab === 'sessions'">
        <div class="text-center py-16 bg-white rounded-[var(--radius-card)] shadow-[var(--shadow-card)] border border-paper-edge">
          <div class="text-5xl mb-3">🎮</div>
          <div class="font-bold text-ink">还没玩过的会话</div>
          <div class="text-sm text-ink-soft mt-1">玩完一遍故事后，这里会按故事归档每次的记录和报告</div>
          <div class="mt-4">
            <BaseButton variant="soft" pill @click="router.push('/library')">去书架选一本 →</BaseButton>
          </div>
        </div>
      </div>

      <div v-else>
        <div class="mb-3">
          <BaseTabs v-model="assetSub" :tabs="assetSubs" variant="underline" />
        </div>
        <div class="flex gap-2 flex-wrap mb-4">
          <BaseButton variant="soft" size="sm" pill @click="toast.push('分享码导入：阶段 2 打通真正后端 CRUD 后可用')">
            ＋ 输入分享码导入
          </BaseButton>
          <BaseButton variant="soft" size="sm" pill @click="toast.push('多选打包分享：阶段 2 可用')">
            📦 打包分享（多选）
          </BaseButton>
        </div>
        <div v-if="assetSub === 'official'" class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
          <BaseCard v-for="(a, i) in MOCK_OFFICIAL" :key="i" hover class="overflow-hidden">
            <div class="h-24 grid place-items-center text-4xl bg-gradient-to-br from-gold to-accent-soft">{{ a.cover }}</div>
            <div class="p-3">
              <div class="font-semibold text-ink text-sm">{{ a.name }}</div>
              <div class="text-xs text-ink-mute">{{ a.kind }} · 官方</div>
            </div>
          </BaseCard>
        </div>
        <div v-else class="text-center py-16 bg-white rounded-[var(--radius-card)] shadow-[var(--shadow-card)] border border-paper-edge">
          <div class="text-5xl mb-3">{{ assetSub === 'imported' ? '📥' : '🎨' }}</div>
          <div class="font-bold text-ink">
            {{ assetSub === 'imported' ? '还没有导入的资产' : '还没有生成过资产' }}
          </div>
          <div class="text-sm text-ink-soft mt-1">
            {{ assetSub === 'imported' ? '让朋友给你一个分享码，粘贴后就能导入他们的角色 / 道具' : '每次创作都会自动把新角色和道具存进来' }}
          </div>
        </div>
      </div>
    </div>

    <!-- 登录 Modal -->
    <BaseModal :open="showLogin" title="👋 欢迎来到漫秀" @close="router.push('/')">
      <p class="text-sm text-ink-soft mb-3">先取个昵称，后续资产、会话、报告都会记到你的账户下。</p>
      <input
        v-model="nick"
        type="text"
        maxlength="20"
        placeholder="小朋友的昵称，例如：糖糖"
        class="w-full px-4 py-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
        @keydown.enter="login"
      />
      <div class="text-xs text-ink-mute mt-2">MVP 阶段：仅本地记录；阶段 2 接入真正账户</div>
      <template #footer>
        <BaseButton variant="soft" pill @click="router.push('/')">稍后</BaseButton>
        <BaseButton pill @click="login">开始</BaseButton>
      </template>
    </BaseModal>
  </div>
</template>
