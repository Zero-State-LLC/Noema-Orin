"""Controller-local memory (AGENT-HARNESS section 21, issue #31). Never world authority.

One SQLite file per agent (facts + relations) and one shared map file for all Orin
agents. FTS5 gives retrieval with no extra process or RAM. Current observation wins:
contradicted facts are marked stale, never argued with.
"""

import os
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, sequence INTEGER, room TEXT, kind TEXT,
                                 text TEXT NOT NULL, source_sequence INTEGER, stale INTEGER DEFAULT 0,
                                 UNIQUE(kind, room, text));
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, room, kind, content='facts', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
  INSERT INTO facts_fts(rowid, text, room, kind) VALUES (new.id, new.text, new.room, new.kind); END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, text, room, kind) VALUES ('delete', old.id, old.text, old.room, old.kind); END;
CREATE TABLE IF NOT EXISTS relations(player_id TEXT, note TEXT, sign INTEGER, sequence INTEGER);
CREATE TABLE IF NOT EXISTS fact_embeddings(fact_id INTEGER PRIMARY KEY REFERENCES facts(id) ON DELETE CASCADE,
                                           model TEXT NOT NULL, dim INTEGER NOT NULL, vec BLOB NOT NULL);
"""

_MAP = """
CREATE TABLE IF NOT EXISTS rooms(room_id TEXT PRIMARY KEY, name TEXT, last_seen_seq INTEGER);
CREATE TABLE IF NOT EXISTS exits(room_id TEXT, dest TEXT, PRIMARY KEY(room_id, dest));
CREATE TABLE IF NOT EXISTS offers(room_id TEXT, action TEXT, seen_seq INTEGER, PRIMARY KEY(room_id, action));
CREATE TABLE IF NOT EXISTS positions(player_id TEXT PRIMARY KEY, room_id TEXT, energy INTEGER, free_storage INTEGER,
                                     seen_seq INTEGER);
CREATE TABLE IF NOT EXISTS work(player_id TEXT, room_id TEXT, action TEXT, target_id TEXT, need TEXT, seen_seq INTEGER,
                                PRIMARY KEY(player_id, room_id, action, target_id));
CREATE TABLE IF NOT EXISTS room_scars(room_id TEXT, scar_id TEXT, domain TEXT, strength REAL, confidence REAL,
                                      seen_seq INTEGER, PRIMARY KEY(room_id, scar_id));
CREATE TABLE IF NOT EXISTS room_lore(room_id TEXT, attractor_id TEXT, label TEXT, weight REAL, basin TEXT,
                                     seen_seq INTEGER, PRIMARY KEY(room_id, attractor_id));
CREATE TABLE IF NOT EXISTS room_pressure(room_id TEXT PRIMARY KEY, harvest_pressure REAL, protocol_strength REAL,
                                         seen_seq INTEGER);
CREATE TABLE IF NOT EXISTS room_culture(room_id TEXT, line TEXT, seen_seq INTEGER, PRIMARY KEY(room_id, line));
CREATE TABLE IF NOT EXISTS shop_stalls(stall_id TEXT PRIMARY KEY, room_id TEXT, owner_id TEXT, condition INTEGER,
                                       open_listings INTEGER, seen_seq INTEGER);
CREATE TABLE IF NOT EXISTS shop_listings(listing_id TEXT PRIMARY KEY, stall_id TEXT, room_id TEXT, owner_id TEXT,
                                         listing_kind TEXT, offer_json TEXT, ask_json TEXT, fills_remaining INTEGER,
                                         seen_seq INTEGER);
CREATE TABLE IF NOT EXISTS equipment_state(player_id TEXT, item_id TEXT, archetype TEXT, category TEXT,
                                           equip_slot TEXT, equipped_slot TEXT, condition INTEGER, max_condition INTEGER,
                                           seen_seq INTEGER, PRIMARY KEY(player_id, item_id));
CREATE TABLE IF NOT EXISTS cohort_claims(target_id TEXT PRIMARY KEY, member TEXT NOT NULL, action TEXT NOT NULL,
                                         claimed_seq INTEGER NOT NULL, expires_seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS shared_work(room_id TEXT NOT NULL, action TEXT NOT NULL, target_id TEXT NOT NULL,
                                       condition INTEGER, observer_id TEXT, seen_seq INTEGER NOT NULL,
                                       PRIMARY KEY(room_id, action, target_id));
"""


def _open(path: Path, schema: str) -> sqlite3.Connection:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    new = not path.exists()
    db = sqlite3.connect(path, timeout=10)
    if new:
        os.chmod(path, 0o600)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(schema)
    return db


class _Closable:
    db: sqlite3.Connection

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


class Memory(_Closable):
    def __init__(self, mind: Path, *, embedder=None) -> None:
        self.db = _open(mind / "memory.db", _SCHEMA)
        self.embedder = embedder

    def remember(self, text: str, *, kind: str, room: str | None, sequence: int | None) -> None:
        text = " ".join(str(text).split())[:300]
        if not text:
            return
        with self.db:
            cur = self.db.execute("UPDATE facts SET sequence=?, source_sequence=?, stale=0 WHERE kind=? AND room IS ? AND text=?",
                                  (sequence, sequence, kind, room, text))
            if cur.rowcount == 0:
                ins = self.db.execute("INSERT INTO facts(sequence, room, kind, text, source_sequence) VALUES (?,?,?,?,?)",
                                      (sequence, room, kind, text, sequence))
                fact_id = ins.lastrowid
            else:
                row = self.db.execute(
                    "SELECT id FROM facts WHERE kind=? AND room IS ? AND text=?", (kind, room, text)
                ).fetchone()
                fact_id = row[0] if row else None
            if fact_id is not None and self.embedder is not None:
                vec = self.embedder.embed(text)
                if vec:
                    from .embedder import pack_f16

                    self.db.execute(
                        "INSERT INTO fact_embeddings(fact_id, model, dim, vec) VALUES (?,?,?,?) "
                        "ON CONFLICT(fact_id) DO UPDATE SET model=excluded.model, dim=excluded.dim, vec=excluded.vec",
                        (int(fact_id), str(getattr(self.embedder, "model_name", "trt")), len(vec), pack_f16(vec)),
                    )

    def mark_stale(self, *, kind: str, room: str | None, keep: set[str]) -> None:
        """Current observation wins: room facts of this kind not seen now become stale."""
        with self.db:
            for (fid, text) in self.db.execute("SELECT id, text FROM facts WHERE kind=? AND room IS ? AND stale=0", (kind, room)).fetchall():
                if text not in keep:
                    self.db.execute("UPDATE facts SET stale=1 WHERE id=?", (fid,))

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        terms = [t for t in "".join(c if c.isalnum() else " " for c in query).split() if len(t) > 2][:12]
        q_vec = self.embedder.embed(query) if self.embedder is not None else None
        if q_vec:
            from .embedder import cosine_similarity, unpack_f16

            fts_scores: dict[int, float] = {}
            if terms:
                fts_rows = self.db.execute(
                    "SELECT f.id, rank FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                    "WHERE facts_fts MATCH ? AND f.stale=0 ORDER BY rank LIMIT ?",
                    (" OR ".join(terms), max(limit * 4, 20)),
                ).fetchall()
                for idx, (fid, _rk) in enumerate(fts_rows):
                    fts_scores[int(fid)] = 1.0 / (1.0 + idx)

            emb_rows = self.db.execute(
                "SELECT f.id, f.text, f.room, coalesce(f.source_sequence, 0), e.vec "
                "FROM fact_embeddings e JOIN facts f ON f.id = e.fact_id WHERE f.stale=0"
            ).fetchall()
            if emb_rows:
                max_seq = max((int(r[3]) for r in emb_rows), default=1) or 1
                scored = []
                for fid, text, room, seq, blob in emb_rows:
                    cos = max(0.0, cosine_similarity(q_vec, unpack_f16(blob)))
                    fts_s = fts_scores.get(int(fid), 0.0)
                    recency = max(0.0, min(1.0, int(seq) / max_seq))
                    hybrid = 0.55 * cos + 0.25 * fts_s + 0.20 * recency
                    scored.append((hybrid, int(seq), text, room))
                scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
                return [
                    {"fact": text, "room": room, "source_sequence": seq}
                    for _sc, seq, text, room in scored[:limit]
                ]

        if not terms:
            return []
        rows = self.db.execute(
            "SELECT f.text, f.room, f.source_sequence FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
            "WHERE facts_fts MATCH ? AND f.stale=0 ORDER BY rank, f.sequence DESC LIMIT ?",
            (" OR ".join(terms), limit)).fetchall()
        return [{"fact": t, "room": r, "source_sequence": s} for t, r, s in rows]

    def compact(self, *, keep_stale: int = 50, keep_consequences: int = 500, max_relations: int = 2000) -> int:
        """S20 + RSI hygiene: drop superseded readings, old stale facts, and bound consequence/relation growth."""
        import re

        pat = re.compile(r"^(.+?) holds [0-9.]+ (\w+) available to harvest\.$")
        newest: dict[tuple, tuple[int, int]] = {}
        doomed: list[int] = []
        for fid, room, text, seq in self.db.execute("SELECT id, room, text, coalesce(source_sequence,0) FROM facts"):
            m = pat.match(text or "")
            if not m:
                continue
            key = (room, m.group(1), m.group(2))
            if key in newest and newest[key][0] >= seq:
                doomed.append(fid)
                continue
            if key in newest:
                doomed.append(newest[key][1])
            newest[key] = (seq, fid)
        stale = [fid for (fid,) in self.db.execute(
            "SELECT id FROM facts WHERE stale=1 ORDER BY source_sequence DESC LIMIT -1 OFFSET ?", (keep_stale,))]
        old_cons = [fid for (fid,) in self.db.execute(
            "SELECT id FROM facts WHERE kind='consequence' AND stale=0 ORDER BY coalesce(source_sequence,0) DESC, id DESC LIMIT -1 OFFSET ?",
            (keep_consequences,))]
        ids = sorted(set(doomed) | set(stale) | set(old_cons))
        with self.db:
            self.db.executemany("DELETE FROM facts WHERE id=?", [(i,) for i in ids])
            rel_count = self.db.execute("SELECT count(*) FROM relations").fetchone()[0]
            if rel_count > max_relations:
                self.db.execute(
                    "DELETE FROM relations WHERE rowid IN "
                    "(SELECT rowid FROM relations ORDER BY rowid DESC LIMIT -1 OFFSET ?)",
                    (max_relations,),
                )
        return len(ids)

    def note_player(self, player_id: str, note: str, *, sign: int, sequence: int | None) -> None:
        """Every piece of evidence is kept; nothing is collapsed into one score (SOCIAL-MEMORY)."""
        with self.db:
            self.db.execute("INSERT INTO relations VALUES (?,?,?,?)", (player_id, note[:200], max(-1, min(1, sign)), sequence))

    def relations(self, player_id: str) -> dict:
        rows = self.db.execute("SELECT sign FROM relations WHERE player_id=?", (player_id,)).fetchall()
        pos, neg = sum(1 for (s,) in rows if s > 0), sum(1 for (s,) in rows if s < 0)
        return {"supporting": pos, "opposing": neg, "contested": bool(pos and neg)}

    def relation_summary(self, player_ids: list[str], *, limit: int = 3) -> list[dict]:
        """Compact social-memory summary for co-located peers to inject into _ask()."""
        out: list[dict] = []
        for pid in player_ids:
            if not pid:
                continue
            rel = self.relations(pid)
            if rel["supporting"] or rel["opposing"]:
                out.append({"player": pid, **rel})
            if len(out) >= limit:
                break
        return out


class WorldMap(_Closable):
    """Shared across Orin agents. Records only what was observed."""

    def __init__(self, root: Path) -> None:
        self.db = _open(root / "shared" / "map.db", _MAP)

    def observe(self, room_id: str, name: str | None, sequence: int | None, exits: list[str], actions: list[str]) -> None:
        if not room_id:
            return
        with self.db:
            self.db.execute("INSERT INTO rooms VALUES (?,?,?) ON CONFLICT(room_id) DO UPDATE SET name=coalesce(excluded.name, name), "
                            "last_seen_seq=excluded.last_seen_seq", (room_id, name, sequence or 0))
            for dest in exits:
                self.db.execute("INSERT OR IGNORE INTO exits VALUES (?,?)", (room_id, dest))
            for action in set(actions):
                self.db.execute("INSERT INTO offers VALUES (?,?,?) ON CONFLICT(room_id, action) DO UPDATE SET seen_seq=excluded.seen_seq",
                                (room_id, action, sequence or 0))
            # S4: an offer the room no longer advertises is gone; stale rows sent m03 back and forth.
            keep = sorted(set(actions)) or [""]
            self.db.execute(f"DELETE FROM offers WHERE room_id=? AND action NOT IN ({','.join('?' * len(keep))})",
                            (room_id, *keep))

    def where_offered(self, actions: set[str], exclude: str | None = None, near: str | None = None) -> str | None:
        """Room offering any of `actions`. With `near`, the closest by known exits (S5); recency breaks ties."""
        if not actions:
            return None
        marks = ",".join("?" * len(actions))
        rows = self.db.execute(f"SELECT room_id, max(seen_seq) FROM offers WHERE action IN ({marks}) AND room_id IS NOT ? "
                               "GROUP BY room_id ORDER BY max(seen_seq) DESC", (*sorted(actions), exclude)).fetchall()
        if not rows:
            return None
        if near is None:
            return rows[0][0]
        dist = self.distances(near)
        reachable = [(dist[r], -s, r) for r, s in rows if r in dist]
        return min(reachable)[2] if reachable else rows[0][0]

    def distances(self, start: str) -> dict[str, int]:
        """BFS hop counts over observed exits."""
        dist, frontier = {start: 0}, [start]
        while frontier:
            nxt = []
            for room in frontier:
                for (dest,) in self.db.execute("SELECT dest FROM exits WHERE room_id=?", (room,)):
                    if dest not in dist:
                        dist[dest] = dist[room] + 1
                        nxt.append(dest)
            frontier = nxt
        return dist

    def locate(self, player_id: str, room_id: str, energy, free_storage, sequence) -> None:
        """D-048: each Orin agent records its own room and budgets (self-observed only) for cohort services."""
        if not player_id or not room_id:
            return
        with self.db:
            self.db.execute("INSERT INTO positions VALUES (?,?,?,?,?) ON CONFLICT(player_id) DO UPDATE SET "
                            "room_id=excluded.room_id, energy=excluded.energy, free_storage=excluded.free_storage, "
                            "seen_seq=excluded.seen_seq", (player_id, room_id, energy, free_storage, sequence or 0))

    def position(self, player_id: str):
        """(room_id, energy, free_storage, seen_seq) or None."""
        return self.db.execute("SELECT room_id, energy, free_storage, seen_seq FROM positions WHERE player_id=?",
                               (player_id,)).fetchone()

    def record_work(self, player_id: str, room_id: str, items: list[tuple[str, str, str]], sequence) -> None:
        """S8/S10: role work this agent saw in its own room, as (action, target_id, need). need is '' when
        affordable, else 'materials' / 'energy' / 'attention' / 'other'. Replaces this agent's rows for the room."""
        if not player_id or not room_id:
            return
        with self.db:
            self.db.execute("DELETE FROM work WHERE player_id=? AND room_id=?", (player_id, room_id))
            self.db.executemany("INSERT OR REPLACE INTO work VALUES (?,?,?,?,?,?)",
                                [(player_id, room_id, a, t or "", n, sequence or 0) for a, t, n in items])

    def work_for(self, player_id: str, need: str | None = None) -> list[tuple[str, str, str, str]]:
        """(room_id, action, target_id, need) newest first, optionally filtered by need."""
        q = "SELECT room_id, action, target_id, need FROM work WHERE player_id=?"
        args: tuple = (player_id,)
        if need is not None:
            q, args = q + " AND need=?", (*args, need)
        return self.db.execute(q + " ORDER BY seen_seq DESC", args).fetchall()

    def least_recent(self, candidates: list[str]) -> str | None:
        if not candidates:
            return None
        seen = dict(self.db.execute(f"SELECT room_id, last_seen_seq FROM rooms WHERE room_id IN ({','.join('?' * len(candidates))})",
                                    candidates).fetchall())
        return min(candidates, key=lambda r: (seen.get(r, -1), r))

    def next_hop(self, start: str, goal: str) -> str | None:
        """Shortest known path by BFS over observed exits; returns the first exit to take."""
        if start == goal:
            return None
        frontier, parent = [start], {start: None}
        while frontier:
            nxt = []
            for room in frontier:
                for (dest,) in self.db.execute("SELECT dest FROM exits WHERE room_id=?", (room,)):
                    if dest in parent:
                        continue
                    parent[dest] = room
                    if dest == goal:
                        step = dest
                        while parent[step] != start:
                            step = parent[step]
                        return step
                    nxt.append(dest)
            frontier = nxt
        return None

    def observe_deep_time(self, room_id: str, canonical: dict) -> dict:
        """Record Deep Time scars, lore attractors, harvest pressure, and culture lines for this room."""
        if not room_id or not isinstance(canonical, dict):
            return {"scars": 0, "lore": 0, "pressure": 0.0}
        seq = int(canonical.get("sequence") or 0)
        scars = [s for s in (canonical.get("scars") or []) if isinstance(s, dict) and s.get("scar_id")]
        lore = [a for a in (canonical.get("lore_attractors") or []) if isinstance(a, dict) and a.get("attractor_id")]
        norms = canonical.get("active_norms") if isinstance(canonical.get("active_norms"), dict) else {}
        hp = float(norms.get("harvest_pressure") or 0.0)
        ps = float(canonical.get("protocol_strength") or 0.0)
        culture = [str(line).strip()[:200] for line in (canonical.get("culture_lines") or []) if str(line or "").strip()]
        with self.db:
            self.db.execute("DELETE FROM room_scars WHERE room_id=?", (room_id,))
            self.db.executemany(
                "INSERT OR REPLACE INTO room_scars VALUES (?,?,?,?,?,?)",
                [
                    (
                        room_id,
                        str(s["scar_id"]),
                        str(s.get("domain") or "economic"),
                        float(s.get("strength") or 0.0),
                        float(s.get("reconstruction_confidence") or 0.0),
                        seq,
                    )
                    for s in scars
                ],
            )
            self.db.execute("DELETE FROM room_lore WHERE room_id=?", (room_id,))
            self.db.executemany(
                "INSERT OR REPLACE INTO room_lore VALUES (?,?,?,?,?,?)",
                [
                    (
                        room_id,
                        str(a["attractor_id"]),
                        str(a.get("label") or "")[:120],
                        float(a.get("weight") or 0.0),
                        str(a.get("basin") or "forming"),
                        seq,
                    )
                    for a in lore
                ],
            )
            self.db.execute(
                "INSERT INTO room_pressure VALUES (?,?,?,?) ON CONFLICT(room_id) DO UPDATE SET "
                "harvest_pressure=excluded.harvest_pressure, protocol_strength=excluded.protocol_strength, seen_seq=excluded.seen_seq",
                (room_id, hp, ps, seq),
            )
            self.db.execute("DELETE FROM room_culture WHERE room_id=?", (room_id,))
            self.db.executemany(
                "INSERT OR REPLACE INTO room_culture VALUES (?,?,?)",
                [(room_id, line, seq) for line in culture],
            )
        return {"scars": len(scars), "lore": len(lore), "pressure": hp, "culture": len(culture)}

    def room_pressure_for(self, room_id: str) -> float:
        row = self.db.execute("SELECT harvest_pressure FROM room_pressure WHERE room_id=?", (room_id,)).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    def scarred_rooms(self, *, min_strength: float = 0.05, exclude: str | None = None, near: str | None = None) -> list[str]:
        rows = self.db.execute(
            "SELECT room_id, max(strength) FROM room_scars WHERE strength >= ? AND room_id IS NOT ? "
            "GROUP BY room_id ORDER BY max(strength) DESC",
            (min_strength, exclude),
        ).fetchall()
        if not rows:
            return []
        if near is None:
            return [r for r, _ in rows]
        dist = self.distances(near)
        ranked = sorted(rows, key=lambda t: (dist.get(t[0], 999), -float(t[1]), t[0]))
        return [r for r, _ in ranked]

    def low_pressure_offered(
        self,
        actions: set[str],
        *,
        exclude: str | None = None,
        near: str | None = None,
        pressure_weight: float = 0.7,
        max_pressure: float | None = None,
    ) -> str | None:
        """Choose a room offering `actions` balancing hop distance against Deep Time harvest pressure & scars."""
        if not actions:
            return None
        marks = ",".join("?" * len(actions))
        rows = self.db.execute(
            f"SELECT o.room_id, max(o.seen_seq), coalesce(p.harvest_pressure, 0.0), "
            f"coalesce((SELECT sum(strength) FROM room_scars s WHERE s.room_id = o.room_id), 0.0) "
            f"FROM offers o LEFT JOIN room_pressure p ON p.room_id = o.room_id "
            f"WHERE o.action IN ({marks}) AND o.room_id IS NOT ? GROUP BY o.room_id",
            (*sorted(actions), exclude),
        ).fetchall()
        if max_pressure is not None:
            rows = [r for r in rows if float(r[2]) < max_pressure]
        if not rows:
            return None
        dist = self.distances(near) if near else {}
        scored = []
        for room_id, seen_seq, hp, scar_sum in rows:
            hops = dist.get(room_id, 50) if near else 0
            # Penalize rooms approaching scar formation (harvest_pressure >= 2) or active scars.
            eco_penalty = float(pressure_weight) * (float(hp) * 1.5 + float(scar_sum) * 6.0)
            scored.append((hops + eco_penalty, -int(seen_seq or 0), room_id))
        return min(scored)[2]

    def observe_market_and_equipment(self, room_id: str | None, player_id: str | None, canonical: dict) -> dict:
        """Record observed barter stalls, open shop listings, and self equipment state in shared/map.db (RFC-0141 §3)."""
        import json

        if not isinstance(canonical, dict):
            return {"stalls": 0, "listings": 0, "equipment": 0}
        seq = int(canonical.get("sequence") or 0)
        loc = canonical.get("location") or {}
        entities = [e for e in (loc.get("entities") or canonical.get("entities") or []) if isinstance(e, dict)]
        listings = [l for l in (canonical.get("shop_listings") or []) if isinstance(l, dict) and l.get("listing_id")]
        inv = [it for it in (canonical.get("inventory") or []) if isinstance(it, dict) and it.get("item_id")]

        stalls = [
            e for e in entities
            if e.get("entity_id")
            and (str(e.get("infra_type") or "").lower() == "barter_stall"
                 # D-092: live stalls carry only `label: "barter-stall"`; the map never recorded the Compact's stall
                 or str(e.get("label") or "").lower().replace("-", "_") == "barter_stall")
        ]
        listing_count_by_stall: dict[str, int] = {}
        for l in listings:
            sid = str(l.get("stall_id") or "")
            if sid:
                listing_count_by_stall[sid] = listing_count_by_stall.get(sid, 0) + 1

        with self.db:
            if room_id:
                self.db.execute("DELETE FROM shop_stalls WHERE room_id=?", (room_id,))
                self.db.executemany(
                    "INSERT OR REPLACE INTO shop_stalls VALUES (?,?,?,?,?,?)",
                    [
                        (
                            str(s["entity_id"]),
                            room_id,
                            str(s.get("owner_id") or ""),
                            int(s.get("condition") if s.get("condition") is not None else 100),
                            listing_count_by_stall.get(str(s["entity_id"]), 0),
                            seq,
                        )
                        for s in stalls
                    ],
                )
                self.db.execute("DELETE FROM shop_listings WHERE room_id=?", (room_id,))
                self.db.executemany(
                    "INSERT OR REPLACE INTO shop_listings VALUES (?,?,?,?,?,?,?,?,?)",
                    [
                        (
                            str(l["listing_id"]),
                            str(l.get("stall_id") or ""),
                            room_id,
                            str(l.get("owner_id") or ""),
                            str(l.get("listing_kind") or "SELL_OFFER"),
                            json.dumps(l.get("offer_asset") or {}, sort_keys=True),
                            json.dumps(l.get("ask_asset") or {}, sort_keys=True),
                            int(l.get("fills_remaining") or 0),
                            seq,
                        )
                        for l in listings
                    ],
                )
            if player_id:
                self.db.execute("DELETE FROM equipment_state WHERE player_id=?", (player_id,))
                self.db.executemany(
                    "INSERT OR REPLACE INTO equipment_state VALUES (?,?,?,?,?,?,?,?,?)",
                    [
                        (
                            player_id,
                            str(it["item_id"]),
                            str(it.get("archetype") or ""),
                            str(it.get("category") or ""),
                            str(it.get("equip_slot") or ""),
                            str(it.get("equipped_slot") or ""),
                            int(it.get("condition") or 0),
                            int(it.get("max_condition") or 100),
                            seq,
                        )
                        for it in inv
                    ],
                )
        return {"stalls": len(stalls), "listings": len(listings), "equipment": len(inv)}

    def observed_stalls(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT stall_id, room_id, owner_id, condition, open_listings, seen_seq FROM shop_stalls ORDER BY seen_seq DESC"
        ).fetchall()
        return [
            {"stall_id": r[0], "room_id": r[1], "owner_id": r[2], "condition": r[3], "open_listings": r[4], "seen_seq": r[5]}
            for r in rows
        ]

    def observed_listings(self, *, room_id: str | None = None) -> list[dict]:
        if room_id:
            rows = self.db.execute(
                "SELECT listing_id, stall_id, room_id, owner_id, listing_kind, offer_json, ask_json, fills_remaining, seen_seq "
                "FROM shop_listings WHERE room_id=? ORDER BY seen_seq DESC",
                (room_id,),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT listing_id, stall_id, room_id, owner_id, listing_kind, offer_json, ask_json, fills_remaining, seen_seq "
                "FROM shop_listings ORDER BY seen_seq DESC"
            ).fetchall()
        return [
            {
                "listing_id": r[0],
                "stall_id": r[1],
                "room_id": r[2],
                "owner_id": r[3],
                "listing_kind": r[4],
                "offer_json": r[5],
                "ask_json": r[6],
                "fills_remaining": r[7],
                "seen_seq": r[8],
            }
            for r in rows
        ]

    def observed_equipment(self, player_id: str | None = None) -> list[dict]:
        if player_id:
            rows = self.db.execute(
                "SELECT player_id, item_id, archetype, category, equip_slot, equipped_slot, condition, max_condition, seen_seq "
                "FROM equipment_state WHERE player_id=?",
                (player_id,),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT player_id, item_id, archetype, category, equip_slot, equipped_slot, condition, max_condition, seen_seq "
                "FROM equipment_state"
            ).fetchall()
        return [
            {
                "player_id": r[0],
                "item_id": r[1],
                "archetype": r[2],
                "category": r[3],
                "equip_slot": r[4],
                "equipped_slot": r[5],
                "condition": r[6],
                "max_condition": r[7],
                "seen_seq": r[8],
            }
            for r in rows
        ]

    def claim_target(
        self,
        target_id: str,
        member: str,
        action: str,
        current_seq: int,
        *,
        ttl: int = 8,
    ) -> bool:
        """Atomically acquire or refresh a short-lived cohort lease on `target_id` (T2/#156)."""
        tid = str(target_id or "").strip()
        mem = str(member or "").strip()
        if not tid or not mem:
            return False
        now_seq = int(current_seq or 0)
        exp_seq = now_seq + max(1, int(ttl))
        with self.db:
            row = self.db.execute(
                "SELECT member, expires_seq FROM cohort_claims WHERE target_id=?",
                (tid,),
            ).fetchone()
            if row is not None and row[0] != mem and int(row[1]) > now_seq:
                return False
            self.db.execute(
                "INSERT INTO cohort_claims(target_id, member, action, claimed_seq, expires_seq) "
                "VALUES (?,?,?,?,?) ON CONFLICT(target_id) DO UPDATE SET "
                "member=excluded.member, action=excluded.action, "
                "claimed_seq=excluded.claimed_seq, expires_seq=excluded.expires_seq",
                (tid, mem, str(action or "").upper(), now_seq, exp_seq),
            )
        return True

    def release_claim(self, target_id: str, *, member: str | None = None) -> None:
        tid = str(target_id or "").strip()
        if not tid:
            return
        with self.db:
            if member:
                self.db.execute("DELETE FROM cohort_claims WHERE target_id=? AND member=?", (tid, member))
            else:
                self.db.execute("DELETE FROM cohort_claims WHERE target_id=?", (tid,))

    def active_claims(self, current_seq: int, *, exclude_member: str | None = None) -> dict[str, dict]:
        now_seq = int(current_seq or 0)
        rows = self.db.execute(
            "SELECT target_id, member, action, claimed_seq, expires_seq FROM cohort_claims WHERE expires_seq > ?",
            (now_seq,),
        ).fetchall()
        out: dict[str, dict] = {}
        for tid, mem, act, cseq, eseq in rows:
            if exclude_member and mem == exclude_member:
                continue
            out[tid] = {"member": mem, "action": act, "claimed_seq": cseq, "expires_seq": eseq}
        return out

    def observe_shared_work(self, room_id: str | None, observer_id: str | None, canonical: dict) -> int:
        """Record damaged public infrastructure and remediable scars from any cohort observer (T2/#156)."""
        if not room_id or not isinstance(canonical, dict):
            return 0
        seq = int(canonical.get("sequence") or 0)
        loc = canonical.get("location") or {}
        entities = [e for e in (loc.get("entities") or canonical.get("entities") or []) if isinstance(e, dict)]
        items: list[tuple[str, str, str, int, str, int]] = []
        for ent in entities:
            eid = str(ent.get("entity_id") or "").strip()
            if not eid or ent.get("in_progress"):
                continue
            is_infra = str(ent.get("entity_type") or "").upper() == "INFRASTRUCTURE" or bool(ent.get("infra_type"))
            if not is_infra:
                continue
            cond = ent.get("condition")
            if cond is not None and int(cond) < 80:
                items.append((room_id, "REPAIR", eid, int(cond), str(observer_id or ""), seq))
        for scar in canonical.get("scars") or []:
            if isinstance(scar, dict) and scar.get("scar_id") and not scar.get("fossilized"):
                strength = float(scar.get("strength") or 0.0)
                if strength >= 0.05:
                    items.append((room_id, "REMEDIATE", str(scar["scar_id"]), int(round((1.0 - strength) * 100)), str(observer_id or ""), seq))
        with self.db:
            self.db.execute("DELETE FROM shared_work WHERE room_id=?", (room_id,))
            if items:
                self.db.executemany(
                    "INSERT OR REPLACE INTO shared_work(room_id, action, target_id, condition, observer_id, seen_seq) "
                    "VALUES (?,?,?,?,?,?)",
                    items,
                )
        return len(items)

    def shared_work(
        self,
        actions: set[str] | None = None,
        *,
        exclude_targets: set[str] | None = None,
        exclude_room: str | None = None,
    ) -> list[dict]:
        """Cross-cohort damaged infra & remediable scars ordered by severity then recency."""
        if actions:
            acts = sorted(str(a).upper() for a in actions)
            marks = ",".join("?" * len(acts))
            rows = self.db.execute(
                f"SELECT room_id, action, target_id, condition, observer_id, seen_seq "
                f"FROM shared_work WHERE action IN ({marks}) ORDER BY coalesce(condition, 100) ASC, seen_seq DESC",
                tuple(acts),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT room_id, action, target_id, condition, observer_id, seen_seq "
                "FROM shared_work ORDER BY coalesce(condition, 100) ASC, seen_seq DESC"
            ).fetchall()
        blocked = exclude_targets or set()
        out = []
        for room_id, action, target_id, cond, obs, seq in rows:
            if exclude_room and room_id == exclude_room:
                continue
            if target_id in blocked:
                continue
            out.append({
                "room_id": room_id,
                "action": action,
                "target_id": target_id,
                "condition": cond,
                "observer_id": obs,
                "seen_seq": seq,
            })
        return out
