const usdc = (n) => `${(n / 1_000_000).toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 6 })} USDC`;
const text = (id, value) => { document.getElementById(id).textContent = value; };
let dashboard, page = 1, stream, serverAvailable = false;

const themeToggle = document.getElementById("theme-toggle");
function setTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  themeToggle.textContent = dark ? "Light mode" : "Dark mode";
  themeToggle.setAttribute("aria-pressed", String(dark));
  try { localStorage.setItem("looprail-theme", dark ? "dark" : "light"); } catch { /* Storage is optional. */ }
}
let savedTheme;
try { savedTheme = localStorage.getItem("looprail-theme"); } catch { /* Storage is optional. */ }
setTheme(savedTheme);
themeToggle.addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));

function render() {
  if (!dashboard) return;
  const { events, metrics } = dashboard;
  const spent = metrics.usdc_spent_base_units;
  const budget = metrics.policy_budget_usdc_base_units;
  text("step-count", String(events.length));
  text("spent", usdc(spent));
  text("budget", usdc(budget));
  text("duration", `${(metrics.duration_ms / 1000).toLocaleString("en-US", { maximumFractionDigits: 2 })} s`);
  text("p95", `${metrics.provider_latency_p95_ms} ms`);
  text("settlements", String(metrics.settlements));
  text("session-id", metrics.session_id);
  text("mode", metrics.mode);
  text("transactions", String(metrics.onchain_transactions));
  text("source", metrics.source);
  text("step-total", `${events.length} steps`);
  text("authorized", usdc(metrics.usdc_authorized_base_units));
  text("reserved", usdc(metrics.usdc_reserved_base_units));
  text("live-spent", usdc(spent));
  text("remaining", usdc(Math.max(0, budget - spent - metrics.usdc_reserved_base_units)));
  const ratio = budget ? spent / budget : 0;
  text("budget-percent", `${(ratio * 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}%`);
  document.getElementById("budget-fill").style.width = `${Math.min(100, ratio * 100)}%`;

  const latencies = events.map((e) => e.provider_latency_ms);
  const maximum = Math.max(20, Math.ceil(Math.max(0, ...latencies) / 20) * 20);
  text("chart-max", `${maximum} ms`);
  text("chart-mid", `${maximum / 2} ms`);
  const points = latencies.map((latency, index) => [
    ((index / Math.max(1, latencies.length - 1)) * 640).toFixed(1),
    (200 - latency / maximum * 180).toFixed(1),
  ]);
  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
  document.getElementById("latency-line").setAttribute("d", line);
  document.getElementById("latency-area").setAttribute("d", line ? `${line} L640 200 L0 200 Z` : "");

  const totals = new Map();
  for (const event of events) totals.set(event.provider, (totals.get(event.provider) || 0) + event.cost_usdc_base_units);
  const bars = document.getElementById("provider-bars");
  bars.replaceChildren();
  const largest = Math.max(1, ...totals.values());
  for (const [provider, total] of totals) {
    const row = document.createElement("div"); row.className = "provider-row";
    const meta = document.createElement("div"); meta.className = "provider-meta";
    const name = document.createElement("span"); name.textContent = provider;
    const amount = document.createElement("span"); amount.textContent = usdc(total);
    meta.append(name, amount);
    const track = document.createElement("div"); track.className = "bar-track";
    const fill = document.createElement("div"); fill.className = "bar-fill";
    fill.style.width = `${total / largest * 100}%`;
    track.append(fill); row.append(meta, track); bars.append(row);
  }

  const size = 10, count = Math.max(1, Math.ceil(events.length / size));
  page = Math.min(page, count);
  const start = (page - 1) * size, rows = document.getElementById("step-rows");
  rows.replaceChildren();
  for (const event of events.slice(start, start + size)) {
    const row = document.createElement("tr");
    const values = [String(event.step_index + 1).padStart(2, "0"), event.tool, event.provider,
      event.outcome, event.reason.replaceAll("_", " "), usdc(event.cost_usdc_base_units), `${event.provider_latency_ms} ms`];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 3) {
        const badge = document.createElement("span");
        badge.className = `outcome ${event.outcome}`;
        badge.textContent = value;
        badge.title = event.reason;
        cell.append(badge);
      } else cell.textContent = value;
      row.append(cell);
    });
    rows.append(row);
  }
  text("page-range", events.length ? `Showing ${start + 1}–${Math.min(start + size, events.length)} of ${events.length} steps` : "No steps");
  text("page-current", `Page ${page} of ${count}`);
  document.getElementById("page-prev").disabled = page === 1;
  document.getElementById("page-next").disabled = page === count;
}
document.getElementById("page-prev").addEventListener("click", () => { page--; render(); });
document.getElementById("page-next").addEventListener("click", () => { page++; render(); });

function setStatus(status) {
  const running = status === "running";
  text("run-status", running ? "Simulation running" : status === "aborted" ? "Simulation aborted" : "Local simulation");
  document.getElementById("start-session").disabled = !serverAvailable || running;
  document.getElementById("replay-session").disabled = !serverAvailable || running;
  document.getElementById("end-session").disabled = !running;
}
function partialMetrics(events, mode) {
  const spent = events.reduce((sum, event) => sum + event.cost_usdc_base_units, 0);
  const latencies = events.map((e) => e.provider_latency_ms).filter(Boolean).sort((a, b) => a - b);
  return { ...dashboard.metrics, session_id: `${mode}-50`, mode, steps: events.length,
    usdc_spent_base_units: Math.max(spent, dashboard.metrics.usdc_spent_base_units),
    usdc_reserved_base_units: dashboard.metrics.usdc_reserved_base_units,
    usdc_authorized_base_units: 0,
    duration_ms: events.length ? Date.parse(events.at(-1).occurred_at) - Date.parse("2026-01-01T00:00:00Z") : 0,
    provider_latency_p95_ms: latencies[Math.ceil(latencies.length * .95) - 1] || 0,
    settlements: 0, onchain_transactions: 0, source: "simulation" };
}
function connectStream(mode, since = 0) {
  stream?.close();
  stream = new EventSource(`/api/events?since=${since}`);
  stream.addEventListener("budget", ({ data }) => {
    const budget = JSON.parse(data);
    dashboard.metrics.usdc_reserved_base_units = budget.reserved_usdc_base_units;
    dashboard.metrics.usdc_spent_base_units = budget.spent_usdc_base_units;
    render();
  });
  stream.addEventListener("step", ({ data }) => {
    dashboard.events.push(JSON.parse(data));
    dashboard.metrics = partialMetrics(dashboard.events, mode);
    render();
  });
  stream.addEventListener("complete", ({ data }) => {
    const result = JSON.parse(data);
    if (result?.metrics) { dashboard = result; render(); }
    else if (result?.error) showError(new Error(result.error));
    stream.close();
    setStatus(result?.status || "error");
  });
}
async function start(mode) {
  const response = await fetch("/api/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
  if (!response.ok) throw new Error("Could not start the local session.");
  dashboard = { events: [], metrics: partialMetrics([], mode) };
  page = 1; render(); setStatus("running"); connectStream(mode);
}
function showError(error) { document.querySelector(".notice span").textContent = error.message; }
document.getElementById("start-session").addEventListener("click", () => start("mock").catch(showError));
document.getElementById("replay-session").addEventListener("click", () => start("replay").catch(showError));
document.getElementById("end-session").addEventListener("click", () => fetch("/api/abort", { method: "POST" }).catch(showError));

async function loadDashboard() {
  const response = await fetch("./data/mock-50.json");
  if (!response.ok) throw new Error("Could not load the demo scenario.");
  dashboard = await response.json(); render();
  try {
    const stateResponse = await fetch("/api/state");
    if (!stateResponse.ok) return;
    serverAvailable = true;
    const state = await stateResponse.json();
    if (state.result?.metrics) dashboard = state.result;
    else if (state.events.length) dashboard = { events: state.events, metrics: partialMetrics(state.events, state.mode) };
    if (state.budget) {
      dashboard.metrics.usdc_reserved_base_units = state.budget.reserved_usdc_base_units;
      dashboard.metrics.usdc_spent_base_units = state.budget.spent_usdc_base_units;
    }
    if (state.status === "running") connectStream(state.mode, state.message_index);
    setStatus(state.status); render();
  } catch { /* Static mode remains usable. */ }
}
loadDashboard().catch(showError);
