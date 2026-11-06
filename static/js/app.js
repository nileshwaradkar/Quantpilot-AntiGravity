/**
 * Quant Pilot - Core Client Application
 * Powers real-time chart, scanner matrix, paper execution, and WebSocket synchronization.
 */

// Global State
let currentSymbol = "NSE:NIFTY50-INDEX";
let currentCandleData = null;
let chart = null;
let candleSeries = null;
let maSeries = null;
let volumeSeries = null;
let pdhLine = null;
let pdlLine = null;
let slLine = null;
let tgtLine = null;

let ws = null;
let isSoundEnabled = true;
let currentTradingMode = "PAPER";
let audioCtx = null;

// Initialize when DOM ready
document.addEventListener("DOMContentLoaded", () => {
  initClock();
  initLightweightChart();
  connectWebSocket();
  loadSymbolData(currentSymbol);
  fetchPortfolio();
  fetchBrokerStatus();
  fetchMarketStatus();
  
  // Re-render chart on window resize
  window.addEventListener("resize", () => {
    if (chart && document.getElementById("chartContainer")) {
      const container = document.getElementById("chartContainer");
      chart.applyOptions({
        width: container.clientWidth,
        height: container.clientHeight
      });
    }
  });
});

// ================= CLOCK & MARKET STATUS =================
function initClock() {
  function updateTime() {
    const now = new Date();
    // Format in Indian Standard Time (IST)
    const options = { timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' };
    const istTime = new Intl.DateTimeFormat('en-IN', options).format(now);
    const clockEl = document.getElementById("marketClock");
    if (clockEl) clockEl.textContent = `${istTime} IST`;
  }
  updateTime();
  setInterval(updateTime, 1000);
}

async function fetchMarketStatus() {
  try {
    const res = await fetch("/api/market-status");
    const data = await res.json();
    const nseEl = document.getElementById("nseStatusBadge");
    const mcxEl = document.getElementById("mcxStatusBadge");
    if (nseEl) {
      nseEl.textContent = `NSE: ${data.nse_status}`;
      nseEl.className = data.nse_status === "OPEN" ? "text-emerald-400 font-semibold" : "text-slate-400 font-semibold";
    }
    if (mcxEl) {
      mcxEl.textContent = `MCX: ${data.mcx_status}`;
      mcxEl.className = data.mcx_status === "OPEN" ? "text-amber-400 font-semibold" : "text-slate-400 font-semibold";
    }
  } catch (e) {
    console.error("Market status fetch error", e);
  }
}

// ================= TRADINGVIEW LIGHTWEIGHT CHARTS =================
function initLightweightChart() {
  const container = document.getElementById("chartContainer");
  if (!container || !window.LightweightCharts) return;

  container.innerHTML = ""; // Clear existing

  chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight || 420,
    layout: {
      background: { color: "#0c1222" },
      textColor: "#94a3b8",
      fontSize: 11
    },
    grid: {
      vertLines: { color: "#1e293b" },
      horzLines: { color: "#1e293b" }
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: "#38bdf8", width: 1, style: 2 },
      horzLine: { color: "#38bdf8", width: 1, style: 2 }
    },
    rightPriceScale: {
      borderColor: "#1e293b",
      autoScale: true
    },
    timeScale: {
      borderColor: "#1e293b",
      timeVisible: true,
      secondsVisible: false
    }
  });

  // 1. Candlestick Series
  candleSeries = chart.addCandlestickSeries({
    upColor: "#26a69a",
    downColor: "#ef5350",
    borderVisible: false,
    wickUpColor: "#26a69a",
    wickDownColor: "#ef5350"
  });

  // 2. MA(20) Line Series
  maSeries = chart.addLineSeries({
    color: "#f59e0b", // Amber
    lineWidth: 2,
    title: "MA(20)",
    priceLineVisible: false
  });

  // 3. Volume Sub-Series
  volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "", // Overlay on main chart
    scaleMargins: {
      top: 0.82,
      bottom: 0
    }
  });

  const overlay = document.getElementById("chartLoadingOverlay");
  if (overlay) overlay.style.display = "none";
}

// ================= SYMBOL SELECTION & DATA LOAD =================
async function selectSymbol(symbol) {
  currentSymbol = symbol;
  
  // Highlight in sidebar & mobile carousel
  document.querySelectorAll(".sym-card").forEach(el => el.classList.remove("border-emerald-500", "bg-emerald-500/10"));
  const cleanId = symbol.replace(/:/g, "_").replace(/-/g, "_");
  const card = document.getElementById(`card-${cleanId}`);
  if (card) card.classList.add("border-emerald-500", "bg-emerald-500/10");

  document.querySelectorAll(".mobile-sym-pill").forEach(el => {
    el.classList.remove("border-emerald-500", "bg-emerald-500/20", "text-emerald-300");
    el.classList.add("text-slate-300");
  });
  const pill = document.getElementById(`pill-${cleanId}`);
  if (pill) {
    pill.classList.add("border-emerald-500", "bg-emerald-500/20", "text-emerald-300");
    pill.classList.remove("text-slate-300");
  }

  // Tell WebSocket server active symbol
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "SELECT_SYMBOL", symbol }));
  }

  await loadSymbolData(symbol);
}

async function reloadActiveCandles() {
  await loadSymbolData(currentSymbol);
}

async function loadSymbolData(symbol) {
  try {
    const res = await fetch(`/api/candles/${encodeURIComponent(symbol)}`);
    if (!res.ok) throw new Error("Failed to load candles");
    const data = await res.json();
    currentCandleData = data;

    // Update Header labels
    const nameEl = document.getElementById("activeSymbolName");
    const codeEl = document.getElementById("activeSymbolCode");
    const priceEl = document.getElementById("activeCurrentPrice");
    
    if (nameEl && data.evaluation && data.evaluation.name) {
      nameEl.textContent = data.evaluation.name;
    }
    if (codeEl) codeEl.textContent = symbol;
    
    const lastCandle = data.candles[data.candles.length - 1];
    if (priceEl && lastCandle) {
      priceEl.textContent = `₹${lastCandle.close.toLocaleString('en-IN')}`;
    }

    // Update Chart Series
    if (candleSeries && data.candles) {
      candleSeries.setData(data.candles);
    }
    if (maSeries && data.ma20) {
      maSeries.setData(data.ma20);
    }
    if (volumeSeries && data.volume) {
      volumeSeries.setData(data.volume);
    }

    // Update PDH / PDL reference levels
    const pdhVal = data.pdh || 0;
    const pdlVal = data.pdl || 0;
    
    const chartPdhEl = document.getElementById("chartPdh");
    const chartPdlEl = document.getElementById("chartPdl");
    if (chartPdhEl) chartPdhEl.textContent = pdhVal ? `₹${pdhVal.toLocaleString('en-IN')}` : "--";
    if (chartPdlEl) chartPdlEl.textContent = pdlVal ? `₹${pdlVal.toLocaleString('en-IN')}` : "--";

    // Update Price Lines on Chart for PDH and PDL
    if (pdhLine && candleSeries) candleSeries.removePriceLine(pdhLine);
    if (pdlLine && candleSeries) candleSeries.removePriceLine(pdlLine);

    if (pdhVal > 0 && candleSeries) {
      pdhLine = candleSeries.createPriceLine({
        price: pdhVal,
        color: "#38bdf8", // Sky blue
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: "PDH (Prev Day High)"
      });
    }

    if (pdlVal > 0 && candleSeries) {
      pdlLine = candleSeries.createPriceLine({
        price: pdlVal,
        color: "#f43f5e", // Rose red
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: "PDL (Prev Day Low)"
      });
    }

    // Render Strategy Evaluation Metrics
    if (data.evaluation) {
      renderStrategyBreakdown(data.evaluation);
    }

    if (chart) chart.timeScale().fitContent();

  } catch (err) {
    console.error("loadSymbolData error", err);
  }
}

// ================= 6 STRATEGY RULES RENDERING =================
function renderStrategyBreakdown(evalData) {
  const verdict = evalData.verdict || "SCANNING";
  const side = evalData.side || "NEUTRAL";
  const breakdown = evalData.rules_breakdown || {};
  const ind = evalData.indicators || {};

  // 1. Top Verdict Banner
  const banner = document.getElementById("activeVerdictBanner");
  const dot = document.getElementById("activeVerdictDot");
  const text = document.getElementById("activeVerdictText");

  if (text) text.textContent = formatVerdictText(verdict, side);

  if (banner && dot) {
    if (verdict === "BUY_SIGNAL") {
      banner.className = "px-3 py-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center gap-2 text-xs font-bold text-emerald-400";
      dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping";
    } else if (verdict === "SELL_SIGNAL") {
      banner.className = "px-3 py-1.5 rounded-lg bg-red-500/20 border border-red-500/40 flex items-center gap-2 text-xs font-bold text-red-400";
      dot.className = "w-2.5 h-2.5 rounded-full bg-red-400 animate-ping";
    } else if (verdict.includes("BUILDING")) {
      banner.className = "px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center gap-2 text-xs font-bold text-amber-300";
      dot.className = "w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse";
    } else {
      banner.className = "px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 flex items-center gap-2 text-xs font-semibold text-slate-300";
      dot.className = "w-2.5 h-2.5 rounded-full bg-slate-500";
    }
  }

  // 2. Score Badge
  const scoreBadge = document.getElementById("rulesScoreBadge");
  if (scoreBadge && evalData.scores) {
    scoreBadge.textContent = side === "SHORT" ? `${evalData.scores.short_score} Passed (Short)` : `${evalData.scores.long_score} Passed (Long)`;
  }

  // 3. Render Each Rule Box
  const targetSide = side === "SHORT" ? "short_passed" : "long_passed";

  // Precondition: PDH / PDL Breakout
  updateRuleItem("pdh", breakdown.pdh_break, targetSide);
  // Rule 1: Candle closes on MA(20)
  updateRuleItem("r1", breakdown.rule1_ma20_candle, targetSide);
  // Rule 2: RSI(14) Crossover RSI(20)
  updateRuleItem("r2", breakdown.rule2_rsi_crossover, targetSide);
  // Rule 3: MACD Green
  updateRuleItem("r3", breakdown.rule3_macd, targetSide);
  // Rule 4: Volume > 5-bar SMA
  updateRuleItem("r4", breakdown.rule4_volume, targetSide);
  // Rule 6: Stop-Loss & Target Plan
  updateRuleItem("r6", breakdown.rule6_stoploss, targetSide);

  // 4. Trade Plan Card (Entry, SL, Target)
  const planEntry = document.getElementById("planEntryPrice");
  const planSL = document.getElementById("planStopLoss");
  const planTgt = document.getElementById("planTarget");
  const planRR = document.getElementById("tradePlanRiskReward");

  if (planEntry) planEntry.textContent = `₹${evalData.entry_price || ind.close || '--'}`;
  if (planSL) planSL.textContent = evalData.stop_loss ? `₹${evalData.stop_loss}` : "--";
  if (planTgt) planTgt.textContent = evalData.target_price ? `₹${evalData.target_price}` : "--";
  if (planRR) planRR.textContent = `RR 1:${evalData.risk_reward || 2}`;

  // Update SL and Target Lines on Chart
  if (slLine && candleSeries) candleSeries.removePriceLine(slLine);
  if (tgtLine && candleSeries) candleSeries.removePriceLine(tgtLine);

  if (evalData.stop_loss > 0 && candleSeries) {
    slLine = candleSeries.createPriceLine({
      price: evalData.stop_loss,
      color: "#ef4444",
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true,
      title: "STOP LOSS"
    });
  }

  if (evalData.target_price > 0 && candleSeries) {
    tgtLine = candleSeries.createPriceLine({
      price: evalData.target_price,
      color: "#10b981",
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true,
      title: "TARGET (1:2)"
    });
  }
}

function updateRuleItem(key, ruleObj, sideKey) {
  if (!ruleObj) return;
  const isPassed = ruleObj[sideKey];
  const badge = document.getElementById(`badge-${key}`);
  const icon = document.getElementById(`icon-${key}`);
  const detail = document.getElementById(`detail-${key}`);

  if (badge) {
    badge.textContent = isPassed ? "PASSED" : "WAITING";
    badge.className = isPassed
      ? "text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-bold font-mono border border-emerald-500/30"
      : "text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-mono";
  }

  if (icon) {
    icon.innerHTML = isPassed ? "✓" : "•";
    icon.className = isPassed
      ? "w-4 h-4 rounded-full bg-emerald-500 text-black font-extrabold flex items-center justify-center text-[10px]"
      : "w-4 h-4 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center text-[10px]";
  }

  if (detail && ruleObj.value) {
    detail.textContent = ruleObj.value;
  }
}

function formatVerdictText(verdict, side) {
  if (verdict === "BUY_SIGNAL") return "STRONG BUY (LONG) - ALL 5 RULES CONFIRMED!";
  if (verdict === "SELL_SIGNAL") return "STRONG SELL (SHORT) - ALL 5 RULES CONFIRMED!";
  if (verdict === "LONG_SETUP_BUILDING") return "LONG SETUP FORMING (4/5 RULES)";
  if (verdict === "SHORT_SETUP_BUILDING") return "SHORT SETUP FORMING (4/5 RULES)";
  if (verdict === "WAITING_PDH_PDL_BREAK") return "WAITING FOR PDH/PDL BREAKOUT";
  return "SCANNING INTRADAY CANDLES...";
}

// ================= WEBSOCKET REAL-TIME SYNC =================
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("[WS] Connected to Quant Pilot real-time feed");
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "SCANNER_UPDATE" || msg.type === "INITIAL_STATE") {
        updateScannerMatrix(msg.data.scanner);
        updatePortfolioUI(msg.data.portfolio);
      } else if (msg.type === "TRADE_ALERT") {
        playAlertChime();
        showNotification(msg.data.action, `Symbol: ${msg.data.symbol} | Entry: ₹${msg.data.entry}`);
      }
    } catch (e) {
      console.error("[WS] message error", e);
    }
  };

  ws.onclose = () => {
    console.log("[WS] Disconnected. Reconnecting in 3s...");
    setTimeout(connectWebSocket, 3000);
  };
}

function updateScannerMatrix(scannerList) {
  if (!scannerList) return;

  scannerList.forEach(item => {
    const sym = item.symbol;
    const cleanId = sym.replace(/:/g, "_").replace(/-/g, "_");
    const closeP = item.indicators ? item.indicators.close : 0;
    const verdict = item.verdict;
    const scores = item.scores || {};

    // 1. Update prices in sidebar and mobile carousel
    document.querySelectorAll(`.sym-price[data-sym="${sym}"]`).forEach(el => {
      if (closeP) el.textContent = `₹${closeP.toLocaleString('en-IN')}`;
    });
    document.querySelectorAll(`.sym-price-tag[data-sym="${sym}"]`).forEach(el => {
      if (closeP) el.textContent = `₹${closeP.toLocaleString('en-IN')}`;
    });

    // 2. Update verdict badges
    const card = document.getElementById(`card-${cleanId}`);
    if (card) {
      const vBadge = card.querySelector(".verdict-badge");
      const sBadge = card.querySelector(".score-badge");
      const pdhEl = card.querySelector(".pdh-val");
      const pdlEl = card.querySelector(".pdl-val");

      if (vBadge) {
        if (verdict === "BUY_SIGNAL") {
          vBadge.textContent = "BUY SIGNAL";
          vBadge.className = "verdict-badge text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 animate-pulse";
        } else if (verdict === "SELL_SIGNAL") {
          vBadge.textContent = "SELL SIGNAL";
          vBadge.className = "verdict-badge text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-500/40 animate-pulse";
        } else if (verdict.includes("BUILDING")) {
          vBadge.textContent = "SETUP FORMING";
          vBadge.className = "verdict-badge text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300";
        } else {
          vBadge.textContent = "SCANNING";
          vBadge.className = "verdict-badge text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-400";
        }
      }

      if (sBadge && scores.long_score) {
        sBadge.textContent = `${scores.long_score} Rules`;
      }

      if (pdhEl && item.indicators && item.indicators.pdh) {
        pdhEl.textContent = item.indicators.pdh;
      }
      if (pdlEl && item.indicators && item.indicators.pdl) {
        pdlEl.textContent = item.indicators.pdl;
      }
    }

    // If this is the active symbol, live refresh strategy view
    if (sym === currentSymbol) {
      renderStrategyBreakdown(item);
      const activeP = document.getElementById("activeCurrentPrice");
      if (activeP && closeP) activeP.textContent = `₹${closeP.toLocaleString('en-IN')}`;
    }
  });
}

// ================= PAPER TRADING & PORTFOLIO UI =================
async function fetchPortfolio() {
  try {
    const res = await fetch("/api/paper/portfolio");
    const data = await res.json();
    updatePortfolioUI(data.summary);
    renderOpenPositions(data.open_positions);
  } catch (e) {
    console.error("fetchPortfolio error", e);
  }
}

function updatePortfolioUI(summary) {
  if (!summary) return;
  const balEl = document.getElementById("portfolioBalance");
  const pnlEl = document.getElementById("portfolioRealizedPnl");

  if (balEl) balEl.textContent = `₹${summary.current_balance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  if (pnlEl) {
    const pnl = summary.realized_pnl || 0;
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}₹${pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    pnlEl.className = pnl >= 0 ? "font-bold font-mono text-emerald-400 text-sm" : "font-bold font-mono text-red-400 text-sm";
  }
}

function renderOpenPositions(positions) {
  const container = document.getElementById("openPositionsList");
  const countEl = document.getElementById("openPositionsCount");
  if (!container) return;

  if (countEl) countEl.textContent = positions ? positions.length : 0;

  if (!positions || positions.length === 0) {
    container.innerHTML = `<div class="text-center py-4 text-xs text-slate-500">No open positions. Scanner is searching...</div>`;
    return;
  }

  container.innerHTML = positions.map(pos => {
    const isProf = pos.unrealized_pnl >= 0;
    const pnlColor = isProf ? "text-emerald-400" : "text-red-400";
    return `
      <div class="p-2.5 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between">
        <div>
          <div class="flex items-center gap-1.5 font-bold text-xs text-white">
            <span class="px-1.5 py-0.5 rounded text-[10px] ${pos.side === 'LONG' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}">${pos.side}</span>
            <span>${pos.name}</span>
          </div>
          <div class="text-[10px] text-slate-400 mt-0.5">
            Qty: ${pos.quantity} | Entry: ₹${pos.entry_price} | SL: ₹${pos.stop_loss}
          </div>
        </div>
        <div class="text-right">
          <div class="font-mono font-bold text-xs ${pnlColor}">
            ${isProf ? '+' : ''}₹${pos.unrealized_pnl} (${pos.unrealized_pnl_pct}%)
          </div>
          <button onclick="squareOffPosition('${pos.symbol}')" class="mt-1 px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 font-semibold border border-slate-700 active:scale-95 transition">
            Square Off
          </button>
        </div>
      </div>
    `;
  }).join("");
}

async function placeManualTrade(side) {
  if (!currentCandleData || !currentCandleData.evaluation) {
    alert("Please wait for symbol data to load");
    return;
  }
  const evalData = currentCandleData.evaluation;
  try {
    const res = await fetch("/api/paper/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: currentSymbol,
        side: side,
        entry_price: evalData.entry_price,
        stop_loss: evalData.stop_loss,
        target_price: evalData.target_price
      })
    });
    const result = await res.json();
    if (res.ok) {
      playAlertChime();
      fetchPortfolio();
      alert(`Paper Order Executed: ${side} ${currentSymbol} at ₹${evalData.entry_price}`);
    } else {
      alert(`Order Failed: ${result.detail || 'Error'}`);
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}

async function squareOffPosition(symbol) {
  try {
    const res = await fetch("/api/paper/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol })
    });
    if (res.ok) {
      fetchPortfolio();
    }
  } catch (e) {
    console.error("squareOff error", e);
  }
}

async function resetPaperAccount() {
  if (!confirm("Reset Paper Trading Capital to ₹1,00,000?")) return;
  try {
    await fetch("/api/paper/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capital: 100000.0 })
    });
    fetchPortfolio();
  } catch (e) {
    console.error("reset error", e);
  }
}

// ================= AUDIO CHIME SYNTHESIZER (iOS Safari & Desktop) =================
function playAlertChime() {
  if (!isSoundEnabled) return;

  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!audioCtx) audioCtx = new AudioContext();
    if (audioCtx.state === 'suspended') audioCtx.resume();

    const now = audioCtx.currentTime;
    
    // Ascending melodic tri-tone chime
    const notes = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
    notes.forEach((freq, idx) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now + idx * 0.08);
      
      gain.gain.setValueAtTime(0.2, now + idx * 0.08);
      gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.08 + 0.3);
      
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      
      osc.start(now + idx * 0.08);
      osc.stop(now + idx * 0.08 + 0.3);
    });
  } catch (e) {
    console.warn("Audio synthesis error:", e);
  }
}

function toggleSound() {
  isSoundEnabled = !isSoundEnabled;
  const icon = document.getElementById("soundIcon");
  const btn = document.getElementById("soundToggleBtn");
  if (icon && btn) {
    if (isSoundEnabled) {
      icon.setAttribute("data-lucide", "volume-2");
      btn.className = "p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-emerald-400 transition";
      playAlertChime();
    } else {
      icon.setAttribute("data-lucide", "volume-x");
      btn.className = "p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-500 transition";
    }
    lucide.createIcons();
  }
}

function showNotification(title, body) {
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification(title, { body, icon: "/static/manifest.json" });
  }
}

// Request notification permission on first user interaction
document.body.addEventListener("click", () => {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
}, { once: true });

// ================= BROKER STATUS & SETTINGS MODAL =================
async function fetchBrokerStatus() {
  try {
    const res = await fetch("/api/broker/status");
    const data = await res.json();
    const dot = document.getElementById("brokerDot");
    const text = document.getElementById("brokerText");
    if (dot && text) {
      if (data.connected) {
        dot.className = "w-2 h-2 rounded-full bg-emerald-400";
        text.textContent = `Fyers: ${data.name || 'Live'}`;
      } else {
        dot.className = "w-2 h-2 rounded-full bg-slate-500";
        text.textContent = "Broker Offline";
      }
    }
  } catch (e) {
    console.error("Broker status error", e);
  }
}

function toggleTradingMode() {
  openSettingsModal();
}

function openSettingsModal() {
  const modal = document.getElementById("settingsModal");
  if (modal) modal.classList.remove("hidden");
  loadSettingsForm();
}

function closeSettingsModal() {
  const modal = document.getElementById("settingsModal");
  if (modal) modal.classList.add("hidden");
}

async function loadSettingsForm() {
  try {
    const res = await fetch("/api/settings");
    const cfg = await res.json();
    
    selectConfigMode(cfg.trading_mode || "PAPER");
    document.getElementById("cfgFyersClientId").value = cfg.fyers_client_id || "";
    document.getElementById("cfgFyersSecretKey").value = cfg.fyers_secret_key || "";
    document.getElementById("cfgFyersToken").value = cfg.fyers_access_token || "";
    document.getElementById("cfgSlMode").value = cfg.strategy.sl_mode || "prev_2_candles";
    document.getElementById("cfgRR").value = cfg.strategy.risk_reward_ratio || 2.0;
    document.getElementById("cfgRiskPct").value = cfg.strategy.risk_per_trade_percent || 1.0;
    document.getElementById("cfgTelegramToken").value = cfg.telegram_bot_token || "";
    document.getElementById("cfgTelegramChatId").value = cfg.telegram_chat_id || "";
  } catch (e) {
    console.error("loadSettingsForm error", e);
  }
}

function selectConfigMode(mode) {
  currentTradingMode = mode;
  const paperBtn = document.getElementById("cfgModePaper");
  const realBtn = document.getElementById("cfgModeReal");
  const modeLabel = document.getElementById("modeLabel");

  if (mode === "PAPER") {
    paperBtn.className = "py-2 px-3 rounded-lg border font-semibold border-emerald-500 bg-emerald-500/10 text-emerald-400";
    realBtn.className = "py-2 px-3 rounded-lg border font-semibold border-slate-700 bg-slate-800 text-slate-400";
    if (modeLabel) modeLabel.textContent = "PAPER TRADING";
  } else {
    realBtn.className = "py-2 px-3 rounded-lg border font-semibold border-emerald-500 bg-emerald-500/10 text-emerald-400";
    paperBtn.className = "py-2 px-3 rounded-lg border font-semibold border-slate-700 bg-slate-800 text-slate-400";
    if (modeLabel) modeLabel.textContent = "REAL TRADING (FYERS)";
  }
}

async function saveSettingsForm() {
  const payload = {
    trading_mode: currentTradingMode,
    fyers_client_id: document.getElementById("cfgFyersClientId").value.trim(),
    fyers_secret_key: document.getElementById("cfgFyersSecretKey").value.trim(),
    fyers_access_token: document.getElementById("cfgFyersToken").value.trim(),
    telegram_bot_token: document.getElementById("cfgTelegramToken").value.trim(),
    telegram_chat_id: document.getElementById("cfgTelegramChatId").value.trim(),
    strategy: {
      sl_mode: document.getElementById("cfgSlMode").value,
      risk_reward_ratio: parseFloat(document.getElementById("cfgRR").value) || 2.0,
      risk_per_trade_percent: parseFloat(document.getElementById("cfgRiskPct").value) || 1.0
    }
  };

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      closeSettingsModal();
      fetchBrokerStatus();
      alert("Settings saved successfully!");
    } else {
      const err = await res.json();
      alert(`Save error: ${err.detail || 'Unknown error'}`);
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}

async function openFyersLogin() {
  try {
    const res = await fetch("/api/broker/login-url");
    const data = await res.json();
    if (data.login_url) {
      window.open(data.login_url, "_blank");
      const authCode = prompt("After logging in, paste the authorization code from the redirected URL:");
      if (authCode) {
        const tokenRes = await fetch("/api/broker/authcode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ auth_code: authCode })
        });
        const tokenData = await tokenRes.json();
        if (tokenData.status === "SUCCESS") {
          alert("Fyers connected successfully!");
          fetchBrokerStatus();
        } else {
          alert(`Fyers auth failed: ${tokenData.message}`);
        }
      }
    }
  } catch (e) {
    alert(`Login error: ${e.message}`);
  }
}

// ================= MOBILE NAVIGATION TABS (iPhone Safari) =================
function switchMobileTab(tab) {
  document.querySelectorAll(".mobile-tab").forEach(el => {
    el.classList.remove("text-emerald-400");
    el.classList.add("text-slate-400");
  });
  const activeTab = document.getElementById(`tab-${tab}`);
  if (activeTab) {
    activeTab.classList.remove("text-slate-400");
    activeTab.classList.add("text-emerald-400");
  }

  // Scroll or focus view accordingly
  if (tab === "chart") {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (tab === "rules") {
    const rulesEl = document.querySelector(".rule-box");
    if (rulesEl) rulesEl.scrollIntoView({ behavior: 'smooth' });
  } else if (tab === "trades") {
    const portEl = document.getElementById("portfolioBalance");
    if (portEl) portEl.scrollIntoView({ behavior: 'smooth' });
  } else if (tab === "settings") {
    openSettingsModal();
  }
}
