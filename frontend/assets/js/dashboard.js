const API = "";
let volumeChart, countChart;

function themeColor(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

async function loadStatus() {
  try {
    const s = await fetch(`${API}/api/status`).then((r) => r.json());
    const last = s.last_run;
    let line = `Auto-refresh every ${s.interval_minutes} min · Next run: ${fmtTime(s.next_run_at)}`;
    if (last) {
      line += last.success
        ? ` · Last run OK — ${last.rows_loaded} rows, ${last.integrity_pct}% integrity`
        : ` · Last run FAILED: ${last.error}`;
    }
    document.getElementById("statusLine").textContent = line;
  } catch (e) { /* backend still booting */ }
}

async function loadAll() {
  try {
    const [stats, summary, txs] = await Promise.all([
      fetch(`${API}/api/stats`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`${API}/api/summary`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`${API}/api/transactions?limit=15`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
    ]);
    renderKpis(stats);
    renderCharts(summary);
    renderTable(txs);
  } catch (e) {
    document.getElementById("runStatus").textContent = "Waiting for first run...";
  }

  try {
    const [analytics, quality] = await Promise.all([
      fetch(`${API}/api/analytics`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
      fetch(`${API}/api/quality`).then((r) => (r.ok ? r.json() : Promise.reject(r))),
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
    const res = await fetch(`${API}/api/run-pipeline`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    document.getElementById("runStatus").textContent = "Done — refreshing";
    await loadAll();
  } catch (e) {
    document.getElementById("runStatus").textContent = "Failed — check logs";
  } finally {
    btn.disabled = false;
  }
}

loadAll();
setInterval(loadAll, 30000);