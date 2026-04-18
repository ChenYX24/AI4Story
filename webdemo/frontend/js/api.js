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

export async function fetchStory() {
  return jsonOrThrow(await fetch("/api/story"));
}

export async function fetchStories() {
  return jsonOrThrow(await fetch("/api/stories"));
}

export async function postReport(payload) {
  return jsonOrThrow(
    await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function fetchScene(idx) {
  return jsonOrThrow(await fetch(`/api/scene/${idx}`));
}

export function ttsUrl(text, opts = {}) {
  // opts: { voice?, tone?, speaker? }. Accepts legacy string as voice too.
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
      body: JSON.stringify(payload),
    })
  );
}

export async function postChat(payload) {
  return jsonOrThrow(
    await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function postPlacements(scene_idx) {
  return jsonOrThrow(
    await fetch("/api/placements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_idx }),
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
