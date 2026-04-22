<script setup lang="ts">
import { RouterView } from "vue-router";
import AppToast from "@/components/AppToast.vue";
</script>

<template>
  <div class="min-h-screen bg-paper text-ink antialiased">
    <RouterView v-slot="{ Component, route }">
      <Transition name="fade" mode="out-in">
        <component :is="Component" :key="route.fullPath" />
      </Transition>
    </RouterView>
    <AppToast />
  </div>
</template>

<style>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.fade-enter-from { opacity: 0; transform: translateY(6px); }
.fade-leave-to   { opacity: 0; transform: translateY(-4px); }
</style>
