"""Synchronous Jira client used by the Streamlit dashboard."""
from __future__ import annotations

import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# Primary brand custom field (confirmed for dataunveil), plus fallbacks.
BRAND_FIELD = "customfield_10519"
BRAND_FIELDS = [
    "customfield_10519", "customfield_10069", "customfield_10149",
    "customfield_10061", "customfield_10062", "customfield_10063",
]
SPRINT_FIELD = "customfield_10020"


class JiraError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_config() -> dict[str, Any]:
    return {
        "email": os.getenv("JIRA_EMAIL", "").strip(),
        "token": os.getenv("JIRA_API_TOKEN", "").strip(),
        "base_url": os.getenv("JIRA_BASE_URL", "https://dataunveil.atlassian.net").rstrip("/"),
        "auto_refresh_seconds": int(os.getenv("AUTO_REFRESH_SECONDS", "30") or "30"),
    }


def credentials_ok(config: dict[str, Any]) -> bool:
    return bool(config["email"] and config["token"])


class JiraClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.email = config["email"]
        self.token = config["token"]
        self.base_url = config["base_url"]

    # ------------------------------------------------------------------ core
    def _client(self) -> httpx.Client:
        return httpx.Client(
            auth=(self.email, self.token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=60.0,
        )

    def _request(self, client: httpx.Client, method: str, path: str, **kwargs) -> Any:
        response = client.request(method, f"{self.base_url}{path}", **kwargs)
        if response.status_code >= 400:
            raise JiraError(
                f"Jira API error ({response.status_code}): {response.text[:400]}",
                status_code=response.status_code,
            )
        if response.status_code == 204:
            return None
        return response.json()

    # -------------------------------------------------------------- identity
    def verify_connection(self) -> dict[str, Any]:
        with self._client() as client:
            data = self._request(client, "GET", "/rest/api/3/myself")
            return {
                "account_id": data.get("accountId"),
                "display_name": data.get("displayName"),
                "email": data.get("emailAddress"),
            }

    def list_users(self) -> list[dict[str, Any]]:
        """All real (human) users in the site, sorted by name."""
        with self._client() as client:
            users: dict[str, dict[str, Any]] = {}
            start = 0
            while True:
                data = self._request(
                    client, "GET", "/rest/api/3/users/search",
                    params={"startAt": start, "maxResults": 100},
                )
                if not data:
                    break
                for u in data:
                    if u.get("accountType") != "atlassian" or not u.get("active"):
                        continue
                    acc = u.get("accountId")
                    if acc and acc not in users:
                        users[acc] = {
                            "account_id": acc,
                            "display_name": u.get("displayName") or acc,
                            "email": u.get("emailAddress"),
                        }
                if len(data) < 100:
                    break
                start += len(data)
            return sorted(users.values(), key=lambda x: (x["display_name"] or "").lower())

    def list_brands(self) -> list[str]:
        """Brand option values for the primary Brand field (no admin needed)."""
        with self._client() as client:
            data = self._request(
                client, "GET", "/rest/api/3/jql/autocompletedata/suggestions",
                params={"fieldName": f"cf[{BRAND_FIELD.replace('customfield_', '')}]"},
            )
            brands: list[str] = []
            for item in data.get("results", []):
                val = (item.get("value") or "").strip().strip('"')
                if val and val not in brands:
                    brands.append(val)
            return sorted(brands, key=str.lower)

    # --------------------------------------------------------------- search
    def _search(self, client: httpx.Client, jql: str, max_results: int = 500) -> list[dict[str, Any]]:
        # Uses the new token-paginated endpoint (/rest/api/3/search/jql);
        # the legacy /rest/api/3/search was removed by Atlassian.
        fields = [
            "summary", "status", "assignee", "priority",
            "updated", "created", "duedate", "project", "labels", SPRINT_FIELD,
        ] + BRAND_FIELDS
        issues: list[dict[str, Any]] = []
        next_token: str | None = None
        while True:
            payload: dict[str, Any] = {
                "jql": jql,
                "maxResults": 100,
                "fields": fields,
            }
            if next_token:
                payload["nextPageToken"] = next_token
            data = self._request(client, "POST", "/rest/api/3/search/jql", json=payload)
            batch = data.get("issues", [])
            issues.extend(batch)
            next_token = data.get("nextPageToken")
            if data.get("isLast") or not next_token or len(issues) >= max_results:
                break
        return issues

    def _worklogs(self, client: httpx.Client, issue_key: str) -> list[dict[str, Any]]:
        worklogs: list[dict[str, Any]] = []
        start_at = 0
        while True:
            data = self._request(
                client, "GET", f"/rest/api/3/issue/{issue_key}/worklog",
                params={"startAt": start_at, "maxResults": 100},
            )
            batch = data.get("worklogs", [])
            worklogs.extend(batch)
            total = data.get("total", 0)
            start_at += len(batch)
            if start_at >= total or not batch:
                break
        return worklogs

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    @staticmethod
    def _hours(seconds: int | float) -> float:
        return round(float(seconds) / 3600.0, 2)

    def _issue_url(self, key: str) -> str:
        return f"{self.base_url}/browse/{key}"

    @staticmethod
    def _extract_brands(f: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for cf in BRAND_FIELDS:
            v = f.get(cf)
            if not v:
                continue
            items = v if isinstance(v, list) else [v]
            for o in items:
                val = o.get("value") if isinstance(o, dict) else str(o)
                if val:
                    val = val.strip().strip('"')
                    if val and val not in out:
                        out.append(val)
        return out

    @staticmethod
    def _extract_sprints(f: dict[str, Any]) -> tuple[list[str], str]:
        raw = f.get(SPRINT_FIELD) or []
        names: list[str] = []
        active = ""
        if isinstance(raw, list):
            for s in raw:
                if isinstance(s, dict):
                    name = s.get("name")
                    if name:
                        names.append(name)
                        if s.get("state") == "active":
                            active = name
                elif isinstance(s, str):
                    names.append(s)
        return names, active

    def _normalize(self, issue: dict[str, Any]) -> dict[str, Any]:
        f = issue.get("fields", {})
        status = f.get("status") or {}
        category = (status.get("statusCategory") or {}).get("key", "undefined")
        project = f.get("project") or {}
        priority = f.get("priority") or {}
        assignee = f.get("assignee") or {}
        brands = self._extract_brands(f)
        labels = f.get("labels") or []
        sprints, active_sprint = self._extract_sprints(f)
        return {
            "key": issue["key"],
            "summary": f.get("summary", ""),
            "status": status.get("name", "Unknown"),
            "status_category": category,
            "priority": priority.get("name", "-"),
            "project_key": project.get("key", ""),
            "project_name": project.get("name", ""),
            "assignee_name": assignee.get("displayName", "Unassigned"),
            "brands": brands,
            "brand": brands[0] if brands else "—",
            "labels": labels,
            "sprints": sprints,
            "sprint": active_sprint or (sprints[-1] if sprints else "—"),
            "updated": f.get("updated"),
            "created": f.get("created"),
            "duedate": f.get("duedate"),
            "issue_url": self._issue_url(issue["key"]),
        }

    @staticmethod
    def _comment(comment: dict[str, Any] | None) -> str:
        if not comment:
            return ""
        parts: list[str] = []

        def walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                if node.get("type") == "text":
                    parts.append(node.get("text", ""))
                if "content" in node:
                    walk(node["content"])

        walk(comment.get("content", []))
        return " ".join(parts).strip()

    # ------------------------------------------------------------ dashboard
    def build_person_dashboard(
        self,
        account_id: str,
        display_name: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        all_jql = f'assignee = "{account_id}" ORDER BY updated DESC'
        worklog_jql = (
            f'worklogAuthor = "{account_id}" '
            f'AND worklogDate >= "{start_date.isoformat()}" '
            f'AND worklogDate <= "{end_date.isoformat()}" ORDER BY updated DESC'
        )
        today = date.today()

        with self._client() as client:
            all_raw = self._search(client, all_jql)
            logged_raw = self._search(client, worklog_jql)

            all_norm = [self._normalize(i) for i in all_raw]
            logged_norm = [self._normalize(i) for i in logged_raw]

            daily: dict[str, float] = defaultdict(float)
            ticket_hours: dict[str, float] = defaultdict(float)
            entries: list[dict[str, Any]] = []
            summaries = {t["key"]: t["summary"] for t in logged_norm}

            # Fetch worklogs concurrently (httpx.Client is thread-safe) for speed.
            keys = [t["key"] for t in logged_norm]
            wl_map: dict[str, list[dict[str, Any]]] = {}
            if keys:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    for key, wls in pool.map(lambda k: (k, self._worklogs(client, k)), keys):
                        wl_map[key] = wls

            for key, worklogs in wl_map.items():
                for wl in worklogs:
                    if (wl.get("author") or {}).get("accountId") != account_id:
                        continue
                    d = self._parse_date(wl.get("started"))
                    if not d or d < start_date or d > end_date:
                        continue
                    hrs = self._hours(wl.get("timeSpentSeconds", 0))
                    daily[d.isoformat()] += hrs
                    ticket_hours[key] += hrs
                    entries.append({
                        "issue_key": key,
                        "summary": summaries.get(key, ""),
                        "date": d.isoformat(),
                        "hours": hrs,
                        "comment": self._comment(wl.get("comment")),
                        "issue_url": self._issue_url(key),
                    })

            entries.sort(key=lambda r: (r["date"], r["issue_key"]), reverse=True)

            # Attach hours + overdue to every known ticket.
            merged: dict[str, dict[str, Any]] = {}
            for t in all_norm + logged_norm:
                merged.setdefault(t["key"], t)
            for t in merged.values():
                t["hours_in_range"] = round(ticket_hours.get(t["key"], 0.0), 2)
                due = self._parse_date(t.get("duedate"))
                t["overdue"] = bool(due and due < today and t["status_category"] != "done")

            all_list = list(merged.values())

            def in_range(value: str | None) -> bool:
                d = self._parse_date(value)
                return bool(d and start_date <= d <= end_date)

            worked = sorted(
                [merged[k] for k in ticket_hours if k in merged],
                key=lambda r: (-r["hours_in_range"], r["updated"] or ""),
            )
            updated = sorted(
                [t for t in all_list if in_range(t["updated"])],
                key=lambda r: (r["updated"] or ""), reverse=True,
            )
            created = sorted(
                [t for t in all_list if in_range(t["created"])],
                key=lambda r: (r["created"] or ""), reverse=True,
            )
            all_sorted = sorted(
                all_list,
                key=lambda r: (r["overdue"], r["status_category"] != "indeterminate", r["updated"] or ""),
                reverse=True,
            )

            scopes = {
                "worked": {"tickets": worked, "counts": self._counts(worked)},
                "updated": {"tickets": updated, "counts": self._counts(updated)},
                "created": {"tickets": created, "counts": self._counts(created)},
                "all": {"tickets": all_sorted, "counts": self._counts(all_sorted)},
            }

            timeline = self._timeline(start_date, end_date, daily)
            total_hours = round(sum(daily.values()), 2)
            logged_days = len([v for v in daily.values() if v > 0])

            return {
                "person": {"account_id": account_id, "display_name": display_name},
                "range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "scopes": scopes,
                "counts": scopes["worked"]["counts"],
                "tickets": scopes["worked"]["tickets"],
                "hours_summary": {
                    "total_hours": total_hours,
                    "days_with_logs": logged_days,
                    "avg_hours_per_logged_day": round(total_hours / max(logged_days, 1), 2),
                    "worklog_count": len(entries),
                },
                "daily_hours": timeline,
                "worklogs": entries,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

    @staticmethod
    def _counts(tickets: list[dict[str, Any]]) -> dict[str, int]:
        counts = {"total": 0, "todo": 0, "in_progress": 0, "done": 0, "overdue": 0}
        for t in tickets:
            counts["total"] += 1
            cat = t["status_category"]
            if cat == "done":
                counts["done"] += 1
            elif cat == "indeterminate":
                counts["in_progress"] += 1
            else:
                counts["todo"] += 1
            if t.get("overdue"):
                counts["overdue"] += 1
        return counts

    def build_brand_view(self, brand: str, only_open: bool = True) -> dict[str, Any]:
        """Tickets for a brand, showing who is working on what."""
        num = BRAND_FIELD.replace("customfield_", "")
        jql = f'cf[{num}] = "{brand}"'
        if only_open:
            jql += " AND statusCategory != Done"
        jql += " ORDER BY assignee ASC, status ASC, updated DESC"

        with self._client() as client:
            issues = self._search(client, jql, max_results=500)

        tickets = [self._normalize(i) for i in issues]
        today = date.today()
        by_person: dict[str, dict[str, Any]] = {}
        status_counts = {"todo": 0, "in_progress": 0, "done": 0, "overdue": 0}

        for t in tickets:
            cat = t["status_category"]
            if cat == "done":
                status_counts["done"] += 1
            elif cat == "indeterminate":
                status_counts["in_progress"] += 1
            else:
                status_counts["todo"] += 1
            due = self._parse_date(t.get("duedate"))
            t["overdue"] = bool(due and due < today and cat != "done")
            if t["overdue"]:
                status_counts["overdue"] += 1

            person = t["assignee_name"]
            bucket = by_person.setdefault(person, {"assignee": person, "total": 0, "in_progress": 0, "tickets": []})
            bucket["total"] += 1
            if cat == "indeterminate":
                bucket["in_progress"] += 1
            bucket["tickets"].append(t)

        people = sorted(by_person.values(), key=lambda p: (-p["total"], p["assignee"].lower()))
        return {
            "brand": brand,
            "ticket_count": len(tickets),
            "people_count": len(people),
            "status_counts": status_counts,
            "people": people,
            "tickets": tickets,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _timeline(start_date: date, end_date: date, daily_hours: dict[str, float]) -> list[dict[str, Any]]:
        timeline = []
        cursor = start_date
        while cursor <= end_date:
            key = cursor.isoformat()
            timeline.append({
                "date": key,
                "label": cursor.strftime("%a %b %d"),
                "hours": round(daily_hours.get(key, 0.0), 2),
                "is_weekend": cursor.weekday() >= 5,
            })
            cursor += timedelta(days=1)
        return timeline


def resolve_date_range(preset: str, custom_start: date | None, custom_end: date | None) -> tuple[date, date]:
    today = date.today()
    preset = (preset or "7").lower()
    if preset == "custom":
        if not custom_start or not custom_end:
            raise ValueError("Custom range requires both start and end dates.")
        if custom_start > custom_end:
            raise ValueError("Start date must be on or before end date.")
        return custom_start, custom_end
    days_map = {"7": 7, "15": 15, "30": 30}
    if preset not in days_map:
        raise ValueError("Invalid preset.")
    return today - timedelta(days=days_map[preset] - 1), today
