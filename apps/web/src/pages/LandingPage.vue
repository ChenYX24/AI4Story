<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import CinemaHero from "@/components/CinemaHero.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import { useUserStore } from "@/stores/user";
import { useToastStore } from "@/stores/toast";
import { createCustomStory } from "@/api/endpoints";

const router = useRouter();
const user = useUserStore();
const toast = useToastStore();

const landingTabs = [
  { key: "text",   label: "文字描述", icon: "✍️" },
  { key: "video",  label: "视频导入", icon: "🎬" },
  { key: "voice",  label: "语音讲述", icon: "🎙️" },
  { key: "sketch", label: "手绘上传", icon: "🎨" },
];
const activeTab = ref("text");
const title = ref("");
const textInput = ref("");
const submitting = ref(false);

async function submitText() {
  const text = textInput.value.trim();
  if (!text) { toast.push("先输入一点故事内容吧", "warn"); return; }
  submitting.value = true;
  try {
    await createCustomStory({ text, title: title.value.trim() || undefined });
    toast.push("故事已进入后台生成，去书架看进度", "success");
    textInput.value = ""; title.value = "";
    router.push("/library");
  } catch (e: any) {
    toast.push(`创建失败：${e.message}`, "error");
  } finally {
    submitting.value = false;
  }
}

function scrollToCreate() {
  document.getElementById("landing-create")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// 公共平台 mock
const plazaTabs = [
  { key: "stories",  label: "热门故事" },
  { key: "assets",   label: "精选资产" },
  { key: "official", label: "官方精选" },
];
const plazaTab = ref("stories");
const PLAZA = {
  stories: [
    { cover: "🦊", title: "月亮画板上的小狐狸", author: "小朋友 ZY", likes: 312 },
    { cover: "🐰", title: "会发光的萝卜田", author: "小朋友 MM", likes: 248 },
    { cover: "🦕", title: "恐龙蛋奇遇记", author: "小朋友 KK", likes: 197 },
    { cover: "🌊", title: "海底邮局的秘密", author: "小朋友 LL", likes: 156 },
    { cover: "🚀", title: "去星星上摘糖果", author: "小朋友 AA", likes: 134 },
    { cover: "🐻", title: "会说话的蜂蜜罐", author: "小朋友 BB", likes: 121 },
  ],
  assets: [
    { cover: "🎭", title: "童话角色包（20 款）", author: "imagineer", likes: 521 },
    { cover: "🏰", title: "魔法城堡背景 × 12", author: "artlover", likes: 389 },
    { cover: "🗝️", title: "魔法道具套装", author: "wizard", likes: 267 },
    { cover: "🌲", title: "森林四季背景", author: "painter", likes: 214 },
  ],
  official: [
    { cover: "📖", title: "经典童话 · 白雪公主", author: "漫秀官方", likes: 1024, official: true },
    { cover: "📖", title: "经典童话 · 三只小猪", author: "漫秀官方", likes: 876, official: true },
    { cover: "🎨", title: "官方角色资产包（初级）", author: "漫秀官方", likes: 702, official: true },
  ],
};
</script>

<template>
  <div class="fade-in">
    <!-- 胶片 hero -->
    <CinemaHero @explore="scrollToCreate">
      <template #overlay>
        <!-- 右上 FAB：进入 profile -->
        <button
          class="absolute top-14 right-6 px-4 py-2 rounded-full text-sm font-semibold text-gold-mute border border-gold/60 bg-gold/10 hover:bg-gold/25 hover:text-white backdrop-blur transition z-10"
          @click="router.push('/profile')"
        >👤 {{ user.isAuthed ? user.user?.nick : "我的" }}</button>
      </template>
    </CinemaHero>

    <!-- 创作入口 -->
    <section id="landing-create" class="max-w-[960px] mx-auto px-5 -mt-10 relative z-10">
      <BaseCard class="px-6 py-7 sm:px-10 sm:py-9">
        <div class="text-center mb-5">
          <span class="inline-block px-3 py-1 rounded-full bg-gold/20 text-ink-soft text-xs font-medium tracking-wide mb-3">
            ✨ 选一个方式开始
          </span>
          <h2 class="font-display text-2xl sm:text-3xl font-bold text-ink m-0">把灵感变成一本绘本故事</h2>
          <p class="text-ink-soft text-sm mt-2">漫秀会帮你拆分章节、生成角色与场景，把故事交给孩子去探索。</p>
        </div>

        <div class="flex justify-center mb-5 overflow-x-auto no-scrollbar">
          <BaseTabs v-model="activeTab" :tabs="landingTabs" />
        </div>

        <div v-if="activeTab === 'text'">
          <input
            v-model="title"
            type="text"
            placeholder="给故事取个名字（选填）"
            maxlength="32"
            class="w-full px-4 py-3 mb-3 rounded-xl border border-paper-edge bg-white focus:outline-none focus:border-accent-soft"
          />
          <textarea
            v-model="textInput"
            rows="3"
            class="w-full px-4 py-3 rounded-xl border border-paper-edge bg-white resize-y focus:outline-none focus:border-accent-soft"
            placeholder="比如：有一只怕黑的小狐狸，为了找回掉进夜空里的画笔，和一群会发光的萤火虫一起穿过森林。"
            @keydown.meta.enter="submitText"
            @keydown.ctrl.enter="submitText"
          ></textarea>
          <div class="mt-4 flex flex-col-reverse sm:flex-row items-stretch sm:items-center gap-3 sm:justify-between">
            <div class="text-xs text-ink-mute">创作过程大约 1 分钟，请保持网络畅通</div>
            <BaseButton :disabled="submitting" size="lg" pill @click="submitText">
              {{ submitting ? "创建中…" : "开始创作" }} →
            </BaseButton>
          </div>
        </div>
        <div v-else class="py-12 text-center text-ink-mute text-sm">
          {{ landingTabs.find((t) => t.key === activeTab)?.icon }} 该入口即将开放 — 追踪在
          <code class="px-1 bg-paper-deep rounded">agent-docs/plan/AI4Story_v2_主计划_*.md</code>
        </div>
      </BaseCard>

      <div class="text-center mt-6">
        <BaseButton variant="ghost" pill @click="router.push('/library')">
          查看现有故事 →
        </BaseButton>
      </div>
    </section>

    <!-- 公共平台 -->
    <section class="max-w-[1100px] mx-auto px-5 mt-16 pb-16">
      <div class="text-center mb-6">
        <h2 class="font-display text-2xl font-bold m-0">公共平台</h2>
        <p class="text-ink-soft text-sm mt-1">来看看大家分享的故事和资产</p>
      </div>
      <div class="flex justify-center mb-6">
        <BaseTabs v-model="plazaTab" :tabs="plazaTabs" />
      </div>
      <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
        <BaseCard
          v-for="(c, i) in PLAZA[plazaTab as keyof typeof PLAZA]"
          :key="i"
          hover
          :glow="!!(c as any).official"
          class="overflow-hidden"
          @click="toast.push('社区详情页在下一版开放')"
        >
          <div
            class="h-24 grid place-items-center text-5xl"
            :class="(c as any).official ? 'bg-gradient-to-br from-gold to-accent-soft' : 'bg-gradient-to-br from-paper-deep to-gold-mute'"
          >{{ c.cover }}</div>
          <div class="p-4">
            <div class="font-bold text-ink leading-snug min-h-[2.7em]">{{ c.title }}</div>
            <div class="mt-1.5 flex items-center justify-between text-xs text-ink-soft">
              <span>@{{ c.author }}</span>
              <span class="text-warn">❤ {{ c.likes }}</span>
            </div>
            <div v-if="(c as any).official" class="mt-2">
              <span class="px-2 py-0.5 rounded-full text-[11px] bg-gradient-to-r from-gold to-accent text-white">官方</span>
            </div>
          </div>
        </BaseCard>
      </div>
      <div class="text-center mt-8">
        <BaseButton variant="soft" pill @click="toast.push('完整社区功能在阶段 2 开放')">
          看更多 →
        </BaseButton>
      </div>
    </section>
  </div>
</template>
