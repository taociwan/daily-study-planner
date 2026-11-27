# -*- coding: utf-8 -*-
"""数据库连接、初始化与密码哈希（共享底层模块）。"""
import os
import sqlite3
import hashlib
import hmac
from datetime import datetime

from flask import g

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get(
    "STUDY_PLANNER_DB", os.path.join(BASE_DIR, "study_planner.db")
)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def current_time():
    return datetime.now().strftime("%H:%M")


# ---------------- 密码哈希（PBKDF2-HMAC-SHA256，纯标准库） ----------------
def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000
    )
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000
        )
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, AttributeError):
        return False


def _add_column_if_missing(cursor, table, column, definition):
    cols = [r[1] for r in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _rebuild_users_without_name_unique(cursor):
    """旧库 users.name 带 UNIQUE 约束，新注册昵称重名会报 500；重建表去掉该约束。"""
    row = cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if not row or "UNIQUE" not in (row[0] or ""):
        return
    cursor.execute(
        """
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            name TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO users_new (id, username, password_hash, name, age, gender, created_at)
        SELECT id, username, password_hash, name, age, gender, created_at FROM users
        """
    )
    cursor.execute("DROP TABLE users")
    cursor.execute("ALTER TABLE users_new RENAME TO users")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 用户表（新结构：用户名 + 密码哈希；name 为昵称）
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT,
            name TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    # 兼容旧库：补齐新列并回填用户名
    _add_column_if_missing(c, "users", "username", "TEXT")
    _add_column_if_missing(c, "users", "password_hash", "TEXT")
    c.execute("UPDATE users SET username=name WHERE username IS NULL OR username=''")
    _rebuild_users_without_name_unique(c)

    # 每日计划
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            started_at TEXT,
            completed_at TEXT,
            elapsed_seconds INTEGER,
            UNIQUE(user_id, plan_date, start_time)
        )
        """
    )
    _add_column_if_missing(c, "plans", "elapsed_seconds", "INTEGER")
    _add_column_if_missing(c, "plans", "source", "TEXT NOT NULL DEFAULT 'manual'")
    _add_column_if_missing(c, "plans", "goal_id", "INTEGER")
    _add_column_if_missing(c, "plans", "closed_at", "TEXT")

    # 长期目标
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS long_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            daily_task TEXT NOT NULL DEFAULT '',
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            weekdays TEXT NOT NULL DEFAULT '',
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS goal_gen_log (
            goal_id INTEGER NOT NULL,
            plan_date TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            PRIMARY KEY (goal_id, plan_date)
        )
        """
    )
    c.execute("DROP TABLE IF EXISTS plan_templates")
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_gen_log (
            user_id INTEGER NOT NULL,
            plan_date TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, plan_date)
        )
        """
    )

    # 复盘记录
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            review_date TEXT NOT NULL,
            manual_text TEXT NOT NULL DEFAULT '',
            ai_review TEXT NOT NULL DEFAULT '',
            ai_advice TEXT NOT NULL DEFAULT '',
            ai_suggestions TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, review_date)
        )
        """
    )

    # 周课表
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            course_name TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            UNIQUE(user_id, weekday, start_time, course_name)
        )
        """
    )

    # AI 模型配置（每用户一条）
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            base_url TEXT NOT NULL DEFAULT '',
            api_key TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )

    # AI 聊天记录
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()
