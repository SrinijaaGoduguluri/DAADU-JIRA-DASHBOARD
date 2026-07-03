(() => {
  "use strict";

  const state = {
    preset: "7",
    customStart: null,
    customEnd: null,
    chart: null,
    timer: null,
    loading: false,
  };

  const els = {
    connectionStatus: document.getElementById("connection-status"),
    refreshBtn: document.getElementById("refresh-btn"),
    presetGroup: document.getElementById("preset-group"),
    customRange: document.getElementById("custom-range"),
    customStart: document.getElementById("custom-start"),
    customEnd: document.getElementById("custom-end"),
    applyCustom: document.getElementById("apply-custom"),
    lastUpdated: document.getElementById("last-updated"),
    statTotalHours: document.getElementById("stat-total-hours"),
    statDaysLogged: document.getElementById("stat-days-logged"),
    statActiveTickets: document.getElementById("stat-active-tickets"),
    statTicketsLogged: document.getElementById("stat-tickets-logged"),
    statAvgHours: document.getElementById("stat-avg-hours"),
    ticketsBody: document.getElementById("tickets-body"),
    worklogsBody: document.getElementById("worklogs-body"),
    toast: document.getElementById("toast"),
  };

  function showToast(message, isError = false) {
    els.toast.textContent = message;
    els.toast.classList.remove("hidden", "error");
    if (isError) els.toast.classList.add("error");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => els.toast.classList.add("hidden"), 4200);
  }

  function setConnectionStatus(kind, text) {
    els.connectionStatus.className = `status-pill ${kind}`;
    els.connectionStatus.querySelector(".status-text").textContent = text;
  }

  function setLoading(isLoading) {
    state.loading = isLoading;
    els.refreshBtn.disabled = isLoading;
    els.refreshBtn.classList.toggle("loading", isLoading);
  }

  function formatHours(value) {
    return `${Number(value).toFixed(2)}h`;
  }

  function statusClass(status, category) {
    const normalized = (status || "").toLowerCase();
    if (category === "done" || normalized.includes("done")) return "done";
    if (normalized.includes("progress") || normalized.includes("review")) return "in-progress";
    return "todo";
  }

  function buildDashboardUrl() {
    const params = new URLSearchParams({ preset: state.preset });
    if (state.preset === "custom") {
      params.set("start", state.customStart);
      params.set("end", state.customEnd);
    }
    return `/api/dashboard?${params.toString()}`;
  }

  async function fetchJson(url) {
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || payload.message || `Request failed (${response.status})`);
    }
    return payload;
  }

  function renderStats(summary) {
    els.statTotalHours.textContent = formatHours(summary.total_hours);
    els.statDaysLogged.textContent = summary.days_with_logs;
    els.statActiveTickets.textContent = summary.active_tickets;
    els.statTicketsLogged.textContent = summary.tickets_with_logs;
    els.statAvgHours.textContent = formatHours(summary.avg_hours_per_logged_day);
  }

  function renderTickets(tickets) {
    if (!tickets.length) {
      els.ticketsBody.innerHTML = `<tr><td colspan="4" class="empty-row">No tickets in this range.</td></tr>`;
      return;
    }

    els.ticketsBody.innerHTML = tickets
      .map((ticket) => {
        const badgeClass = statusClass(ticket.status, ticket.status_category);
        return `
          <tr>
            <td><a class="ticket-key" href="${ticket.issue_url}" target="_blank" rel="noopener">${ticket.key}</a></td>
            <td>${escapeHtml(ticket.summary)}</td>
            <td><span class="status-badge ${badgeClass}">${escapeHtml(ticket.status)}</span></td>
            <td><span class="hours-chip">${formatHours(ticket.hours_in_range)}</span></td>
          </tr>`;
      })
      .join("");
  }

  function renderWorklogs(worklogs) {
    if (!worklogs.length) {
      els.worklogsBody.innerHTML = `<tr><td colspan="4" class="empty-row">No worklogs in this range.</td></tr>`;
      return;
    }

    els.worklogsBody.innerHTML = worklogs
      .map((entry) => `
        <tr>
          <td>${entry.date}</td>
          <td><a class="ticket-key" href="${entry.issue_url}" target="_blank" rel="noopener">${entry.issue_key}</a></td>
          <td><span class="hours-chip">${formatHours(entry.hours)}</span></td>
          <td class="comment-cell">${escapeHtml(entry.comment || "—")}</td>
        </tr>`)
      .join("");
  }

  function renderChart(dailyHours) {
    const labels = dailyHours.map((row) => row.label);
    const values = dailyHours.map((row) => row.hours);
    const colors = dailyHours.map((row) =>
      row.is_weekend ? "rgba(255, 176, 32, 0.55)" : "rgba(79, 140, 255, 0.85)"
    );

    const canvas = document.getElementById("hours-chart");
    if (state.chart) state.chart.destroy();

    state.chart = new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Logged hours",
          data: values,
          backgroundColor: colors,
          borderRadius: 8,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${formatHours(ctx.raw)}`,
            },
          },
        },
        scales: {
          x: {
            ticks: { color: "#8b9bb0", maxRotation: 45, minRotation: 0 },
            grid: { color: "rgba(255,255,255,0.04)" },
          },
          y: {
            beginAtZero: true,
            ticks: { color: "#8b9bb0" },
            grid: { color: "rgba(255,255,255,0.06)" },
          },
        },
      },
    });
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  async function checkHealth() {
    try {
      const health = await fetchJson("/api/health");
      if (health.status === "ok") {
        setConnectionStatus("ok", `Connected · ${health.user.display_name}`);
      } else if (health.status === "missing_credentials") {
        setConnectionStatus("warn", "Credentials missing");
      } else {
        setConnectionStatus("error", "Jira connection issue");
      }
      return health;
    } catch (error) {
      setConnectionStatus("error", "Offline");
      throw error;
    }
  }

  async function loadDashboard(manual = false) {
    if (state.loading) return;
    if (state.preset === "custom" && (!state.customStart || !state.customEnd)) {
      showToast("Pick both custom dates first.", true);
      return;
    }

    setLoading(true);
    try {
      const data = await fetchJson(buildDashboardUrl());
      renderStats(data.summary);
      renderTickets(data.tickets);
      renderWorklogs(data.worklogs);
      renderChart(data.daily_hours);

      const fetched = new Date(data.fetched_at);
      els.lastUpdated.textContent = `Last updated: ${fetched.toLocaleString()}`;
      setConnectionStatus("ok", `Connected · ${data.user.display_name}`);

      if (manual) showToast("Dashboard refreshed");
    } catch (error) {
      showToast(error.message, true);
      setConnectionStatus("error", "Refresh failed");
    } finally {
      setLoading(false);
    }
  }

  function setPreset(preset) {
    state.preset = preset;
    document.querySelectorAll(".preset-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.preset === preset);
    });
    els.customRange.classList.toggle("hidden", preset !== "custom");
    if (preset !== "custom") loadDashboard();
  }

  function initCustomDates() {
    const today = new Date();
    const weekAgo = new Date(today);
    weekAgo.setDate(today.getDate() - 6);
    els.customEnd.value = today.toISOString().slice(0, 10);
    els.customStart.value = weekAgo.toISOString().slice(0, 10);
    state.customStart = els.customStart.value;
    state.customEnd = els.customEnd.value;
  }

  function bindEvents() {
    els.refreshBtn.addEventListener("click", () => loadDashboard(true));

    els.presetGroup.addEventListener("click", (event) => {
      const btn = event.target.closest(".preset-btn");
      if (!btn) return;
      setPreset(btn.dataset.preset);
    });

    els.applyCustom.addEventListener("click", () => {
      state.customStart = els.customStart.value;
      state.customEnd = els.customEnd.value;
      loadDashboard(true);
    });

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) loadDashboard();
    });
  }

  function startAutoRefresh() {
    const seconds = window.APP_CONFIG?.autoRefreshSeconds || 30;
    if (state.timer) clearInterval(state.timer);
    state.timer = setInterval(() => {
      if (!document.hidden) loadDashboard();
    }, seconds * 1000);
  }

  async function init() {
    initCustomDates();
    bindEvents();
    startAutoRefresh();

    if (!window.APP_CONFIG?.credentialsConfigured) {
      setConnectionStatus("warn", "Add API token in .env");
      return;
    }

    try {
      await checkHealth();
      await loadDashboard();
    } catch (error) {
      showToast(error.message, true);
    }
  }

  init();
})();
