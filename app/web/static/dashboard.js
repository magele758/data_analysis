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

function openView(btn) {
  const view = readView(btn);
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
    if (data && data.report_markdown) result.appendChild(renderMarkdown(data.report_markdown));
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
  hint.textContent = exampleHint(id);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn";
  button.textContent = "运行";
  const result = document.createElement("div");
  button.addEventListener("click", () => runExample(id, label, button, result));
  root.append(heading, hint, button, result);
}

function findFromHash() {
  const raw = (location.hash || "").replace(/^#/, "");
  if (!raw) return null;
  if (raw.startsWith("example-")) {
    return document.querySelector('[data-example="' + CSS.escape(raw.slice("example-".length)) + '"]');
  }
  return document.querySelector('[data-view="' + CSS.escape(raw) + '"]');
}

function enterWorkspace() {
  const cover = document.getElementById("cover");
  const app = document.getElementById("app");
  if (cover) cover.hidden = true;
  if (app) app.hidden = false;
  if (document.querySelector('[aria-current="page"]')) return;
  const fromHash = findFromHash();
  if (fromHash) fromHash.click();
  else {
    const first = document.querySelector("[data-view]");
    if (first) first.click();
  }
}

function init() {
  restoreSession();
  bindSession();
  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => openView(btn));
  });
  document.querySelectorAll("[data-example]").forEach((btn) => {
    btn.addEventListener("click", () => openExample(btn));
  });
  const enter = document.getElementById("enter");
  if (enter) enter.addEventListener("click", enterWorkspace);
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
