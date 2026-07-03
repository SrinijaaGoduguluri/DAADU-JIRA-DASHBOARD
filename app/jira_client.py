from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings


class JiraError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JiraClient:
    ACTIVE_TICKETS_JQL = (
        "assignee = currentUser() AND status != Done "
        "ORDER BY status DESC, created DESC, updated DESC"
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.jira_base_url_normalized

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _auth(self) -> tuple[str, str]:
        return (self.settings.jira_email, self.settings.jira_api_token)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = await client.request(
            method,
            url,
            auth=self._auth(),
            headers=self._headers(),
            params=params,
            json=json,
            timeout=60.0,
        )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise JiraError(
                f"Jira API error ({response.status_code}): {detail}",
                status_code=response.status_code,
            )
        if response.status_code == 204:
            return None
        return response.json()

    async def verify_connection(self) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            data = await self._request(client, "GET", "/rest/api/3/myself")
            return {
                "account_id": data.get("accountId"),
                "display_name": data.get("displayName"),
                "email": data.get("emailAddress"),
            }

    async def search_issues(
        self,
        client: httpx.AsyncClient,
        jql: str,
        *,
        fields: list[str] | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        selected_fields = fields or [
            "summary",
            "status",
            "assignee",
            "priority",
            "updated",
            "created",
            "timespent",
            "project",
        ]
        issues: list[dict[str, Any]] = []
        start_at = 0

        while True:
            payload = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": min(max_results, 100),
                "fields": selected_fields,
            }
            data = await self._request(
                client, "POST", "/rest/api/3/search", json=payload
            )
            batch = data.get("issues", [])
            issues.extend(batch)

            total = data.get("total", 0)
            if len(batch) == 0 or start_at + len(batch) >= total:
                break
            start_at += len(batch)
            if start_at >= max_results:
                break

        return issues

    async def get_issue_worklogs(
        self, client: httpx.AsyncClient, issue_key: str
    ) -> list[dict[str, Any]]:
        worklogs: list[dict[str, Any]] = []
        start_at = 0

        while True:
            data = await self._request(
                client,
                "GET",
                f"/rest/api/3/issue/{issue_key}/worklog",
                params={"startAt": start_at, "maxResults": 100},
            )
            batch = data.get("worklogs", [])
            worklogs.extend(batch)
            total = data.get("total", 0)
            start_at += len(batch)
            if start_at >= total or not batch:
                break

        return worklogs

    @staticmethod
    def _parse_jira_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            if len(value) >= 10:
                return date.fromisoformat(value[:10])
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _seconds_to_hours(seconds: int | float) -> float:
        return round(float(seconds) / 3600.0, 2)

    @staticmethod
    def _issue_url(issue_key: str, base_url: str) -> str:
        return f"{base_url}/browse/{issue_key}"

    async def build_dashboard(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        worklog_jql = (
            f'worklogAuthor = currentUser() AND worklogDate >= "{start_date.isoformat()}" '
            f'AND worklogDate <= "{end_date.isoformat()}" '
            "ORDER BY updated DESC"
        )

        async with httpx.AsyncClient() as client:
            me = await self.verify_connection()
            account_id = me["account_id"]

            active_issues, worklog_issues = await self._gather_issues(
                client, worklog_jql
            )

            issue_map: dict[str, dict[str, Any]] = {}
            for issue in active_issues + worklog_issues:
                key = issue["key"]
                if key not in issue_map:
                    issue_map[key] = self._normalize_issue(issue)

            daily_hours: dict[str, float] = defaultdict(float)
            worklog_entries: list[dict[str, Any]] = []
            ticket_hours: dict[str, float] = defaultdict(float)

            for issue_key in issue_map:
                worklogs = await self.get_issue_worklogs(client, issue_key)
                for entry in worklogs:
                    author = entry.get("author", {})
                    if author.get("accountId") != account_id:
                        continue

                    entry_date = self._parse_jira_date(entry.get("started"))
                    if not entry_date:
                        continue
                    if entry_date < start_date or entry_date > end_date:
                        continue

                    hours = self._seconds_to_hours(entry.get("timeSpentSeconds", 0))
                    day_key = entry_date.isoformat()
                    daily_hours[day_key] += hours
                    ticket_hours[issue_key] += hours

                    worklog_entries.append(
                        {
                            "issue_key": issue_key,
                            "issue_summary": issue_map[issue_key]["summary"],
                            "date": day_key,
                            "hours": hours,
                            "time_spent": entry.get("timeSpent", ""),
                            "comment": self._extract_comment(entry.get("comment")),
                            "started": entry.get("started"),
                            "issue_url": self._issue_url(issue_key, self.base_url),
                        }
                    )

            worklog_entries.sort(
                key=lambda row: (row["date"], row["issue_key"]),
                reverse=True,
            )

            tickets = []
            for key, meta in issue_map.items():
                tickets.append(
                    {
                        **meta,
                        "hours_in_range": round(ticket_hours.get(key, 0.0), 2),
                        "is_active_assignment": meta["status_category"] != "done",
                    }
                )
            tickets.sort(
                key=lambda row: (row["hours_in_range"], row["updated"]),
                reverse=True,
            )

            timeline = self._build_daily_timeline(start_date, end_date, daily_hours)
            total_hours = round(sum(daily_hours.values()), 2)

            return {
                "user": me,
                "range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": (end_date - start_date).days + 1,
                },
                "summary": {
                    "total_hours": total_hours,
                    "days_with_logs": len([d for d in daily_hours.values() if d > 0]),
                    "active_tickets": len(
                        [t for t in tickets if t["is_active_assignment"]]
                    ),
                    "tickets_with_logs": len(
                        [t for t in tickets if t["hours_in_range"] > 0]
                    ),
                    "worklog_count": len(worklog_entries),
                    "avg_hours_per_logged_day": round(
                        total_hours / max(len([d for d in daily_hours.values() if d > 0]), 1),
                        2,
                    ),
                },
                "daily_hours": timeline,
                "tickets": tickets,
                "worklogs": worklog_entries,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

    async def _gather_issues(
        self, client: httpx.AsyncClient, worklog_jql: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        active_issues = await self.search_issues(client, self.ACTIVE_TICKETS_JQL)
        worklog_issues = await self.search_issues(client, worklog_jql)
        return active_issues, worklog_issues

    def _normalize_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        fields = issue.get("fields", {})
        status = fields.get("status") or {}
        status_category = (status.get("statusCategory") or {}).get("key", "undefined")
        priority = fields.get("priority") or {}
        project = fields.get("project") or {}
        assignee = fields.get("assignee") or {}

        return {
            "key": issue["key"],
            "summary": fields.get("summary", ""),
            "status": status.get("name", "Unknown"),
            "status_category": status_category,
            "priority": priority.get("name", "—"),
            "project_key": project.get("key", ""),
            "project_name": project.get("name", ""),
            "assignee": assignee.get("displayName", "Unassigned"),
            "updated": fields.get("updated"),
            "created": fields.get("created"),
            "total_time_spent_hours": self._seconds_to_hours(
                fields.get("timespent") or 0
            ),
            "issue_url": self._issue_url(issue["key"], self.base_url),
        }

    @staticmethod
    def _extract_comment(comment: dict[str, Any] | None) -> str:
        if not comment:
            return ""
        content = comment.get("content", [])
        parts: list[str] = []

        def walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                if node.get("type") == "text":
                    parts.append(node.get("text", ""))
                if "content" in node:
                    walk(node["content"])

        walk(content)
        return " ".join(parts).strip()

    @staticmethod
    def _build_daily_timeline(
        start_date: date,
        end_date: date,
        daily_hours: dict[str, float],
    ) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        cursor = start_date
        while cursor <= end_date:
            key = cursor.isoformat()
            timeline.append(
                {
                    "date": key,
                    "label": cursor.strftime("%a %b %d"),
                    "hours": round(daily_hours.get(key, 0.0), 2),
                    "is_weekend": cursor.weekday() >= 5,
                }
            )
            cursor += timedelta(days=1)
        return timeline


def resolve_date_range(
    preset: str | None,
    custom_start: date | None,
    custom_end: date | None,
) -> tuple[date, date]:
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
        raise ValueError("Invalid preset. Use 7, 15, 30, or custom.")

    days = days_map[preset]
    start = today - timedelta(days=days - 1)
    return start, today
