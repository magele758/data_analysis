// Dashboard shell. Section panes live in /static/sections/*.js and register
// window.DashboardSections.<name>.mount(container, ctx). A missing file must
// not break navigation.

const SESSION_KEY = "das.session_id";
const MISSING_SECTION = "这一段还没装上";

const scriptLoads = new Map();

function sessionInput() {
  return document.getElementById("session-id");
}

function sessionId() {
  return sessionInput().value.trim();
}

function newSessionId() {
  return "dashboard-" + Math.random().toString(36).slice(2, 8);
}

function persistSession(value) {
  try {
    localStorage.setItem(SESSION_KEY, value);
  } catch (err) {
    /* private mode */
  }
}

function restoreSession() {
  const input = sessionInput();
  let saved = "";
  try {
    saved = localStorage.getItem(SESSION_KEY) || "";
  } catch (err) {
    saved = "";
  }
  if (!saved.trim()) {
    saved = newSessionId();
    persistSession(saved);
  }
  input.value = saved;
}

function bindSession() {
  const input = sessionInput();
  input.addEventListener("input", () => persistSession(input.value.trim()));
  input.addEventListener("change", () => {
    let value = input.value.trim();
    if (!value) {
      value = newSessionId();
      input.value = value;
    }
    persistSession(value);
  });
}

function apiUrl(path) {
  if (typeof path !== "string" || !path) throw new Error("缺少 API 路径");
  if (/^[a-z]+:/i.test(path)) throw new Error("仅允许同源 /api/v1");
  if (path.startsWith("/api/v1/") || path === "/api/v1") return path;
  if (path.startsWith("/")) return "/api/v1" + path;
  return "/api/v1/" + path;
}

function errorMessage(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => (item && item.msg) || String(item)).join("；");
  }
  if (data && data.message) return String(data.message);
  return "HTTP " + status;
}

const HTTP_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]);

function readApiCall(first, second, third) {
  if (typeof second === "string" && HTTP_METHODS.has(String(first || "").toUpperCase())) {
    return { method: String(first).toUpperCase(), path: second, body: third };
  }
  const opts = second && typeof second === "object" ? second : {};
  return {
    method: String(opts.method || "GET").toUpperCase(),
    path: first,
    body: opts.body,
  };
}

async function api(first, second, third) {
  const call = readApiCall(first, second, third);
  const headers = { "Content-Type": "application/json" };
  const init = { method: call.method, headers };
  if (call.body != null && call.method !== "GET" && call.method !== "HEAD") {
    if (typeof FormData !== "undefined" && call.body instanceof FormData) {
      delete headers["Content-Type"];
      init.body = call.body;
    } else {
      init.body = JSON.stringify(call.body);
    }
  }
  const res = await fetch(apiUrl(call.path), init);
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (err) {
      data = { detail: text };
    }
  }
  if (!res.ok) {
    const err = new Error(errorMessage(data, res.status));
    err.detail = data && data.detail != null ? data.detail : err.message;
    throw err;
  }
  return data;
}

function notify(text) {
  const el = document.getElementById("notify");
  const msg = String(text ?? "");
  el.hidden = false;
  el.textContent = msg;
  el.dataset.kind = /失败|错误|异常/.test(msg) ? "error" : "ok";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function formatCell(value) {
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function buildTable(rows) {
  const shown = rows.slice(0, 100);
  const cols = [];
  shown.forEach((row) => {
    if (!row || typeof row !== "object") return;
    Object.keys(row).forEach((key) => {
      if (!cols.includes(key)) cols.push(key);
    });
  });
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  cols.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  const tbody = document.createElement("tbody");
  shown.forEach((row) => {
    const tr = document.createElement("tr");
    cols.forEach((col) => {
      const td = document.createElement("td");
      td.textContent = formatCell(row && row[col]);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.append(thead, tbody);
  return table;
}

function tabularRows(payload) {
  if (Array.isArray(payload)) {
    return payload.length && payload.every((row) => row && typeof row === "object") ? payload : null;
  }
  if (!payload || typeof payload !== "object") return null;
  const keys = ["data_preview", "data", "records", "rows", "steps", "tables", "metrics", "models"];
  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value) && value.length && value.every((row) => row && typeof row === "object" && !Array.isArray(row))) {
      return value;
    }
  }
  return null;
}

function scalarRows(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return [];
  return Object.keys(payload)
    .filter((key) => {
      const value = payload[key];
      return value == null || ["string", "number", "boolean"].includes(typeof value);
    })
    .map((key) => ({ field: key, value: payload[key] }));
}

function loadScript(src) {
  if (scriptLoads.has(src)) return scriptLoads.get(src);
  const pending = new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = src;
    el.onload = () => resolve();
    el.onerror = () => reject(new Error("脚本加载失败"));
    document.head.appendChild(el);
  });
  scriptLoads.set(src, pending);
  return pending;
}

function isVega(spec) {
  return spec && typeof spec.$schema === "string" && spec.$schema.indexOf("vega") !== -1;
}

function isEcharts(spec) {
  return spec && Array.isArray(spec.series);
}

async function drawChart(host, spec) {
  const charts = window.DashboardSections?.analyze;
  if (charts?.drawChart) {
    host.classList.add("sec-analyze-chart");
    return charts.drawChart(host, spec);
  }
  if (isVega(spec)) {
    await loadScript("https://cdn.jsdelivr.net/npm/vega@5");
    await loadScript("https://cdn.jsdelivr.net/npm/vega-lite@5");
    await loadScript("https://cdn.jsdelivr.net/npm/vega-embed@6");
    if (!window.vegaEmbed) throw new Error("Vega-Lite 未加载");
    await window.vegaEmbed(host, spec, { actions: false });
    return;
  }
  if (isEcharts(spec)) {
    await loadScript("https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js");
    if (!window.echarts) throw new Error("ECharts 未加载");
    window.echarts.init(host).setOption(spec);
    return;
  }
  host.textContent = "图表未能绘制";
}

function render(host, payload) {
  if (!host || payload == null) return;
  const rows = tabularRows(payload);
  if (rows) host.appendChild(buildTable(rows));
  else {
    const scalars = scalarRows(payload);
    if (scalars.length) host.appendChild(buildTable(scalars));
  }
  if (payload && typeof payload === "object" && payload.chart_spec) {
    const box = document.createElement("div");
    box.className = "chart-host";
    host.appendChild(box);
    drawChart(box, payload.chart_spec).catch((err) => {
      box.textContent = "图表未能绘制";
      notify("失败：" + (err && err.message ? err.message : "图表未能绘制"));
    });
  }
}

function inlineNodes(text) {
  const span = document.createElement("span");
  span.innerHTML = escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return span;
}

function splitMarkdownRow(line) {
  return line.replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function markdownTable(lines) {
  const rows = lines.filter((line) => !splitMarkdownRow(line).every((cell) => /^:?-+:?$/.test(cell)));
  const records = rows.map((line) => {
    const cells = splitMarkdownRow(line);
    const record = {};
    cells.forEach((cell, index) => {
      record["c" + index] = cell;
    });
    return record;
  });
  if (records.length < 2) return buildTable(records);
  const header = records[0];
  const body = records.slice(1).map((row) => {
    const named = {};
    Object.keys(header).forEach((key) => {
      named[header[key] || key] = row[key];
    });
    return named;
  });
  return buildTable(body);
}

function renderMarkdown(source) {
  const root = document.createElement("div");
  root.className = "markdown";
  const lines = String(source).replace(/\r\n/g, "\n").split("\n");
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (line.startsWith("|")) {
      const block = [];
      while (index < lines.length && lines[index].startsWith("|")) {
        block.push(lines[index]);
        index += 1;
      }
      root.appendChild(markdownTable(block));
      continue;
    }
    if (line.startsWith(">")) {
      const quote = document.createElement("blockquote");
      const bits = [];
      while (index < lines.length && lines[index].startsWith(">")) {
        bits.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      quote.appendChild(inlineNodes(bits.join(" ")));
      root.appendChild(quote);
      continue;
    }
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const h = document.createElement("h" + heading[1].length);
      h.appendChild(inlineNodes(heading[2]));
      root.appendChild(h);
      index += 1;
      continue;
    }
    if (/^[-*]\s/.test(line)) {
      const list = document.createElement("ul");
      while (index < lines.length && /^[-*]\s/.test(lines[index])) {
        const li = document.createElement("li");
        li.appendChild(inlineNodes(lines[index].replace(/^[-*]\s/, "")));
        list.appendChild(li);
        index += 1;
      }
      root.appendChild(list);
      continue;
    }
    const p = document.createElement("p");
    p.appendChild(inlineNodes(line));
    root.appendChild(p);
    index += 1;
  }
  return root;
}

function mountEl() {
  return document.getElementById("mount");
}

function setCrumb(text) {
  document.getElementById("crumb").textContent = text;
}

function setCurrent(btn) {
  document.querySelectorAll(".nav-item").forEach((el) => el.removeAttribute("aria-current"));
  btn.setAttribute("aria-current", "page");
}

function setHash(id) {
  const next = "#" + id;
  if (location.hash === next) return;
  history.replaceState(null, "", next);
}

function resetMount() {
  const root = mountEl();
  window.DashboardSections?.analyze?.unmount?.(root);
  root.replaceChildren();
  root.className = "";
  return root;
}

function showMissing(title) {
  const root = resetMount();
  const wrap = document.createElement("div");
  wrap.className = "missing";
  const heading = document.createElement("h2");
  heading.textContent = title;
  const note = document.createElement("p");
  note.textContent = MISSING_SECTION;
  wrap.append(heading, note);
  root.appendChild(wrap);
}

function showMountError(title, err) {
  const root = resetMount();
  const heading = document.createElement("h2");
  heading.textContent = title;
  const note = document.createElement("p");
  note.className = "hint";
  note.textContent = err && err.message ? err.message : String(err);
  root.append(heading, note);
}

function sectionModule(name) {
  const bag = window.DashboardSections;
  if (!bag || !bag[name] || typeof bag[name].mount !== "function") return null;
  return bag[name];
}

function makeCtx(view) {
  return {
    sessionId,
    api,
    notify,
    render,
    view,
  };
}

function readView(btn) {
  const groupEl = btn.closest("[data-group]");
  const labelEl = groupEl && groupEl.querySelector(".group-label");
  return {
    id: btn.dataset.view,
    label: btn.textContent.trim(),
    group: groupEl ? groupEl.dataset.group : "",
    groupLabel: labelEl ? labelEl.textContent.trim() : "",
    section: btn.dataset.section,
  };
}

const PAGE_HEADINGS = {"report":["从证据，走向判断。","选择你的数据、时间与业务维度，生成可核查的分析报告。"],"import-file":["从一份数据开始。","把文件带入分析会话，保留字段、类型与来源。"],"connect-db":["连接业务发生的地方。","建立数据连接，把所需表载入当前分析会话。"],"import-trace":["让每一次调用可被理解。","导入遥测数据，统一 span 与 event，再进行路径和性能分析。"],"clean":["让数据回到清晰。","去重、填充与极值处理，让每个转换都有明确的输入和输出。"],"pipeline":["把转换编织成路径。","以 SQL DAG 组织模型依赖，让数据按顺序流向下一步。"],"wide":["把分散的记录连接起来。","围绕分析主体关联业务表，形成可复用的销售宽表。"],"objects":["万象相连，自有秩序。","让数据表成为业务对象，让键关系成为可探索的路径。"],"playground":["看见对象如何相连。","已注册的业务对象、关系与动作画在一张图上；断掉的关系单独列出，不造假节点。"],"traverse":["沿着关系，追问下去。","从客户走向订单与商品，逐跳查看实体路径。"],"metrics":["让每个指标有来处。","从口径到物理表，沿血缘查看依赖与影响范围。"],"eda":["先看清数据，再提出问题。","从完整性、字段类型与分布开始，建立数据画像。"],"olap":["在不同维度，看见同一业务。","以区域与品类组织指标，查看销售和利润的差异。"],"driver":["变化，必有其贡献。","沿区域与品类拆解利润变化，区分整体波动与局部贡献。"],"hypothesis":["让判断，经得起检验。","把观察变成假设，用统计量与边界约束结论。"],"variance":["分散之中，找到结构。","按业务维度拆解波动，区分组间与组内差异。"],"signals":["在噪声中，辨认真正的信号。","从异常、趋势与集中度中发现值得继续追问的变化。"],"paths":["看见行为的下一步。","把事件组织为漏斗、留存与路径，理解行为如何发生。"],"forecast":["面向未来，保留不确定性。","根据时间序列生成预测，明确历史范围与预测区间。"],"assert":["可信，从核对开始。","以清晰的断言检查数据，再决定它能否进入下一步。"],"drift":["感知结构中的变化。","对照基线识别字段新增、缺失与类型变化。"],"sync":["让分析抵达业务系统。","配置目标与同步方式，执行前清晰呈现数据范围。"],"audience":["让分群成为可行动的名单。","把分析得到的客户分群转成业务可使用的受众。"],"alert":["把重要的变化送达。","从数据质量与指标异动生成告警，并保留发送结果。"],"example-erp":["从订单，走到洞察。","项目内置合成 ERP 数据示例：接入、探索、质量、分群、归因。"],"example-dota2":["从比赛，走到战术。","基于项目已有 OpenDota 比赛数据，查看战队与选手的分析路径。"]};
function paintPageHeading(id, label, section) {
  const copy = PAGE_HEADINGS[id] || [label, "连接数据，构建关系，让每次洞察都有据可循。"];
  document.getElementById("page-title").textContent = copy[0];
  document.getElementById("page-description").textContent = copy[1];
  document.getElementById("page-sculpture").src = "/static/cover/" + (section === "analyze" ? "athena" : section === "govern" ? "hermes" : "apollo") + ".jpg";
}

function openView(btn) {
  setNavOpen(false);
  const view = readView(btn);
  paintPageHeading(view.id, view.label, view.section);
  setPrinciple(view.section);
  setCurrent(btn);
  setCrumb(view.groupLabel + " / " + view.label);
  setHash(view.id);
  const mod = sectionModule(view.section);
  if (!mod) {
    showMissing(view.label);
    return;
  }
  const root = resetMount();
  try {
    Promise.resolve()
      .then(() => mod.mount(root, makeCtx(view)))
      .then(() => {
        selectGovernTab(root, view);
        selectIngestTab(root, view);
        selectWorkspaceTab(root, view);
      })
      .catch((err) => {
        notify("失败：" + (err && err.message ? err.message : err));
        showMountError(view.label, err);
      });
  } catch (err) {
    notify("失败：" + (err && err.message ? err.message : err));
    showMountError(view.label, err);
  }
}

function selectGovernTab(root, view) {
  if (!view || view.section !== "govern" || !view.id) return;
  const tab = root.querySelector('[data-govern-tab="' + CSS.escape(view.id) + '"]');
  if (!tab || tab.getAttribute("aria-selected") === "true") return;
  tab.click();
}

const INGEST_TABS = {
  "import-file": "file",
  "connect-db": "db",
  "import-trace": "trace",
};

function selectIngestTab(root, view) {
  if (!view || view.section !== "ingest") return;
  const id = INGEST_TABS[view.id];
  if (!id) return;
  const tab = root.querySelector('.sec-ingest-tab[data-tab="' + CSS.escape(id) + '"]');
  if (!tab || tab.getAttribute("aria-selected") === "true") return;
  tab.click();
}

// Sidebar groups may map onto a more specific tool tab in a section.
const ANALYZE_TABS = {
  eda: "eda", olap: "olap", driver: "driver", hypothesis: "test",
  variance: "variance", signals: "outliers", paths: "funnel", forecast: "forecast"
};
function selectWorkspaceTab(root, view) {
  let selector;
  if (view.section === "transform" || view.section === "model") {
    selector = '[data-tab="' + CSS.escape(view.id) + '"]';
  } else if (view.section === "analyze") {
    selector = '[data-sec-analyze-tab="' + CSS.escape(ANALYZE_TABS[view.id] || view.id) + '"]';
  }
  const tab = selector && root.querySelector(selector);
  if (tab && tab.getAttribute("aria-selected") !== "true") tab.click();
}

function exampleHint(id) {
  if (id === "dota2") return "调用 POST /api/v1/examples/dota2/run，把 Dota 2 示例写入当前会话。";
  return "调用 POST /api/v1/examples/erp/run，把 ERP 示例写入当前会话。";
}

async function runExample(id, label, button, result) {
  button.disabled = true;
  button.textContent = "运行中";
  try {
    const data = await api("/examples/" + id + "/run", {
      method: "POST",
      body: { session_id: sessionId() },
    });
    notify(label + " 已完成");
    result.replaceChildren();
    const meta = document.createElement("p");
    meta.className = "hint";
    const bits = [];
    if (data && data.dataset_name) bits.push("数据集 " + data.dataset_name);
    if (data && data.rows != null) bits.push(String(data.rows) + " 行");
    meta.textContent = bits.join(" · ");
    if (meta.textContent) result.appendChild(meta);
    if (data && data.report_markdown) {
      if (id === "erp") {
        const full = document.createElement("details");
        full.className = "erp-full-report";
        const summary = document.createElement("summary");
        summary.textContent = "展开完整分析报告（原始叙述与明细）";
        full.append(summary, renderMarkdown(data.report_markdown));
        result.appendChild(full);
        if (window.ERPReport) await window.ERPReport.render(result, data, {api});
        else full.open = true;
        if (window.ERPProfitReport) await window.ERPProfitReport.render(result, data, {api});
      } else result.appendChild(renderMarkdown(data.report_markdown));
    }
    else render(result, data);
    if (data && data.chart_spec) render(result, { chart_spec: data.chart_spec });
  } catch (err) {
    notify("失败：" + (err && err.message ? err.message : err));
  } finally {
    button.disabled = false;
    button.textContent = "运行";
  }
}

function openExample(btn) {
  paintPageHeading("example-" + btn.dataset.example, btn.textContent.trim(), "analyze");
  setNavOpen(false);
  setPrinciple("analyze");
  const id = btn.dataset.example;
  const label = btn.textContent.trim();
  setCurrent(btn);
  setCrumb("示例 / " + label);
  setHash("example-" + id);
  const root = resetMount();
  const heading = document.createElement("h2");
  heading.textContent = label;
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = id === "erp"
    ? "用可复现的合成 ERP 数据，走完从订单到收款的分析流程。数据与报告写入当前会话，可继续下钻。"
    : "从仓库内置的 OpenDota 比赛快照出发，观察战队战绩、选手表现与英雄偏好。具体来源与时间以生成报告为准。";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn";
  button.textContent = "运行";
  const result = document.createElement("div");
  button.addEventListener("click", () => runExample(id, label, button, result));
  const intro = document.createElement("section");
  intro.className = "example-intro";
  const topics = document.createElement("ul");
  topics.className = "example-topics";
  const labels = id === "erp" ? ["销售与利润", "数据质量", "客户分群", "变化归因"] : ["战队战绩", "选手表现", "打法聚类", "战术指导"];
  labels.forEach(label => { const item = document.createElement("li"); item.textContent = label; topics.appendChild(item); });
  intro.append(heading, hint, topics, button);
  result.className = "example-output";
  root.append(intro, result);
}

function findFromHash() {
  const raw = (location.hash || "").replace(/^#/, "");
  if (!raw) return null;
  if (raw.startsWith("example-")) {
    return document.querySelector('[data-example="' + CSS.escape(raw.slice("example-".length)) + '"]');
  }
  return document.querySelector('[data-view="' + CSS.escape(raw) + '"]');
}

function setPrinciple(section) {
  const theme = section === "analyze" ? "wisdom" :
    (section === "model" || section === "transform") ? "order" : "connection";
  document.querySelectorAll("[data-principle]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.principle === theme);
  });
}

let ritualTimers = [];
let ritualActive = false;

function finishEntryRitual() {
  ritualTimers.forEach(clearTimeout);
  ritualTimers = [];
  ritualActive = false;
  const ritual = document.getElementById("entry-ritual");
  ritual.hidden = true;
  ritual.classList.remove("is-playing");
  document.getElementById("cover").inert = false;
  document.getElementById("app").inert = false;
  document.getElementById("enter").disabled = false;
  enterWorkspace();
}

function startEntryRitual() {
  if (ritualActive) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    enterWorkspace();
    return;
  }
  ritualActive = true;
  document.getElementById("enter").disabled = true;
  document.getElementById("cover").inert = true;
  document.getElementById("app").inert = true;
  const ritual = document.getElementById("entry-ritual");
  ritual.hidden = false;
  ritual.classList.add("is-playing");
  document.getElementById("skip-ritual").focus({ preventScroll: true });
  // Reveal the destination beneath the veil before its final fade.
  ritualTimers.push(setTimeout(() => enterWorkspace(false), 1800));
  // A wall-clock fallback also works when CSS animations are unavailable.
  ritualTimers.push(setTimeout(finishEntryRitual, 2300));
}

function enterWorkspace(focusContent = true) {
  const cover = document.getElementById("cover");
  const app = document.getElementById("app");
  if (cover) cover.hidden = true;
  if (app) app.hidden = false;
  if (focusContent) document.getElementById("workspace-content").focus({ preventScroll: true });
  if (document.querySelector('[aria-current="page"]')) return;
  const fromHash = findFromHash();
  if (fromHash) fromHash.click();
  else {
    const first = document.querySelector("[data-view]");
    if (first) first.click();
  }
}

function setNavOpen(open) {
  const app = document.getElementById("app");
  app.classList.toggle("nav-open", open);
  document.getElementById("nav-toggle").setAttribute("aria-expanded", String(open));
  document.getElementById("nav-toggle").setAttribute("aria-label", open ? "关闭导航" : "打开导航");
  document.getElementById("nav-scrim").hidden = !open;
  document.getElementById("workspace-nav").inert = window.innerWidth <= 760 && !open;
  if (open) document.getElementById("return-cover").focus();
}

function returnToCover() {
  setNavOpen(false);
  document.getElementById("app").hidden = true;
  document.getElementById("cover").hidden = false;
  history.replaceState(null, "", location.pathname);
  window.scrollTo(0, 0);
  document.getElementById("enter").focus({ preventScroll: true });
}

function init() {
  restoreSession();
  bindSession();
  document.querySelectorAll("[data-target-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.querySelector('[data-view="' + CSS.escape(button.dataset.targetView) + '"]');
      if (target) target.click();
    });
  });
  document.getElementById("return-cover").addEventListener("click", returnToCover);
  document.getElementById("nav-toggle").addEventListener("click", () => {
    setNavOpen(!document.getElementById("app").classList.contains("nav-open"));
  });
  document.getElementById("nav-scrim").addEventListener("click", () => setNavOpen(false));
  document.addEventListener("keydown", (event) => {
    if (ritualActive && event.key === "Escape") {
      finishEntryRitual();
      return;
    }
    if (ritualActive && event.key === "Tab") {
      event.preventDefault();
      document.getElementById("skip-ritual").focus();
      return;
    }
    if (event.key === "Escape" && document.getElementById("app").classList.contains("nav-open")) {
      setNavOpen(false);
      document.getElementById("nav-toggle").focus();
    }
  });
  window.addEventListener("resize", () => setNavOpen(false));
  setNavOpen(false);
  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => openView(btn));
  });
  document.querySelectorAll("[data-example]").forEach((btn) => {
    btn.addEventListener("click", () => openExample(btn));
  });
  window.addEventListener("hashchange", () => {
    const target = findFromHash();
    if (target) {
      enterWorkspace(false);
      if (target.getAttribute("aria-current") !== "page") target.click();
    }
  });
  if (findFromHash()) enterWorkspace(false);
  const enter = document.getElementById("enter");
  if (enter) enter.addEventListener("click", startEntryRitual);
  document.getElementById("skip-ritual").addEventListener("click", finishEntryRitual);
  document.querySelectorAll(".cover-stone img").forEach((img) => {
    const markMissing = () => {
      img.hidden = true;
      const figure = img.closest(".cover-figure");
      if (figure) figure.classList.add("is-missing");
    };
    img.addEventListener("error", markMissing);
    if (img.complete && img.naturalWidth === 0) markMissing();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
