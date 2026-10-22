// Coin Lab 화면 (F2013). 서버의 JSON API만 호출하며 API 키는 다루지 않는다.
// 서버가 없으면 web/sample/coins_sample.js 로 샘플 모드(조회·키워드 탐색만)로 동작한다.

const state = {
  coins: [],
  byId: new Map(),
  coinId: "",
  category: "all",
  query: "",
  timeframe: "7d",
  histories: loadHistories(), // {coin_id: [{role, content, sources, cited}]}
  busy: false,
  homeShown: 24, // 메인 코인 리스트에 보여 줄 개수
  offline: false,
  disclaimer: "",
};

const $ = (id) => document.getElementById(id);
const DEFAULT_DISCLAIMER =
  "이 서비스의 답변은 수집된 문서를 요약한 정보이며 투자 조언이 아닙니다. 가상자산은 가격 변동과 원금 손실 위험이 크므로 투자 판단은 본인 책임하에 전문가 상담을 거쳐 결정하세요.";

// 카테고리 필터: CoinGecko categories 문자열로 판정
const CATEGORIES = [
  ["all", "전체", () => true],
  ["l1", "L1", (c) => has(c, /Layer 1/)],
  ["stable", "스테이블", (c) => has(c, /Stablecoin/)],
  ["defi", "DeFi", (c) => has(c, /Decentralized Finance|DEX/)],
  ["meme", "밈", (c) => has(c, /^Meme$|Meme/)],
  ["rwa", "RWA", (c) => has(c, /Real World Assets|Tokenized/)],
  ["docs", "위키 문서", (c) => Boolean(c.kowiki_title || c.enwiki_title)],
];
const has = (coin, re) => (coin.categories || []).some((x) => re.test(x));

// 메인 화면 예시 질문: 근거 없이 답하면 틀리기 쉬운 질문 (docs/plan.md 1-1)
const EXAMPLES = [
  ["bitcoin", "비트코인의 발행량 상한과 반감기는 어떻게 되나요?"],
  ["ethereum", "이더리움은 언제, 어떤 방식으로 지분증명으로 바뀌었나요?"],
  ["solana", "솔라나는 어떤 방식으로 빠른 처리 속도를 내나요?"],
  ["ripple", "리플(XRP)은 미국 SEC와 어떤 소송을 겪었나요?"],
];

// 저장
function loadHistories() {
  try {
    return JSON.parse(localStorage.getItem("coinlab.histories") || "{}");
  } catch {
    return {};
  }
}

function saveHistories() {
  try {
    localStorage.setItem("coinlab.histories", JSON.stringify(state.histories));
  } catch {
    /* 저장이 막혀 있으면 이번 세션 동안만 유지한다 */
  }
}

function chatHistory(coinId) {
  if (!state.histories[coinId]) state.histories[coinId] = [];
  return state.histories[coinId];
}

// API
async function api(path, options = {}) {
  if (state.offline) throw new Error("서버가 연결되지 않은 샘플 모드입니다. 서버를 실행한 뒤 이용하세요.");
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    /* 본문이 JSON이 아닌 오류 */
  }
  if (!response.ok) {
    // 서버가 준 사용자용 문장만 보여주고, 추적 정보는 표시하지 않는다. (NF2004)
    const detail = data && typeof data.detail === "string" ? data.detail : "요청을 처리하지 못했습니다.";
    throw new Error(detail);
  }
  return data;
}

const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });

// 작은 DOM 도우미 (텍스트는 항상 textContent 로 넣는다)
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function link(text, url) {
  if (!url || !/^https?:\/\//.test(url)) return null;
  const a = el("a", "", text);
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function hue(symbol) {
  let h = 0;
  for (const ch of symbol || "?") h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

// CoinGecko 로고 URL 을 바로 불러오고, 없거나 실패하면 심볼 첫 글자로 대체한다.
function fillIcon(node, coin) {
  node.replaceChildren();
  node.classList.remove("has-logo");
  node.style.setProperty("--h", hue(coin.symbol));
  node.setAttribute("aria-hidden", "true");
  const letter = () => {
    node.classList.remove("has-logo");
    node.replaceChildren(document.createTextNode([...(coin.symbol || "?")][0]));
  };
  if (!coin.image || !/^https:\/\//.test(coin.image)) return letter();
  const img = document.createElement("img");
  img.src = coin.image;
  img.alt = "";
  img.loading = "lazy";
  img.decoding = "async";
  img.referrerPolicy = "no-referrer";
  img.addEventListener("error", letter, { once: true });
  node.classList.add("has-logo");
  node.appendChild(img);
}

function icon(coin, cls) {
  const node = el("div", cls);
  fillIcon(node, coin);
  return node;
}

// 한국 시간 표시
const KST_FORMAT = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function kst(value, style = "full") {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const p = Object.fromEntries(KST_FORMAT.formatToParts(date).map((x) => [x.type, x.value]));
  if (style === "md") return `${p.month}.${p.day}`;
  if (style === "hm") return `${p.hour}:${p.minute}`;
  if (style === "mdhm") return `${p.month}.${p.day} ${p.hour}:${p.minute}`;
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} KST`;
}

// 숫자 표시
function usd(value) {
  if (value == null) return "-";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1) return `$${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  return `$${Number(value).toPrecision(4)}`;
}

function amount(value) {
  if (value == null) return "-";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

// 색과 함께 ▲▼ 기호로 방향을 표시한다
function change(value) {
  if (value == null) return { text: "—", cls: "flat" };
  const cls = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const mark = value > 0 ? "▲" : value < 0 ? "▼" : "■";
  return { text: `${mark} ${Math.abs(value).toFixed(2)}%`, cls };
}

// 안전한 마크다운 표시
function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function inline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/[\[［]\s*근거[^\]］<]*[\]］]/g, (match) => `<span class="cite">${match}</span>`);
}

function renderMarkdown(markdown) {
  const lines = escapeHtml(markdown).split(/\r?\n/);
  const html = [];
  let list = false;
  let paragraph = [];
  const flush = () => {
    if (paragraph.length) html.push(`<p>${inline(paragraph.join("<br>"))}</p>`);
    paragraph = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    const bullet = line.match(/^[-*]\s+(.*)$/);
    if (!bullet && list) {
      html.push("</ul>");
      list = false;
    }
    if (!line) {
      flush();
    } else if (/^#{1,4}\s+/.test(line)) {
      flush();
      html.push(`<h4>${inline(line.replace(/^#{1,4}\s+/, ""))}</h4>`);
    } else if (bullet) {
      flush();
      if (!list) {
        html.push("<ul>");
        list = true;
      }
      html.push(`<li>${inline(bullet[1])}</li>`);
    } else {
      paragraph.push(line);
    }
  }
  flush();
  if (list) html.push("</ul>");
  return html.join("");
}

// 근거 목록 (F2008 · F2016)
function mergeSources(sources) {
  const merged = new Map();
  for (const source of sources) {
    const key = `${source.title}|${source.source_type}|${source.url}|${source.page ?? ""}`;
    if (!merged.has(key)) merged.set(key, { ...source, indexes: [] });
    merged.get(key).indexes.push(source.index);
  }
  return [...merged.values()];
}

function sourcesElement(message) {
  const sources = message.sources || [];
  const cited = typeof message.cited === "boolean" ? message.cited : /[\[［]\s*근거\s*\d/.test(message.content);
  if (!cited || !sources.length) return el("p", "caption", "ⓘ 답변에 인용된 근거가 없습니다.");
  const documents = mergeSources(sources);
  const box = el("details", "sources");
  box.open = true;
  box.appendChild(el("summary", "", `답변에 사용한 근거 ${documents.length}건`));
  const list = el("ul");
  for (const doc of documents) {
    const item = el("li");
    const numbers = doc.indexes.filter((n) => n != null).sort((a, b) => a - b).join(", ");
    item.appendChild(el("b", "", numbers ? `[근거 ${numbers}] ` : ""));
    item.appendChild(document.createTextNode(doc.title));
    item.appendChild(el("span", `badge ${doc.source_type || ""}`, doc.source_label));
    if (doc.page) item.appendChild(document.createTextNode(` p.${doc.page}`));
    const a = link("원문 ↗", doc.url);
    if (a) item.appendChild(a);
    list.appendChild(item);
  }
  box.appendChild(list);
  return box;
}

// 대화
function messageElement(message) {
  const box = el("div", `message ${message.role === "user" ? "user" : "assistant"}`);
  box.appendChild(el("div", "role", message.role === "user" ? "YOU" : "COIN LAB"));
  const body = el("div");
  if (message.role === "user") body.textContent = message.content;
  else body.innerHTML = renderMarkdown(message.content); // escapeHtml 을 먼저 거친다
  box.appendChild(body);
  if (message.role === "assistant") {
    box.appendChild(sourcesElement(message));
    box.appendChild(el("p", "answer-disclaimer", "⚠ 투자 조언이 아닙니다 · 문서 근거 요약"));
  }
  return box;
}

// 메인 화면(코인 미선택)에서는 왼쪽 코인 목록·오른쪽 정보를 숨긴다
function updateLayout() {
  document.querySelector(".app").classList.toggle("home-mode", !state.coinId);
}

function renderChat() {
  updateLayout();
  const hasCoin = Boolean(state.coinId);
  $("welcome").classList.toggle("hidden", hasCoin);
  $("coin-card").classList.toggle("hidden", !hasCoin);
  $("chat-view").classList.toggle("hidden", !hasCoin);
  const container = $("messages");
  container.replaceChildren();
  if (!hasCoin) return;
  if (state.offline) {
    container.appendChild(el("div", "notice warn", "샘플 모드입니다. 질의응답·브리핑·팩트체크는 서버(python -m src.server)를 실행해야 동작합니다."));
  }
  const items = chatHistory(state.coinId);
  if (!items.length && !state.offline) {
    container.appendChild(el("p", "caption", "첫 질문을 하면 관련 문서를 수집한 뒤 근거와 함께 답합니다."));
  }
  for (const message of items) container.appendChild(messageElement(message));
  $("clear-button").classList.toggle("hidden", !items.length);
  scrollMessages();
}

// 메시지 영역만 맨 아래로 (페이지 전체는 움직이지 않음)
function scrollMessages() {
  const container = $("messages");
  container.scrollTop = container.scrollHeight;
}

function renderTalking() {
  const talking = Object.entries(state.histories).filter(([, items]) => items.length);
  $("talking-box").classList.toggle("hidden", !talking.length);
  const list = $("talking-list");
  list.replaceChildren();
  for (const [coinId, items] of talking) {
    const asked = items.filter((m) => m.role === "user").length;
    const current = coinId === state.coinId;
    const item = el("li", current ? "current" : "", `${current ? "▶" : "·"} ${state.byId.get(coinId)?.label || coinId} (${asked}문답)`);
    item.addEventListener("click", () => selectCoin(coinId));
    list.appendChild(item);
  }
}

function showError(text) {
  $("messages").appendChild(el("div", "notice error", text));
  scrollMessages();
}

function setBusy(busy, text = "") {
  state.busy = busy;
  $("progress").classList.toggle("hidden", !busy);
  $("progress-text").textContent = text;
  for (const id of ["chat-input", "send-button", "brief-button", "factcheck-button"]) $(id).disabled = busy;
  if (!busy) updateFeatureButtons();
}

function updateFeatureButtons() {
  const off = !state.coinId;
  $("brief-button").disabled = off;
  $("factcheck-button").disabled = off;
}

// 왼쪽 목록
function renderPills() {
  const box = $("category-pills");
  box.replaceChildren();
  for (const [key, name, test] of CATEGORIES) {
    const count = state.coins.filter(test).length;
    if (key !== "all" && !count) continue;
    const pill = el("button", "pill", `${name} ${count}`);
    pill.type = "button";
    pill.setAttribute("role", "tab");
    pill.setAttribute("aria-selected", String(state.category === key));
    pill.addEventListener("click", () => {
      state.category = key;
      renderPills();
      renderRail();
    });
    box.appendChild(pill);
  }
}

function renderRail() {
  const test = (CATEGORIES.find(([key]) => key === state.category) || CATEGORIES[0])[2];
  const list = $("coin-rail");
  list.replaceChildren();
  const q = state.query;
  const match = (c) => !q || [c.symbol, c.name, c.name_ko, c.coin_id].some((x) => x && x.toLowerCase().includes(q));
  const shown = state.coins.filter((c) => test(c) && match(c));
  if (!shown.length) list.appendChild(el("li", "caption", q ? "일치하는 코인이 없습니다. Enter 로 조건 탐색을 해 보세요." : "해당 카테고리에 코인이 없습니다."));
  for (const coin of shown) {
    const row = el("li", `coin-row${coin.coin_id === state.coinId ? " active" : ""}`);
    row.tabIndex = 0;
    row.setAttribute("aria-label", coin.label);
    const name = el("span", "nm");
    name.append(el("span", "sym", coin.symbol), el("span", "full", coin.name_ko || coin.name));
    const c = change(coin.market?.change_24h_pct);
    row.append(el("span", "rk", coin.market_cap_rank ?? "-"), icon(coin, "mini-icon"), name, el("span", `chg ${c.cls}`, c.text));
    row.addEventListener("click", () => selectCoin(coin.coin_id));
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectCoin(coin.coin_id);
      }
    });
    list.appendChild(row);
  }
}

// 코인 위젯
function renderCoinCard(coin) {
  const m = coin.market || {};
  fillIcon($("coin-icon"), coin);
  $("coin-symbol").textContent = coin.symbol;
  $("coin-title").textContent = coin.name_ko ? `${coin.name} · ${coin.name_ko}` : coin.name;
  $("coin-rank").textContent = `#${coin.market_cap_rank ?? "-"}`;
  $("coin-price").textContent = usd(m.current_price_usd);
  const key = { "24h": "change_24h_pct", "7d": "change_7d_pct", "30d": "change_30d_pct" }[state.timeframe];
  const c = change(m[key]);
  $("coin-delta").className = `delta ${c.cls}`;
  $("coin-delta").textContent = `${c.text} · ${state.timeframe.toUpperCase()}`;
  for (const tab of $("tf-tabs").querySelectorAll("button")) tab.setAttribute("aria-selected", String(tab.dataset.tf === state.timeframe));
  renderChart(m);

  const stats = $("coin-stats");
  stats.replaceChildren();
  const supply = m.max_supply ? `${amount(m.circulating_supply)} / ${amount(m.max_supply)}` : amount(m.circulating_supply);
  for (const [label, value, sub] of [
    ["시가총액", usd(m.market_cap_usd), ""],
    ["24H 거래량", usd(m.total_volume_usd), ""],
    ["유통 / 최대", supply, m.max_supply ? "" : "최대 공급량 없음"],
    ["ATH", usd(m.ath_usd), m.ath_date || ""],
  ]) {
    const cell = el("div", "stat");
    cell.append(el("span", "", label), el("b", "", value));
    if (sub) cell.appendChild(el("small", "", sub));
    stats.appendChild(cell);
  }
  $("coin-snapshot").textContent = coin.snapshot_at ? `기준 ${kst(coin.snapshot_at)}` : "";
}

// 차트 데이터: CoinGecko 7일 시간별 가격(sparkline)을 쓰고,
// 30D 이거나 sparkline 이 없으면 변동률(24H·7D·30D)로 과거 가격을 역산한 추정치를 쓴다.
function chartSeries(m, tf) {
  const spark = Array.isArray(m.sparkline_7d) ? m.sparkline_7d.filter((v) => v != null) : [];
  const end = Date.parse(m.last_updated || "") || Date.now();
  if (tf !== "30d" && spark.length >= 2) {
    const values = tf === "24h" ? spark.slice(-25) : spark;
    const n = values.length;
    return {
      estimated: false,
      points: values.map((value, i) => ({ value, t: end - (n - 1 - i) * 3600e3 })),
    };
  }
  const price = m.current_price_usd;
  if (price == null) return { estimated: true, points: [] };
  const back = [[30, m.change_30d_pct], [7, m.change_7d_pct], [1, m.change_24h_pct]]
    .filter(([days, pct]) => pct != null && pct > -100 && (tf === "30d" || days <= (tf === "7d" ? 7 : 1)))
    .map(([days, pct]) => ({ value: price / (1 + pct / 100), t: end - days * 86400e3 }));
  return { estimated: true, points: [...back, { value: price, t: end }] };
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function renderChart(m) {
  const box = $("chart");
  box.replaceChildren();
  const tf = state.timeframe;
  const { estimated, points } = chartSeries(m, tf);
  $("chart-note").textContent = !points.length
    ? ""
    : estimated
      ? `${tf === "30d" ? "30일" : "시간별 데이터가 없어"} 차트는 CoinGecko 변동률로 역산한 추정치입니다 · 한국 시간`
      : `CoinGecko 시간별 가격 (최근 ${tf === "24h" ? "24시간" : "7일"}) · 한국 시간`;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  const W = Math.max(280, box.clientWidth || 640), H = 200, PX = 28, PT = 18, PB = 28;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  if (points.length < 2) {
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", W / 2);
    t.setAttribute("y", H / 2);
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("class", "empty");
    t.textContent = "가격 데이터가 없습니다";
    svg.appendChild(t);
    box.appendChild(svg);
    return;
  }
  const values = points.map((p) => p.value);
  const lo = Math.min(...values), hi = Math.max(...values);
  const span = hi - lo || hi * 0.01 || 1;
  const t0 = points[0].t, t1 = points[points.length - 1].t;
  const xy = points.map((p, i) => ({
    ...p,
    x: estimated ? PX + (i * (W - PX * 2)) / (points.length - 1) : PX + ((p.t - t0) / (t1 - t0 || 1)) * (W - PX * 2),
    y: PT + (1 - (p.value - lo) / span) * (H - PT - PB),
  }));
  const rising = xy[xy.length - 1].value >= xy[0].value;
  const color = cssVar(rising ? "--acid-ink" : "--pink") || (rising ? "#4d7c00" : "#d0175a");
  const fmt = tf === "24h" ? "hm" : "md";
  svg.setAttribute("aria-label", `가격 변화(${tf.toUpperCase()}): 시작 ${usd(xy[0].value)}, 최저 ${usd(lo)}, 최고 ${usd(hi)}, 현재 ${usd(xy[xy.length - 1].value)}`);

  const defs = document.createElementNS(NS, "defs");
  defs.innerHTML = `
    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${color}" stop-opacity="0.22"/>
      <stop offset="1" stop-color="${color}" stop-opacity="0"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`;
  svg.appendChild(defs);

  // 축 눈금: 추정치는 모든 점, 시간별 데이터는 5개 정도
  const ticks = estimated ? xy : [0, 0.25, 0.5, 0.75, 1].map((r) => xy[Math.round(r * (xy.length - 1))]);
  for (const p of ticks) {
    const g = document.createElementNS(NS, "line");
    g.setAttribute("x1", p.x); g.setAttribute("x2", p.x); g.setAttribute("y1", PT - 6); g.setAttribute("y2", H - PB);
    g.setAttribute("class", "grid");
    svg.appendChild(g);
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", p.x); t.setAttribute("y", H - 8);
    t.setAttribute("text-anchor", p === ticks[0] ? "start" : p === ticks[ticks.length - 1] ? "end" : "middle");
    t.setAttribute("class", "axis");
    t.textContent = p === xy[xy.length - 1] ? "현재" : kst(p.t, fmt);
    svg.appendChild(t);
  }

  let d = `M${xy[0].x},${xy[0].y}`;
  if (xy.length <= 6) {
    for (let i = 0; i < xy.length - 1; i++) {
      const p0 = xy[i - 1] || xy[i], p1 = xy[i], p2 = xy[i + 1], p3 = xy[i + 2] || p2;
      d += ` C${p1.x + (p2.x - p0.x) / 6},${p1.y + (p2.y - p0.y) / 6} ${p2.x - (p3.x - p1.x) / 6},${p2.y - (p3.y - p1.y) / 6} ${p2.x},${p2.y}`;
    }
  } else {
    for (const p of xy.slice(1)) d += ` L${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }
  const area = document.createElementNS(NS, "path");
  area.setAttribute("d", `${d} L${xy[xy.length - 1].x},${H - PB} L${xy[0].x},${H - PB} Z`);
  area.setAttribute("fill", "url(#fill)");
  svg.appendChild(area);
  const line = document.createElementNS(NS, "path");
  line.setAttribute("d", d);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", color);
  line.setAttribute("stroke-width", "2.2");
  line.setAttribute("stroke-linejoin", "round");
  if (document.documentElement.dataset.theme === "dark") line.setAttribute("filter", "url(#glow)");
  if (estimated) line.setAttribute("stroke-dasharray", "6 5");
  svg.appendChild(line);

  const last = xy[xy.length - 1];
  const halo = document.createElementNS(NS, "circle");
  halo.setAttribute("cx", last.x); halo.setAttribute("cy", last.y); halo.setAttribute("r", "6");
  halo.setAttribute("fill", color); halo.setAttribute("opacity", "0.4");
  halo.innerHTML = '<animate attributeName="r" values="6;12;6" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.4;0;0.4" dur="2s" repeatCount="indefinite"/>';
  svg.appendChild(halo);
  for (const p of estimated ? xy : [last]) {
    const dot = document.createElementNS(NS, "circle");
    dot.setAttribute("cx", p.x); dot.setAttribute("cy", p.y);
    dot.setAttribute("r", p === last ? "5" : "3.5");
    dot.setAttribute("fill", p === last ? color : cssVar("--surface"));
    dot.setAttribute("stroke", color);
    dot.setAttribute("stroke-width", "2");
    svg.appendChild(dot);
  }
  const cursor = document.createElementNS(NS, "circle");
  cursor.setAttribute("r", "4");
  cursor.setAttribute("fill", color);
  cursor.setAttribute("visibility", "hidden");
  svg.appendChild(cursor);
  box.appendChild(svg);

  // 호버: 가장 가까운 점의 가격·한국 시간
  const tip = el("div", "tip hidden");
  box.appendChild(tip);
  box.onmousemove = (e) => {
    const r = box.getBoundingClientRect();
    const sx = ((e.clientX - r.left) / r.width) * W;
    const p = xy.reduce((a, b) => (Math.abs(b.x - sx) < Math.abs(a.x - sx) ? b : a));
    tip.replaceChildren(document.createTextNode(usd(p.value)), el("small", "", `${kst(p.t, "mdhm")}${estimated ? " (추정)" : ""}`));
    tip.style.left = `${(p.x / W) * 100}%`;
    tip.style.top = `${(p.y / H) * 100}%`;
    tip.classList.remove("hidden");
    cursor.setAttribute("cx", p.x);
    cursor.setAttribute("cy", p.y);
    cursor.setAttribute("visibility", "visible");
  };
  box.onmouseleave = () => {
    tip.classList.add("hidden");
    cursor.setAttribute("visibility", "hidden");
  };
}

// 오른쪽 정보
function renderCoinInfo(coin) {
  const meta = $("coin-meta");
  meta.replaceChildren();
  for (const [k, v] of [
    ["코인", coin.label],
    ["출시", coin.genesis_date],
    ["알고리즘", coin.hashing_algorithm],
    ["플랫폼", coin.asset_platform_id],
  ]) {
    if (!v) continue;
    const row = el("div");
    row.append(el("dt", "", k), el("dd", "", v));
    meta.appendChild(row);
  }
  const chips = $("coin-categories");
  chips.replaceChildren();
  const cats = (coin.categories || []).filter((c) => !/Portfolio|Index|Ecosystem|Holdings|Made in/.test(c));
  for (const c of cats.slice(0, 8)) chips.appendChild(el("span", "chip", c));
  if (!coin.categories?.length) chips.appendChild(el("span", "chip", "카테고리 미수집"));

  const links = $("coin-links");
  links.replaceChildren();
  for (const [name, url] of [["홈페이지", coin.homepage], ["백서", coin.whitepaper], ["GitHub", coin.github]]) {
    const a = link(`${name} ↗`, url);
    if (a) links.appendChild(a);
  }
  const docs = coin.doc_titles || [coin.kowiki_title && `위키백과(ko) ${coin.kowiki_title}`, coin.enwiki_title && `Wikipedia(en) ${coin.enwiki_title}`].filter(Boolean);
  $("coin-docs").textContent = docs.length ? docs.join("\n") : "연결된 위키 문서가 없습니다. 첫 질문 때 검색해 수집합니다.";
}

// 코인 선택 (F2009)
// push: 브라우저 뒤로가기용 주소 기록 (뒤로가기로 들어온 경우 false)
async function selectCoin(coinId, push = true) {
  if (push && state.coinId !== coinId) history.pushState({ coin: coinId, inApp: true }, "", `?coin=${encodeURIComponent(coinId)}`);
  state.coinId = coinId;
  $("recommend-view").classList.add("hidden");
  renderRail();
  renderChat();
  renderTalking();
  updateFeatureButtons();
  const local = state.byId.get(coinId);
  if (local) {
    renderCoinCard(local);
    renderCoinInfo(local);
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
  document.querySelector(".stage").scrollTo({ top: 0 }); // 넓은 화면은 무대만 스크롤된다
  await refreshCoinInfo(coinId);
}

// 로고: 메인(환영) 화면으로. 대화 기록은 그대로 둔다
function goHome(push = true) {
  if (push && state.coinId) history.pushState({ coin: "", inApp: true }, "", location.pathname);
  state.coinId = "";
  $("home-input").value = "";
  renderSuggest("");
  $("recommend-view").classList.add("hidden");
  renderRail();
  renderChat();
  renderTalking();
  updateFeatureButtons();
  $("coin-meta").replaceChildren(el("div"));
  $("coin-meta").firstChild.append(el("dt", "", "코인"), el("dd", "", "선택되지 않음"));
  for (const id of ["coin-categories", "coin-links"]) $(id).replaceChildren();
  $("coin-docs").textContent = "—";
  window.scrollTo({ top: 0 });
  document.querySelector(".stage").scrollTo({ top: 0 });
}

// 서버의 최신 정보(수집된 문서 목록 포함)로 오른쪽 정보를 다시 그린다
async function refreshCoinInfo(coinId) {
  if (state.offline) return;
  try {
    const coin = await api(`/api/coins/${encodeURIComponent(coinId)}`);
    if (coinId !== state.coinId) return;
    const merged = { ...state.byId.get(coinId), ...coin };
    state.byId.set(coinId, merged);
    renderCoinInfo(merged);
  } catch (error) {
    $("coin-docs").textContent = error.message;
  }
}

// 질의응답 (F2007 · F2012)
async function ask(question) {
  const coinId = state.coinId;
  const messages = chatHistory(coinId);
  messages.push({ role: "user", content: question });
  renderChat();
  renderTalking();
  $("chat-form").scrollIntoView({ block: "nearest" }); // 입력창·진행 표시가 보이도록 (넓은 화면에서는 무대만 스크롤)
  try {
    setBusy(true, "관련 위키백과·백서 문서를 확인하는 중…");
    const collected = await post(`/api/coins/${encodeURIComponent(coinId)}/collect`, { question });
    const added = collected.added_titles.length;
    setBusy(true, `${added ? `문서 ${added}건 추가 (${collected.added_titles.slice(0, 3).join(", ")})` : `수집된 문서 ${collected.titles.length}건 사용`} · 근거 검색·답변 생성 중…`);
    const result = await post("/api/ask", { coin_id: coinId, question });
    messages.push({ role: "assistant", content: result.answer, sources: result.sources, cited: result.cited });
    saveHistories();
    if (coinId === state.coinId) {
      renderChat();
      refreshCoinInfo(coinId);
    }
  } catch (error) {
    messages.pop();
    renderChat();
    showError(`답변을 만들지 못했습니다. ${error.message}`);
  } finally {
    setBusy(false);
    renderTalking();
  }
}

// 도메인 특화 기능 (F2010)
async function runFeature(kind, claim = "") {
  const coinId = state.coinId;
  if (!coinId || state.busy) return;
  if (kind === "factcheck") chatHistory(coinId).push({ role: "user", content: `팩트체크: ${claim}` });
  renderChat();
  try {
    setBusy(true, kind === "brief" ? "관련 문서를 확인하고 리스크 브리핑을 작성하는 중…" : "주장을 문서 근거와 대조하는 중…");
    await post(`/api/coins/${encodeURIComponent(coinId)}/collect`, { question: claim });
    const result = await post(`/api/coins/${encodeURIComponent(coinId)}/${kind}`, { claim });
    chatHistory(coinId).push({ role: "assistant", content: result.answer, sources: result.sources, cited: result.cited });
    saveHistories();
    if (coinId === state.coinId) {
      renderChat();
      refreshCoinInfo(coinId);
    }
  } catch (error) {
    if (kind === "factcheck") chatHistory(coinId).pop();
    renderChat();
    showError(`${kind === "brief" ? "브리핑" : "팩트체크"}을(를) 만들지 못했습니다. ${error.message}`);
  } finally {
    setBusy(false);
    renderTalking();
  }
}

// 조건 기반 탐색 (F2011)
function offlineFilter(query) {
  // 샘플 모드 전용 키워드 일치 (서버 모드는 벡터 검색 + LLM 선별)
  const words = query.toLowerCase().split(/[\s,]+/).filter((w) => w.length >= 2);
  return state.coins
    .map((c) => {
      const hay = [c.name, c.symbol, c.name_ko, ...(c.categories || []), c.description_ko, c.description_en].join(" ").toLowerCase();
      const hits = words.filter((w) => hay.includes(w));
      return { coin: c, hits };
    })
    .filter((s) => s.hits.length)
    .sort((a, b) => b.hits.length - a.hits.length || (a.coin.market_cap_rank ?? 9999) - (b.coin.market_cap_rank ?? 9999))
    .slice(0, 9)
    .map((s) => ({ ...s.coin, reason: `일치한 키워드: ${s.hits.join(", ")}` }));
}

async function findCoins(query) {
  $("welcome").classList.add("hidden");
  $("coin-card").classList.add("hidden");
  $("chat-view").classList.add("hidden");
  $("recommend-view").classList.remove("hidden");
  $("recommend-title").textContent = `“${query}”`;
  $("recommend-caption").textContent = state.offline
    ? "샘플 모드: 키워드가 일치하는 코인만 보여줍니다. (서버 모드에서는 의미 검색 후 LLM이 조건에 맞는 코인만 고릅니다.)"
    : "코인 메타데이터 색인에서 후보를 찾고 조건에 맞는 것만 골랐습니다. 고르면 그 코인의 대화가 시작됩니다.";
  const results = $("recommend-results");
  results.replaceChildren();
  const waiting = el("div", "progress");
  waiting.append(el("span", "spinner"), document.createTextNode("코인을 찾는 중…"));
  results.appendChild(waiting);

  try {
    const list = state.offline ? offlineFilter(query) : (await post("/api/recommend", { query })).results;
    results.replaceChildren();
    if (!list.length) results.appendChild(el("div", "notice info", "조건에 맞는 코인을 찾지 못했습니다. 다른 표현으로 다시 찾아보세요."));
    for (const coin of list) {
      const local = state.byId.get(coin.coin_id) || coin;
      const card = el("article", "card result-card");
      const top = el("div", "top");
      const title = el("div");
      title.append(el("h3", "", `${local.symbol} · ${local.name}`), el("span", "caption", `#${local.market_cap_rank ?? "-"}`));
      top.append(icon(local, "mini-icon"), title);
      const button = el("button", "btn-acid small", "이 코인 질문하기 →");
      button.type = "button";
      button.addEventListener("click", () => selectCoin(coin.coin_id));
      card.append(top, el("p", "", (local.categories || []).slice(0, 3).join(" · ") || "카테고리 미수집"), el("p", "", coin.reason || ""), button);
      results.appendChild(card);
    }
  } catch (error) {
    results.replaceChildren(el("div", "notice error", `코인을 찾지 못했습니다. ${error.message}`));
  }
}

function backFromResults() {
  $("recommend-view").classList.add("hidden");
  renderChat();
}

// 시작
function useSample(reason) {
  state.offline = true;
  const sample = window.COIN_SAMPLE;
  const coins = sample?.coins || [];
  $("status-chip").classList.add("offline");
  $("index-status").textContent = `SAMPLE MODE · ${coins.length} coins · ${sample?.generated_at ? kst(sample.generated_at, "mdhm") : "-"} KST`;
  const warnings = [reason];
  if (!coins.length) warnings.push("샘플 데이터도 없습니다. python -m scripts.build_web_sample 을 실행하세요.");
  $("setup-warning").textContent = warnings.join(" ");
  $("setup-warning").classList.remove("hidden");
  return coins;
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    state.disclaimer = status.disclaimer || "";
    const idx = status.indexes;
    $("index-status").textContent = `INDEX · ${idx.coin_meta} coins · ${idx.coin_docs} chunks · ${status.chat_model}`;
    const warnings = [];
    if (!status.api_key) warnings.push("GMS_KEY가 설정되지 않았습니다. .env를 확인하세요.");
    if (status.contact === false) warnings.push("CONTACT_EMAIL이 없어 질문할 때 위키 문서를 새로 수집하지 않습니다. .env에 이메일을 넣으세요.");
    if (!idx.coin_meta) warnings.push("코인 색인이 없습니다. python -m scripts.index_coins 를 실행하세요.");
    if (!idx.coin_docs) warnings.push("문서 색인이 비어 있어 사실 질문이 '문서로 확인 불가'로 나옵니다. python -m scripts.index_docs 를 실행하세요.");
    $("setup-warning").textContent = warnings.join(" ");
    $("setup-warning").classList.toggle("hidden", !warnings.length);
    return true;
  } catch {
    return false;
  }
}

function setCoins(coins) {
  state.coins = coins.map((c) => ({ ...c, label: c.label || `${c.name} (${c.symbol})${c.name_ko ? " · " + c.name_ko : ""}` }));
  for (const coin of state.coins) state.byId.set(coin.coin_id, coin);
  renderPills();
  renderRail();
  renderCoinGrid();
  renderExamples();
}

// 메인 코인 리스트: 시가총액 순, "더 보기"로 PAGE 개씩
const PAGE = 24;
const LIST_COLS = [["#", ""], ["코인", ""], ["가격", ""], ["24H", ""], ["7D", "hide-sm"], ["시가총액", "hide-sm"], ["거래량(24H)", "hide-sm"], ["7일", "spark hide-sm"]];

function miniSpark(values, cls) {
  const box = el("span", `spark hide-sm ${cls}`);
  const pts = (values || []).filter((v) => v != null);
  if (pts.length < 2) {
    box.textContent = "—";
    return box;
  }
  const min = Math.min(...pts);
  const span = Math.max(...pts) - min || 1;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 32");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("aria-hidden", "true");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", pts.map((v, i) => `${((i / (pts.length - 1)) * 100).toFixed(2)},${(30 - ((v - min) / span) * 28).toFixed(2)}`).join(" "));
  svg.appendChild(line);
  box.appendChild(svg);
  return box;
}

function renderCoinGrid() {
  const grid = $("coin-grid");
  const more = $("more-coins"); // 리스트 안에 있으므로 비우기 전에 잡아 둔다
  const keep = grid.scrollTop; // "더 보기" 후에도 보던 위치 유지
  grid.replaceChildren();
  const list = [...state.coins].sort((a, b) => (a.market_cap_rank ?? 9999) - (b.market_cap_rank ?? 9999));
  const shown = list.slice(0, state.homeShown);
  grid.classList.toggle("no-spark", !list.some((c) => c.market?.sparkline_7d?.length));
  const head = el("div", "coin-head");
  head.setAttribute("aria-hidden", "true");
  for (const [label, cls] of LIST_COLS) head.appendChild(el("span", cls, label));
  grid.appendChild(head);
  for (const coin of shown) {
    const m = coin.market || {};
    const tile = el("button", "coin-tile");
    tile.type = "button";
    tile.setAttribute("aria-label", coin.label);
    const name = el("span", "nm");
    name.append(el("span", "sym", coin.symbol), el("span", "full", coin.name_ko || coin.name));
    const who = el("span", "coin");
    who.append(icon(coin, "mini-icon"), name);
    const c24 = change(m.change_24h_pct);
    const c7 = change(m.change_7d_pct);
    tile.append(
      el("span", "rk", coin.market_cap_rank ?? "-"),
      who,
      el("b", "px", usd(m.current_price_usd)),
      el("span", `chg ${c24.cls}`, c24.text),
      el("span", `chg hide-sm ${c7.cls}`, c7.text),
      el("span", "num hide-sm", usd(m.market_cap_usd)),
      el("span", "num hide-sm", usd(m.total_volume_usd)),
      miniSpark(m.sparkline_7d, c7.cls),
    );
    tile.addEventListener("click", () => selectCoin(coin.coin_id));
    grid.appendChild(tile);
  }
  more.classList.toggle("hidden", shown.length >= list.length);
  grid.appendChild(more); // 리스트 스크롤 영역의 맨 끝
  grid.scrollTop = keep;
}

// 메인 검색창 제안 목록: 이름·심볼·한글명 일치 최대 6개
function renderSuggest(value) {
  const box = $("home-suggest");
  box.replaceChildren();
  const v = value.trim().toLowerCase();
  const hits = v
    ? state.coins.filter((c) => [c.symbol, c.name, c.name_ko, c.coin_id].some((x) => x && x.toLowerCase().includes(v))).slice(0, 6)
    : [];
  box.classList.toggle("hidden", !hits.length);
  $("home-input").setAttribute("aria-expanded", String(Boolean(hits.length)));
  for (const coin of hits) {
    const item = el("li");
    item.setAttribute("role", "option");
    item.append(icon(coin, "mini-icon"), el("span", "sym", coin.symbol), el("span", "full", coin.name_ko || coin.name), el("span", "rk", `#${coin.market_cap_rank ?? "-"}`));
    item.addEventListener("mousedown", (e) => e.preventDefault()); // 입력창 blur 전에 클릭 처리
    item.addEventListener("click", () => selectCoin(coin.coin_id));
    box.appendChild(item);
  }
}

function renderExamples() {
  const box = $("example-list");
  box.replaceChildren();
  for (const [coinId, question] of EXAMPLES) {
    const coin = state.byId.get(coinId);
    if (!coin) continue;
    const button = el("button", "example");
    button.type = "button";
    button.append(icon(coin, "mini-icon"), document.createTextNode(question));
    button.addEventListener("click", () => {
      selectCoin(coinId);
      $("chat-input").value = question; // 보내기는 사용자가 누른다
      $("chat-input").focus();
    });
    box.appendChild(button);
  }
  box.parentElement.classList.toggle("hidden", !box.children.length);
}

function findCoinByInput(value) {
  const v = value.trim().toLowerCase();
  if (!v) return "";
  const hit = state.coins.find((c) => [c.symbol, c.name, c.name_ko, c.coin_id].some((x) => x && x.toLowerCase() === v));
  return hit ? hit.coin_id : "";
}

function applyTheme(theme) {
  const dark = theme === "dark";
  if (dark) document.documentElement.dataset.theme = "dark";
  else delete document.documentElement.dataset.theme;
  const btn = $("theme-toggle");
  btn.textContent = dark ? "☀" : "☾";
  btn.setAttribute("aria-label", dark ? "라이트 모드로 전환" : "다크 모드로 전환");
  try {
    localStorage.setItem("coinlab.theme", dark ? "dark" : "light");
  } catch {
    /* 저장이 막혀 있으면 이번 세션 동안만 유지한다 */
  }
  const coin = state.byId.get(state.coinId);
  if (coin && !$("coin-card").classList.contains("hidden")) renderChart(coin.market || {});
}

function bindEvents() {
  $("theme-toggle").addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
  // 코인 검색: 입력 중에는 목록을 거르고, Enter 는 정확히 일치하는 코인을 열거나 조건 탐색(F2011)을 한다
  $("recommend-input").addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    renderRail();
  });

  $("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const question = $("chat-input").value.trim();
    if (!question || state.busy || !state.coinId) return;
    if (state.offline) {
      showError("샘플 모드에서는 질문할 수 없습니다. 서버를 실행한 뒤 다시 시도하세요.");
      return;
    }
    $("chat-input").value = "";
    ask(question);
  });

  $("recommend-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const query = $("recommend-input").value.trim();
    if (!query) return;
    const coinId = findCoinByInput(query);
    if (coinId) selectCoin(coinId);
    else findCoins(query);
  });

  $("back-button").addEventListener("click", backFromResults);
  // 메인 검색창: 입력 중 제안, Enter 는 정확히 일치하면 코인 열기, 아니면 조건 탐색
  $("home-input").addEventListener("input", (event) => renderSuggest(event.target.value));
  $("home-input").addEventListener("blur", () => $("home-suggest").classList.add("hidden"));
  $("home-input").addEventListener("keydown", (event) => {
    if (event.key === "Escape") $("home-suggest").classList.add("hidden");
  });
  $("home-input").addEventListener("focus", (event) => renderSuggest(event.target.value));
  $("home-search").addEventListener("submit", (event) => {
    event.preventDefault();
    const query = $("home-input").value.trim();
    if (!query) return;
    $("home-suggest").classList.add("hidden");
    const coinId = findCoinByInput(query);
    if (coinId) selectCoin(coinId);
    else findCoins(query);
  });
  $("more-coins").addEventListener("click", () => {
    state.homeShown += PAGE;
    renderCoinGrid();
  });
  // 브라우저(주소창) 뒤로가기·앞으로가기
  window.addEventListener("popstate", () => {
    const coinId = new URLSearchParams(location.search).get("coin");
    if (coinId && state.byId.has(coinId)) selectCoin(coinId, false);
    else goHome(false);
  });
  $("home-link").addEventListener("click", (event) => {
    event.preventDefault();
    goHome();
  });

  for (const tab of $("tf-tabs").querySelectorAll("button")) {
    tab.addEventListener("click", () => {
      state.timeframe = tab.dataset.tf;
      const coin = state.byId.get(state.coinId);
      if (coin) renderCoinCard(coin);
    });
  }

  $("brief-button").addEventListener("click", () => {
    if (state.offline) return showError("샘플 모드에서는 브리핑을 만들 수 없습니다. 서버를 실행하세요.");
    runFeature("brief");
  });

  $("factcheck-button").addEventListener("click", () => {
    if (state.offline) return showError("샘플 모드에서는 팩트체크를 할 수 없습니다. 서버를 실행하세요.");
    const claim = $("chat-input").value.trim();
    if (!claim) {
      showError("확인할 주장을 입력창에 적은 뒤 '주장 팩트체크'를 누르세요. 예: 발행량 상한은 2,100만 개다");
      return;
    }
    $("chat-input").value = "";
    runFeature("factcheck", claim);
  });

  $("clear-button").addEventListener("click", () => {
    if (!state.coinId) return;
    state.histories[state.coinId] = [];
    saveHistories();
    renderChat();
    renderTalking();
  });
}

async function main() {
  bindEvents();
  applyTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  renderChat();
  renderTalking();
  updateFeatureButtons();
  const online = await loadStatus();
  try {
    setCoins(online ? await api("/api/coins") : useSample("서버(/api)에 연결하지 못해 샘플 모드로 표시합니다."));
  } catch (e) {
    setCoins(useSample(`코인 목록을 불러오지 못했습니다. ${e.message}`));
  }
  $("disclaimer").textContent = state.disclaimer || window.COIN_SAMPLE?.disclaimer || DEFAULT_DISCLAIMER;

  const linked = new URLSearchParams(location.search).get("coin");
  if (linked && state.byId.has(linked)) selectCoin(linked, false);
  else if (linked) history.replaceState(null, "", location.pathname);
}

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    const coin = state.byId.get(state.coinId);
    if (coin && !$("coin-card").classList.contains("hidden")) renderChart(coin.market || {});
  }, 150);
});

main();
