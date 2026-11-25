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
"""

_MAP = """
CREATE TABLE IF NOT EXISTS rooms(room_id TEXT PRIMARY KEY, name TEXT, last_seen_seq INTEGER);
CREATE TABLE IF NOT EXISTS exits(room_id TEXT, dest TEXT, PRIMARY KEY(room_id, dest));
CREATE TABLE IF NOT EXISTS offers(room_id TEXT, action TEXT, seen_seq INTEGER, PRIMARY KEY(room_id, action));
CREATE TABLE IF NOT EXISTS positions(player_id TEXT PRIMARY KEY, room_id TEXT, energy INTEGER, free_storage INTEGER,
                                     seen_seq INTEGER);
"""


def _open(path: Path, schema: str) -> sqlite3.Connection:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    new = not path.exists()
    db = sqlite3.connect(path, timeout=10)
    if new:
        os.chmod(path, 0o600)
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
    def __init__(self, mind: Path) -> None:
        self.db = _open(mind / "memory.db", _SCHEMA)

    def remember(self, text: str, *, kind: str, room: str | None, sequence: int | None) -> None:
        text = " ".join(str(text).split())[:300]
        if not text:
            return
        with self.db:
            cur = self.db.execute("UPDATE facts SET sequence=?, source_sequence=?, stale=0 WHERE kind=? AND room IS ? AND text=?",
                                  (sequence, sequence, kind, room, text))
            if cur.rowcount == 0:
                self.db.execute("INSERT INTO facts(sequence, room, kind, text, source_sequence) VALUES (?,?,?,?,?)",
                                (sequence, room, kind, text, sequence))

    def mark_stale(self, *, kind: str, room: str | None, keep: set[str]) -> None:
        """Current observation wins: room facts of this kind not seen now become stale."""
        with self.db:
            for (fid, text) in self.db.execute("SELECT id, text FROM facts WHERE kind=? AND room IS ? AND stale=0", (kind, room)).fetchall():
                if text not in keep:
                    self.db.execute("UPDATE facts SET stale=1 WHERE id=?", (fid,))

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        terms = [t for t in "".join(c if c.isalnum() else " " for c in query).split() if len(t) > 2][:12]
        if not terms:
            return []
        rows = self.db.execute(
            "SELECT f.text, f.room, f.source_sequence FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
            "WHERE facts_fts MATCH ? AND f.stale=0 ORDER BY rank, f.sequence DESC LIMIT ?",
            (" OR ".join(terms), limit)).fetchall()
        return [{"fact": t, "room": r, "source_sequence": s} for t, r, s in rows]

    def compact(self, *, keep_stale: int = 50) -> int:
        """S20: drop superseded readings and old stale facts. Returns rows deleted.

        "<Label> holds N <res> available to harvest." is a reading: only the newest per (room, label) is kept.
        Stale facts beyond the newest `keep_stale` are dropped (current observation already won).
        """
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
        ids = sorted(set(doomed) | set(stale))
        with self.db:
            self.db.executemany("DELETE FROM facts WHERE id=?", [(i,) for i in ids])
        return len(ids)

    def note_player(self, player_id: str, note: str, *, sign: int, sequence: int | None) -> None:
        """Every piece of evidence is kept; nothing is collapsed into one score (SOCIAL-MEMORY)."""
        with self.db:
            self.db.execute("INSERT INTO relations VALUES (?,?,?,?)", (player_id, note[:200], max(-1, min(1, sign)), sequence))

    def relations(self, player_id: str) -> dict:
        rows = self.db.execute("SELECT sign FROM relations WHERE player_id=?", (player_id,)).fetchall()
        pos, neg = sum(1 for (s,) in rows if s > 0), sum(1 for (s,) in rows if s < 0)
        return {"supporting": pos, "opposing": neg, "contested": bool(pos and neg)}


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
