import sqlite3
import time
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DB_PATH = "defense_leaderboard.db"

def utcnow_i() -> int:
    return int(time.time())

# ---------- Decorator ----------
def with_db(func):
    def wrapper(*args, **kwargs):
        con = sqlite3.connect(DB_PATH, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            res = func(con, *args, **kwargs)
            con.commit()
            return res
        finally:
            con.close()
    return wrapper

# ---------- Create / migrate DB ----------
def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    cur = con.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())

def create_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages(
            message_id INTEGER PRIMARY KEY,
            guild_id   INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            created_ts INTEGER NOT NULL,
            outcome    TEXT,
            incomplete INTEGER,
            last_ts    INTEGER NOT NULL,
            creator_id INTEGER,
            team       INTEGER,
            attack_incomplete INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS participants(
            message_id INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            added_by   INTEGER,
            source     TEXT,
            ts         INTEGER NOT NULL,
            PRIMARY KEY(message_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard_posts(
            guild_id   INTEGER,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            type       TEXT NOT NULL,
            PRIMARY KEY (guild_id, type)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard_totals(
            guild_id INTEGER NOT NULL,
            type     TEXT NOT NULL,
            user_id  INTEGER NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, type, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS aggregates(
            guild_id INTEGER NOT NULL,
            scope    TEXT NOT NULL,
            key      TEXT NOT NULL,
            value    INTEGER NOT NULL,
            PRIMARY KEY (guild_id, scope, key)
        )
    """)

    # ---------- config multi-équipes (4 guildes) ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guild_config(
            guild_id INTEGER PRIMARY KEY,
            alert_channel_id INTEGER,
            leaderboard_channel_id INTEGER,
            snapshot_channel_id INTEGER,
            role_g1_id INTEGER,
            role_g2_id INTEGER,
            role_g3_id INTEGER,
            role_g4_id INTEGER,
            role_test_id INTEGER,
            admin_role_id INTEGER
        )
    """)

    # migrations légères
    try:
        if not _column_exists(con, "messages", "team"):
            cur.execute("ALTER TABLE messages ADD COLUMN team INTEGER")
        if not _column_exists(con, "messages", "attack_incomplete"):
            cur.execute("ALTER TABLE messages ADD COLUMN attack_incomplete INTEGER DEFAULT 0")

        # nouvelles colonnes config si besoin
        for col in ["role_g1_id","role_g2_id","role_g3_id","role_g4_id","role_test_id","admin_role_id",
                    "alert_channel_id","leaderboard_channel_id","snapshot_channel_id"]:
            if not _column_exists(con, "guild_config", col):
                cur.execute(f"ALTER TABLE guild_config ADD COLUMN {col} INTEGER")
        con.commit()
    except Exception:
        pass

    con.commit()
    con.close()

# ---------- Guild config ----------
@with_db
def upsert_guild_config(
    con: sqlite3.Connection,
    guild_id: int,
    alert_channel_id: int,
    leaderboard_channel_id: int,
    snapshot_channel_id: int,
    role_g1_id: int,
    role_g2_id: int,
    role_g3_id: int,
    role_g4_id: int,
    role_test_id: int,
    admin_role_id: int
):
    con.execute("""
        INSERT INTO guild_config
        (guild_id, alert_channel_id, leaderboard_channel_id, snapshot_channel_id,
         role_g1_id, role_g2_id, role_g3_id, role_g4_id, role_test_id, admin_role_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(guild_id) DO UPDATE SET
            alert_channel_id=excluded.alert_channel_id,
            leaderboard_channel_id=excluded.leaderboard_channel_id,
            snapshot_channel_id=excluded.snapshot_channel_id,
            role_g1_id=excluded.role_g1_id,
            role_g2_id=excluded.role_g2_id,
            role_g3_id=excluded.role_g3_id,
            role_g4_id=excluded.role_g4_id,
            role_test_id=excluded.role_test_id,
            admin_role_id=excluded.admin_role_id
    """, (guild_id, alert_channel_id, leaderboard_channel_id, snapshot_channel_id,
          role_g1_id, role_g2_id, role_g3_id, role_g4_id, role_test_id, admin_role_id))

@with_db
def get_guild_config(con: sqlite3.Connection, guild_id: int) -> Optional[dict]:
    row = con.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)).fetchone()
    return dict(row) if row else None

# ---------- Messages ----------
@with_db
def upsert_message(
    con: sqlite3.Connection,
    message_id: int,
    guild_id: int,
    channel_id: int,
    created_ts: int,
    creator_id: Optional[int] = None,
    team: Optional[int] = None,
):
    con.execute("""
        INSERT INTO messages(message_id, guild_id, channel_id, created_ts, outcome, incomplete, last_ts, creator_id, team, attack_incomplete)
        VALUES (?,?,?,?,NULL,0,?,?,?,0)
        ON CONFLICT(message_id) DO NOTHING
    """, (message_id, guild_id, channel_id, created_ts, utcnow_i(), creator_id, team))
    if team is not None:
        con.execute("UPDATE messages SET team=?, last_ts=? WHERE message_id=?", (team, utcnow_i(), message_id))

@with_db
def is_tracked_message(con: sqlite3.Connection, message_id: int) -> bool:
    row = con.execute("SELECT 1 FROM messages WHERE message_id=?", (message_id,)).fetchone()
    return row is not None

@with_db
def get_message_creator(con: sqlite3.Connection, message_id: int) -> Optional[int]:
    row = con.execute("SELECT creator_id FROM messages WHERE message_id=?", (message_id,)).fetchone()
    return row["creator_id"] if row else None

@with_db
def get_message_team(con: sqlite3.Connection, message_id: int) -> Optional[int]:
    row = con.execute("SELECT team FROM messages WHERE message_id=?", (message_id,)).fetchone()
    return int(row["team"]) if row and row["team"] is not None else None

@with_db
def set_outcome(con: sqlite3.Connection, message_id: int, outcome: Optional[str]):
    con.execute("UPDATE messages SET outcome=?, last_ts=? WHERE message_id=?", (outcome, utcnow_i(), message_id))

@with_db
def set_incomplete(con: sqlite3.Connection, message_id: int, incomplete: bool):
    con.execute("UPDATE messages SET incomplete=?, last_ts=? WHERE message_id=?", (1 if incomplete else 0, utcnow_i(), message_id))

# ---------- Participants ----------
@with_db
def add_participant(
    con: sqlite3.Connection,
    message_id: int,
    user_id: int,
    added_by: Optional[int] = None,
    source: str = "reaction"
) -> bool:
    try:
        con.execute("""
            INSERT INTO participants(message_id, user_id, added_by, source, ts)
            VALUES (?,?,?,?,?)
        """, (message_id, user_id, added_by, source, utcnow_i()))
        return True
    except sqlite3.IntegrityError:
        return False

@with_db
def remove_participant(con: sqlite3.Connection, message_id: int, user_id: int) -> bool:
    cur = con.cursor()
    cur.execute("DELETE FROM participants WHERE message_id=? AND user_id=?", (message_id, user_id))
    return cur.rowcount > 0

@with_db
def get_participant_entry(con: sqlite3.Connection, message_id: int, user_id: int):
    row = con.execute("""
        SELECT added_by, source, ts
        FROM participants
        WHERE message_id=? AND user_id=?
    """, (message_id, user_id)).fetchone()
    return (row["added_by"], row["source"], row["ts"]) if row else None

@with_db
def get_participants_detailed(con: sqlite3.Connection, message_id: int) -> List[Tuple[int, Optional[int], int]]:
    rows = con.execute("""
        SELECT user_id, added_by, ts
        FROM participants
        WHERE message_id=?
        ORDER BY ts ASC
    """, (message_id,)).fetchall()
    return [(r["user_id"], r["added_by"], r["ts"]) for r in rows]

@with_db
def get_first_defender(con: sqlite3.Connection, message_id: int) -> Optional[int]:
    row = con.execute("""
        SELECT user_id
        FROM participants
        WHERE message_id=?
        ORDER BY ts ASC
        LIMIT 1
    """, (message_id,)).fetchone()
    return row["user_id"] if row else None

# ---------- Leaderboard counters ----------
@with_db
def incr_leaderboard(con: sqlite3.Connection, guild_id: int, type_: str, user_id: int):
    con.execute("""
        INSERT INTO leaderboard_totals(guild_id, type, user_id, count)
        VALUES (?,?,?,1)
        ON CONFLICT(guild_id, type, user_id) DO UPDATE SET count=count+1
    """, (guild_id, type_, user_id))

@with_db
def decr_leaderboard(con: sqlite3.Connection, guild_id: int, type_: str, user_id: int):
    con.execute("""
        UPDATE leaderboard_totals
        SET count = count - 1
        WHERE guild_id=? AND type=? AND user_id=?
    """, (guild_id, type_, user_id))
    con.execute("""
        DELETE FROM leaderboard_totals
        WHERE guild_id=? AND type=? AND user_id=? AND count<=0
    """, (guild_id, type_, user_id))

@with_db
def reset_leaderboard(con: sqlite3.Connection, guild_id: int, type_: str):
    con.execute("DELETE FROM leaderboard_totals WHERE guild_id=? AND type=?", (guild_id, type_))

@with_db
def get_leaderboard_totals(con: sqlite3.Connection, guild_id: int, type_: str, limit: int = 100):
    rows = con.execute("""
        SELECT user_id, count
        FROM leaderboard_totals
        WHERE guild_id=? AND type=?
        ORDER BY count DESC
        LIMIT ?
    """, (guild_id, type_, limit)).fetchall()
    return [(r["user_id"], r["count"]) for r in rows]

@with_db
def get_leaderboard_totals_all(con: sqlite3.Connection, guild_id: int, type_: str) -> Dict[int, int]:
    rows = con.execute("""
        SELECT user_id, count
        FROM leaderboard_totals
        WHERE guild_id=? AND type=?
        ORDER BY count DESC
    """, (guild_id, type_)).fetchall()
    return {r["user_id"]: r["count"] for r in rows}

# ---------- Leaderboard posts ----------
@with_db
def get_leaderboard_post(con: sqlite3.Connection, guild_id: int, type_: str):
    row = con.execute("""
        SELECT channel_id, message_id
        FROM leaderboard_posts
        WHERE guild_id=? AND type=?
    """, (guild_id, type_)).fetchone()
    return (row["channel_id"], row["message_id"]) if row else None

@with_db
def set_leaderboard_post(con: sqlite3.Connection, guild_id: int, channel_id: int, message_id: int, type_: str):
    con.execute("""
        INSERT INTO leaderboard_posts(guild_id, channel_id, message_id, type)
        VALUES (?,?,?,?)
        ON CONFLICT(guild_id, type) DO UPDATE
        SET channel_id=excluded.channel_id, message_id=excluded.message_id
    """, (guild_id, channel_id, message_id, type_))

# ---------- Aggregates (snapshots) ----------
@with_db
def set_aggregate(con: sqlite3.Connection, guild_id: int, scope: str, key: str, value: int):
    con.execute("""
        INSERT INTO aggregates(guild_id, scope, key, value)
        VALUES (?,?,?,?)
        ON CONFLICT(guild_id, scope, key) DO UPDATE SET value=excluded.value
    """, (guild_id, scope, key, value))

@with_db
def get_aggregate(con: sqlite3.Connection, guild_id: int, scope: str, key: str) -> int:
    row = con.execute("""
        SELECT value FROM aggregates
        WHERE guild_id=? AND scope=? AND key=?
    """, (guild_id, scope, key)).fetchone()
    return int(row["value"]) if row else 0

@with_db
def seed_aggregates(con: sqlite3.Connection, guild_id: int, global_tot: dict, team1: dict, team2: dict, hourly: dict):
    for key, val in global_tot.items():
        set_aggregate(guild_id, "global", key, int(val))
    for key, val in team1.items():
        set_aggregate(guild_id, "team1", key, int(val))
    for key, val in team2.items():
        set_aggregate(guild_id, "team2", key, int(val))
    for key, val in hourly.items():
        set_aggregate(guild_id, "hourly", key, int(val))

@with_db
def seed_leaderboard_totals(con: sqlite3.Connection, guild_id: int, type_: str, totals: Dict[int, int]):
    con.execute("DELETE FROM leaderboard_totals WHERE guild_id=? AND type=?", (guild_id, type_))
    for uid, cnt in totals.items():
        con.execute("""
            INSERT INTO leaderboard_totals(guild_id, type, user_id, count)
            VALUES (?,?,?,?)
        """, (guild_id, type_, int(uid), int(cnt)))

# ---------- Aggregates-aware readers ----------
@with_db
def agg_totals_all(con: sqlite3.Connection, guild_id: int) -> Tuple[int, int, int, int]:
    row = con.execute("""
        SELECT
            SUM(CASE WHEN outcome='win'  THEN 1 ELSE 0 END) AS w,
            SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS l,
            SUM(CASE WHEN incomplete=1  THEN 1 ELSE 0 END) AS inc,
            COUNT(*) AS tot
        FROM messages
        WHERE guild_id=?
    """, (guild_id,)).fetchone()
    w,l,inc,tot = (row["w"] or 0), (row["l"] or 0), (row["inc"] or 0), (row["tot"] or 0)
    if tot > 0:
        return (w, l, inc, tot)
    att = get_aggregate(guild_id, "global", "attacks")
    return (
        get_aggregate(guild_id, "global", "wins"),
        get_aggregate(guild_id, "global", "losses"),
        get_aggregate(guild_id, "global", "incomplete"),
        att,
    )

@with_db
def agg_totals_by_team(con: sqlite3.Connection, guild_id: int, team: int) -> Tuple[int, int, int, int]:
    row = con.execute("""
        SELECT
            SUM(CASE WHEN outcome='win'  THEN 1 ELSE 0 END) AS w,
            SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS l,
            SUM(CASE WHEN incomplete=1  THEN 1 ELSE 0 END) AS inc,
            COUNT(*) AS tot
        FROM messages
        WHERE guild_id=? AND team=?
    """, (guild_id, team)).fetchone()
    w,l,inc,tot = (row["w"] or 0), (row["l"] or 0), (row["inc"] or 0), (row["tot"] or 0)
    if tot > 0:
        return (w, l, inc, tot)
    # fallback snapshot scopes support only team1/team2 historiquement
    scope = "team1" if team == 1 else "team2"
    att = get_aggregate(guild_id, scope, "attacks")
    return (
        get_aggregate(guild_id, scope, "wins"),
        get_aggregate(guild_id, scope, "losses"),
        get_aggregate(guild_id, scope, "incomplete"),
        att,
    )

# ---------- Helpers suppression ----------
@with_db
def get_message_info(con: sqlite3.Connection, message_id: int):
    row = con.execute("SELECT guild_id, creator_id FROM messages WHERE message_id=?", (message_id,)).fetchone()
    if not row:
        return None
    return int(row["guild_id"]), (int(row["creator_id"]) if row["creator_id"] is not None else None)

@with_db
def get_participants_user_ids(con: sqlite3.Connection, message_id: int) -> List[int]:
    rows = con.execute("SELECT user_id FROM participants WHERE message_id=?", (message_id,)).fetchall()
    return [int(r["user_id"]) for r in rows]

@with_db
def delete_message_and_participants(con: sqlite3.Connection, message_id: int):
    con.execute("DELETE FROM participants WHERE message_id=?", (message_id,))
    con.execute("DELETE FROM messages WHERE message_id=?", (message_id,))

# ---------- Player stats ----------
@with_db
def get_player_stats(con: sqlite3.Connection, guild_id: int, user_id: int) -> Tuple[int, int, int, int]:
    row = con.execute("""
        SELECT COUNT(*) AS c
        FROM participants p
        JOIN messages m ON m.message_id = p.message_id
        WHERE m.guild_id = ? AND p.user_id = ?
    """, (guild_id, user_id)).fetchone()
    defenses = int(row["c"] or 0)

    row = con.execute("""
        SELECT COUNT(*) AS c
        FROM messages
        WHERE guild_id = ? AND creator_id = ?
    """, (guild_id, user_id)).fetchone()
    pings = int(row["c"] or 0)

    row = con.execute("""
        SELECT
            SUM(CASE WHEN m.outcome='win'  THEN 1 ELSE 0 END) AS w,
            SUM(CASE WHEN m.outcome='loss' THEN 1 ELSE 0 END) AS l
        FROM messages m
        JOIN participants p ON m.message_id = p.message_id
        WHERE m.guild_id = ? AND p.user_id = ?
    """, (guild_id, user_id)).fetchone()
    wins   = int(row["w"] or 0)
    losses = int(row["l"] or 0)

    return defenses, pings, wins, losses

@with_db
def get_player_recent_defenses(con: sqlite3.Connection, guild_id: int, user_id: int, limit: int = 3) -> List[Tuple[int, Optional[str]]]:
    rows = con.execute("""
        SELECT m.created_ts, m.outcome
        FROM messages m
        JOIN participants p ON m.message_id = p.message_id
        WHERE m.guild_id = ? AND p.user_id = ?
        ORDER BY m.created_ts DESC
        LIMIT ?
    """, (guild_id, user_id, limit)).fetchall()
    return [(int(r["created_ts"]), r["outcome"]) for r in rows]

@with_db
def get_player_hourly_counts(con: sqlite3.Connection, guild_id: int, user_id: int) -> Tuple[int, int, int, int]:
    rows = con.execute("""
        SELECT m.created_ts
        FROM messages m
        JOIN participants p ON m.message_id = p.message_id
        WHERE m.guild_id = ? AND p.user_id = ?
    """, (guild_id, user_id)).fetchall()
    counts = [0, 0, 0, 0]
    for r in rows:
        ts = int(r["created_ts"])
        dt_paris = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ZoneInfo("Europe/Paris"))
        h = dt_paris.hour
        if 6 <= h < 10:
            counts[0] += 1
        elif 10 <= h < 18:
            counts[1] += 1
        elif 18 <= h < 24:
            counts[2] += 1
        else:
            counts[3] += 1
    return tuple(counts)
