# storage.py — PARTIE 1/3
import sqlite3
import time
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DB_PATH = "defense_leaderboard.db"


def utcnow_i() -> int:
    return int(time.time())


# ================================
# 📌 DECORATOR DB
# ================================
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


# ================================
# 📌 CREATE / MIGRATE DATABASE
# ================================
def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    cur = con.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def create_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # ---------- ALERTES DEFENSE ----------
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

    # ---------- LEADERBOARDS ----------
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

    # ---------- GUILDE & TEAMS ----------
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

    # ================================
    # 📌 ATTAQUES (/attaque)
    # ================================
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

    cur.execute("CREATE INDEX IF NOT EXISTS idx_attack_reports_guild_ts ON attack_reports(guild_id, created_ts)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_attack_coops_report ON attack_report_coops(report_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_attack_target_totals_guild_count ON attack_target_totals(guild_id, count)")

    # ---------- Migrations légères ----------
    try:
        if not _column_exists(con, "messages", "team"):
            cur.execute("ALTER TABLE messages ADD COLUMN team INTEGER")
        if not _column_exists(con, "messages", "attack_incomplete"):
            cur.execute("ALTER TABLE messages ADD COLUMN attack_incomplete INTEGER DEFAULT 0")
    except Exception:
        pass

    con.commit()
    con.close()

# ================================
# 📌 MESSAGES D’ALERTE (DEFENSE)
# ================================

@with_db
def insert_message(con, message_id: int, guild_id: int, channel_id: int, creator_id: int, team: int):
    con.execute("""
        INSERT OR REPLACE INTO messages(message_id, guild_id, channel_id, created_ts, last_ts, creator_id, team)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (message_id, guild_id, channel_id, utcnow_i(), utcnow_i(), creator_id, team))


@with_db
def is_tracked_message(con, message_id: int) -> bool:
    cur = con.execute("SELECT 1 FROM messages WHERE message_id=?", (message_id,))
    return cur.fetchone() is not None


@with_db
def set_outcome(con, message_id: int, outcome: Optional[str]):
    con.execute("UPDATE messages SET outcome=?, last_ts=? WHERE message_id=?",
                (outcome, utcnow_i(), message_id))


@with_db
def set_incomplete(con, message_id: int, inc: bool):
    con.execute("UPDATE messages SET incomplete=?, last_ts=? WHERE message_id=?",
                (1 if inc else 0), utcnow_i(), message_id)


@with_db
def get_message_outcome(con, message_id: int) -> Optional[str]:
    cur = con.execute("SELECT outcome FROM messages WHERE message_id=?", (message_id,))
    row = cur.fetchone()
    return row["outcome"] if row else None


@with_db
def get_message_info(con, message_id: int) -> Optional[Tuple[int, int]]:
    cur = con.execute("SELECT guild_id, creator_id FROM messages WHERE message_id=?", (message_id,))
    row = cur.fetchone()
    return (row["guild_id"], row["creator_id"]) if row else None


# ================================
# 📌 PARTICIPANTS DES DEFENSES
# ================================

@with_db
def add_participant(con, message_id: int, user_id: int, added_by: int, source: str) -> bool:
    try:
        con.execute("""
            INSERT INTO participants(message_id, user_id, added_by, source, ts)
            VALUES (?, ?, ?, ?, ?)
        """, (message_id, user_id, added_by, source, utcnow_i()))
        return True
    except sqlite3.IntegrityError:
        return False


@with_db
def remove_participant(con, message_id: int, user_id: int) -> bool:
    cur = con.execute("DELETE FROM participants WHERE message_id=? AND user_id=?",
                      (message_id, user_id))
    return cur.rowcount > 0


@with_db
def get_participant_entry(con, message_id: int, user_id: int):
    cur = con.execute("""
        SELECT added_by, source, ts FROM participants
        WHERE message_id=? AND user_id=?
    """, (message_id, user_id))
    row = cur.fetchone()
    return (row["added_by"], row["source"], row["ts"]) if row else None


@with_db
def get_participants_user_ids(con, message_id: int) -> List[int]:
    cur = con.execute("SELECT user_id FROM participants WHERE message_id=?", (message_id,))
    return [r["user_id"] for r in cur.fetchall()]


@with_db
def get_first_defender(con, message_id: int) -> Optional[int]:
    cur = con.execute("""
        SELECT user_id FROM participants
        WHERE message_id=?
        ORDER BY ts ASC LIMIT 1
    """, (message_id,))
    row = cur.fetchone()
    return row["user_id"] if row else None


@with_db
def delete_message_and_participants(con, message_id: int):
    con.execute("DELETE FROM participants WHERE message_id=?", (message_id,))
    con.execute("DELETE FROM messages WHERE message_id=?", (message_id,))


# ================================
# 📌 LEADERBOARD — GLOBAL COUNTERS
# ================================

@with_db
def incr_leaderboard(con, guild_id: int, lb_type: str, user_id: int):
    con.execute("""
        INSERT INTO leaderboard_totals(guild_id, type, user_id, count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(guild_id, type, user_id)
        DO UPDATE SET count = count + 1
    """, (guild_id, lb_type, user_id))


@with_db
def decr_leaderboard(con, guild_id: int, lb_type: str, user_id: int):
    con.execute("""
        UPDATE leaderboard_totals
        SET count = MAX(count - 1, 0)
        WHERE guild_id=? AND type=? AND user_id=?
    """, (guild_id, lb_type, user_id))


@with_db
def get_leaderboard_totals(con, guild_id: int, lb_type: str, limit: int = 100) -> List[Tuple[int, int]]:
    cur = con.execute("""
        SELECT user_id, count
        FROM leaderboard_totals
        WHERE guild_id=? AND type=?
        ORDER BY count DESC
        LIMIT ?
    """, (guild_id, lb_type, limit))
    return [(row["user_id"], row["count"]) for row in cur.fetchall()]


@with_db
def get_leaderboard_value(con, guild_id: int, lb_type: str, user_id: int) -> int:
    cur = con.execute("""
        SELECT count FROM leaderboard_totals
        WHERE guild_id=? AND type=? AND user_id=?
    """, (guild_id, lb_type, user_id))
    row = cur.fetchone()
    return row["count"] if row else 0


# ================================
# 📌 GUILDS / TEAMS CONFIG
# ================================

@with_db
def get_guild_config(con, guild_id: int) -> Optional[Dict]:
    cur = con.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))
    row = cur.fetchone()
    return dict(row) if row else None


@with_db
def get_teams(con, guild_id: int) -> List[Dict]:
    cur = con.execute("""
        SELECT * FROM team_config
        WHERE guild_id=? ORDER BY order_index ASC
    """, (guild_id,))
    return [dict(r) for r in cur.fetchall()]


@with_db
def get_leaderboard_post(con, guild_id: int, lb_type: str) -> Optional[Tuple[int, int]]:
    cur = con.execute("""
        SELECT channel_id, message_id
        FROM leaderboard_posts
        WHERE guild_id=? AND type=?
    """, (guild_id, lb_type))
    row = cur.fetchone()
    return (row["channel_id"], row["message_id"]) if row else None


@with_db
def set_leaderboard_post(con, guild_id: int, channel_id: int, message_id: int, lb_type: str):
    con.execute("""
        INSERT OR REPLACE INTO leaderboard_posts(guild_id, channel_id, message_id, type)
        VALUES (?, ?, ?, ?)
    """, (guild_id, channel_id, message_id, lb_type))

# ================================
# 📁 ATTACK LOG (JSON)
# ================================

import json
from typing import Dict, List
from utils import LOG_FILE

def _load_logs() -> dict:
    """Charge le fichier JSON contenant l’historique des attaques."""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_logs(data: dict):
    """Sauvegarde l’historique dans le fichier JSON."""
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# --------------------------------
# 🧩 UTILITAIRES D'ACCÈS
# --------------------------------

def add_attack_log_entry(guild_id: int, message_id: int, team_name: str, timestamp: int):
    """Ajoute une nouvelle entrée dans l’historique (appelée lors d’une nouvelle alerte)."""
    data = _load_logs()
    logs = data.get(str(guild_id), [])

    logs.insert(0, {
        "message_id": message_id,
        "team": team_name,
        "time": timestamp,
        "attackers": "—"
    })

    data[str(guild_id)] = logs[:30]  # conserve les 30 dernières attaques
    _save_logs(data)


def update_attack_log_entry(guild_id: int, message_id: int, alliance_name: str):
    """Met à jour les attaquants pour une alerte déjà enregistrée."""
    data = _load_logs()
    logs = data.get(str(guild_id), [])

    for entry in logs:
        if str(entry.get("message_id")) == str(message_id):
            entry["attackers"] = alliance_name
            break

    data[str(guild_id)] = logs[:30]
    _save_logs(data)


def delete_attack_log_entry(guild_id: int, team_name: str):
    """Supprime l’entrée correspondant à une guilde attaquée (si l’alerte est supprimée)."""
    data = _load_logs()
    logs = data.get(str(guild_id), [])

    logs = [l for l in logs if l.get("team", "").lower() != team_name.lower()]

    data[str(guild_id)] = logs[:30]
    _save_logs(data)


def get_attack_logs(guild_id: int) -> List[dict]:
    """Retourne les dernières attaques enregistrées."""
    data = _load_logs()
    return data.get(str(guild_id), [])
