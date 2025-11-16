# storage.py
import sqlite3
import time
from typing import Optional, Tuple, List, Dict

DB_PATH = "defense_leaderboard.db"

def utcnow_i() -> int:
    return int(time.time())

# ==============================
# WRAPPER DB
# ==============================

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

# ==============================
# CREATE DB
# ==============================

def create_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Messages
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

    # Participants
    cur.execute("""
        CREATE TABLE IF NOT EXISTS participants(
            message_id INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            added_by   INTEGER,
            source     TEXT,
            ts         INTEGER NOT NULL,
            PRIMARY KEY (message_id, user_id)
        )
    """)

    # Guild config
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

    # Teams
    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_config(
            guild_id    INTEGER NOT NULL,
            team_id     INTEGER NOT NULL,
            name        TEXT NOT NULL,
            role_id     INTEGER NOT NULL,
            label       TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            PRIMARY KEY (guild_id, team_id)
        )
    """)

    # Leaderboard
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard_totals(
            guild_id INTEGER NOT NULL,
            type     TEXT NOT NULL,
            user_id  INTEGER NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, type, user_id)
        )
    """)

    # Attack reports (conservé car certaines parties y font référence)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attack_reports(
            report_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id   INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            author_id  INTEGER NOT NULL,
            target     TEXT,
            created_ts INTEGER NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attack_report_coops(
            report_id INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            PRIMARY KEY (report_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attack_target_totals(
            guild_id INTEGER NOT NULL,
            target   TEXT NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, target)
        )
    """)

    # NEW : dernière alerte utilisée par un joueur (pour attackers)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_last_alert(
            user_id INTEGER PRIMARY KEY,
            message_id INTEGER NOT NULL,
            ts INTEGER NOT NULL
        )
    """)

    con.commit()
    con.close()

# ==============================
# CONFIG GUILDE
# ==============================

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

# ==============================
# TEAMS
# ==============================

@with_db
def upsert_team(con, guild_id: int, team_id: int, name: str, role_id: int, label: str, order_index: int):
    con.execute("""
        INSERT INTO team_config(guild_id, team_id, name, role_id, label, order_index)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(guild_id, team_id) DO UPDATE SET
            name=excluded.name,
            role_id=excluded.role_id,
            label=excluded.label,
            order_index=excluded.order_index
    """, (guild_id, team_id, name, role_id, label, order_index))

@with_db
def get_teams(con, guild_id: int) -> List[dict]:
    rows = con.execute("""
        SELECT team_id, name, role_id, label, order_index
        FROM team_config
        WHERE guild_id=?
        ORDER BY order_index ASC
    """, (guild_id,)).fetchall()
    return [dict(r) for r in rows]

# ==============================
# MESSAGES
# ==============================

@with_db
def upsert_message(con, message_id, guild_id, channel_id, created_ts, creator_id=None, team=None):
    con.execute("""
        INSERT INTO messages(message_id, guild_id, channel_id, created_ts,
                             outcome, incomplete, last_ts, creator_id, team, attack_incomplete)
        VALUES (?,?,?,?,NULL,0,?,?,?,0)
        ON CONFLICT(message_id) DO NOTHING
    """, (message_id, guild_id, channel_id, created_ts, utcnow_i(), creator_id, team))

    if team is not None:
        con.execute("UPDATE messages SET team=?, last_ts=? WHERE message_id=?",
                    (team, utcnow_i(), message_id))

@with_db
def is_tracked_message(con, message_id: int) -> bool:
    return con.execute("SELECT 1 FROM messages WHERE message_id=?", (message_id,)).fetchone() is not None

@with_db
def get_message_creator(con, message_id: int) -> Optional[int]:
    row = con.execute("SELECT creator_id FROM messages WHERE message_id=?", (message_id,)).fetchone()
    return row["creator_id"] if row else None

@with_db
def get_message_team(con, message_id: int) -> Optional[int]:
    row = con.execute("SELECT team FROM messages WHERE message_id=?", (message_id,)).fetchone()
    return row["team"] if row else None

@with_db
def get_message_outcome(con, message_id: int) -> Optional[str]:
    row = con.execute("SELECT outcome FROM messages WHERE message_id=?", (message_id,)).fetchone()
    return row["outcome"] if row else None

@with_db
def set_outcome(con, message_id: int, outcome: Optional[str]):
    con.execute("UPDATE messages SET outcome=?, last_ts=? WHERE message_id=?",
                (outcome, utcnow_i(), message_id))

@with_db
def set_incomplete(con, message_id: int, incomplete: bool):
    con.execute("UPDATE messages SET incomplete=?, last_ts=? WHERE message_id=?",
                (1 if incomplete else 0, utcnow_i(), message_id))

# ==============================
# PARTICIPANTS
# ==============================

@with_db
def add_participant(con, message_id, user_id, added_by=None, source="reaction") -> bool:
    try:
        con.execute("""
            INSERT INTO participants(message_id, user_id, added_by, source, ts)
            VALUES (?,?,?,?,?)
        """, (message_id, user_id, added_by, source, utcnow_i()))
        return True
    except sqlite3.IntegrityError:
        return False

@with_db
def remove_participant(con, message_id, user_id) -> bool:
    cur = con.execute("DELETE FROM participants WHERE message_id=? AND user_id=?",
                      (message_id, user_id))
    return cur.rowcount > 0

@with_db
def get_participant_entry(con, message_id, user_id):
    row = con.execute("""
        SELECT added_by, source, ts
        FROM participants
        WHERE message_id=? AND user_id=?
    """, (message_id, user_id)).fetchone()
    return (row["added_by"], row["source"], row["ts"]) if row else None

@with_db
def get_participants_detailed(con, message_id) -> List[Tuple[int, Optional[int], int]]:
    rows = con.execute("""
        SELECT user_id, added_by, ts
        FROM participants
        WHERE message_id=?
        ORDER BY ts ASC
    """, (message_id,)).fetchall()
    return [(r["user_id"], r["added_by"], r["ts"]) for r in rows]

@with_db
def get_first_defender(con, message_id: int) -> Optional[int]:
    row = con.execute("""
        SELECT user_id FROM participants
        WHERE message_id=?
        ORDER BY ts ASC LIMIT 1
    """, (message_id,)).fetchone()
    return row["user_id"] if row else None

@with_db
def get_participants_user_ids(con, message_id: int) -> List[int]:
    return [r["user_id"] for r in con.execute(
        "SELECT user_id FROM participants WHERE message_id=?", (message_id,)
    ).fetchall()]

# ==============================
# LEADERBOARDS
# ==============================

@with_db
def incr_leaderboard(con, guild_id: int, type_: str, user_id: int):
    con.execute("""
        INSERT INTO leaderboard_totals(guild_id, type, user_id, count)
        VALUES (?,?,?,1)
        ON CONFLICT(guild_id, type, user_id)
        DO UPDATE SET count=count+1
    """, (guild_id, type_, user_id))

@with_db
def decr_leaderboard(con, guild_id: int, type_: str, user_id: int):
    con.execute("""
        UPDATE leaderboard_totals SET count = count - 1
        WHERE guild_id=? AND type=? AND user_id=?
    """, (guild_id, type_, user_id))
    con.execute("""
        DELETE FROM leaderboard_totals
        WHERE guild_id=? AND type=? AND user_id=? AND count<=0
    """, (guild_id, type_, user_id))

@with_db
def get_leaderboard_totals(con, guild_id: int, type_: str, limit: int = 100):
    rows = con.execute("""
        SELECT user_id, count
        FROM leaderboard_totals
        WHERE guild_id=? AND type=?
        ORDER BY count DESC
        LIMIT ?
    """, (guild_id, type_, limit)).fetchall()
    return [(r["user_id"], r["count"]) for r in rows]

@with_db
def get_leaderboard_totals_all(con, guild_id: int, type_: str) -> Dict[int, int]:
    rows = con.execute("""
        SELECT user_id, count
        FROM leaderboard_totals
        WHERE guild_id=? AND type=?
        ORDER BY count DESC
    """, (guild_id, type_)).fetchall()
    return {r["user_id"]: r["count"] for r in rows}

@with_db
def get_leaderboard_value(con, guild_id: int, type_: str, user_id: int) -> int:
    row = con.execute("""
        SELECT count FROM leaderboard_totals
        WHERE guild_id=? AND type=? AND user_id=?
    """, (guild_id, type_, user_id)).fetchone()
    return row["count"] if row else 0

# ==============================
# TRACK MESSAGE + DELETE
# ==============================

@with_db
def get_message_info(con, message_id: int) -> Optional[Tuple[int, int]]:
    row = con.execute("""
        SELECT guild_id, creator_id
        FROM messages WHERE message_id=?
    """, (message_id,)).fetchone()
    return (row["guild_id"], row["creator_id"]) if row else None

@with_db
def delete_message_and_participants(con, message_id: int):
    con.execute("DELETE FROM participants WHERE message_id=?", (message_id,))
    con.execute("DELETE FROM messages WHERE message_id=?", (message_id,))

# ==============================
# LAST ALERT (Pour Attackers)
# ==============================

@with_db
def save_last_alert_for_user(con, user_id: int, message_id: int):
    con.execute("""
        INSERT INTO user_last_alert(user_id, message_id, ts)
        VALUES (?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            message_id=excluded.message_id,
            ts=excluded.ts
    """, (user_id, message_id, utcnow_i()))

@with_db
def get_last_alert_for_user(con, user_id: int) -> Optional[int]:
    row = con.execute("""
        SELECT message_id FROM user_last_alert
        WHERE user_id=?
    """, (user_id,)).fetchone()
    return row["message_id"] if row else None
