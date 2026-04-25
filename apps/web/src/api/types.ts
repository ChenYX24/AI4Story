// 从后端现有 models.py / routers 反推的 TypeScript 类型
// 当 contracts/openapi/openapi.yaml 补全后，这里将由 openapi-typescript 自动生成

export interface StoryCard {
  id: string;
  title: string;
  summary?: string;
  scene_count: number;
  is_custom?: boolean;
  status?: "ready" | "generating" | "failed" | "locked";
  progress?: number;
  progress_label?: string;
  cover_url?: string;
  available?: boolean;
  error_message?: string;
}

export interface StoriesResponse {
  stories: StoryCard[];
}

export interface StoryboardLine {
  kind: "narrator" | "character" | "assistant";
  speaker: string;
  text: string;
  tone?: string;
}

export interface SceneCharacter {
  name: string;
  url: string;
  default_x?: number;
  default_y?: number;
  default_scale?: number;
}
export interface SceneProp {
  name: string;
  url: string;
  description?: string;
}
export interface Scene {
  index: number;
  /** 后端字段名是 type；narrative / interactive */
  type: "narrative" | "interactive";
  title?: string;
  summary?: string;
  narration?: string;
  // narrative + interactive 都有：narrative 是叙事四格漫画，interactive 是这一交互场景在原故事中的发展过程四格图
  comic_url?: string;
  // narrative-only
  storyboard?: StoryboardLine[];
  // interactive-only
  interaction_goal?: string;
  initial_frame?: string;
  event_outcome?: string;
  background_url?: string;
  characters?: SceneCharacter[];
  props?: SceneProp[];
}

export interface StoryDetail {
  /** 后端 /api/story 不返回 id（路径已经知道）；前端在 store 里手工补上 */
  id?: string;
  title?: string;
  story_summary?: string;
  scene_count: number;
  scenes: Array<{ index: number; type: "narrative" | "interactive"; title?: string; interaction_goal?: string | null }>;
  global_characters?: SceneCharacter[];
  global_objects?: SceneProp[];
}

export interface OpItem {
  subject?: string;
  target?: string;
  action: string;
}
export interface CustomProp {
  // 后端 model 只有 name + url；id 仅前端 UI 自己生成，可选
  id?: string;
  name: string;
  url: string;
}
export interface Interaction {
  scene_idx: number;
  interaction_goal?: string;
  ops: OpItem[];
  custom_props: CustomProp[];
  dynamic_summary?: string;
  comic_url?: string;
}

export interface ReportRequest {
  session_id: string;
  story_id: string;
  interactions: Interaction[];
}

export interface ReportMetric {
  name: string;
  value: number;
  evidence?: string;
}
export interface ReportResponse {
  share: {
    summary?: string;
    honor_title?: string;
    achievements?: Array<{ icon?: string; text?: string }>;
  };
  kid_section: {
    title?: string;
    your_story?: string;
    original_story?: string;
    differences?: string[];
    questions?: string[];
  };
  parent_section: {
    title?: string;
    traits?: string[];
    weaknesses?: string[];
    observations?: string[];
    suggestions?: string[];
    metrics?: ReportMetric[];
  };
}

export interface ShareInit {
  story_title?: string;
  comics: string[];
  props?: CustomProp[];
}
export interface ShareResponse {
  share_id: string;
}

// ---- 互动 ----
export interface Transform {
  name: string;
  kind: "character" | "object";
  x: number;
  y: number;
  scale?: number;
  rotation?: number;
  custom_url?: string;
}
export interface Operation {
  subject?: string;
  subject_kind?: "character" | "object";
  target?: string;
  target_kind?: "character" | "object";
  action: string;
}
export interface InteractRequest {
  story_id?: string;
  session_id: string;
  scene_idx: number;
  placements: Transform[];
  ops: Operation[];
  custom_props: CustomProp[];
}
export interface DialogueLine { speaker: string; content: string; tone?: string; }
export interface InteractResponse {
  node_id: string;
  type: "narrative";
  summary: string;
  narration: string;
  dialogue: DialogueLine[];
  storyboard: StoryboardLine[];
  comic_url: string;
  thumbnail_url: string;
}

export interface PlacementItem {
  name: string;
  kind: "character" | "object";
  x: number;
  y: number;
  scale?: number;
  rotation?: number;
  url?: string;
}
export interface PlacementResponse { placements: PlacementItem[]; }

export interface ChatRequest {
  story_id?: string;
  session_id: string;
  scene_idx: number;
  user_text: string;
}
export interface ChatResponse { reply: string; }

export interface CreatePropRequest {
  session_id: string;
  scene_idx: number;
  name: string;
  description?: string;
  reference_image_url?: string;
  skip_ai?: boolean;
}
export interface CreatePropResponse {
  name: string;
  url: string;
  reference_image_url?: string;
}

// ---- 账号 ----
export interface AuthResponse {
  id: string;
  nickname: string;
  token: string;
}
export interface MeResponse {
  id: string;
  nickname: string;
  created_at: number;
}

// ---- 公共平台 ----
export interface PublicStoryCard {
  id: string;
  title: string;
  summary: string;
  cover_url?: string | null;
  scene_count: number;
  author: string;
  likes: number;
  official?: boolean;
  category?: string;
  emoji_cover?: string | null;
}
export interface PublicAsset {
  id: string;
  name: string;
  kind: "character" | "object";
  url: string;
  svg_url?: string | null;
  category?: string;
}
export interface PublicAssetBundle {
  id: string;
  name: string;
  description?: string;
  cover_emoji?: string | null;
  cover_url?: string | null;
  kind: "character_pack" | "object_pack" | "mixed";
  asset_ids: string[];
  item_count: number;
  official?: boolean;
  likes?: number;
}
export interface PublicStoriesResponse { stories: PublicStoryCard[]; }
export interface PublicAssetsResponse {
  assets: PublicAsset[];
  bundles?: PublicAssetBundle[];
}

// ---- 上传 ----
export interface UploadImageRequest {
  data: string;           // data URL 或纯 base64
  ext?: string;           // 裸 base64 时必填
  kind?: string;          // sketch / prop / avatar / cover / misc
}
export interface UploadImageResponse {
  url: string;
  size: number;
}
