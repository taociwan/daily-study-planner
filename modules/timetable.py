# -*- coding: utf-8 -*-
"""周课表模块：每周固定课程的增删改查。"""
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from .auth import login_required
from .db import get_db

bp = Blueprint("timetable", __name__)


def _validate(data):
    weekday = data.get("weekday")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    course_name = (data.get("course_name") or "").strip()
    location = (data.get("location") or "").strip()
    note = (data.get("note") or "").strip()

    try:
        weekday = int(weekday)
    except (TypeError, ValueError):
        return None, "星期不合法"
    if not 0 <= weekday <= 6:
        return None, "星期不合法"
    if not course_name:
        return None, "请填写课程名称"
    if not isinstance(start_time, str) or not isinstance(end_time, str):
        return None, "请填写上课时间"
    try:
        datetime.strptime(start_time, "%H:%M")
        datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return None, "时间格式不正确（HH:MM）"
    if end_time <= start_time:
        return None, "下课时间必须晚于上课时间"

    return {
        "weekday": weekday,
        "start_time": start_time,
        "end_time": end_time,
        "course_name": course_name,
        "location": location,
        "note": note,
    }, None


@bp.route("/api/timetable", methods=["GET"])
@login_required
def list_timetable():
    user_id = session["user_id"]
    rows = get_db().execute(
        "SELECT * FROM timetable WHERE user_id=? ORDER BY weekday, start_time",
        (user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/timetable", methods=["POST"])
@login_required
def add_timetable():
    user_id = session["user_id"]
    payload, error = _validate(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO timetable (user_id, weekday, start_time, end_time, course_name, location, note) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, payload["weekday"], payload["start_time"], payload["end_time"],
             payload["course_name"], payload["location"], payload["note"]),
        )
        db.commit()
    except Exception:
        return jsonify({"error": "该时段课程已存在，请调整时间或名称"}), 409
    row = db.execute("SELECT * FROM timetable WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify({"ok": True, "item": dict(row)})


@bp.route("/api/timetable/<int:item_id>", methods=["PUT"])
@login_required
def update_timetable(item_id):
    db = get_db()
    row = db.execute("SELECT * FROM timetable WHERE id=?", (item_id,)).fetchone()
    if row is None:
        return jsonify({"error": "课程不存在"}), 404

    payload, error = _validate(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400

    db.execute(
        "UPDATE timetable SET weekday=?, start_time=?, end_time=?, course_name=?, location=?, note=? "
        "WHERE id=?",
        (payload["weekday"], payload["start_time"], payload["end_time"],
         payload["course_name"], payload["location"], payload["note"], item_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM timetable WHERE id=?", (item_id,)).fetchone()
    return jsonify({"ok": True, "item": dict(row)})


@bp.route("/api/timetable/<int:item_id>", methods=["DELETE"])
@login_required
def delete_timetable(item_id):
    db = get_db()
    db.execute("DELETE FROM timetable WHERE id=?", (item_id,))
    db.commit()
    return jsonify({"ok": True})
