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
  id: string;
  name: string;
  url: string;
}
export interface SceneProp {
  id: string;
  name: string;
  url: string;
}
export interface Scene {
  index: number;
  kind: "narrative" | "interactive";
  title?: string;
  summary?: string;
  narration?: string;
  comic_url?: string;
  storyboard?: StoryboardLine[];
  background_url?: string;
  characters?: SceneCharacter[];
  props?: SceneProp[];
}

export interface StoryDetail {
  id: string;
  title: string;
  story_summary?: string;
  scene_count: number;
  scenes: Array<{ index: number; kind: "narrative" | "interactive"; title?: string }>;
}

export interface OpItem {
  subject?: string;
  target?: string;
  action: string;
}
export interface CustomProp {
  id: string;
  name: string;
  url: string;
}
export interface Interaction {
  scene_idx: number;
  interaction_goal?: string;
  ops: OpItem[];
  custom_props: CustomProp[];
  dynamic_summary?: string;
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
}
export interface ShareResponse {
  share_id: string;
}
