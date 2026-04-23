import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { getAuthToken } from "@/api/client";

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

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !getAuthToken()) {
    return { name: "landing", query: { login: "1", redirect: to.fullPath } };
  }
});

export default router;
