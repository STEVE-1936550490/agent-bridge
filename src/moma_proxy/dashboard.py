"""Static dashboard HTML for local observability."""

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentBridge Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f5;
      --panel: #ffffff;
      --text: #202124;
      --muted: #5f6368;
      --line: #d7d9dc;
      --ok: #116329;
      --warn: #9a4f00;
      --bad: #b3261e;
      --accent: #0b57d0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }
    main { padding: 18px 20px; }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 14px;
      align-items: center;
    }
    input, select, button {
      height: 34px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 6px;
      padding: 0 10px;
      color: var(--text);
    }
    button {
      cursor: pointer;
      border-color: var(--accent);
      color: var(--accent);
      font-weight: 600;
    }
    .status { color: var(--muted); }
    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
    }
    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }
    th {
      font-size: 12px;
      color: var(--muted);
      background: #fbfbfa;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    td.wrap {
      white-space: normal;
      overflow-wrap: anywhere;
      max-width: 260px;
    }
    .ok { color: var(--ok); font-weight: 650; }
    .warn { color: var(--warn); font-weight: 650; }
    .bad { color: var(--bad); font-weight: 650; }
    .empty {
      padding: 28px;
      text-align: center;
      color: var(--muted);
      background: var(--panel);
      border: 1px solid var(--line);
    }
  </style>
</head>
<body>
  <header>
    <h1>AgentBridge Dashboard</h1>
    <div class="status" id="status">Loading</div>
  </header>
  <main>
    <div class="toolbar">
      <input id="filter" placeholder="Filter request id, provider, model, path, error" size="42">
      <select id="statusFilter">
        <option value="">All status</option>
        <option value="2">2xx</option>
        <option value="4">4xx</option>
        <option value="5">5xx</option>
      </select>
      <button id="refresh">Refresh</button>
    </div>
    <div id="content" class="empty">No logs yet</div>
  </main>
  <script>
    const content = document.getElementById("content");
    const statusEl = document.getElementById("status");
    const filterEl = document.getElementById("filter");
    const statusFilterEl = document.getElementById("statusFilter");
    document.getElementById("refresh").addEventListener("click", loadLogs);
    filterEl.addEventListener("input", renderCurrent);
    statusFilterEl.addEventListener("change", renderCurrent);
    let currentLogs = [];

    function statusClass(status) {
      if (status >= 500) return "bad";
      if (status >= 400) return "warn";
      return "ok";
    }
    function tokenText(usage) {
      if (!usage) return "unavailable";
      const source = usage.source || "unavailable";
      if (source === "unavailable") return "unavailable";
      return `${source}: ${usage.input_tokens ?? "-"} / ${usage.output_tokens ?? "-"} / ${usage.total_tokens ?? "-"}`;
    }
    function matches(log) {
      const query = filterEl.value.toLowerCase().trim();
      const prefix = statusFilterEl.value;
      if (prefix && String(log.status || "").charAt(0) !== prefix) return false;
      if (!query) return true;
      return JSON.stringify(log).toLowerCase().includes(query);
    }
    function renderCurrent() {
      const rows = currentLogs.filter(matches).reverse();
      if (!rows.length) {
        content.className = "empty";
        content.textContent = "No matching logs";
        return;
      }
      content.className = "";
      content.innerHTML = `<table>
        <thead><tr>
          <th>Time</th><th>Status</th><th>Latency</th><th>Endpoint</th><th>Provider</th>
          <th>Model</th><th>Protocols</th><th>Stream</th><th>Tokens</th><th>Request</th><th>Error</th>
        </tr></thead>
        <tbody>${rows.map(log => `
          <tr>
            <td>${log.timestamp_iso || ""}</td>
            <td class="${statusClass(log.status)}">${log.status}</td>
            <td>${log.latency_ms} ms</td>
            <td>${log.method} ${log.path}</td>
            <td>${log.provider || "-"}</td>
            <td>${log.model || "-"}</td>
            <td>${log.client_protocol || "-"} -> ${log.provider_protocol || "-"}</td>
            <td>${log.stream_state || "-"}</td>
            <td>${tokenText(log.token_usage)}</td>
            <td class="wrap">${log.request_id}</td>
            <td class="wrap">${log.error || ""}</td>
          </tr>`).join("")}</tbody>
      </table>`;
    }
    async function loadLogs() {
      try {
        const response = await fetch("/logs?limit=200", { cache: "no-store" });
        const payload = await response.json();
        currentLogs = payload.data || [];
        statusEl.textContent = `${currentLogs.length} log entries`;
        renderCurrent();
      } catch (error) {
        statusEl.textContent = "Failed to load logs";
        content.className = "empty";
        content.textContent = String(error);
      }
    }
    loadLogs();
    setInterval(loadLogs, 2000);
  </script>
</body>
</html>
"""
