<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppToast from "@/components/AppToast.vue";
import TopBar from "@/components/TopBar.vue";
import LoginModal from "@/components/LoginModal.vue";

const route = useRoute();
const router = useRouter();
const showLogin = ref(false);

watch(() => route.query.login, (v) => {
  if (v === "1") showLogin.value = true;
}, { immediate: true });

function onLoginClose() {
  showLogin.value = false;
  router.replace({ query: { ...route.query, login: undefined, redirect: undefined } });
}

function onLoginSuccess() {
  showLogin.value = false;
  const redirect = route.query.redirect as string | undefined;
  if (redirect) {
    router.replace(redirect);
  } else {
    router.replace({ query: { ...route.query, login: undefined, redirect: undefined } });
  }
}
</script>

<template>
  <div class="min-h-screen bg-paper text-ink antialiased">
    <TopBar />
    <main class="pt-14">
      <RouterView />
    </main>
    <AppToast />
    <LoginModal :open="showLogin" @close="onLoginClose" @success="onLoginSuccess" />
  </div>
</template>
