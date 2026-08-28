const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const formatPrice = (value) => `₹${new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)}`;

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
  $("#niftyPrice").textContent = formatPrice(data.nifty_price);
  $("#niftyChange").textContent = `${data.nifty_change >= 0 ? "+" : ""}${data.nifty_change.toFixed(2)}%`;
  $("#niftyChange").className = data.nifty_change >= 0 ? "positive" : "negative";
  $("#vixValue").textContent = Number(data.india_vix).toFixed(2);
  $("#lastUpdated").textContent = "JUST NOW";
}

function bindCards() {
  $$(".stock-card").forEach((card) => {
    const button = card.querySelector(".expand");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      card.classList.toggle("expanded");
      button.textContent = card.classList.contains("expanded") ? "×" : "+";
    });
    card.addEventListener("click", (event) => {
      if (!event.target.closest("a") && !event.target.closest("button")) card.classList.toggle("expanded");
    });
  });
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
      card.querySelector(".summary").textContent = stock.gemini_summary;
      card.querySelector(".target").textContent = formatPrice(stock.target_price).replace(".00", "");
      card.querySelector(".stop").textContent = formatPrice(stock.stop_price).replace(".00", "");
      const levelEmphasis = card.querySelectorAll(".levels em");
      levelEmphasis[0].textContent = `+${((stock.target_price / stock.current_price - 1) * 100).toFixed(1)}%`;
      levelEmphasis[1].textContent = `${((stock.stop_price / stock.current_price - 1) * 100).toFixed(1)}%`;
    });
    window.__DASHBOARD__ = data;
    if (showMessage) toast("Dashboard data refreshed");
  } catch {
    if (showMessage) toast("Could not refresh dashboard");
  }
}

updateMarket(window.__DASHBOARD__);
bindCards();
$("#refreshButton").addEventListener("click", () => refreshDashboard(true));
window.setInterval(() => refreshDashboard(false), 60000);
