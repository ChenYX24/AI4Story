import { apiGet, apiPost, apiDelete, apiPatch } from "./client";
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
export const fetchScene     = (idx: number) => apiGet<Scene>(`/api/scene/${idx}`);
export const postReport     = (req: ReportRequest) => apiPost<ReportResponse>("/api/report", req);
export const postShare      = (body: ShareInit) => apiPost<ShareResponse>("/api/share", body);
export const createCustomStory = (body: { text: string; title?: string }) =>
  apiPost<import("./types").StoryCard>("/api/stories/custom", body);
export const deleteCustomStory = (id: string) =>
  apiDelete<{ ok: boolean }>(`/api/stories/${encodeURIComponent(id)}`);
export const patchCustomStory = (id: string, body: { title?: string }) =>
  apiPatch<{ ok: boolean }>(`/api/stories/${encodeURIComponent(id)}`, body);


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
