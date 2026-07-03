"""Jira Work Dashboard — Streamlit (light theme, navy headers).

An internal Data Unveil productivity dashboard.

Section tabs:
  • Overview        — period assignment summary + work item register
  • Time Activity    — daily logged-hours heatmap
  • Utilization      — daily & weekly (Mon–Fri) logged vs. target
  • Brand Portfolio  — brand filter and team allocation
  • Records          — detailed ticket & time-entry tables

All controls live in the sidebar, grouped by section.
Run:  streamlit run streamlit_app.py   →   http://localhost:8501
"""
from __future__ import annotations

import html as _html
from datetime import date, datetime, timedelta

import plotly.graph_objects as go
import streamlit as st

from jira_sync import (
    JiraClient,
    JiraError,
    credentials_ok,
    get_config,
    resolve_date_range,
)

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# ----- Playful light theme palette (traffic-light semantics) -----------------
BG = "#eef3fb"
CARD = "#ffffff"
NAVY = "#0a1f44"
NAVY2 = "#12336b"
BLUE = "#3b82f6"
LIGHT_BLUE = "#4da3ff"
SKY = "#8ecae6"
TEXT = "#0a1f44"
MUTED = "#5a6b85"
GREEN = "#16a34a"
AMBER = "#f59e0b"
ORANGE = "#f97316"
RED = "#ef4444"
PURPLE = "#8b5cf6"
GRID = "#d7e0f0"

# Soft tints for bubbly cards / conditional formatting
T_GREEN = "#dcfce7"
T_AMBER = "#fef3c7"
T_RED = "#fee2e2"
T_BLUE = "#dbeafe"
T_SKY = "#e0f2fe"
T_PURPLE = "#ede9fe"
T_GRAY = "#eef1f6"

SCOPES = {
    "updated": "Assigned & active in period",
    "worked": "Time logged in period",
    "created": "Created in period",
    "all": "All assigned (all-time)",
}

st.set_page_config(page_title="DAADU JIRA Activity Timeline", page_icon="📊", layout="wide")


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        html, body, .stApp, [class*="css"], .stMarkdown, table.duv,
        section[data-testid="stSidebar"] * {{
            font-family: 'Segoe UI', Calibri, Candara, 'Trebuchet MS', sans-serif !important;
        }}
        header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
        .block-container {{ padding-top: 1.4rem !important; padding-bottom: 2rem; }}
        .stApp {{
            background:
                radial-gradient(circle at 8% 4%, rgba(139,92,246,0.10), transparent 30%),
                radial-gradient(circle at 92% 2%, rgba(59,130,246,0.12), transparent 28%),
                radial-gradient(circle at 55% 100%, rgba(22,163,74,0.08), transparent 35%),
                {BG};
            color: {TEXT};
            font-family: 'Segoe UI', Calibri, sans-serif;
        }}
        h1,h2,h3,h4,p,span,div,label {{ color: {TEXT}; font-family: 'Segoe UI', Calibri, sans-serif; }}
        section[data-testid="stSidebar"] > div {{ background: {NAVY}; border-radius: 0 28px 28px 0; }}
        section[data-testid="stSidebar"] * {{ color: #eaf1ff !important; }}
        section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.15); margin: 0.6rem 0; }}
        /* rounded pill inputs in sidebar */
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div,
        section[data-testid="stSidebar"] input {{ border-radius: 999px !important; }}

        .header-bar {{
            display:flex; align-items:center; justify-content:space-between; gap:16px;
            margin: 0 0 10px; padding: 12px 20px;
            background: rgba(255,255,255,0.7); border:1px solid {GRID};
            border-radius: 30px; box-shadow: 0 10px 26px rgba(10,31,68,0.08);
            backdrop-filter: blur(6px);
        }}
        .header-left {{ display:flex; align-items:center; gap:14px; }}
        .header-mark {{
            width:52px; height:52px; border-radius:50%; display:grid; place-items:center;
            background: linear-gradient(135deg, {PURPLE}, {BLUE}); color:#fff; font-weight:700; font-size:1.15rem;
            font-family:'Segoe UI', Calibri, sans-serif; box-shadow: 0 10px 22px rgba(59,130,246,0.35);
        }}
        .header-title {{ font-family:'Segoe UI', Calibri, sans-serif; font-size:1.7rem; font-weight:700; color:{NAVY}; line-height:1.05; }}
        .header-sub {{ color:{MUTED}; font-size:0.9rem; margin-top:1px; font-weight:600; }}
        .header-right {{ text-align:right; font-size:0.82rem; color:{MUTED}; font-weight:600; }}
        .pill {{ display:inline-block; padding:3px 12px; border-radius:999px; font-weight:800; font-size:0.78rem; }}
        .pill.ok {{ background:{T_GREEN}; color:{GREEN}; }}

        .sidebar-group {{ color:#9fc0ff !important; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.1em; margin:6px 0 4px; font-weight:800; }}

        .sec {{
            display:inline-block; background: linear-gradient(90deg, {NAVY}, {PURPLE});
            color:#fff; padding:9px 22px; border-radius:999px; font-family:'Segoe UI', Calibri, sans-serif;
            font-weight:600; font-size:1.02rem; margin:10px 0 14px;
            box-shadow:0 8px 20px rgba(10,31,68,0.20);
        }}
        .sec span {{ color:#fff !important; }}

        a.kpi-link {{ text-decoration:none !important; display:block; }}
        a.kpi-link:hover {{ text-decoration:none !important; }}
        .card {{
            background:{CARD}; border:2px solid {GRID}; border-radius:28px; padding:16px 18px;
            box-shadow:0 10px 24px rgba(10,31,68,0.07); height:100%; transition: transform .12s ease, box-shadow .12s ease;
        }}
        a.kpi-link:hover .card {{ transform: translateY(-4px); box-shadow:0 16px 30px rgba(10,31,68,0.16); cursor:pointer; }}
        .card.active {{ outline:3px solid {PURPLE}; outline-offset:1px; }}
        .card .lbl {{ color:{MUTED}; font-size:0.82rem; text-transform:uppercase; letter-spacing:0.04em; font-weight:800; }}
        .card .val {{ font-family:'Segoe UI', Calibri, sans-serif; font-size:2rem; font-weight:700; color:{NAVY}; line-height:1.1; margin-top:2px; }}
        .card .desc {{ font-size:0.69rem; color:#8595ad; margin-top:7px; line-height:1.25; font-weight:600; }}
        .card.todo  {{ background:{T_SKY};   border-color:#bde0fe; }}
        .card.todo .val  {{ color:{BLUE}; }}
        .card.prog  {{ background:{T_PURPLE}; border-color:#ddd6fe; }}
        .card.prog .val  {{ color:{PURPLE}; }}
        .card.done  {{ background:{T_GREEN}; border-color:#bbf7d0; }}
        .card.done .val  {{ color:{GREEN}; }}
        .card.over  {{ background:{T_RED};   border-color:#fecaca; }}
        .card.over .val  {{ color:{RED}; }}
        .card.total {{ background: linear-gradient(135deg, #ffffff, #eef2ff); border-color:#c7d2fe; }}

        .status-ok {{ color:{GREEN}; font-weight:800; }}
        .status-err {{ color:{RED}; font-weight:800; }}

        .stButton > button {{
            background: linear-gradient(135deg, {PURPLE}, {BLUE}); color:#fff; border:none;
            border-radius:999px; padding:0.55rem 1rem; font-weight:800; width:100%;
            box-shadow:0 8px 18px rgba(99,102,241,0.30);
        }}
        .stButton > button:hover {{ filter:brightness(1.07); transform:translateY(-1px); }}

        .stTabs [data-baseweb="tab-list"] {{ gap:8px; }}
        .stTabs [data-baseweb="tab"] {{
            background:#e2e9f8; border-radius:999px; padding:8px 20px; font-weight:800; border:2px solid transparent;
        }}
        .stTabs [aria-selected="true"] {{
            background: linear-gradient(135deg, {NAVY}, {PURPLE}); border-color:transparent;
        }}
        .stTabs [aria-selected="true"] * {{ color:#fff !important; }}

        div[data-testid="stDataFrame"] {{ border-radius:22px; overflow:hidden; border:2px solid {GRID}; }}
        a {{ color:{BLUE}; font-weight:700; }}

        /* Navy-header HTML tables */
        .tbl-scroll {{ max-height:460px; overflow:auto; border:2px solid {GRID}; border-radius:22px; box-shadow:0 10px 24px rgba(10,31,68,0.07); }}
        table.duv {{ border-collapse:separate; border-spacing:0; width:100%; font-size:0.9rem; background:{CARD}; }}
        table.duv thead th {{
            position:sticky; top:0; z-index:3; background:{NAVY}; color:#fff !important;
            font-family:'Segoe UI', Calibri, sans-serif; font-weight:800; font-size:0.93rem; text-transform:uppercase;
            letter-spacing:0.03em; padding:12px 13px; text-align:left; white-space:nowrap;
        }}
        table.duv thead th:first-child {{ border-top-left-radius:18px; }}
        table.duv thead th:last-child {{ border-top-right-radius:18px; }}
        table.duv tbody td {{ padding:9px 13px; border-bottom:1px solid {GRID}; color:{TEXT}; vertical-align:top; }}
        table.duv tbody tr:hover td {{ background:#f5f8ff; }}
        table.duv tbody tr:last-child td {{ border-bottom:none; }}
        table.duv a {{ font-weight:800; }}
        .chip {{ padding:3px 11px; border-radius:999px; font-weight:800; font-size:0.76rem; display:inline-block; white-space:nowrap; }}
        .cell-summary {{ max-width:340px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def sec(title: str) -> None:
    st.markdown(f'<div class="sec"><span>{title}</span></div>', unsafe_allow_html=True)


def card(label: str, value: str, kind: str = "", icon: str = "", desc: str = "", active: bool = False) -> str:
    lbl = f"{icon} {label}".strip()
    cls = f"card {kind}" + (" active" if active else "")
    return (
        f'<div class="{cls}" title="{desc}">'
        f'<div class="lbl">{lbl}</div>'
        f'<div class="val">{value}</div>'
        f'<div class="desc">{desc}</div></div>'
    )


def group(title: str) -> None:
    st.markdown(f'<div class="sidebar-group">{title}</div>', unsafe_allow_html=True)


# ----- Cached loaders --------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def cached_users() -> list[dict]:
    return JiraClient(get_config()).list_users()


@st.cache_data(ttl=600, show_spinner=False)
def cached_brands() -> list[str]:
    return JiraClient(get_config()).list_brands()


@st.cache_data(ttl=90, show_spinner=False)
def cached_person(account_id: str, display_name: str, start_iso: str, end_iso: str) -> dict:
    return JiraClient(get_config()).build_person_dashboard(
        account_id, display_name, date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    )


@st.cache_data(ttl=90, show_spinner=False)
def cached_brand_view(brand: str, only_open: bool) -> dict:
    return JiraClient(get_config()).build_brand_view(brand, only_open)


# ----- Helpers ---------------------------------------------------------------
def apply_filters(tickets: list[dict], priorities: list, labels_sel: list, sprints_sel: list) -> list[dict]:
    out = []
    for t in tickets:
        if priorities and t.get("priority") not in priorities:
            continue
        if labels_sel and not (set(t.get("labels", [])) & set(labels_sel)):
            continue
        if sprints_sel and not (set(t.get("sprints", [])) & set(sprints_sel)):
            continue
        out.append(t)
    return out


def search_tickets(tickets: list[dict], query: str) -> list[dict]:
    q = query.strip().lower()
    if not q:
        return tickets
    out = []
    for t in tickets:
        haystack = " ".join([
            t.get("key", ""), t.get("summary", ""), t.get("brand", ""),
            t.get("status", ""), t.get("priority", ""), t.get("sprint", ""),
            " ".join(t.get("labels", [])),
        ]).lower()
        if q in haystack:
            out.append(t)
    return out


def counts_of(tickets: list[dict]) -> dict:
    c = {"total": 0, "todo": 0, "in_progress": 0, "done": 0, "overdue": 0}
    for t in tickets:
        c["total"] += 1
        cat = t["status_category"]
        if cat == "done":
            c["done"] += 1
        elif cat == "indeterminate":
            c["in_progress"] += 1
        else:
            c["todo"] += 1
        if t.get("overdue"):
            c["overdue"] += 1
    return c


def _esc(v) -> str:
    return _html.escape(str(v if v is not None else ""))


def chip(text: str, bg: str, fg: str) -> str:
    return f'<span class="chip" style="background:{bg};color:{fg}">{_esc(text)}</span>'


def status_chip(v: str) -> str:
    s = str(v).lower()
    if any(w in s for w in ("done", "closed", "resolved", "complete")):
        return chip(v, T_GREEN, GREEN)
    if any(w in s for w in ("progress", "review", "testing", "dev")):
        return chip(v, T_PURPLE, PURPLE)
    return chip(v, T_SKY, BLUE)


def priority_chip(v: str) -> str:
    s = str(v).lower()
    if s in ("highest", "high", "critical", "blocker"):
        return chip(v, T_RED, RED)
    if s == "medium":
        return chip(v, T_AMBER, ORANGE)
    if s in ("low", "lowest", "trivial", "minor"):
        return chip(v, T_GREEN, GREEN)
    return _esc(v)


def overdue_chip(is_overdue: bool) -> str:
    return chip("Yes", T_RED, RED) if is_overdue else chip("No", T_GREEN, GREEN)


def _link(url: str, text: str) -> str:
    return f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(text)}</a>'


def render_html_table(
    headers: list[str], rows: list[list[str]], height: int = 460,
    row_styles: list[str] | None = None,
) -> None:
    thead = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_parts = []
    for i, r in enumerate(rows):
        style = f' style="background:{row_styles[i]}"' if row_styles else ""
        body_parts.append(f"<tr{style}>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    body = "".join(body_parts)
    st.markdown(
        f'<div class="tbl-scroll" style="max-height:{height}px">'
        f'<table class="duv"><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def ticket_table(tickets: list[dict]) -> None:
    if not tickets:
        st.info("No work items match the current filters.")
        return
    headers = ["Key", "Summary", "Brand", "Priority", "Status", "Sprint",
               "Labels", "Due", "Overdue", "Hours"]
    rows = []
    for t in tickets:
        rows.append([
            _link(t["issue_url"], t["key"]),
            f'<div class="cell-summary">{_esc(t["summary"])}</div>',
            _esc(t.get("brand", "—")),
            priority_chip(t.get("priority", "-")),
            status_chip(t["status"]),
            _esc(t.get("sprint", "—")),
            _esc(", ".join(t.get("labels", [])) or "—"),
            _esc(t.get("duedate") or "—"),
            overdue_chip(bool(t.get("overdue"))),
            f'{t.get("hours_in_range", 0.0):.2f} h',
        ])
    render_html_table(headers, rows)


# ----- Charts ----------------------------------------------------------------
def heatmap(daily: list[dict]) -> go.Figure:
    hours = {d["date"]: d["hours"] for d in daily}
    dates = sorted(date.fromisoformat(d["date"]) for d in daily)
    start, end = dates[0], dates[-1]
    grid_start = start - timedelta(days=start.weekday())
    num_weeks = ((end - grid_start).days // 7) + 1
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    z = [[None] * num_weeks for _ in range(7)]
    text = [[""] * num_weeks for _ in range(7)]
    x_labels = []
    for w in range(num_weeks):
        monday = grid_start + timedelta(weeks=w)
        x_labels.append(monday.strftime("%b %d"))
        for wd in range(7):
            day = monday + timedelta(days=wd)
            if start <= day <= end:
                val = hours.get(day.isoformat(), 0.0)
                z[wd][w] = val
                text[wd][w] = f"{day.strftime('%a %b %d')}<br>{val:.2f} h"
    fig = go.Figure(go.Heatmap(
        z=z, x=x_labels, y=weekdays, text=text, hoverinfo="text",
        colorscale=[[0.0, "#e8eefc"], [0.3, "#9cc4f5"], [0.6, LIGHT_BLUE], [1.0, NAVY]],
        xgap=4, ygap=4, hoverongaps=False, colorbar=dict(title="Hours"),
    ))
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color=TEXT,
        margin=dict(l=10, r=10, t=10, b=10), height=300,
        yaxis=dict(autorange="reversed", showgrid=False), xaxis=dict(showgrid=False, side="top"),
    )
    return fig


def stacked_bar(rows: list[dict]) -> go.Figure:
    labels = [r["label"] for r in rows]
    fig = go.Figure()
    fig.add_bar(x=labels, y=[r["logged"] for r in rows], name="Logged", marker_color=NAVY,
                hovertemplate="%{x}<br>Logged %{y:.2f}h<extra></extra>")
    fig.add_bar(x=labels, y=[r["remaining"] for r in rows], name="Remaining", marker_color=SKY,
                hovertemplate="%{x}<br>Remaining %{y:.2f}h<extra></extra>")
    fig.update_layout(
        barmode="stack", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font_color=TEXT, margin=dict(l=10, r=10, t=10, b=10), height=320,
        legend=dict(orientation="h", y=1.12), yaxis=dict(gridcolor=GRID, title="Hours"),
        xaxis=dict(showgrid=False),
    )
    return fig


def build_daygrid(daily: list[dict], target: float, count_weekends: bool) -> tuple[list[dict], float]:
    rows, total_deficit = [], 0.0
    for d in daily:
        tgt = target if (count_weekends or not d["is_weekend"]) else 0.0
        logged = d["hours"]
        remaining = round(max(0.0, tgt - logged), 2)
        total_deficit += remaining
        status = ("Weekend" if tgt == 0 else "Met" if logged >= tgt
                  else "Not logged" if logged == 0 else "Short")
        rows.append({
            "date": d["date"], "label": d["label"], "is_weekend": d["is_weekend"],
            "logged": logged, "target": tgt, "remaining": remaining, "status": status,
        })
    return rows, round(total_deficit, 2)


def build_weekly(daily: list[dict], target: float, count_weekends: bool) -> list[dict]:
    weeks: dict[tuple, dict] = {}
    for d in daily:
        dt = date.fromisoformat(d["date"])
        iso = dt.isocalendar()
        key = (iso[0], iso[1])
        wk = weeks.setdefault(key, {"start": dt, "end": dt, "logged": 0.0, "target_days": 0})
        wk["start"] = min(wk["start"], dt)
        wk["end"] = max(wk["end"], dt)
        wk["logged"] += d["hours"]
        if count_weekends or not d["is_weekend"]:
            wk["target_days"] += 1
    rows = []
    for _, wk in sorted(weeks.items()):
        tgt = wk["target_days"] * target
        logged = round(wk["logged"], 2)
        rows.append({
            "Week": f'{wk["start"].strftime("%b %d")} – {wk["end"].strftime("%b %d")}',
            "Logged (h)": logged,
            "Work days": wk["target_days"],
            "Target (h)": round(tgt, 1),
            "Remaining (h)": round(max(0.0, tgt - logged), 2),
            "Avg/day (h)": round(logged / wk["target_days"], 2) if wk["target_days"] else 0.0,
        })
    return rows


KPI_DEFS = [
    ("total", "Total Work Items", "total", "📌", "All tickets in scope, regardless of status."),
    ("todo", "Not Started", "todo", "🕒", "Items in a To-Do / backlog status."),
    ("in_progress", "In Progress", "prog", "🔧", "Items actively being worked."),
    ("done", "Completed", "done", "✅", "Items resolved / done in this period."),
    ("overdue", "Overdue", "over", "⚠️", "Past their due date and not yet completed."),
]


def _kpi_filter(tickets: list[dict], key: str) -> list[dict]:
    if key == "total":
        return tickets
    if key == "done":
        return [t for t in tickets if t["status_category"] == "done"]
    if key == "in_progress":
        return [t for t in tickets if t["status_category"] == "indeterminate"]
    if key == "todo":
        return [t for t in tickets if t["status_category"] not in ("done", "indeterminate")]
    if key == "overdue":
        return [t for t in tickets if t.get("overdue")]
    return tickets


def current_kpi() -> str:
    sel = st.query_params.get("kpi", "total")
    return sel if sel in {k for k, *_ in KPI_DEFS} else "total"


def kpi_summary_clickable(tickets: list[dict]) -> None:
    counts = counts_of(tickets)
    values = {
        "total": counts["total"], "todo": counts["todo"], "in_progress": counts["in_progress"],
        "done": counts["done"], "overdue": counts["overdue"],
    }
    sel = current_kpi()
    cols = st.columns(5)
    for i, (key, label, kind, icon, desc) in enumerate(KPI_DEFS):
        with cols[i]:
            html_card = card(label, str(values[key]), kind, icon, desc, active=(key == sel))
            st.markdown(
                f'<a class="kpi-link" href="?kpi={key}" target="_self">{html_card}</a>',
                unsafe_allow_html=True,
            )


# ----- Section renderers -----------------------------------------------------
def tab_overview(tickets: list[dict], scope: str) -> None:
    sec(f"Assignment Summary — {SCOPES[scope]}")
    kpi_summary_clickable(tickets)
    st.caption(
        "Click any metric card to dump its ticket-level data below "
        "(honours the sidebar period, scope and filters)."
    )
    st.write("")

    brand_agg: dict[str, dict] = {}
    for t in tickets:
        b = t.get("brand", "—")
        agg = brand_agg.setdefault(b, {"brand": b, "items": 0, "hours": 0.0})
        agg["items"] += 1
        agg["hours"] += t.get("hours_in_range", 0.0)
    sec("Portfolio by Brand")
    if brand_agg:
        rows = [
            [_esc(a["brand"]), str(a["items"]), f'{a["hours"]:.2f} h']
            for a in sorted(brand_agg.values(), key=lambda r: -r["items"])
        ]
        render_html_table(["Brand", "Work Items", "Hours Logged"], rows, height=320)
    else:
        st.info("No work items in this period.")

    st.write("")
    sel = current_kpi()
    sel_label = next((lbl for k, lbl, *_ in KPI_DEFS if k == sel), "Total Work Items")
    drill = _kpi_filter(tickets, sel)

    query = st.text_input(
        "🔎 Search work items", key="ticket_search",
        placeholder="Search by key, summary, brand, status, priority, sprint or label…",
    )
    if query:
        drill = search_tickets(drill, query)

    sec(f"Work Item Register — {sel_label} ({len(drill)})")
    ticket_table(drill)


def tab_hours(data: dict) -> None:
    hsum = data["hours_summary"]
    sec("Time Logging Activity — Daily Heatmap")
    hc, mc = st.columns([3, 1])
    with hc:
        if any(d["hours"] > 0 for d in data["daily_hours"]):
            st.plotly_chart(heatmap(data["daily_hours"]), use_container_width=True)
        else:
            st.info("No time logged in this period.")
    with mc:
        st.markdown(card("Total Hours", f'{hsum["total_hours"]:.1f}h', "", "⏱️",
                         "Total time logged across the period."), unsafe_allow_html=True)
        st.write("")
        st.markdown(card("Active Days", str(hsum["days_with_logs"]), "", "📅",
                         "Days with at least one time entry."), unsafe_allow_html=True)
        st.write("")
        st.markdown(card("Avg / Active Day", f'{hsum["avg_hours_per_logged_day"]:.1f}h', "", "📈",
                         "Average hours on days you logged time."), unsafe_allow_html=True)


def tab_utilization(data: dict, target: float, count_weekends: bool) -> None:
    weekly = build_weekly(data["daily_hours"], target, count_weekends)
    if weekly:
        latest = weekly[-1]
        sec("Current Week Utilization (Mon–Fri)")
        c = st.columns(4)
        c[0].markdown(card("Hours Logged", f'{latest["Logged (h)"]:.1f}h', "done", "⏱️",
                           f'Week of {latest["Week"]}.'), unsafe_allow_html=True)
        c[1].markdown(card("Target", f'{latest["Target (h)"]:.0f}h', "", "🎯",
                           f'{latest["Work days"]} work days × {target:.0f}h.'), unsafe_allow_html=True)
        c[2].markdown(card("Remaining", f'{latest["Remaining (h)"]:.1f}h', "over", "🧮",
                           "Hours still required to hit the weekly target."), unsafe_allow_html=True)
        c[3].markdown(card("Avg / Day", f'{latest["Avg/day (h)"]:.1f}h', "prog", "📊",
                           "Average logged per work day this week."), unsafe_allow_html=True)
        st.write("")

    rows, total_deficit = build_daygrid(data["daily_hours"], target, count_weekends)
    sec(f"Daily Utilization vs. Target ({target:.0f}h / work day)")
    gc, scol = st.columns([3, 1])
    with gc:
        status_bg = {"Met": T_GREEN, "Short": T_AMBER, "Not logged": T_RED, "Weekend": T_GRAY}
        status_fg = {"Met": GREEN, "Short": ORANGE, "Not logged": RED, "Weekend": MUTED}
        table_rows, row_styles = [], []
        for r in rows:
            table_rows.append([
                _esc(r["label"]), f'{r["logged"]:.2f}', f'{r["target"]:.0f}',
                f'{r["remaining"]:.2f}',
                chip(r["status"], "#ffffff", status_fg.get(r["status"], TEXT)),
            ])
            row_styles.append(status_bg.get(r["status"], "#ffffff"))
        render_html_table(
            ["Day", "Logged (h)", "Target (h)", "Remaining (h)", "Status"],
            table_rows, height=430, row_styles=row_styles,
        )
    with scol:
        st.markdown(card("Hours Still to Log", f"{total_deficit:.1f}h", "over", "🧮",
                         "Sum of remaining hours across all work days."), unsafe_allow_html=True)
        st.write("")
        met = sum(1 for r in rows if r["status"] == "Met")
        st.markdown(card("Days On Target", str(met), "done", "✅",
                         "Days meeting or exceeding the target."), unsafe_allow_html=True)
        st.write("")
        short = sum(1 for r in rows if r["status"] in ("Short", "Not logged"))
        st.markdown(card("Days Under Target", str(short), "todo", "⚠️",
                         "Work days below the target."), unsafe_allow_html=True)

    st.write("")
    sec("Weekly Utilization (Mon–Fri)")
    if weekly:
        wrows = []
        for w in weekly:
            rem = w["Remaining (h)"]
            rem_chip = (chip(f'{rem:.1f} h', T_GREEN, GREEN) if rem <= 0
                        else chip(f'{rem:.1f} h', T_AMBER, ORANGE))
            wrows.append([
                _esc(w["Week"]), f'{w["Logged (h)"]:.1f} h', str(w["Work days"]),
                f'{w["Target (h)"]:.0f} h', rem_chip, f'{w["Avg/day (h)"]:.1f} h',
            ])
        render_html_table(
            ["Week", "Logged", "Work Days", "Target", "Remaining", "Avg / Day"],
            wrows, height=320,
        )
    st.plotly_chart(stacked_bar(rows), use_container_width=True)


def tab_records(tickets: list[dict], data: dict, scope: str) -> None:
    hsum = data["hours_summary"]
    sec(f"Work Item Register — {SCOPES[scope]} ({len(tickets)})")
    ticket_table(tickets)
    sec(f"Time Entry Log ({hsum['worklog_count']})")
    if data["worklogs"]:
        wrows = [
            [
                _esc(w["date"]), _link(w["issue_url"], w["issue_key"]),
                f'{w["hours"]:.2f} h',
                f'<div class="cell-summary">{_esc(w.get("comment") or "—")}</div>',
            ]
            for w in data["worklogs"]
        ]
        render_html_table(["Date", "Work Item", "Hours", "Notes"], wrows)
    else:
        st.info("No time entries in this period.")


def tab_brands(brand_sel: str, only_open: bool) -> None:
    try:
        bv = cached_brand_view(brand_sel, only_open)
    except JiraError as exc:
        st.error(str(exc)); return
    scnt = bv["status_counts"]
    sec(f"Brand Portfolio — {brand_sel} ({'open' if only_open else 'all'} items)")
    c = st.columns(5)
    c[0].markdown(card("Work Items", str(bv["ticket_count"]), "total", "📦",
                       "Total tickets for this brand."), unsafe_allow_html=True)
    c[1].markdown(card("Contributors", str(bv["people_count"]), "prog", "👥",
                       "Distinct assignees on this brand."), unsafe_allow_html=True)
    c[2].markdown(card("In Progress", str(scnt["in_progress"]), "prog", "🔧",
                       "Items actively being worked."), unsafe_allow_html=True)
    c[3].markdown(card("Not Started", str(scnt["todo"]), "todo", "🕒",
                       "Items in a To-Do status."), unsafe_allow_html=True)
    c[4].markdown(card("Overdue", str(scnt["overdue"]), "over", "⚠️",
                       "Past due and not completed."), unsafe_allow_html=True)
    st.write("")
    sec("Team Allocation by Assignee")
    prows = [
        [_esc(p["assignee"]), str(p["total"]), str(p["in_progress"])]
        for p in bv["people"]
    ]
    render_html_table(["Assignee", "Work Items", "In Progress"], prows, height=340)

    st.write("")
    sec("Work Item Detail")
    if bv["tickets"]:
        headers = ["Assignee", "Key", "Summary", "Priority", "Status", "Due", "Overdue"]
        rows = []
        for t in bv["tickets"]:
            rows.append([
                _esc(t["assignee_name"]),
                _link(t["issue_url"], t["key"]),
                f'<div class="cell-summary">{_esc(t["summary"])}</div>',
                priority_chip(t.get("priority", "-")),
                status_chip(t["status"]),
                _esc(t.get("duedate") or "—"),
                overdue_chip(bool(t.get("overdue"))),
            ])
        render_html_table(headers, rows)


# ----- One-time default-user onboarding --------------------------------------
DU_PARAM = "du_user"


def get_default_user_id() -> str | None:
    """Resolve the current default user id from the URL (durable) or session."""
    val = st.query_params.get(DU_PARAM)
    if val:
        return val
    return st.session_state.get(DU_PARAM)


def set_default_user(account_id: str, remember: bool) -> None:
    """Record the chosen default user. `remember` writes it to the URL query
    param (so it survives reloads and is shareable); otherwise it lives only for
    this browser session. Works identically locally and on Streamlit Cloud."""
    st.session_state[DU_PARAM] = account_id
    if remember:
        st.query_params[DU_PARAM] = account_id
    st.rerun()


def reset_default_user() -> None:
    """Forget the default user and return to the onboarding gate."""
    st.session_state.pop(DU_PARAM, None)
    if DU_PARAM in st.query_params:
        del st.query_params[DU_PARAM]
    st.rerun()


def onboarding_gate(users: list[dict], me: dict) -> None:
    """First-run screen: pick your name, optionally remember it on this device."""
    st.markdown(
        f"""
        <div style="max-width:640px;margin:6vh auto 18px;text-align:center;">
          <div style="width:74px;height:74px;border-radius:50%;margin:0 auto 18px;
                      display:grid;place-items:center;color:#fff;font-weight:800;font-size:1.5rem;
                      font-family:'Segoe UI',Calibri,sans-serif;
                      background:linear-gradient(135deg,{PURPLE},{BLUE});
                      box-shadow:0 14px 30px rgba(59,130,246,0.35);">DU</div>
          <div style="font-family:'Segoe UI',Calibri,sans-serif;font-size:1.9rem;font-weight:800;color:{NAVY};">
            Welcome to the DAADU JIRA Activity Timeline
          </div>
          <div style="color:{MUTED};font-size:1rem;font-weight:600;margin-top:8px;">
            Let's set you up. Search for your name below to make it your default view.
            We'll remember you on this device so you won't be asked again.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c = st.columns([1, 2, 1])
    with c[1]:
        names = [u["display_name"] for u in users]
        default_idx = next(
            (i for i, u in enumerate(users) if u["account_id"] == me["account_id"]), 0
        )
        sel = st.selectbox(
            "🔎 Search your name", names, index=default_idx, key="onb_select",
            help="Type to filter the team list.",
        )
        remember = st.checkbox(
            "Set as my default user on this device", value=True, key="onb_remember"
        )
        if st.button("Continue to dashboard  →", key="onb_go", use_container_width=True):
            acc = users[names.index(sel)]["account_id"]
            set_default_user(acc, remember)
    st.stop()


# ----- Main ------------------------------------------------------------------
def main() -> None:
    inject_css()
    config = get_config()

    if not credentials_ok(config):
        st.markdown('<span class="status-err">● Credentials missing</span>', unsafe_allow_html=True)
        st.info("Add `JIRA_EMAIL` and `JIRA_API_TOKEN` to `.env`, then restart.")
        st.stop()

    try:
        me = JiraClient(config).verify_connection()
    except JiraError as exc:
        st.error(f"Connection failed: {exc}"); st.stop()

    # ---------------- Team roster (needed for onboarding + sidebar) ----------
    try:
        users = cached_users()
    except JiraError:
        users = []
    if not any(u["account_id"] == me["account_id"] for u in users):
        users.insert(0, {"account_id": me["account_id"], "display_name": me["display_name"], "email": me["email"]})

    # ---------------- One-time default-user gate -----------------------------
    du_user = get_default_user_id()
    if not du_user or not any(u["account_id"] == du_user for u in users):
        onboarding_gate(users, me)  # renders the gate and stops the run

    default_user = next((u for u in users if u["account_id"] == du_user), me)

    # ---------------- Sidebar: section-wise controls ----------------
    with st.sidebar:
        st.header("Controls")

        group("Team Member & Period")
        names = [u["display_name"] for u in users]
        default_idx = next((i for i, u in enumerate(users) if u["account_id"] == default_user["account_id"]), 0)
        chosen_name = st.selectbox("Team member", names, index=default_idx)
        chosen = users[names.index(chosen_name)]
        is_me = chosen["account_id"] == me["account_id"]
        is_default = chosen["account_id"] == default_user["account_id"]
        st.caption(
            f"⭐ Default user: {default_user['display_name']}"
            + ("" if is_default else f" · viewing {chosen_name}")
        )
        if st.button("↺ Reset default user (this device)", key="reset_default"):
            reset_default_user()

        labels_map = {"7": "Last 7 days", "15": "Last 15 days", "30": "Last 30 days", "custom": "Custom"}
        preset = st.radio("Reporting period", list(labels_map.keys()), format_func=lambda k: labels_map[k], index=0)
        if preset == "custom":
            today = date.today()
            cc = st.columns(2)
            with cc[0]:
                cs = st.date_input("From", value=today - timedelta(days=13))
            with cc[1]:
                ce = st.date_input("To", value=today)
            start_iso, end_iso = cs.isoformat(), ce.isoformat()
        else:
            s, e = resolve_date_range(preset, None, None)
            start_iso, end_iso = s.isoformat(), e.isoformat()

        scope = st.radio("Ticket scope", list(SCOPES.keys()), format_func=lambda k: SCOPES[k], index=0)

    # ---------------- Load person data ----------------
    try:
        with st.spinner(f"Loading {chosen_name}'s Jira data…"):
            data = cached_person(chosen["account_id"], chosen_name, start_iso, end_iso)
    except JiraError as exc:
        st.error(str(exc)); st.stop()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Unexpected error: {exc}"); st.stop()

    all_tickets = data["scopes"]["all"]["tickets"]
    priorities_all = sorted({t["priority"] for t in all_tickets if t.get("priority")})
    labels_all = sorted({lb for t in all_tickets for lb in t.get("labels", [])})
    sprints_all = sorted({sp for t in all_tickets for sp in t.get("sprints", [])})

    with st.sidebar:
        st.divider()
        group("Work Item Filters")
        f_priority = st.multiselect("Priority", priorities_all)
        f_labels = st.multiselect("Labels", labels_all)
        f_sprint = st.multiselect("Sprint", sprints_all)

        st.divider()
        group("Utilization")
        target = float(st.slider("Target hours / work day", 1, 12, 8))
        count_weekends = st.toggle("Count weekends", value=False)

        st.divider()
        group("Brand Portfolio")
        try:
            brands = cached_brands()
        except JiraError:
            brands = []
        brand_sel = st.selectbox(
            "Brand", brands or ["—"],
            index=brands.index("Dupixent") if "Dupixent" in brands else 0,
        )
        brand_open = st.toggle("Open items only", value=True)

        st.divider()
        group("Data & Refresh")
        if st.button("🔄 Refresh now"):
            st.cache_data.clear()
        auto = st.toggle("Auto-refresh", value=True)
        interval = st.slider("Interval (seconds)", 5, 120, config["auto_refresh_seconds"], 5, disabled=not auto)
        if auto and HAS_AUTOREFRESH:
            st_autorefresh(interval=interval * 1000, key="auto_refresh")
        elif auto:
            st.caption("Install `streamlit-autorefresh` for auto-refresh.")

    # Apply filters to the selected scope's tickets.
    scoped_tickets = apply_filters(
        data["scopes"][scope]["tickets"], f_priority, f_labels, f_sprint
    )

    # ---------------- Header ----------------
    fetched = datetime.fromisoformat(data["fetched_at"])
    filt = sum(1 for x in (f_priority, f_labels, f_sprint) if x)
    st.markdown(
        f"""
        <div class="header-bar">
          <div class="header-left">
            <div class="header-mark">DU</div>
            <div>
              <div class="header-title">DAADU JIRA Activity Timeline</div>
              <div class="header-sub">Data Unveil · {chosen_name}{" (you)" if is_me else ""} ·
              {data["range"]["start"]} → {data["range"]["end"]}</div>
            </div>
          </div>
          <div class="header-right">
            <div><span class="status-ok">● Connected</span></div>
            <div>Updated {fetched.astimezone().strftime("%d %b %Y, %H:%M:%S")}</div>
            <div>{filt} filter(s) active</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------- Section tabs ----------------
    t_over, t_hours, t_util, t_brand, t_rec = st.tabs(
        ["📊 Overview", "🔥 Time Activity", "🎯 Utilization", "🏷️ Brand Portfolio", "📋 Records"]
    )
    with t_over:
        tab_overview(scoped_tickets, scope)
    with t_hours:
        tab_hours(data)
    with t_util:
        tab_utilization(data, target, count_weekends)
    with t_brand:
        if brands:
            tab_brands(brand_sel, brand_open)
        else:
            st.info("No brands available.")
    with t_rec:
        tab_records(scoped_tickets, data, scope)


if __name__ == "__main__":
    main()
