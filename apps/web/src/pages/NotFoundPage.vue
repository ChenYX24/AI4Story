<script setup lang="ts">
import { useRouter } from "vue-router";
import BaseButton from "@/components/BaseButton.vue";
const router = useRouter();
</script>

<template>
  <div class="min-h-screen grid place-items-center px-6 fade-in">
    <div class="text-center max-w-md">
      <div class="text-8xl mb-4 animate-floaty">📖</div>
      <h1 class="font-display text-3xl font-bold m-0 mb-2">这页故事书没找到</h1>
      <p class="text-ink-soft m-0 mb-6">
        可能是链接写错了，或者这本书还在小画家的抽屉里没画好。
      </p>
      <div class="flex gap-3 justify-center flex-wrap">
        <BaseButton variant="soft" pill @click="router.back()">← 返回上一页</BaseButton>
        <BaseButton pill @click="router.push('/')">回首页</BaseButton>
      </div>
    </div>
  </div>
</template>
