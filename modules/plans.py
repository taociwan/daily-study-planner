# -*- coding: utf-8 -*-
"""计划与长期目标模块（每日计划、自动生成、完成度统计）。"""
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from .auth import login_required
from .db import get_db, now_str, current_time

bp = Blueprint("plans", __name__)


def _elapsed_seconds(started_at, completed_at):
    if not started_at or not completed_at:
        return None
    try:
        s = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
        e = datetime.strptime(completed_at, "%Y-%m-%d %H:%M:%S")
        return int((e - s).total_seconds())
    except ValueError:
        return None


def refresh_statuses(user_id, plan_date):
    db = get_db()
    today = date.today().isoformat()
    if plan_date < today:
        db.execute(
            "UPDATE plans SET status='not_completed' "
            "WHERE user_id=? AND plan_date=? AND status='planned'",
            (user_id, plan_date),
        )
        db.execute(
            "UPDATE plans SET status='completed', completed_at=? "
            "WHERE user_id=? AND plan_date=? AND status='in_progress'",
            (now_str(), user_id, plan_date),
        )
    elif plan_date == today:
        now = current_time()
        db.execute(
            "UPDATE plans SET status='not_completed' "
            "WHERE user_id=? AND plan_date=? AND status='planned' AND end_time <= ?",
            (user_id, plan_date, now),
        )
    db.commit()


# ---------------- 通用工具函数 ----------------
def _time_to_minutes(t):
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


def _is_time(t):
    if not isinstance(t, str):
        return False
    try:
        datetime.strptime(t, "%H:%M")
        return True
    except ValueError:
        return False


def _int_list(value):
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for v in value:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def _parse_int_list(text):
    return [int(x) for x in str(text or "").split(",") if x.strip().isdigit()]


def _load_occupied(db, user_id, plan_date):
    rows = db.execute(
        "SELECT start_time, end_time, description FROM plans WHERE user_id=? AND plan_date=?",
        (user_id, plan_date),
    ).fetchall()
    occupied = [(_time_to_minutes(r["start_time"]), _time_to_minutes(r["end_time"])) for r in rows]
    titles = {(r["description"] or "").strip() for r in rows}
    return occupied, titles


def _try_insert_auto(db, user_id, plan_date, title, start_time, end_time,
                     source, occupied, titles, goal_id=None):
    title = (title or "").strip()
    if not title or not _is_time(start_time) or not _is_time(end_time):
        return False
    if end_time <= start_time:
        return False
    if plan_date == date.today().isoformat() and start_time <= current_time():
        return False
    if title in titles:
        return False
    start_min = _time_to_minutes(start_time)
    end_min = _time_to_minutes(end_time)
    for other_start, other_end in occupied:
        if start_min < other_end and end_min > other_start:
            return False
    try:
        db.execute(
            """
            INSERT INTO plans
                (user_id, plan_date, start_time, end_time, description, status,
                 source, goal_id)
            VALUES (?,?,?,?,?,'planned',?,?)
            """,
            (user_id, plan_date, start_time, end_time, title, source, goal_id),
        )
    except sqlite3.IntegrityError:
        return False
    occupied.append((start_min, end_min))
    titles.add(title)
    return True


def _history_candidates(db, user_id, target_date, days=28, limit=4):
    since = (target_date - timedelta(days=days)).isoformat()
    rows = db.execute(
        """
        SELECT plan_date, start_time, end_time, description FROM plans
        WHERE user_id=? AND plan_date >= ? AND plan_date < ?
          AND status IN ('completed', 'in_progress')
        """,
        (user_id, since, target_date.isoformat()),
    ).fetchall()

    same_weekday = defaultdict(list)
    overall = defaultdict(list)
    for r in rows:
        title = (r["description"] or "").strip()
        if not title:
            continue
        try:
            d = date.fromisoformat(r["plan_date"])
        except ValueError:
            continue
        overall[title].append(r)
        if d.weekday() == target_date.weekday():
            same_weekday[title].append(r)

    def rank(groups, min_count):
        items = []
        for title, rs in groups.items():
            if len(rs) < min_count:
                continue
            slot = Counter((r["start_time"], r["end_time"]) for r in rs).most_common(1)[0][0]
            items.append((len(rs), title, slot[0], slot[1]))
        items.sort(key=lambda x: (-x[0], x[2]))
        return items

    picks = rank(same_weekday, 1)
    if len(picks) < 3:
        seen = {p[1] for p in picks}
        picks += [p for p in rank(overall, 2) if p[1] not in seen]
    return picks[:limit]


def ensure_auto_plans(user_id, plan_date):
    try:
        d = date.fromisoformat(plan_date)
    except (TypeError, ValueError):
        return
    if d < date.today():
        return

    db = get_db()
    _ensure_goal_plans(db, user_id, plan_date)

    logged = db.execute(
        "SELECT 1 FROM auto_gen_log WHERE user_id=? AND plan_date=?",
        (user_id, plan_date),
    ).fetchone()
    if logged:
        return

    occupied, titles = _load_occupied(db, user_id, plan_date)
    for _, title, start_time, end_time in _history_candidates(db, user_id, d):
        _try_insert_auto(
            db, user_id, plan_date, title, start_time, end_time,
            "history", occupied, titles,
        )

    db.execute(
        "INSERT OR IGNORE INTO auto_gen_log (user_id, plan_date, generated_at) VALUES (?,?,?)",
        (user_id, plan_date, now_str()),
    )
    db.commit()


# ---------------- 长期目标：工具函数 ----------------
MAX_GOAL_DAYS = 366


def _goal_title(goal):
    return (goal["daily_task"] or "").strip() or goal["title"]


def _goal_covers(goal, d):
    if not (goal["start_date"] <= d.isoformat() <= goal["end_date"]):
        return False
    weekdays = _parse_int_list(goal["weekdays"])
    return not weekdays or d.weekday() in weekdays


def _try_add_goal_plan(db, goal, d):
    if not _goal_covers(goal, d):
        return False
    plan_date = d.isoformat()
    logged = db.execute(
        "SELECT 1 FROM goal_gen_log WHERE goal_id=? AND plan_date=?",
        (goal["id"], plan_date),
    ).fetchone()
    if logged:
        return False

    occupied, titles = _load_occupied(db, goal["user_id"], plan_date)
    inserted = _try_insert_auto(
        db, goal["user_id"], plan_date, _goal_title(goal),
        goal["start_time"], goal["end_time"], "goal", occupied, titles,
        goal_id=goal["id"],
    )
    db.execute(
        "INSERT OR IGNORE INTO goal_gen_log (goal_id, plan_date, generated_at) VALUES (?,?,?)",
        (goal["id"], plan_date, now_str()),
    )
    return inserted


def apply_goal_plans(goal, from_date=None):
    try:
        start = date.fromisoformat(goal["start_date"])
        end = date.fromisoformat(goal["end_date"])
    except (TypeError, ValueError):
        return
    start = max(start, from_date or date.today())
    if start > end:
        return
    db = get_db()
    d = start
    while d <= end:
        _try_add_goal_plan(db, goal, d)
        d += timedelta(days=1)
    db.commit()


def _ensure_goal_plans(db, user_id, plan_date):
    try:
        d = date.fromisoformat(plan_date)
    except (TypeError, ValueError):
        return
    goals = db.execute(
        "SELECT * FROM long_goals WHERE user_id=? AND start_date<=? AND end_date>=?",
        (user_id, plan_date, plan_date),
    ).fetchall()
    for goal in goals:
        _try_add_goal_plan(db, goal, d)
    db.commit()


def _goal_stats(db, user_id):
    rows = db.execute(
        "SELECT goal_id, COUNT(*) AS total, "
        "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS done "
        "FROM plans WHERE user_id=? AND goal_id IS NOT NULL GROUP BY goal_id",
        (user_id,),
    ).fetchall()
    return {r["goal_id"]: (r["total"], r["done"] or 0) for r in rows}


def _goal_json(row, stats, today_str):
    if today_str < row["start_date"]:
        status = "upcoming"
    elif today_str > row["end_date"]:
        status = "ended"
    else:
        status = "active"
    total, done = stats.get(row["id"], (0, 0))
    return {
        "id": row["id"],
        "title": row["title"],
        "daily_task": row["daily_task"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "weekdays": _parse_int_list(row["weekdays"]),
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "status": status,
        "scheduled_count": total,
        "completed_count": done,
    }


def _goal_payload(data):
    title = (data.get("title") or "").strip()
    daily_task = (data.get("daily_task") or "").strip()
    start_time = data.get("start_time")
    end_time = data.get("end_time")

    if not title:
        return None, "请填写目标名称"
    try:
        start_date = date.fromisoformat(data.get("start_date"))
        end_date = date.fromisoformat(data.get("end_date"))
    except (TypeError, ValueError):
        return None, "请选择正确的开始和结束日期"
    if end_date < start_date:
        return None, "结束日期不能早于开始日期"
    if (end_date - start_date).days + 1 > MAX_GOAL_DAYS:
        return None, f"时间范围最多 {MAX_GOAL_DAYS} 天"
    if not _is_time(start_time) or not _is_time(end_time):
        return None, "请填写正确的每日时间段"
    if end_time <= start_time:
        return None, "结束时间必须晚于开始时间"
    weekdays = sorted({d for d in _int_list(data.get("weekdays")) if 0 <= d <= 6})
    if not weekdays:
        return None, "请至少选择一个执行日"

    return {
        "title": title,
        "daily_task": daily_task,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "start_time": start_time,
        "end_time": end_time,
        "weekdays": ",".join(map(str, weekdays)),
    }, None


# ---------------- 长期目标 ----------------
@bp.route("/api/goals", methods=["GET"])
@login_required
def get_goals():
    from flask import session
    user_id = session["user_id"]
    db = get_db()
    today_str = date.today().isoformat()
    rows = db.execute(
        "SELECT * FROM long_goals WHERE user_id=? "
        "ORDER BY CASE WHEN end_date >= ? THEN 0 ELSE 1 END, start_date, id",
        (user_id, today_str),
    ).fetchall()
    stats = _goal_stats(db, user_id)
    return jsonify([_goal_json(r, stats, today_str) for r in rows])


@bp.route("/api/goals", methods=["POST"])
@login_required
def add_goal():
    from flask import session
    data = request.get_json(silent=True) or {}
    user_id = session["user_id"]

    payload, error = _goal_payload(data)
    if error:
        return jsonify({"error": error}), 400

    db = get_db()
    now = now_str()
    cur = db.execute(
        """
        INSERT INTO long_goals
            (user_id, title, daily_task, start_date, end_date, weekdays,
             start_time, end_time, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id, payload["title"], payload["daily_task"],
            payload["start_date"], payload["end_date"], payload["weekdays"],
            payload["start_time"], payload["end_time"], now, now,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM long_goals WHERE id=?", (cur.lastrowid,)).fetchone()
    apply_goal_plans(row)

    stats = _goal_stats(db, user_id)
    return jsonify(
        {"ok": True, "goal": _goal_json(row, stats, date.today().isoformat())}
    )


@bp.route("/api/goals/<int:goal_id>", methods=["PUT"])
@login_required
def update_goal(goal_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM long_goals WHERE id=?", (goal_id,)).fetchone()
    if row is None:
        return jsonify({"error": "长期目标不存在"}), 404

    payload, error = _goal_payload(data)
    if error:
        return jsonify({"error": error}), 400

    today_str = date.today().isoformat()
    db.execute(
        "DELETE FROM plans WHERE goal_id=? AND source='goal' "
        "AND status='planned' AND plan_date>=?",
        (goal_id, today_str),
    )
    db.execute(
        "DELETE FROM goal_gen_log WHERE goal_id=? AND plan_date>=?",
        (goal_id, today_str),
    )
    db.execute(
        """
        UPDATE long_goals
        SET title=?, daily_task=?, start_date=?, end_date=?, weekdays=?,
            start_time=?, end_time=?, updated_at=?
        WHERE id=?
        """,
        (
            payload["title"], payload["daily_task"],
            payload["start_date"], payload["end_date"], payload["weekdays"],
            payload["start_time"], payload["end_time"], now_str(), goal_id,
        ),
    )
    db.commit()

    row = db.execute("SELECT * FROM long_goals WHERE id=?", (goal_id,)).fetchone()
    apply_goal_plans(row)
    stats = _goal_stats(db, row["user_id"])
    return jsonify(
        {"ok": True, "goal": _goal_json(row, stats, date.today().isoformat())}
    )


@bp.route("/api/goals/<int:goal_id>", methods=["DELETE"])
@login_required
def delete_goal(goal_id):
    db = get_db()
    row = db.execute("SELECT * FROM long_goals WHERE id=?", (goal_id,)).fetchone()
    if row is None:
        return jsonify({"error": "长期目标不存在"}), 404

    today_str = date.today().isoformat()
    db.execute(
        "DELETE FROM plans WHERE goal_id=? AND source='goal' "
        "AND status='planned' AND plan_date>=?",
        (goal_id, today_str),
    )
    db.execute("DELETE FROM goal_gen_log WHERE goal_id=?", (goal_id,))
    db.execute("DELETE FROM long_goals WHERE id=?", (goal_id,))
    db.commit()
    return jsonify({"ok": True})


# ---------------- 计划 ----------------
@bp.route("/api/plans", methods=["GET"])
@login_required
def get_plans():
    from flask import session
    user_id = session["user_id"]
    plan_date = request.args.get("date") or date.today().isoformat()

    ensure_auto_plans(user_id, plan_date)
    refresh_statuses(user_id, plan_date)
    rows = get_db().execute(
        "SELECT * FROM plans WHERE user_id=? AND plan_date=? ORDER BY start_time",
        (user_id, plan_date),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/plans", methods=["POST"])
@login_required
def add_plan():
    from flask import session
    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    plan_date = data.get("date") or date.today().isoformat()
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    description = (data.get("description") or "").strip()

    if not start_time or not end_time or not description:
        return jsonify({"error": "请填写完整：开始时间、结束时间、计划内容"}), 400
    if end_time <= start_time:
        return jsonify({"error": "结束时间必须晚于开始时间"}), 400

    db = get_db()
    db.execute(
        """
        INSERT INTO plans (user_id, plan_date, start_time, end_time, description, status, source)
        VALUES (?,?,?,?,?,'planned','manual')
        ON CONFLICT(user_id, plan_date, start_time)
        DO UPDATE SET end_time=excluded.end_time,
                      description=excluded.description,
                      status='planned',
                      started_at=NULL,
                      completed_at=NULL,
                      elapsed_seconds=NULL,
                      closed_at=NULL,
                      source='manual',
                      goal_id=NULL
        """,
        (user_id, plan_date, start_time, end_time, description),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/plans/<int:plan_id>", methods=["PUT"])
@login_required
def update_plan(plan_id):
    data = request.get_json(silent=True) or {}
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    description = (data.get("description") or "").strip()

    db = get_db()
    row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if row is None:
        return jsonify({"error": "计划不存在"}), 404
    if row["status"] != "planned":
        return jsonify({"error": "只有待开始的计划可以编辑"}), 400
    if not start_time or not end_time or not description:
        return jsonify({"error": "请填写完整：开始时间、结束时间、计划内容"}), 400
    if end_time <= start_time:
        return jsonify({"error": "结束时间必须晚于开始时间"}), 400

    clash = db.execute(
        "SELECT 1 FROM plans WHERE user_id=? AND plan_date=? AND start_time=? AND id<>?",
        (row["user_id"], row["plan_date"], start_time, plan_id),
    ).fetchone()
    if clash:
        return jsonify({"error": "该开始时间已有其他计划，请调整时间"}), 409

    db.execute(
        """
        UPDATE plans
        SET start_time=?, end_time=?, description=?, status='planned',
            started_at=NULL, completed_at=NULL, elapsed_seconds=NULL,
            closed_at=NULL, source='manual'
        WHERE id=?
        """,
        (start_time, end_time, description, plan_id),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/plans/generate", methods=["POST"])
@login_required
def generate_plans():
    from flask import session
    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    plan_date = data.get("date") or date.today().isoformat()
    try:
        d = date.fromisoformat(plan_date)
    except (TypeError, ValueError):
        return jsonify({"error": "日期格式不正确"}), 400
    if d < date.today():
        return jsonify({"error": "只能生成今天或未来日期的计划"}), 400

    db = get_db()
    db.execute(
        "DELETE FROM plans WHERE user_id=? AND plan_date=? "
        "AND source IN ('history', 'goal') AND status='planned'",
        (user_id, plan_date),
    )
    db.execute(
        "DELETE FROM auto_gen_log WHERE user_id=? AND plan_date=?",
        (user_id, plan_date),
    )
    db.execute(
        "DELETE FROM goal_gen_log WHERE plan_date=? "
        "AND goal_id IN (SELECT id FROM long_goals WHERE user_id=?)",
        (plan_date, user_id),
    )
    db.commit()
    ensure_auto_plans(user_id, plan_date)
    return jsonify({"ok": True})


@bp.route("/api/plans/<int:plan_id>/start", methods=["POST"])
@login_required
def start_plan(plan_id):
    db = get_db()
    row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if row is None:
        return jsonify({"error": "计划不存在"}), 404

    today = date.today().isoformat()
    if row["plan_date"] < today:
        return jsonify({"error": "计划日期已过，无法开始"}), 409
    if row["plan_date"] > today:
        return jsonify({"error": "只能当天开始计划"}), 409
    if row["status"] == "not_completed":
        return jsonify({"error": "计划时间已过，无法开始"}), 409
    if row["status"] == "completed":
        return jsonify({"error": "该计划已完成"}), 409
    if row["status"] == "in_progress":
        return jsonify({"error": "该计划已开始"}), 409

    now = current_time()
    if now >= row["end_time"]:
        db.execute(
            "UPDATE plans SET status='not_completed' WHERE id=?", (plan_id,)
        )
        db.commit()
        return jsonify({"error": "计划时间已过，无法开始"}), 409

    started_at = now_str()
    early = now < row["start_time"]
    db.execute(
        "UPDATE plans SET status='in_progress', started_at=?, closed_at=NULL WHERE id=?",
        (started_at, plan_id),
    )
    db.commit()
    return jsonify({"ok": True, "started_at": started_at, "early": early})


@bp.route("/api/plans/<int:plan_id>/complete", methods=["POST"])
@login_required
def complete_plan(plan_id):
    db = get_db()
    row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if row is None:
        return jsonify({"error": "计划不存在"}), 404
    if row["status"] not in ("in_progress", "completed"):
        return jsonify({"error": "计划未开始或已结束，不能标记完成"}), 409

    completed_at = now_str()
    elapsed = _elapsed_seconds(row["started_at"], completed_at)
    db.execute(
        "UPDATE plans SET status='completed', completed_at=?, elapsed_seconds=?, closed_at=NULL "
        "WHERE id=?",
        (completed_at, elapsed, plan_id),
    )
    db.commit()
    return jsonify({"ok": True, "completed_at": completed_at, "elapsed_seconds": elapsed})


@bp.route("/api/plans/<int:plan_id>/close", methods=["POST"])
@login_required
def close_plan(plan_id):
    db = get_db()
    row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if row is None:
        return jsonify({"error": "计划不存在"}), 404
    if row["status"] == "completed":
        return jsonify({"error": "该计划已完成，无需结束"}), 409

    closed_at = now_str()
    if row["status"] == "in_progress":
        elapsed = _elapsed_seconds(row["started_at"], closed_at)
        db.execute(
            "UPDATE plans SET status='not_completed', closed_at=?, elapsed_seconds=? WHERE id=?",
            (closed_at, elapsed, plan_id),
        )
    else:
        db.execute(
            "UPDATE plans SET status='not_completed', closed_at=? WHERE id=?",
            (closed_at, plan_id),
        )
    db.commit()
    return jsonify({"ok": True, "closed_at": closed_at})


@bp.route("/api/plans/<int:plan_id>/postpone", methods=["POST"])
@login_required
def postpone_plan(plan_id):
    data = request.get_json(silent=True) or {}
    plan_date = data.get("date")
    start_time = data.get("start_time")
    end_time = data.get("end_time")

    db = get_db()
    row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if row is None:
        return jsonify({"error": "计划不存在"}), 404
    if row["status"] == "completed":
        return jsonify({"error": "已完成的计划不能延顺"}), 409
    if row["status"] == "in_progress":
        return jsonify({"error": "进行中的计划请先结束后再延顺"}), 409

    try:
        new_date = date.fromisoformat(plan_date)
    except (TypeError, ValueError):
        return jsonify({"error": "请选择正确的日期"}), 400
    if new_date < date.today():
        return jsonify({"error": "不能延顺到过去的日期"}), 400
    if not _is_time(start_time) or not _is_time(end_time):
        return jsonify({"error": "请填写正确的开始和结束时间"}), 400
    if end_time <= start_time:
        return jsonify({"error": "结束时间必须晚于开始时间"}), 400
    if new_date.isoformat() == date.today().isoformat() and end_time <= current_time():
        return jsonify({"error": "新时段已结束，请选择更晚的时间"}), 400

    start_min = _time_to_minutes(start_time)
    end_min = _time_to_minutes(end_time)
    others = db.execute(
        "SELECT start_time, end_time FROM plans "
        "WHERE user_id=? AND plan_date=? AND id<>?",
        (row["user_id"], plan_date, plan_id),
    ).fetchall()
    for other in others:
        other_start = _time_to_minutes(other["start_time"])
        other_end = _time_to_minutes(other["end_time"])
        if start_min < other_end and end_min > other_start:
            return jsonify({"error": "该时段与已有计划冲突，请调整时间"}), 409

    db.execute(
        """
        UPDATE plans
        SET plan_date=?, start_time=?, end_time=?, status='planned',
            started_at=NULL, completed_at=NULL, elapsed_seconds=NULL,
            closed_at=NULL, source='manual'
        WHERE id=?
        """,
        (plan_date, start_time, end_time, plan_id),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/plans/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_plan(plan_id):
    db = get_db()
    db.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    db.commit()
    return jsonify({"ok": True})


# ---------------- 每日完成度 ----------------
@bp.route("/api/summary", methods=["GET"])
@login_required
def summary():
    from flask import session
    user_id = session["user_id"]
    plan_date = request.args.get("date") or date.today().isoformat()

    ensure_auto_plans(user_id, plan_date)
    refresh_statuses(user_id, plan_date)
    rows = get_db().execute(
        "SELECT status, COUNT(*) AS c FROM plans "
        "WHERE user_id=? AND plan_date=? GROUP BY status",
        (user_id, plan_date),
    ).fetchall()
    counts = {r["status"]: r["c"] for r in rows}
    total = sum(counts.values())
    return jsonify(
        {
            "total": total,
            "planned": counts.get("planned", 0),
            "in_progress": counts.get("in_progress", 0),
            "completed": counts.get("completed", 0),
            "not_completed": counts.get("not_completed", 0),
        }
    )
