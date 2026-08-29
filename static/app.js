const $ = (selector, scope = document) => scope.querySelector(selector);
const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));
const formatPrice = (value) => `₹${new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)}`;
const formatInt = (value) => new Intl.NumberFormat("en-IN").format(value);

const REGIME_NOTES = {
  "RISK-ON": "Broad participation with momentum leadership",
  "NEUTRAL": "Mixed signals - selective setups only",
  "RISK-OFF": "Elevated risk - all scores penalized 20pts",
};

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  window.setTimeout(() => element.classList.remove("show"), 2300);
}

function updateMarket(data) {
  const badge = $("#regimeBadge");
  badge.classList.toggle("neutral", data.market_regime === "NEUTRAL");
  badge.classList.toggle("risk-off", data.market_regime === "RISK-OFF");
  $("#regimeValue").textContent = data.market_regime;
  const note = $("#regimeNote");
  if (note) note.textContent = REGIME_NOTES[data.market_regime] || "";

  $("#niftyPrice").textContent = formatPrice(data.nifty_price);
  $("#niftyChange").textContent = `${data.nifty_change >= 0 ? "+" : ""}${data.nifty_change.toFixed(2)}%`;
  $("#niftyChange").className = data.nifty_change >= 0 ? "positive" : "negative";
  $("#vixValue").textContent = Number(data.india_vix).toFixed(2);

  const advEl = $("#breadthAdv");
  if (advEl) advEl.innerHTML = `${formatInt(data.breadth_advances)} <small>ADV</small>`;
  const decEl = $("#breadthDec");
  if (decEl) decEl.innerHTML = `${formatInt(data.breadth_declines)} <small>DEC</small>`;
  const pctEl = $("#breadthPct");
  if (pctEl) pctEl.textContent = data.breadth_pct;

  const asOf = $("#asOfTime");
  if (asOf && data.as_of_ist) asOf.textContent = `As of ${data.as_of_ist}`;

  const sync = $("#syncStatus");
  if (sync) sync.innerHTML = `<i></i> ${data.is_live ? "Zerodha live" : "Sample data"} <b>·</b> Auto-refresh 60s`;

  $("#lastUpdated").textContent = "JUST NOW";
}

function buildChecklistRows(checklist) {
  let html = "";
  let currentCategory = null;
  checklist.forEach((item, index) => {
    const pillarClass = `pillar-${index % 5}`;
    if (item.category !== currentCategory) {
      html += `<tr class="pillar-header ${pillarClass}"><td colspan="5"><strong>${item.category}</strong></td></tr>`;
      currentCategory = item.category;
    }
    const shortName = item.category.length > 12 ? `${item.category.slice(0, 12)}…` : item.category;
    const mark = item.status === "pass" ? "✓" : "×";
    html += `<tr><td class="pillar-badge ${pillarClass}">${shortName}</td><td>${item.signal}</td><td><small>${item.threshold}</small></td><td><small>${item.actual}</small></td><td class="${item.status}">${mark}</td></tr>`;
  });
  return html;
}

function renderPoints(points) {
  return (points || [])
    .map((p) => `<li><b>${p.label}</b>${p.text}</li>`)
    .join("");
}

function populateDetail(symbol) {
  const data = window.__DASHBOARD__;
  const stock = data.top_5_stocks.find((s) => s.symbol === symbol);
  if (!stock) return false;

  $("#detailIcon").textContent = stock.symbol.slice(0, 2);
  $("#detailName").textContent = stock.symbol;
  $("#detailScore").innerHTML = `${stock.score}<span class="detail-score-suffix">/100</span>`;
  $("#detailNarrative").textContent = stock.gemini_summary;
  $("#detailPointsList").innerHTML = renderPoints(stock.summary_points);
  $("#detailChecklistBody").innerHTML = buildChecklistRows(stock.checklist);
  return true;
}

function openDetail(symbol, { scroll = true } = {}) {
  if (!populateDetail(symbol)) return;
  const panel = $("#detailPanel");
  panel.dataset.symbol = symbol;
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
  $$(".stock-card").forEach((c) => c.classList.toggle("active", c.dataset.symbol === symbol));
  if (scroll) panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeDetail() {
  const panel = $("#detailPanel");
  panel.classList.remove("open");
  panel.setAttribute("aria-hidden", "true");
  delete panel.dataset.symbol;
  $$(".stock-card").forEach((c) => c.classList.remove("active"));
}

function bindCards() {
  $$(".stock-card").forEach((card) => {
    const button = card.querySelector(".expand");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openDetail(card.dataset.symbol);
    });
    card.addEventListener("click", (event) => {
      if (!event.target.closest("a") && !event.target.closest("button")) openDetail(card.dataset.symbol);
    });
  });
  const closeBtn = $("#detailClose");
  if (closeBtn) closeBtn.addEventListener("click", closeDetail);
}

async function refreshDashboard(showMessage = false) {
  try {
    const response = await fetch("/api/dashboard", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("refresh failed");
    const data = await response.json();
    updateMarket(data);
    data.top_5_stocks.forEach((stock) => {
      const card = $(`.stock-card[data-symbol="${stock.symbol}"]`);
      if (!card) return;
      card.querySelector(".price strong").textContent = formatPrice(stock.current_price);
      const move = card.querySelector(".price span");
      move.textContent = `${stock.change_percent >= 0 ? "+" : ""}${Number(stock.change_percent).toFixed(2)}%`;
      move.className = stock.change_percent >= 0 ? "positive" : "negative";

      card.querySelector(".score strong").innerHTML = `${stock.score}<em>/100</em>`;
      const ring = card.querySelector(".ring");
      if (ring) ring.className = `ring ring-${Math.floor(stock.score / 10)}`;

      card.querySelector(".summary").textContent = stock.gemini_summary;
      card.querySelector(".target").textContent = formatPrice(stock.target_price).replace(".00", "");
      card.querySelector(".stop").textContent = formatPrice(stock.stop_price).replace(".00", "");
      const levelEmphasis = card.querySelectorAll(".levels em");
      levelEmphasis[0].textContent = `+${((stock.target_price / stock.current_price - 1) * 100).toFixed(1)}%`;
      levelEmphasis[1].textContent = `${((stock.stop_price / stock.current_price - 1) * 100).toFixed(1)}%`;
    });
    window.__DASHBOARD__ = data;

    const panel = $("#detailPanel");
    if (panel.classList.contains("open") && panel.dataset.symbol) {
      populateDetail(panel.dataset.symbol);
    }

    if (showMessage) toast("Dashboard data refreshed");
  } catch {
    if (showMessage) toast("Could not refresh dashboard");
  }
}

updateMarket(window.__DASHBOARD__);
bindCards();
$("#refreshButton").addEventListener("click", () => refreshDashboard(true));
window.setInterval(() => refreshDashboard(false), 60000);
