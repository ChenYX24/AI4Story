<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import TopBar from "@/components/TopBar.vue";
import BaseCard from "@/components/BaseCard.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseTabs from "@/components/BaseTabs.vue";
import { useReportStream } from "@/composables/useReportStream";
import { useStoryStore } from "@/stores/story";
import { useSessionStore } from "@/stores/session";
import { useToastStore } from "@/stores/toast";
import { fetchServerInfo, postShare } from "@/api/endpoints";
import type { ReportResponse } from "@/api/types";

const props = defineProps<{ id: string }>();
const router = useRouter();
const store = useStoryStore();
const session = useSessionStore();
const toast = useToastStore();

const stream = useReportStream();
const payload = ref<ReportResponse | null>(null);
const tab = ref("share");
const failed = ref(false);

// Share / QR state
const shareId = ref<string | null>(null);
const shareUrl = ref<string>("");
const shareQrSrc = computed(() =>
  shareId.value
    ? `/api/share/${shareId.value}/qr.svg?url=${encodeURIComponent(shareUrl.value)}`
    : "",
);
const shareBuilding = ref(false);

async function buildShare() {
  if (shareId.value || shareBuilding.value) return;
  shareBuilding.value = true;
  try {
    const comics = store.comicUrls.slice();
    const title = (store.current?.title || store.current?.story_summary || "").slice(0, 30);
    const r = await postShare({ story_title: title, comics });
    shareId.value = r.share_id;
    // LAN IP 判断：localhost/127.0.0.1 时从 /api/server-info 取真正局域网 IP，方便手机扫码
    let host = location.hostname;
    const isLocal = host === "localhost" || host === "127.0.0.1";
    if (isLocal) {
      const info = await fetchServerInfo();
      if (info.lan_ip && info.lan_ip !== "127.0.0.1") host = info.lan_ip;
    }
    const port = location.port ? `:${location.port}` : "";
    shareUrl.value = `${location.protocol}//${host}${port}/view/${r.share_id}`;
  } catch (e: any) {
    toast.push(`分享码生成失败：${e.message}`, "warn");
  } finally {
    shareBuilding.value = false;
  }
}

async function copyShareUrl() {
  if (!shareUrl.value) return;
  try {
    await navigator.clipboard.writeText(shareUrl.value);
    toast.push("链接已复制", "success");
  } catch {
    toast.push("复制失败，请长按链接手动复制", "warn");
  }
}

// 在 stream 期间根据 chunks 渐进显示（chunk.kind 决定渲染哪块）
type ChunkAny = { kind: string; data: any };
const chunkByKind = computed(() => {
  const map: Record<string, any> = {};
  for (const c of stream.chunks.value as ChunkAny[]) map[c.kind] = c.data;
  return map;
});

async function runStream() {
  const sessionId = session.start(props.id, store.current?.title || props.id);
  try {
    const resp = await stream.run({
      session_id: sessionId,
      story_id: props.id,
      interactions: store.interactions, // 真实记录，不是空数组
    });
    payload.value = resp;
    session.markReportReady(sessionId);
    // 完成后异步生成分享码 + QR
    void buildShare();
  } catch (e: any) {
    failed.value = true;
    toast.push(`报告生成失败：${e.message}`, "error");
  }
}

onMounted(() => {
  runStream();
});

const reportTabs = [
  { key: "share",  label: "分享页", icon: "🏆" },
  { key: "kid",    label: "给孩子", icon: "🧒" },
  { key: "parent", label: "给家长", icon: "👨‍👩‍👧" },
];
</script>

<template>
  <div class="min-h-screen pt-14">
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
        <!-- 流式渐进卡片 -->
        <div class="mt-5 space-y-3">
          <BaseCard v-if="chunkByKind.share" class="p-5 fade-in">
            <div class="flex items-center gap-3">
              <div class="text-3xl">🏆</div>
              <div>
                <div class="font-bold text-ink">{{ chunkByKind.share.honor_title || "故事小主人" }}</div>
                <div class="text-sm text-ink-soft">{{ chunkByKind.share.summary }}</div>
              </div>
            </div>
            <div v-if="chunkByKind.share.achievements?.length" class="grid grid-cols-3 gap-2 mt-3">
              <div
                v-for="(a, i) in chunkByKind.share.achievements"
                :key="i"
                class="bg-gold/10 rounded-lg p-2 text-center text-xs"
              >
                <div class="text-xl">{{ a.icon }}</div>
                <div class="mt-1 text-ink-soft">{{ a.text }}</div>
              </div>
            </div>
          </BaseCard>

          <BaseCard v-if="chunkByKind.kid_header" class="p-5 fade-in">
            <div class="text-xs tracking-wider text-ink-mute mb-1">🧒 给孩子</div>
            <div class="font-bold mb-1">🌟 你创造的故事</div>
            <p class="text-sm text-ink-soft m-0">{{ chunkByKind.kid_header.your_story }}</p>
          </BaseCard>
          <BaseCard v-if="chunkByKind.kid_list" class="p-5 fade-in">
            <div class="text-xs tracking-wider text-ink-mute mb-2">🧒 给孩子</div>
            <div v-if="chunkByKind.kid_list.differences?.length" class="mb-3">
              <div class="font-bold mb-1">🔍 你的故事和原著有什么不同</div>
              <ul class="list-disc pl-5 space-y-0.5 text-sm text-ink-soft">
                <li v-for="(d, i) in chunkByKind.kid_list.differences" :key="i">{{ d }}</li>
              </ul>
            </div>
            <div v-if="chunkByKind.kid_list.questions?.length">
              <div class="font-bold mb-1">💭 思考一下</div>
              <ol class="list-decimal pl-5 space-y-0.5 text-sm text-ink-soft">
                <li v-for="(q, i) in chunkByKind.kid_list.questions" :key="i">{{ q }}</li>
              </ol>
            </div>
          </BaseCard>

          <BaseCard v-if="chunkByKind.parent_metrics" class="p-5 fade-in">
            <div class="text-xs tracking-wider text-ink-mute mb-2">👨‍👩‍👧 给家长</div>
            <div class="font-bold mb-2">📊 能力维度画像</div>
            <div
              v-for="(m, i) in (chunkByKind.parent_metrics.metrics || [])"
              :key="i"
              class="mb-2"
            >
              <div class="flex justify-between text-sm">
                <span>{{ m.name }}</span>
                <span class="font-medium">{{ m.value }}%</span>
              </div>
              <div class="h-1.5 bg-paper-deep rounded-full overflow-hidden">
                <div
                  class="h-full transition-all"
                  :style="{ width: `${m.value}%`, background: 'linear-gradient(90deg, #ffa952, #ff7a3d)' }"
                ></div>
              </div>
            </div>
          </BaseCard>
          <BaseCard v-if="chunkByKind.parent_lists" class="p-5 fade-in">
            <div class="text-xs tracking-wider text-ink-mute mb-2">👨‍👩‍👧 给家长</div>
            <div v-if="chunkByKind.parent_lists.traits?.length" class="mb-3">
              <div class="font-bold mb-1">🧩 行为亮点</div>
              <ul class="list-disc pl-5 space-y-0.5 text-sm text-ink-soft">
                <li v-for="(t, i) in chunkByKind.parent_lists.traits" :key="i">{{ t }}</li>
              </ul>
            </div>
            <div v-if="chunkByKind.parent_lists.suggestions?.length">
              <div class="font-bold mb-1">🌱 教育建议</div>
              <ol class="list-decimal pl-5 space-y-0.5 text-sm text-ink-soft">
                <li v-for="(s, i) in chunkByKind.parent_lists.suggestions" :key="i">{{ s }}</li>
              </ol>
            </div>
          </BaseCard>
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
          <BaseCard class="p-6 text-center relative overflow-hidden">
            <!-- confetti 背景渐变 -->
            <div
              class="absolute inset-0 pointer-events-none opacity-40"
              style="background: radial-gradient(circle at 20% 30%, #ffcb63 0, transparent 40%), radial-gradient(circle at 80% 70%, #ff7a3d 0, transparent 40%);"
            ></div>
            <div class="relative">
              <div class="text-6xl mb-2">🏆</div>
              <div class="text-2xl font-bold mb-2">{{ payload.share?.honor_title }}</div>
              <p class="text-ink-soft m-0">{{ payload.share?.summary }}</p>
            </div>
          </BaseCard>

          <!-- 成就 -->
          <div class="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3 mt-4">
            <BaseCard
              v-for="(a, i) in payload.share?.achievements || []"
              :key="i"
              class="p-4 text-center"
            >
              <div class="text-3xl">{{ a.icon }}</div>
              <div class="text-sm mt-2 text-ink-soft">{{ a.text }}</div>
            </BaseCard>
          </div>

          <!-- 漫画条 -->
          <BaseCard v-if="store.comicUrls.length" class="p-5 mt-4">
            <div class="text-xs tracking-wider text-ink-mute mb-2">
              📚 故事漫画一览 · {{ store.comicUrls.length }} 幅
            </div>
            <div class="flex gap-2 overflow-x-auto no-scrollbar pb-2">
              <img
                v-for="(u, i) in store.comicUrls"
                :key="i"
                :src="u"
                loading="lazy"
                decoding="async"
                :alt="`第 ${i + 1} 幅`"
                class="h-28 w-auto rounded-lg border border-paper-edge shadow-sm hover:shadow-md hover:-translate-y-0.5 transition shrink-0"
              />
            </div>
          </BaseCard>

          <!-- 分享 QR -->
          <BaseCard class="p-5 mt-4">
            <div class="flex flex-col sm:flex-row gap-5 items-center">
              <div
                class="shrink-0 w-[148px] h-[148px] bg-white rounded-xl border border-paper-edge grid place-items-center"
              >
                <img
                  v-if="shareQrSrc"
                  :src="shareQrSrc"
                  alt="分享二维码"
                  class="w-[140px] h-[140px]"
                />
                <div v-else-if="shareBuilding" class="text-ink-mute text-xs animate-pulse">生成中…</div>
                <div v-else class="text-ink-mute text-xs">准备中</div>
              </div>
              <div class="flex-1 min-w-0 text-center sm:text-left">
                <div class="text-sm font-semibold text-ink mb-1">扫码分享给家人朋友</div>
                <div class="text-xs text-ink-soft mb-3">手机上可左右滑动翻看故事漫画</div>
                <div v-if="shareUrl" class="flex items-center gap-2">
                  <code class="flex-1 min-w-0 truncate text-xs bg-paper-deep rounded px-2 py-1 text-ink-soft">{{ shareUrl }}</code>
                  <BaseButton variant="soft" size="sm" pill @click="copyShareUrl">复制</BaseButton>
                </div>
              </div>
            </div>
          </BaseCard>
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
