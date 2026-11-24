// Private backup sink for Orin Controller-local memory (D-013, #36).
// POST /sync with Bearer SYNC_TOKEN and {member, facts, relations, rooms, exits, offers, persona}.
// GET /stats returns row counts only, still authenticated. No other routes.

const LIMIT = 2000;

function unauthorized() {
  return new Response("unauthorized", { status: 401 });
}

async function authed(request, env) {
  const got = request.headers.get("authorization") || "";
  const want = `Bearer ${env.SYNC_TOKEN || ""}`;
  if (!env.SYNC_TOKEN || got.length !== want.length) return false;
  const a = new TextEncoder().encode(got);
  const b = new TextEncoder().encode(want);
  return crypto.subtle.timingSafeEqual(a, b);
}

function rows(list, n = LIMIT) {
  return Array.isArray(list) ? list.slice(0, n) : [];
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!(await authed(request, env))) return unauthorized();

    if (request.method === "GET" && url.pathname === "/stats") {
      const out = {};
      for (const t of ["facts", "relations", "rooms", "exits", "offers", "personas"]) {
        out[t] = (await env.DB.prepare(`SELECT count(*) AS n FROM ${t}`).first()).n;
      }
      return Response.json(out);
    }

    if (request.method === "POST" && (url.pathname === "/reflect" || url.pathname === "/chat")) {
      const body = await request.json().catch(() => null);
      if (!body || typeof body.user !== "string" || typeof body.system !== "string") {
        return new Response("bad request", { status: 400 });
      }
      // /reflect: end-of-session persona drift. /chat: per-turn action choice (D-016), short and fast.
      const decide = url.pathname === "/chat";
      const model = decide ? env.DECIDE_MODEL || "@cf/meta/llama-4-scout-17b-16e-instruct"
        : env.REFLECT_MODEL || "@cf/google/gemma-4-26b-a4b-it";
      const maxTokens = Math.min(Math.max(Number(body.max_tokens) || (decide ? 80 : 1024), 16), 1024);
      const out = await env.AI.run(model, {
        messages: [
          { role: "system", content: body.system.slice(0, 4000) },
          { role: "user", content: body.user.slice(0, 6000) },
        ],
        max_tokens: maxTokens,
        temperature: decide ? 0.3 : 0.4,
      });
      const text =
        typeof out?.response === "string" && out.response ? out.response
          : out?.choices?.[0]?.message?.content ?? (typeof out?.response === "object" ? JSON.stringify(out.response) : "");
      return Response.json({ model, text: String(text || ""), shape: Object.keys(out || {}) });
    }

    if (request.method !== "POST" || url.pathname !== "/sync") return new Response("not found", { status: 404 });
    const body = await request.json().catch(() => null);
    if (!body || typeof body.member !== "string" || !/^(_map|[a-z0-9]{1,16})$/.test(body.member)) {
      return new Response("bad request", { status: 400 });
    }
    const m = body.member;
    const stmts = [];
    for (const f of rows(body.facts)) {
      stmts.push(env.DB.prepare(
        "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(member,id) DO UPDATE SET sequence=excluded.sequence, " +
        "source_sequence=excluded.source_sequence, stale=excluded.stale",
      ).bind(m, f.id, f.sequence ?? null, f.room ?? null, f.kind ?? null, String(f.text).slice(0, 300), f.source_sequence ?? null, f.stale ? 1 : 0));
    }
    for (const r of rows(body.relations)) {
      stmts.push(env.DB.prepare("INSERT OR IGNORE INTO relations VALUES (?,?,?,?,?,?)")
        .bind(m, r.rowid, r.player_id, String(r.note || "").slice(0, 200), r.sign, r.sequence ?? null));
    }
    for (const r of rows(body.rooms)) {
      stmts.push(env.DB.prepare("INSERT INTO rooms VALUES (?,?,?) ON CONFLICT(room_id) DO UPDATE SET name=excluded.name, " +
        "last_seen_seq=max(last_seen_seq, excluded.last_seen_seq)").bind(r.room_id, r.name ?? null, r.last_seen_seq ?? 0));
    }
    for (const e of rows(body.exits)) {
      stmts.push(env.DB.prepare("INSERT OR IGNORE INTO exits VALUES (?,?)").bind(e.room_id, e.dest));
    }
    for (const o of rows(body.offers)) {
      stmts.push(env.DB.prepare("INSERT INTO offers VALUES (?,?,?) ON CONFLICT(room_id,action) DO UPDATE SET " +
        "seen_seq=max(seen_seq, excluded.seen_seq)").bind(o.room_id, o.action, o.seen_seq ?? 0));
    }
    if (body.persona && typeof body.persona === "object") {
      stmts.push(env.DB.prepare("INSERT INTO personas VALUES (?,?,?,?) ON CONFLICT(member) DO UPDATE SET version=excluded.version, " +
        "body=excluded.body, updated_at=excluded.updated_at")
        .bind(m, body.persona.version ?? 0, JSON.stringify(body.persona).slice(0, 8000), new Date().toISOString()));
    }
    for (let i = 0; i < stmts.length; i += 100) await env.DB.batch(stmts.slice(i, i + 100));
    return Response.json({ ok: true, written: stmts.length });
  },
};
