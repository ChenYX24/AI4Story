<script setup lang="ts">
import { onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useStoryStore } from "@/stores/story";
import { useRetell } from "@/composables/useRetell";
import { useTTSPreload } from "@/composables/useTTSPreload";
import TopBar from "@/components/TopBar.vue";
import BaseButton from "@/components/BaseButton.vue";
import BaseCard from "@/components/BaseCard.vue";
import Skeleton from "@/components/Skeleton.vue";
import RetellMicButton from "@/components/RetellMicButton.vue";
import RetellProgressBar from "@/components/RetellProgressBar.vue";
import RetellFeedbackCard from "@/components/RetellFeedbackCard.vue";
import RetellSummaryView from "@/components/RetellSummaryView.vue";
import { useToastStore } from "@/stores/toast";

const props = defineProps<{ id: string }>();
const route = useRoute();
const router = useRouter();
const story = useStoryStore();
const toast = useToastStore();
const tts = useTTSPreload();
const retell = useRetell();

onMounted(async () => {
  try {
    await story.loadStory(props.id);
    await retell.start(props.id);
  } catch (e: any) {
    toast.push(e?.message || "加载失败", "error");
  }
});

async function onTranscript(text: string) {
  await retell.submit(text);
}

function onMicError(err: Error) {
  toast.push(err.message || "录音失败", "error");
}

function onNextScene() {
  if (retell.isLastScene.value) {
    retell.requestSummary();
  } else {
    retell.advance();
  }
}

function onRetry() {
  retell.retry();
}

function goLibrary() {
  router.push("/library");
}

function onRestart() {
  retell.restart();
}

// Play hint question via TTS on scene change
import { watch } from "vue";
watch(
  () => retell.cursor.value,
  () => {
    const scene = retell.currentScene.value;
    if (scene?.hint_question && retell.phase.value === "telling") {
      tts.playOne({
        text: scene.hint_question,
        speaker: "旁白",
        tone: "温柔",
        speaker_gender: "neutral",
      });
    }
  },
);

watch(
  () => retell.phase.value,
  (p) => {
    if (p === "telling") {
      const scene = retell.currentScene.value;
      if (scene?.hint_question) {
        tts.playOne({
          text: scene.hint_question,
          speaker: "旁白",
          tone: "温柔",
          speaker_gender: "neutral",
        });
      }
    }
  },
);
</script>

<template>
  <div class="min-h-screen flex flex-col bg-paper">
    <TopBar />

    <main class="flex-1 flex flex-col items-center px-4 py-6 max-w-2xl mx-auto w-full">
      <!-- Loading -->
      <div v-if="retell.phase.value === 'loading'" class="flex-1 flex flex-col items-center justify-center w-full gap-4">
        <Skeleton class="w-full h-64 rounded-2xl" />
        <Skeleton class="w-64 h-8 rounded-lg" />
        <Skeleton class="w-40 h-6 rounded-lg" />
      </div>

      <!-- Error -->
      <div v-else-if="retell.phase.value === 'error'" class="flex-1 flex flex-col items-center justify-center gap-4 text-center">
        <div class="text-4xl">😢</div>
        <p class="text-lg font-semibold text-ink">加载失败了</p>
        <p class="text-sm text-ink-soft">{{ retell.error.value }}</p>
        <BaseButton variant="soft" @click="retell.start(props.id)">重试</BaseButton>
      </div>

      <!-- Telling / Feedback phases -->
      <template v-else-if="retell.phase.value === 'telling' || retell.phase.value === 'feedback'">
        <!-- Progress -->
        <RetellProgressBar
          :total="retell.totalScenes.value"
          :current="retell.cursor.value"
        />

        <!-- Scene comic -->
        <div class="w-full mt-4">
          <BaseCard class="overflow-hidden !p-0">
            <img
              v-if="retell.currentScene.value?.comic_url"
              :src="retell.currentScene.value.comic_url"
              :alt="`场景 ${retell.currentScene.value?.scene_index}`"
              class="w-full h-auto object-cover rounded-2xl"
              loading="lazy"
            />
            <div
              v-else
              class="w-full aspect-[4/3] bg-paper-deep flex items-center justify-center rounded-2xl"
            >
              <p class="text-ink-soft text-sm text-center px-4">
                {{ retell.currentScene.value?.summary || retell.currentScene.value?.narration || '看看这一页' }}
              </p>
            </div>
          </BaseCard>
        </div>

        <!-- Hint question -->
        <div class="w-full mt-4 text-center">
          <p class="text-lg font-semibold text-ink">
            💡 {{ retell.currentScene.value?.hint_question }}
          </p>
        </div>

        <!-- Telling phase: mic -->
        <div v-if="retell.phase.value === 'telling'" class="mt-6">
          <RetellMicButton
            @transcript="onTranscript"
            @error="onMicError"
          />
          <p v-if="retell.submitting.value" class="text-center text-sm text-ink-soft mt-3 animate-pulse">
            正在听...
          </p>
        </div>

        <!-- Feedback phase -->
        <div v-else class="mt-6 w-full">
          <RetellFeedbackCard
            v-if="retell.results.value.get(retell.currentScene.value?.scene_index ?? -1)"
            :feedback="retell.results.value.get(retell.currentScene.value?.scene_index ?? -1)!"
            :is-last-scene="retell.isLastScene.value"
            @next="onNextScene"
            @retry="onRetry"
          />
        </div>
      </template>

      <!-- Summary phase -->
      <div v-else-if="retell.phase.value === 'summary'" class="w-full mt-4">
        <RetellSummaryView
          v-if="retell.summary.value"
          :summary="retell.summary.value"
          :story-title="retell.storyTitle.value"
          @go-library="goLibrary"
          @restart="onRestart"
        />
      </div>
    </main>
  </div>
</template>
