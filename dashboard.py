from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from flask import Blueprint, jsonify, render_template, request, redirect

from config import SITE_EMOJI, TIMEZONE
from db import get_daily_movements, get_statuses_for_date
from app import compute_dashboard_context  # intentional import after helpers are available


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def home():
    return redirect("/dashboard")


@dashboard_bp.route("/dashboard")
def dashboard():
    date_str = request.args.get("date")
    context = compute_dashboard_context(date_str)
    return render_template("dashboard.html", **context)


@dashboard_bp.route("/api/status")
def api_status():
    date_str = request.args.get("date")
    context = compute_dashboard_context(date_str)
    return jsonify({
        "work_date": context["work_date"],
        "is_today": context["is_today"],
        "site_sections": context["site_sections"],
        "missing_people": context["missing_people"],
        "not_scheduled_people": context["not_scheduled_people"],
    })


@dashboard_bp.route("/api/movements")
def api_movements():
    date_str = request.args.get("date")
    context = compute_dashboard_context(date_str)
    return jsonify({
        "work_date": context["work_date"],
        "movements": context["movements"],
    })

