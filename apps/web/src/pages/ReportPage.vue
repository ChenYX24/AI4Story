<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import TopBar from "@/components/TopBar.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import { useReportStream } from "@/composables/useReportStream";
import { useStoryStore } from "@/stores/story";
import { useToastStore } from "@/stores/toast";
import type { ReportResponse } from "@/api/types";

const props = defineProps<{ id: string }>();
const router = useRouter();
const store = useStoryStore();
const toast = useToastStore();

const stream = useReportStream();
const payload = ref<ReportResponse | null>(null);
const tab = ref("share");
const failed = ref(false);

async function runStream() {
  // 构建一个最小 session — 本地没跟踪 interactions 时走空数组
  const sessionId = "s_" + Date.now().toString(36);
  try {
    const resp = await stream.run({
      session_id: sessionId,
      story_id: props.id,
      interactions: [],
    });
    payload.value = resp;
  } catch (e: any) {
    failed.value = true;
    toast.push(`报告生成失败：${e.message}`, "error");
  }
}

onMounted(() => {
  if (!store.current || store.current.id !== props.id) {
    // 没走过故事流，直接请求看报告也可以 —— 后端能应付空 interactions
  }
  runStream();
});

const reportTabs = [
  { key: "share",  label: "分享页", icon: "🏆" },
  { key: "kid",    label: "给孩子", icon: "🧒" },
  { key: "parent", label: "给家长", icon: "👨‍👩‍👧" },
];
</script>

<template>
  <div class="min-h-screen">
    <TopBar />

    <div class="max-w-[960px] mx-auto px-5 py-8 fade-in">
      <!-- 流式阶段指示器 -->
      <section v-if="!payload" class="mb-6">
        <div class="flex gap-3 flex-wrap mb-4">
          <div
            v-for="s in stream.stages.value"
            :key="s.name"
            class="flex-1 min-w-[130px] rounded-xl px-4 py-3 border transition-all text-sm"
            :class="[
              s.state === 'done'
                ? 'bg-good/15 border-good/40 text-ink'
                : s.state === 'running'
                ? 'bg-gold/20 border-gold/60 text-ink'
                : 'bg-white border-paper-edge text-ink-mute',
            ]"
          >
            <span
              class="inline-block w-2 h-2 rounded-full mr-2 align-middle"
              :class="[
                s.state === 'done' ? 'bg-good' : s.state === 'running' ? 'bg-accent animate-pulse' : 'bg-ink-mute/50',
              ]"
            ></span>{{ s.label }}
          </div>
        </div>
        <div v-if="stream.perScene.value" class="px-3">
          <div class="h-1.5 bg-paper-deep rounded-full overflow-hidden">
            <div
              class="h-full bg-gradient-to-r from-accent-soft to-accent-deep transition-all"
              :style="{ width: `${Math.round((stream.perScene.value.index / stream.perScene.value.total) * 100)}%` }"
            ></div>
          </div>
          <div class="text-xs text-ink-mute mt-1">{{ stream.perScene.value.label }}</div>
        </div>
        <div class="mt-5 text-sm text-ink-soft bg-gold/10 rounded-xl px-4 py-3 border border-gold/30 animate-pulse">
          正在仔细读孩子的每次操作…
        </div>
        <div v-if="stream.chunks.value.length" class="mt-5 space-y-2">
          <div
            v-for="(c, i) in stream.chunks.value"
            :key="i"
            class="fade-in rounded-xl px-4 py-3 text-sm border"
            :class="c.kind.startsWith('parent') ? 'bg-[#eef6ff] border-[#c5daf0]' : c.kind.startsWith('kid') ? 'bg-paper-deep border-paper-edge' : 'bg-[#fffaef] border-gold/40'"
          >
            <span class="text-xs uppercase tracking-wider text-ink-mute mr-2">{{ c.kind }}</span>
            {{ JSON.stringify(c.data).slice(0, 200) }}…
          </div>
        </div>
        <div v-if="failed" class="mt-6 text-center">
          <BaseButton variant="soft" pill @click="router.back()">返回</BaseButton>
          <BaseButton class="ml-2" pill @click="runStream">🔁 重试</BaseButton>
        </div>
      </section>

      <!-- 生成好的报告 -->
      <section v-else>
        <div class="mb-5 flex justify-between items-center flex-wrap gap-2">
          <h1 class="font-display text-2xl sm:text-3xl font-bold m-0">
            🏆 {{ payload.share?.honor_title || "故事小主人" }}
          </h1>
          <BaseTabs v-model="tab" :tabs="reportTabs" />
        </div>

        <!-- Share 视图 -->
        <template v-if="tab === 'share'">
          <BaseCard class="p-6 text-center">
            <div class="text-6xl mb-2">🏆</div>
            <div class="text-xl font-bold mb-2">{{ payload.share?.honor_title }}</div>
            <p class="text-ink-soft">{{ payload.share?.summary }}</p>
          </BaseCard>
          <div class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3 mt-4">
            <BaseCard
              v-for="(a, i) in payload.share?.achievements || []"
              :key="i"
              class="p-4 text-center"
            >
              <div class="text-3xl">{{ a.icon }}</div>
              <div class="text-sm mt-2">{{ a.text }}</div>
            </BaseCard>
          </div>
        </template>

        <!-- Kid -->
        <template v-else-if="tab === 'kid'">
          <BaseCard class="p-6 mb-4">
            <h3 class="font-display text-lg font-bold m-0 mb-2">🌟 你创造的故事</h3>
            <p class="text-ink-soft">{{ payload.kid_section?.your_story || "（空）" }}</p>
          </BaseCard>
          <BaseCard class="p-6 mb-4">
            <h3 class="font-display text-lg font-bold m-0 mb-2">📖 真实的故事</h3>
            <p class="text-ink-soft">{{ payload.kid_section?.original_story || "（空）" }}</p>
          </BaseCard>
          <BaseCard class="p-6 mb-4">
            <h3 class="font-display text-lg font-bold m-0 mb-2">🔍 有什么不同</h3>
            <ul class="list-disc pl-5 space-y-1 text-ink-soft">
              <li v-for="(d, i) in payload.kid_section?.differences || []" :key="i">{{ d }}</li>
            </ul>
          </BaseCard>
          <BaseCard class="p-6">
            <h3 class="font-display text-lg font-bold m-0 mb-2">💭 思考一下</h3>
            <ol class="list-decimal pl-5 space-y-1 text-ink-soft">
              <li v-for="(q, i) in payload.kid_section?.questions || []" :key="i">{{ q }}</li>
            </ol>
          </BaseCard>
        </template>

        <!-- Parent -->
        <template v-else>
          <BaseCard class="p-6 mb-4">
            <h3 class="font-display text-lg font-bold m-0 mb-3">📊 能力维度画像</h3>
            <div
              v-for="(m, i) in payload.parent_section?.metrics || []"
              :key="i"
              class="mb-3"
            >
              <div class="flex justify-between text-sm mb-1">
                <span class="font-medium">{{ m.name }}</span>
                <span :style="{ color: m.value >= 80 ? 'var(--color-good)' : m.value >= 60 ? 'var(--color-accent)' : 'var(--color-gold-deep)' }">{{ m.value }}%</span>
              </div>
              <div class="h-2 bg-paper-deep rounded-full overflow-hidden">
                <div
                  class="h-full transition-all"
                  :style="{
                    width: `${m.value}%`,
                    background: m.value >= 80 ? 'linear-gradient(90deg, #8fc97b, #5bbf82)' : m.value >= 60 ? 'linear-gradient(90deg, #ffa952, #ff7a3d)' : 'linear-gradient(90deg, #f6dba1, #d59339)',
                  }"
                ></div>
              </div>
              <div v-if="m.evidence" class="text-xs text-ink-mute mt-1">{{ m.evidence }}</div>
            </div>
          </BaseCard>
          <BaseCard class="p-6 mb-4">
            <h3 class="font-display text-lg font-bold m-0 mb-2">🧩 亮点</h3>
            <ul class="list-disc pl-5 space-y-1 text-ink-soft">
              <li v-for="(t, i) in payload.parent_section?.traits || []" :key="i">{{ t }}</li>
            </ul>
          </BaseCard>
          <BaseCard class="p-6 mb-4">
            <h3 class="font-display text-lg font-bold m-0 mb-2">💡 可以加强</h3>
            <ul class="list-disc pl-5 space-y-1 text-ink-soft">
              <li v-for="(w, i) in payload.parent_section?.weaknesses || []" :key="i">{{ w }}</li>
            </ul>
          </BaseCard>
          <BaseCard class="p-6">
            <h3 class="font-display text-lg font-bold m-0 mb-2">🌱 教育建议</h3>
            <ol class="list-decimal pl-5 space-y-1 text-ink-soft">
              <li v-for="(s, i) in payload.parent_section?.suggestions || []" :key="i">{{ s }}</li>
            </ol>
          </BaseCard>
        </template>

        <div class="mt-8 flex justify-between flex-wrap gap-2">
          <BaseButton variant="soft" pill @click="router.push('/library')">← 回书架</BaseButton>
          <BaseButton pill @click="router.push({ name: 'story', params: { id: props.id } })">
            🔁 再玩一遍
          </BaseButton>
        </div>
      </section>
    </div>
  </div>
</template>
