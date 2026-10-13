const usdc = (baseUnits) => `${(baseUnits / 1_000_000).toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 6 })} USDC`;
const text = (id, value) => { document.getElementById(id).textContent = value; };

const themeToggle = document.getElementById("theme-toggle");
const savedTheme = (() => {
  try { return localStorage.getItem("looprail-theme"); } catch { return null; }
})();
function setTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  themeToggle.textContent = dark ? "Light mode" : "Dark mode";
  themeToggle.setAttribute("aria-pressed", String(dark));
  try { localStorage.setItem("looprail-theme", dark ? "dark" : "light"); } catch { /* Storage may be unavailable. */ }
}
setTheme(savedTheme === "dark" ? "dark" : "light");
themeToggle.addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

async function loadDashboard() {
  const response = await fetch("./data/mock-50.json");
  if (!response.ok) throw new Error("Could not load the demo scenario.");
  const { events, metrics } = await response.json();
  text("step-count", String(metrics.steps));
  text("spent", usdc(metrics.usdc_spent_base_units));
  text("budget", usdc(metrics.policy_budget_usdc_base_units));
  text("duration", `${(metrics.duration_ms / 1000).toLocaleString("en-US", { maximumFractionDigits: 2 })} s`);
  text("p95", `${metrics.provider_latency_p95_ms} ms`);
  text("settlements", String(metrics.settlements));
  text("session-id", metrics.session_id);
  text("mode", metrics.mode);
  text("transactions", String(metrics.onchain_transactions));
  text("source", metrics.source);
  text("step-total", `${events.length} steps`);
  const budgetRatio = metrics.policy_budget_usdc_base_units > 0
    ? metrics.usdc_spent_base_units / metrics.policy_budget_usdc_base_units
    : 0;
  text("budget-percent", `${(budgetRatio * 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}%`);
  document.getElementById("budget-fill").style.width = `${Math.min(100, budgetRatio * 100)}%`;

  const latencies = events.map((event) => event.provider_latency_ms);
  const chartMaximum = Math.max(20, Math.ceil(Math.max(...latencies) / 20) * 20);
  text("chart-max", `${chartMaximum} ms`);
  text("chart-mid", `${chartMaximum / 2} ms`);
  const points = latencies.map((latency, index) => {
    const x = (index / Math.max(1, latencies.length - 1)) * 640;
    const y = 200 - (latency / chartMaximum) * 180;
    return [x.toFixed(1), y.toFixed(1)];
  });
  const linePath = points.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x} ${y}`).join(" ");
  document.getElementById("latency-line").setAttribute("d", linePath);
  document.getElementById("latency-area").setAttribute("d", `${linePath} L640 200 L0 200 Z`);

  const totals = new Map();
  for (const event of events) totals.set(event.provider, (totals.get(event.provider) || 0) + event.cost_usdc_base_units);
  const maximum = Math.max(1, ...totals.values());
  const providerBars = document.getElementById("provider-bars");
  for (const [provider, total] of totals) {
    const row = document.createElement("div");
    row.className = "provider-row";
    const meta = document.createElement("div");
    meta.className = "provider-meta";
    const name = document.createElement("span");
    name.textContent = provider;
    const amount = document.createElement("span");
    amount.textContent = usdc(total);
    meta.append(name, amount);
    const track = document.createElement("div");
    track.className = "bar-track";
    const fill = document.createElement("div");
    fill.className = "bar-fill";
    fill.style.width = `${(total / maximum) * 100}%`;
    track.append(fill);
    row.append(meta, track);
    providerBars.append(row);
  }

  const rows = document.getElementById("step-rows");
  const pageSize = 10;
  const pageCount = Math.max(1, Math.ceil(events.length / pageSize));
  let currentPage = 1;

  function renderPage() {
    rows.replaceChildren();
    const start = (currentPage - 1) * pageSize;
    for (const event of events.slice(start, start + pageSize)) {
      const row = document.createElement("tr");
      const values = [
        String(event.step_index + 1).padStart(2, "0"),
        event.tool,
        event.provider,
        event.outcome,
        usdc(event.cost_usdc_base_units),
        `${event.provider_latency_ms} ms`,
      ];
      values.forEach((value, index) => {
        const cell = document.createElement("td");
        if (index === 3) {
          const badge = document.createElement("span");
          badge.className = `outcome ${event.outcome}`;
          badge.textContent = value;
          badge.title = event.reason;
          cell.append(badge);
        } else {
          cell.textContent = value;
        }
        row.append(cell);
      });
      rows.append(row);
    }
    text("page-range", events.length
      ? `Showing ${start + 1}–${Math.min(start + pageSize, events.length)} of ${events.length} steps`
      : "No steps");
    text("page-current", `Page ${currentPage} of ${pageCount}`);
    document.getElementById("page-prev").disabled = currentPage === 1;
    document.getElementById("page-next").disabled = currentPage === pageCount;
  }

  document.getElementById("page-prev").addEventListener("click", () => {
    currentPage -= 1;
    renderPage();
  });
  document.getElementById("page-next").addEventListener("click", () => {
    currentPage += 1;
    renderPage();
  });
  renderPage();
}

loadDashboard().catch((error) => {
  document.querySelector(".notice").textContent = error.message;
});
