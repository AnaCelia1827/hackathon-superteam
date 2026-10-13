const usdc = (baseUnits) => `${(baseUnits / 1_000_000).toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 6 })} USDC`;
const text = (id, value) => { document.getElementById(id).textContent = value; };

async function loadDashboard() {
  const response = await fetch("./data/mock-50.json");
  if (!response.ok) throw new Error("Não foi possível carregar o cenário de demonstração.");
  const { events, metrics } = await response.json();
  text("step-count", String(metrics.steps));
  text("spent", usdc(metrics.usdc_spent_base_units));
  text("budget", usdc(metrics.policy_budget_usdc_base_units));
  text("duration", `${(metrics.duration_ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} s`);
  text("p95", `${metrics.provider_latency_p95_ms} ms`);
  text("settlements", String(metrics.settlements));
  text("session-id", metrics.session_id);
  text("mode", metrics.mode);
  text("transactions", String(metrics.onchain_transactions));
  text("source", metrics.source);
  text("step-total", `${events.length} passos`);

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
  for (const event of events) {
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
}

loadDashboard().catch((error) => {
  document.querySelector(".notice").textContent = error.message;
});
