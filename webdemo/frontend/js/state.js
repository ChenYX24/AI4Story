export const state = {
  stage: "picking",     // "picking" | "playing" | "report"
  stories: [],          // from /api/stories
  storyId: null,        // picked story id
  story: null,          // /api/story for picked story
  flow: [],            // [FlowNode]
  cursor: 0,
  highestUnlocked: 0,
  sessionId: (crypto?.randomUUID?.() || `s${Date.now()}${Math.random().toString(16).slice(2, 8)}`),
  interactive: resetInteractive(),
  // accumulates interactions for the final report
  storyLog: {
    interactions: [],   // [{scene_idx, interaction_goal, ops, custom_props, dynamic_summary}]
  },
};

export function resetInteractive() {
  return {
    tray: [],           // available items in side tray [{name, kind, url, custom_url?}]
    items: [],          // on-stage items [{name, kind, url, x, y, scale, rotation, custom_url}]
    customProps: [],    // all custom-generated props [{name, url}]
    pendingProps: [],   // [{id, label, promise, resolved:boolean, ok:boolean}]
    selection: [],      // [name]
    ops: [],
    status: "idle",
    placementLoaded: false,
  };
}

export function clearInteractive() {
  state.interactive = resetInteractive();
}

/**
 * FlowNode = {
 *   id: string,
 *   kind: "narrative" | "interactive",
 *   source: "fixed" | "dynamic",
 *   sceneIdx?: number,        // for fixed
 *   title: string,
 *   payload?: object,         // for dynamic narrative (the /api/interact response)
 *   thumbnail?: string,
 *   visited: boolean,
 * }
 */
export function buildInitialFlow(story) {
  return story.scenes.map((s) => ({
    id: `s${s.index}`,
    kind: s.type, // "narrative" | "interactive"
    source: "fixed",
    sceneIdx: s.index,
    title: s.title || `第 ${s.index} 幕`,
    visited: false,
  }));
}

export function insertDynamicNarrative(afterCursor, payload) {
  const node = {
    id: payload.node_id,
    kind: "narrative",
    source: "dynamic",
    title: payload.summary || "新的故事段落",
    payload,
    thumbnail: payload.thumbnail_url,
    visited: false,
  };
  state.flow.splice(afterCursor + 1, 0, node);
  return afterCursor + 1;
}
