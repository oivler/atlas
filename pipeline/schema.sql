PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT    NOT NULL,
  url         TEXT    NOT NULL UNIQUE,
  community   TEXT,
  source      TEXT    NOT NULL,
  score       INTEGER DEFAULT 0,
  created_at  TEXT    NOT NULL,
  latitude    REAL,
  longitude   REAL,
  location    TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_created ON items(created_at);
CREATE INDEX IF NOT EXISTS idx_items_source  ON items(source);
CREATE INDEX IF NOT EXISTS idx_items_loc     ON items(location) WHERE location IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_title   ON items(title);

CREATE TABLE IF NOT EXISTS term_trends (
  key         TEXT PRIMARY KEY,
  term        TEXT    NOT NULL,
  momentum    REAL    DEFAULT 0,
  recent      INTEGER DEFAULT 0,
  total       INTEGER DEFAULT 0,
  last_seen   TEXT
);

CREATE TABLE IF NOT EXISTS source_state (
  key           TEXT PRIMARY KEY,
  last_fetched  TEXT
);

CREATE TABLE IF NOT EXISTS topics (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  label         TEXT    NOT NULL,
  keywords      TEXT    DEFAULT '[]',
  size          INTEGER DEFAULT 0,
  status        TEXT    DEFAULT 'active',
  first_seen_at TEXT,
  last_seen_at  TEXT
);

CREATE TABLE IF NOT EXISTS topic_history (
  topic_id      INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  bucket_ts     TEXT    NOT NULL,
  emergence     REAL    DEFAULT 0,
  velocity      REAL    DEFAULT 0,
  n_communities INTEGER DEFAULT 0,
  PRIMARY KEY (topic_id, bucket_ts)
);

CREATE TABLE IF NOT EXISTS item_topics (
  item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  topic_id   INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  similarity REAL    DEFAULT 0,
  PRIMARY KEY (item_id, topic_id)
);
