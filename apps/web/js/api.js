import { state } from "./state.js";

async function jsonOrThrow(resp) {
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return resp.json();
}

function storyIdOrCurrent(storyId = null) {
  return storyId || state.storyId || null;
}

function withStoryId(payload = {}, storyId = null) {
  const resolvedStoryId = payload.story_id || storyIdOrCurrent(storyId);
  if (!resolvedStoryId) return payload;
  return { ...payload, story_id: resolvedStoryId };
}

function withStoryQuery(path, storyId = null) {
  const resolvedStoryId = storyIdOrCurrent(storyId);
  if (!resolvedStoryId) return path;
  const url = new URL(path, window.location.origin);
  url.searchParams.set("story_id", resolvedStoryId);
  return `${url.pathname}${url.search}`;
}

export async function fetchStory(storyId = null) {
  return jsonOrThrow(await fetch(withStoryQuery("/api/story", storyId)));
}

export async function fetchStories() {
  return jsonOrThrow(await fetch("/api/stories"));
}

export async function postCreateCustomStory(payload) {
  return jsonOrThrow(
    await fetch("/api/stories/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function postReport(payload) {
  return jsonOrThrow(
    await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(withStoryId(payload)),
    })
  );
}

export async function fetchScene(idx, storyId = null) {
  return jsonOrThrow(await fetch(withStoryQuery(`/api/scene/${idx}`, storyId)));
}

export function ttsUrl(text, opts = {}) {
  if (typeof opts === "string") opts = { voice: opts };
  const { voice, tone, speaker } = opts;
  const p = new URLSearchParams({ text });
  if (voice) p.set("voice", voice);
  if (tone) p.set("tone", tone);
  if (speaker) p.set("speaker", speaker);
  return `/api/tts?${p.toString()}`;
}

export async function postInteract(payload) {
  return jsonOrThrow(
    await fetch("/api/interact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(withStoryId(payload)),
    })
  );
}

export async function postChat(payload) {
  return jsonOrThrow(
    await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(withStoryId(payload)),
    })
  );
}

export async function postPlacements(scene_idx, storyId = null) {
  return jsonOrThrow(
    await fetch("/api/placements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(withStoryId({ scene_idx }, storyId)),
    })
  );
}

export async function postCreateProp(payload) {
  return jsonOrThrow(
    await fetch("/api/create_prop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function postCreatePropsBatch(payload) {
  return jsonOrThrow(
    await fetch("/api/create_props_batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function postCreatePropsSmart(payload) {
  return jsonOrThrow(
    await fetch("/api/create_props_smart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function deleteCustomStory(storyId) {
  const resp = await fetch(`/api/stories/custom/${encodeURIComponent(storyId)}`, { method: "DELETE" });
  if (!resp.ok && resp.status !== 204) {
    let detail = `HTTP ${resp.status}`;
    try { const body = await resp.json(); if (body?.detail) detail = body.detail; } catch (_) {}
    throw new Error(detail);
  }
}

export async function patchCustomStory(storyId, payload) {
  return jsonOrThrow(
    await fetch(`/api/stories/custom/${encodeURIComponent(storyId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function postShare(payload) {
  return jsonOrThrow(
    await fetch("/api/share", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}
