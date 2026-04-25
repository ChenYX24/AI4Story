import { apiGet, apiPost, apiDelete, apiPatch, apiPut } from "./client";
import type {
  StoriesResponse,
  StoryDetail,
  Scene,
  ReportRequest,
  ReportResponse,
  ShareInit,
  ShareResponse,
} from "./types";

export const fetchStories   = () => apiGet<StoriesResponse>("/api/stories");
export const fetchStory     = (id: string) => apiGet<StoryDetail>(`/api/story?story_id=${encodeURIComponent(id)}`);
export const fetchScene     = (idx: number, storyId?: string) => {
  const qs = storyId ? `?story_id=${encodeURIComponent(storyId)}` : "";
  return apiGet<Scene>(`/api/scene/${idx}${qs}`);
};
export const postReport     = (req: ReportRequest) => apiPost<ReportResponse>("/api/report", req);
export const postShare      = (body: ShareInit) => apiPost<ShareResponse>("/api/share", body);
export const createCustomStory = (body: { text: string; title?: string }) =>
  apiPost<import("./types").StoryCard>("/api/stories/custom", body);
export const createStoryFromVideo = (body: { url: string; title?: string }) =>
  apiPost<import("./types").StoryCard>("/api/stories/from-video", body);
export const fetchCustomStory = (id: string) =>
  apiGet<import("./types").StoryCard>(`/api/stories/custom/${encodeURIComponent(id)}`);
export const deleteCustomStory = (id: string) =>
  apiDelete<{ ok: boolean }>(`/api/stories/custom/${encodeURIComponent(id)}`);
export const patchCustomStory = (id: string, body: { title?: string }) =>
  apiPatch<{ ok: boolean }>(`/api/stories/custom/${encodeURIComponent(id)}`, body);


// 拉服务器信息（LAN IP 之类）
export const fetchServerInfo = () =>
  apiGet<{ lan_ip?: string }>("/api/server-info").catch(() => ({} as { lan_ip?: string }));

// SSE — 用 fetch + ReadableStream 手工解析（见 composables/useReportStream）
export const reportStreamUrl = "/api/report/stream";

import type {
  InteractRequest, InteractResponse,
  PlacementResponse,
  ChatRequest, ChatResponse,
  CreatePropRequest, CreatePropResponse,
} from "./types";

export const fetchPlacements = (storyId: string | undefined, sceneIdx: number) =>
  apiPost<PlacementResponse>("/api/placements", { story_id: storyId, scene_idx: sceneIdx });
export const postInteract = (req: InteractRequest) =>
  apiPost<InteractResponse>("/api/interact", req);
export const postChat = (req: ChatRequest) =>
  apiPost<ChatResponse>("/api/chat", req);
export const fetchChatSuggestions = (storyId: string | undefined, sceneIdx: number) => {
  const qs = new URLSearchParams({ scene_idx: String(sceneIdx) });
  if (storyId) qs.set("story_id", storyId);
  return apiGet<{ questions: string[] }>(`/api/chat/suggestions?${qs.toString()}`);
};
export const createProp = (req: CreatePropRequest) =>
  apiPost<CreatePropResponse>("/api/create_prop", req);

// ---- 账号 ----
import type {
  AuthResponse, MeResponse,
  PublicStoriesResponse, PublicAssetsResponse,
  UploadImageRequest, UploadImageResponse,
} from "./types";

export const authRegister = (nickname: string, password: string) =>
  apiPost<AuthResponse>("/api/auth/register", { nickname, password });
export const authLogin = (nickname: string, password: string) =>
  apiPost<AuthResponse>("/api/auth/login", { nickname, password });
export const authMe = () => apiGet<MeResponse>("/api/auth/me");
export const authLogout = () => apiPost<{ ok: boolean }>("/api/auth/logout");

// ---- 公共平台 ----
export const fetchPublicStories = () => apiGet<PublicStoriesResponse>("/api/public/stories");
export const fetchPublicAssets  = () => apiGet<PublicAssetsResponse>("/api/public/assets");

// ---- 上传 ----
export const uploadImage = (body: UploadImageRequest) =>
  apiPost<UploadImageResponse>("/api/upload/image", body);

// ---- 用户自创道具（需登录）----
export interface UserAssetOut {
  id: string;
  name: string;
  url: string;
  kind: string;
  origin_story_id?: string;
  origin_scene_idx?: number;
  created_at: number;
}
export const fetchMyAssets = () =>
  apiGet<{ assets: UserAssetOut[] }>("/api/user/assets");
export const createMyAsset = (a: Partial<UserAssetOut> & { name: string; url: string }) =>
  apiPost<UserAssetOut>("/api/user/assets", a);
export const deleteMyAsset = (id: string) =>
  apiDelete<{ ok: boolean }>(`/api/user/assets/${encodeURIComponent(id)}`);
export const syncMyAssets = (assets: Array<Partial<UserAssetOut> & { name: string; url: string }>) =>
  apiPost<{ assets: UserAssetOut[] }>("/api/user/assets/sync", { assets });

// ---- 分享码 + 打包 ----
export interface PackAssetItem {
  id: string; name: string; url: string; kind: string;
  origin_story_id?: string; origin_scene_idx?: number;
}
export interface PackOut {
  code: string;
  name: string;
  description: string;
  public: boolean;
  asset_ids: string[];
  assets: PackAssetItem[];
  created_at: number;
  owner_user_id?: string;
}
export const createPack = (body: { name: string; description?: string; asset_ids: string[]; public?: boolean }) =>
  apiPost<PackOut>("/api/packs", body);
export const fetchPack = (code: string) =>
  apiGet<PackOut>(`/api/packs/${encodeURIComponent(code.toUpperCase())}`);
export const fetchPublicPacks = () =>
  apiGet<{ packs: PackOut[] }>("/api/packs/");

// ---- 游玩会话（后端持久化）----
export interface SessionOut {
  id: string;
  user_id: string;
  story_id: string;
  play_state: Record<string, unknown>;
  status: "playing" | "finished";
  created_at: number;
  updated_at: number;
}
export const createSessionApi = (body: { story_id: string; play_state: object }) =>
  apiPost<SessionOut>("/api/sessions", body);
export const updateSessionApi = (id: string, body: { play_state: object; status?: string }) =>
  apiPut<{ ok: boolean }>(`/api/sessions/${encodeURIComponent(id)}`, body);
export const fetchSessionsApi = (storyId: string) =>
  apiGet<{ sessions: SessionOut[] }>(`/api/sessions?story_id=${encodeURIComponent(storyId)}`);
export const deleteSessionApi = (id: string) =>
  apiDelete<{ ok: boolean }>(`/api/sessions/${encodeURIComponent(id)}`);

// ---- 资产包管理（需登录）----
export const fetchMyPacks = () =>
  apiGet<{ packs: PackOut[] }>("/api/packs/mine");
export const updatePack = (code: string, body: { name?: string; description?: string; asset_ids?: string[]; public?: boolean }) =>
  apiPut<PackOut>(`/api/packs/${encodeURIComponent(code)}`, body);
export const deletePack = (code: string) =>
  apiDelete<{ ok: boolean }>(`/api/packs/${encodeURIComponent(code)}`);
