<script setup lang="ts">
import { RouterView } from "vue-router";
import AppToast from "@/components/AppToast.vue";
import TopBar from "@/components/TopBar.vue";
</script>

<template>
  <div class="min-h-screen bg-paper text-ink antialiased">
    <!-- 全站常驻 TopBar（fixed，始终在顶，不随页面 Transition 卸载） -->
    <TopBar />
    <!-- 页面内容：pt-14 预留 TopBar 高度 -->
    <main class="pt-14 relative">
      <RouterView v-slot="{ Component, route }">
        <Transition name="fade">
          <component :is="Component" :key="route.fullPath" />
        </Transition>
      </RouterView>
    </main>
    <AppToast />
  </div>
</template>

<style>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.fade-leave-active {
  position: absolute;
  inset: 0;
}
.fade-enter-from { opacity: 0; transform: translateY(6px); }
.fade-leave-to   { opacity: 0; transform: translateY(-4px); }
</style>
