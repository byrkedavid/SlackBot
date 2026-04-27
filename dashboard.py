from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, redirect

from services import compute_dashboard_context


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def home():
    return redirect("/dashboard")


@dashboard_bp.route("/dashboard")
def dashboard():
    date_str = request.args.get("date")

    site_filter = request.args.getlist("site")
    if not site_filter:
        site_filter = None

    show_all_sites = request.args.get("show") == "all"

    context = compute_dashboard_context(
        date_str,
        site_filter=site_filter,
        show_all_sites=show_all_sites,
    )
    return render_template("dashboard.html", **context)


@dashboard_bp.route("/api/status")
def api_status():
    date_str = request.args.get("date")
    site_filter = request.args.getlist("site")
    if not site_filter:
        site_filter = None
    context = compute_dashboard_context(date_str, site_filter=site_filter)
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
    site_filter = request.args.getlist("site")
    if not site_filter:
        site_filter = None
    context = compute_dashboard_context(date_str, site_filter=site_filter)
    return jsonify({
        "work_date": context["work_date"],
        "movements": context["movements"],
    })

