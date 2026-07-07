const API = "";
let volumeChart, countChart;

/* ---------------------------------------------------------------
   Tenant identity: a random token this browser holds, no login.
   "useOwnData" flag decides whether we send it on requests (true)
   or view the shared demo dataset (false, the default for new visitors).
--------------------------------------------------------------- */
const CLIENT_ID_KEY = "blackloom-client-id";
const USE_OWN_DATA_KEY = "blackloom-use-own-data";

function getOrCreateClientId() {
  let id = localStorage.getItem(CLIENT_ID_KEY);
  if (!id) {
    id = "u" + crypto.randomUUID().replace(/-/g, "").slice(0, 24);
    localStorage.setItem(CLIENT_ID_KEY, id);
  }
  return id;
}

function usingOwnData() {
  return localStorage.getItem(USE_OWN_DATA_KEY) === "true";
}

function authHeaders() {
  return usingOwnData() ? { "X-Client-ID": getOrCreateClientId() } : {};
}

function themeColor(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

/* ---------------------------------------------------------------
   Config panel — "Connect your own wallet"
--------------------------------------------------------------- */
function toggleConfigPanel() {
  const panel = document.getElementById("configPanel");
  panel.style.display = panel.style.display === "none" ? "block" : "none";
}

function viewDemoData() {
  localStorage.setItem(USE_OWN_DATA_KEY, "false");
  updateDataSourceBanner();
  loadAll();
}

function updateDataSourceBanner() {
  const isOwn = usingOwnData();
  document.getElementById("dataSourceLabel").textContent = isOwn ? "Viewing: your data" : "Viewing: demo data";
  document.getElementById("viewDemoBtn").style.display = isOwn ? "inline-flex" : "none";
}

async function loadSavedConfig() {
  if (!usingOwnData()) return;
  try {
    const cfg = await fetch(`${API}/api/config`, { headers: authHeaders() }).then((r) => r.json());
    if (cfg.configured) {
      document.getElementById("cfgDataSource").value = cfg.data_source;
      document.getElementById("cfgChainId").value = cfg.chain_id || "1";
      document.getElementById("cfgWallet").value = cfg.wallet_address || "";
      if (cfg.etherscan_api_key_masked) {
        document.getElementById("cfgApiKey").placeholder = `saved (${cfg.etherscan_api_key_masked})`;
      }
    }
  } catch (e) { /* not configured yet */ }
}

async function saveConfig() {
  const btn = document.getElementById("saveConfigBtn");
  const statusEl = document.getElementById("configStatus");
  btn.disabled = true;
  statusEl.textContent = "Saving and running your pipeline...";

  const clientId = getOrCreateClientId();
  const body = {
    data_source: document.getElementById("cfgDataSource").value,
    chain_id: document.getElementById("cfgChainId").value || "1",
    wallet_address: document.getElementById("cfgWallet").value.trim() || null,
    etherscan_api_key: document.getElementById("cfgApiKey").value.trim() || null,
  };

  try {
    const res = await fetch(`${API}/api/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Client-ID": clientId },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Save failed");

    localStorage.setItem(USE_OWN_DATA_KEY, "true");
    updateDataSourceBanner();
    statusEl.textContent = `Done — ${data.run_result.rows_loaded} rows loaded, ${data.run_result.integrity_pct}% integrity.`;
    await loadAll();
  } catch (e) {
    statusEl.textContent = "Failed: " + e.message;
  } finally {
    btn.disabled = false;
  }
}

/* ---------------------------------------------------------------
   Exports — JS fetch + blob, since custom headers can't ride on
   a plain <a href download> link.
--------------------------------------------------------------- */
async function exportFile(kind) {
  const mimeExt = { csv: "csv", xlsx: "xlsx", pdf: "pdf" };
  try {
    const res = await fetch(`${API}/api/export/${kind}`, { headers: authHeaders() });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `blackloom-export.${mimeExt[kind]}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    document.getElementById("runStatus").textContent = "Export failed — run the pipeline first";
  }
}

/* ---------------------------------------------------------------
   Data loading + rendering
--------------------------------------------------------------- */
async function loadStatus() {
  try {
    const s = await fetch(`${API}/api/status`, { headers: authHeaders() }).then((r) => r.json());
    const last = s.last_run;
    let line = s.is_tenant
      ? "Your data — runs when you save config or click Run now"
      : `Auto-refresh every ${s.interval_minutes} min · Next run: ${fmtTime(s.next_run_at)}`;
    if (last) {
      line += last.success
        ? ` · Last run OK — ${last.rows_loaded} rows, ${last.integrity_pct}% integrity`
        : ` · Last run FAILED: ${last.error}`;
    }
    document.getElementById("statusLine").textContent = line;
  } catch (e) { /* backend still booting */ }
}

async function loadAll() {
  const headers = authHeaders();
  try {
    const [stats, summary, txs] = await Promise.all([
      fetch(`${API}/api/stats`, { headers }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`${API}/api/summary`, { headers }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`${API}/api/transactions?limit=15`, { headers }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
    ]);
    renderKpis(stats);
    renderCharts(summary);
    renderTable(txs);
    document.getElementById("runStatus").textContent = "";
  } catch (e) {
    document.getElementById("runStatus").textContent = usingOwnData()
      ? "No data yet — save your config above to run your first pipeline"
      : "Waiting for first run...";
  }

  try {
    const [analytics, quality] = await Promise.all([
      fetch(`${API}/api/analytics`, { headers }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`${API}/api/quality`, { headers }).then((r) => (r.ok ? r.json() : Promise.reject(r))),
    ]);
    renderAnomalies(analytics.anomalies);
    renderForecast(analytics.forecast, analytics.trend_direction);
    renderQuality(quality);
  } catch (e) { /* not generated yet */ }

  loadStatus();
}

function renderKpis(s) {
  document.getElementById("kpis").innerHTML = `
    <div class="card"><div class="label">Total transactions</div><div class="value">${s.total_transactions.toLocaleString()}</div></div>
    <div class="card"><div class="label">Total ETH volume</div><div class="value">${s.total_eth_volume.toLocaleString()}</div></div>
    <div class="card"><div class="label">Failed tx</div><div class="value">${s.failed_transactions}</div></div>
    <div class="card"><div class="label">Failure rate</div><div class="value">${s.failure_rate_pct}%</div></div>
  `;
}

function renderCharts(summary) {
  const labels = summary.map((d) => d.day);
  const volumes = summary.map((d) => d.total_eth_volume);
  const counts = summary.map((d) => d.tx_count);

  if (volumeChart) volumeChart.destroy();
  if (countChart) countChart.destroy();

  const gridColor = themeColor("--border-soft");
  const textColor = themeColor("--text-muted");
  const commonOpts = {
    scales: {
      x: { ticks: { color: textColor }, grid: { color: gridColor } },
      y: { ticks: { color: textColor }, grid: { color: gridColor } },
    },
    plugins: { legend: { labels: { color: themeColor("--text") } } },
  };

  volumeChart = new Chart(document.getElementById("volumeChart"), {
    type: "line",
    data: { labels, datasets: [{ label: "ETH", data: volumes, borderColor: themeColor("--thread-gold-bright"), backgroundColor: "transparent", tension: 0.3 }] },
    options: commonOpts,
  });

  countChart = new Chart(document.getElementById("countChart"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Tx", data: counts, backgroundColor: themeColor("--thread-teal-bright") }] },
    options: commonOpts,
  });
}

function renderTable(txs) {
  if (!txs.length) {
    document.getElementById("txTableWrap").innerHTML = `<div class="empty">No transactions</div>`;
    return;
  }
  const rows = txs.map((t) => `
    <tr>
      <td class="mono">${t.hash.slice(0, 10)}...</td>
      <td class="mono">${t.from.slice(0, 8)}...</td>
      <td class="mono">${t.to.slice(0, 8)}...</td>
      <td>${t.value_eth}</td>
      <td>${t.gas_price_gwei}</td>
      <td>${t.tx_time}</td>
      <td class="${t.is_error ? "fail" : "ok"}">${t.is_error ? "Failed" : "OK"}</td>
    </tr>`).join("");
  document.getElementById("txTableWrap").innerHTML = `
    <table><thead><tr><th>Hash</th><th>From</th><th>To</th><th>ETH</th><th>Gas (gwei)</th><th>Time</th><th>Status</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderAnomalies(anomalies) {
  const el = document.getElementById("anomalyWrap");
  if (!anomalies || !anomalies.length) {
    el.innerHTML = `<div class="empty">No statistical anomalies detected</div>`;
    return;
  }
  const rows = anomalies.slice(0, 8).map((a) => `
    <tr><td class="mono">${a.hash.slice(0, 10)}...</td><td>${a.metric}</td><td>${a.value}</td><td class="fail">${a.z_score}</td><td>${a.tx_time}</td></tr>`).join("");
  el.innerHTML = `<table><thead><tr><th>Hash</th><th>Metric</th><th>Value</th><th>Z-score</th><th>Time</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderForecast(forecast, direction) {
  const el = document.getElementById("forecastWrap");
  if (!forecast || !forecast.length) {
    el.innerHTML = `<div class="empty">Not enough history to forecast yet</div>`;
    return;
  }
  const dirColor = direction === "up" ? themeColor("--good") : themeColor("--bad");
  const cards = forecast.map((f) => `
    <div class="card" style="flex:1;"><div class="label">${f.day}</div><div class="value" style="color:${dirColor}; font-size:1.4rem;">${f.predicted_volume} ETH</div></div>`).join("");
  el.innerHTML = `<div style="display:flex; gap:12px;">${cards}</div>
    <div style="margin-top:12px; color:var(--text-muted); font-size:0.85rem;">Trend direction: <b style="color:${dirColor}">${direction}</b></div>`;
}

function renderQuality(report) {
  const el = document.getElementById("qualityWrap");
  const s = report.scores;
  const good = themeColor("--good"), warn = themeColor("--warn"), bad = themeColor("--bad");
  const overallColor = report.overall_score >= 90 ? good : report.overall_score >= 70 ? warn : bad;
  el.innerHTML = `
    <div style="font-family:var(--font-display); font-size:2rem; font-weight:600; color:${overallColor};">${report.overall_score}%</div>
    <div style="color:var(--text-muted); font-size:0.85rem; margin-bottom:12px;">Overall quality score</div>
    <table><tbody>
      <tr><td>Completeness</td><td>${s.completeness}%</td></tr>
      <tr><td>Uniqueness</td><td>${s.uniqueness}%</td></tr>
      <tr><td>Validity</td><td>${s.validity}%</td></tr>
      <tr><td>Timeliness</td><td>${s.timeliness}%</td></tr>
    </tbody></table>`;
}

async function runPipeline() {
  const btn = document.getElementById("runBtn");
  btn.disabled = true;
  document.getElementById("runStatus").textContent = "Running...";
  try {
    const res = await fetch(`${API}/api/run-pipeline`, { method: "POST", headers: authHeaders() });
    if (!res.ok) throw new Error((await res.json()).detail || "failed");
    document.getElementById("runStatus").textContent = "Done — refreshing";
    await loadAll();
  } catch (e) {
    document.getElementById("runStatus").textContent = "Failed: " + e.message;
  } finally {
    btn.disabled = false;
  }
}

updateDataSourceBanner();
loadSavedConfig();
loadAll();
setInterval(loadAll, 30000);