import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { getAuthToken } from "@/api/client";
import { useStoryStore } from "@/stores/story";

declare module "vue-router" {
  interface RouteMeta { requiresAuth?: boolean; }
}

const routes: RouteRecordRaw[] = [
  { path: "/", name: "landing", component: () => import("@/pages/LandingPage.vue") },
  { path: "/library", name: "library", component: () => import("@/pages/LibraryPage.vue"), meta: { requiresAuth: true } },
  { path: "/store", name: "store", component: () => import("@/pages/StorePage.vue") },
  {
    path: "/story/:id",
    name: "story",
    component: () => import("@/pages/StoryPage.vue"),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: "/story/:id/report",
    name: "report",
    component: () => import("@/pages/ReportPage.vue"),
    props: true,
    meta: { requiresAuth: true },
  },
  { path: "/profile", name: "profile", component: () => import("@/pages/ProfilePage.vue"), meta: { requiresAuth: true } },
  { path: "/:path(.*)", name: "not-found", component: () => import("@/pages/NotFoundPage.vue") },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
});

router.beforeEach((to, from) => {
  if (from.name === "story" && to.name !== "story" && to.name !== "report") {
    const story = useStoryStore();
    const storyId = String(from.params.id || "");
    if (story.hasPendingWork(storyId)) {
      const leave = window.confirm(
        "当前还有道具或新场景正在生成。退出后会继续在后台生成。\n\n选择“确定”退出，选择“取消”继续故事。",
      );
      if (!leave) return false;
    }
  }
  if (to.meta.requiresAuth && !getAuthToken()) {
    return { name: "landing", query: { login: "1", redirect: to.fullPath } };
  }
});

export default router;
