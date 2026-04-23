import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  { path: "/", name: "landing", component: () => import("@/pages/LandingPage.vue") },
  { path: "/library", name: "library", component: () => import("@/pages/LibraryPage.vue") },
  { path: "/store", name: "store", component: () => import("@/pages/StorePage.vue") },
  {
    path: "/story/:id",
    name: "story",
    component: () => import("@/pages/StoryPage.vue"),
    props: true,
  },
  {
    path: "/story/:id/report",
    name: "report",
    component: () => import("@/pages/ReportPage.vue"),
    props: true,
  },
  { path: "/profile", name: "profile", component: () => import("@/pages/ProfilePage.vue") },
  { path: "/:path(.*)", name: "not-found", component: () => import("@/pages/NotFoundPage.vue") },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
});

export default router;
