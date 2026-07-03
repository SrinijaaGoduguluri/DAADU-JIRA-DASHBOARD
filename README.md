# Jira Work Dashboard (Streamlit)

A polished **navy blue + light blue** Python dashboard for **dataunveil.atlassian.net** that shows:

- Your **active assigned tickets** (same filter as your Jira saved view)
- **Hours logged per day** in the selected date range (bar chart)
- **Ticket-level totals** and a detailed worklog table
- **7 / 15 / 30 day** presets plus a **custom date range**
- **Manual Refresh** + **auto-refresh** (configurable interval)

Runs on **localhost** via Streamlit, and teammates on the same Wi‑Fi/LAN can open it too.

---

## 1. Get your Jira API token

1. Log in to Atlassian: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**, name it (e.g. `work-dashboard`), and copy it

You need:

| Setting | Value |
|--------|--------|
| **Email** | The email you use to log into Jira |
| **API token** | The token you just created |
| **Site URL** | `https://dataunveil.atlassian.net` |

---

## 2. Install

Open **PowerShell** in this folder:

```powershell
cd "c:\Users\srinija.goduguluri\Desktop\Cursor Projects\Misc\jira-work-dashboard"

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> Already installed during setup — you can skip if the `.venv` folder exists.

---

## 3. Add your credentials

```powershell
copy .env.example .env
```

Edit `.env`:

```env
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=paste_your_token_here
JIRA_BASE_URL=https://dataunveil.atlassian.net
AUTO_REFRESH_SECONDS=30
```

---

## 4. Run

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

or, with the venv activated:

```powershell
streamlit run streamlit_app.py
```

You'll see:

```
Local URL:   http://localhost:8501
Network URL: http://192.168.x.x:8501
```

- **You:** open the **Local URL**
- **Teammates on same network:** open the **Network URL**

> **Firewall:** If teammates can't connect, allow inbound TCP on port `8501`:
> `New-NetFirewallRule -DisplayName "Jira Dashboard" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow`

---

## 5. Using the dashboard

| Control (sidebar) | What it does |
|--------|----------------|
| **Date range** | 7 / 15 / 30 days, or Custom (pick From/To) |
| **Refresh now** | Pull the latest data from Jira immediately |
| **Auto-refresh** | Toggle + slider to set the interval (seconds) |

The dashboard reads:

- Open tickets: `assignee = currentUser() AND status != Done`
- Worklogs: `worklogAuthor = currentUser()` in the selected date range

---

## 6. Project structure

```
jira-work-dashboard/
├── streamlit_app.py       # The Streamlit dashboard (run this)
├── jira_sync.py           # Synchronous Jira API client + aggregation
├── requirements.txt
├── .env.example           # Copy to .env and add your token
└── .streamlit/
    └── config.toml        # Navy/light-blue theme + server settings
```

> The `app/` folder + `run.py` are the older FastAPI version — not needed for Streamlit.

---

## 7. Troubleshooting

| Problem | Fix |
|--------|-----|
| Sidebar says "Credentials missing" | Create `.env` from `.env.example`, restart |
| `401 Unauthorized` | Wrong email or token — regenerate the token |
| `403 Forbidden` | Your account may lack permission to view issues/worklogs |
| Slow first load | Many tickets = more worklog calls; try a shorter range (data cached ~25s) |
| LAN can't connect | Allow port 8501 in firewall; confirm same network; use the Network URL |
| Browser didn't open | Manually visit `http://localhost:8501` |

---

## Security notes

- **Never commit `.env`** — it contains your API token
- Anyone on the LAN can view **your** Jira data while the app is running
