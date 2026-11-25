-- Mirror of the Orin's local SQLite memory. Local files stay authoritative for agents.
CREATE TABLE IF NOT EXISTS facts (
  member TEXT NOT NULL, id INTEGER NOT NULL, sequence INTEGER, room TEXT, kind TEXT,
  text TEXT NOT NULL, source_sequence INTEGER, stale INTEGER DEFAULT 0,
  PRIMARY KEY (member, id)
);
CREATE TABLE IF NOT EXISTS relations (
  member TEXT NOT NULL, rowid_local INTEGER NOT NULL, player_id TEXT, note TEXT, sign INTEGER, sequence INTEGER,
  PRIMARY KEY (member, rowid_local)
);
CREATE TABLE IF NOT EXISTS rooms (room_id TEXT PRIMARY KEY, name TEXT, last_seen_seq INTEGER);
CREATE TABLE IF NOT EXISTS exits (room_id TEXT, dest TEXT, PRIMARY KEY (room_id, dest));
CREATE TABLE IF NOT EXISTS offers (room_id TEXT, action TEXT, seen_seq INTEGER, PRIMARY KEY (room_id, action));
CREATE TABLE IF NOT EXISTS personas (member TEXT PRIMARY KEY, version INTEGER, body TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS sessions (
  src TEXT NOT NULL, line INTEGER NOT NULL, ts REAL, member TEXT, role TEXT, actions INTEGER, stop_reason TEXT,
  stop_detail TEXT, role_actions INTEGER, idle_actions INTEGER, turns INTEGER, drops INTEGER, rejections TEXT,
  PRIMARY KEY (src, line)
);
CREATE TABLE IF NOT EXISTS digests (day TEXT PRIMARY KEY, body TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS ai_usage (day TEXT PRIMARY KEY, calls INTEGER DEFAULT 0, cheap_calls INTEGER DEFAULT 0, tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0);
