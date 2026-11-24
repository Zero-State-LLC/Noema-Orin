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
