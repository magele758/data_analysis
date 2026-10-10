// 准备段：清洗、管道、宽表。只调用已有 REST。
// ctx.sessionId() 返回当前会话。
// ctx.api(method, path, body) 成功时返回 JSON；失败时抛出错误，detail 放在错误对象上或 message 里。
// ctx.notify(message) 用来提示短结果。
window.DashboardSections = window.DashboardSections || {};
window.DashboardSections.transform = {
  mount(container, ctx) {
    container.innerHTML = TEMPLATE;
    const raw = container.querySelector("style");
    if (raw) {
      const style = document.createElement("style");
      style.setAttribute("data-sec-transform-style", "");
      style.textContent = raw.textContent;
      raw.replaceWith(style);
    }
    bind(container, ctx || {});
  }
};

const TEMPLATE = `
<style>
  .sec-transform-root { background:#fff; color:#1a1a1a; font-size:13px; line-height:1.4; }
  .sec-transform-tabs { display:flex; gap:2px; border-bottom:1px solid #e6e6e6; margin:0 0 10px; }
  .sec-transform-tab { appearance:none; background:#fff; border:0; border-bottom:2px solid transparent; color:#666; padding:6px 10px; margin-bottom:-1px; cursor:pointer; font:inherit; }
  .sec-transform-tab.sec-transform-on { color:#111; border-bottom-color:#111; font-weight:600; }
  .sec-transform-note { margin:0 0 10px; color:#444; font-size:12px; }
  .sec-transform-body { display:grid; grid-template-columns:minmax(240px,320px) minmax(0,1fr); gap:16px; align-items:start; }
  .sec-transform-form { margin:0; padding:0; border:0; }
  .sec-transform-field { display:flex; flex-direction:column; gap:2px; margin:0 0 8px; }
  .sec-transform-field > span { color:#444; font-size:12px; }
  .sec-transform-input, .sec-transform-textarea, .sec-transform-select { width:100%; border:1px solid #d0d0d0; border-radius:2px; background:#fff; color:#111; padding:4px 6px; font:inherit; }
  .sec-transform-textarea { min-height:68px; resize:vertical; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px; }
  .sec-transform-hint { margin:-4px 0 8px; color:#777; font-size:11px; }
  .sec-transform-btn { margin-top:2px; background:#1a1a1a; color:#fff; border:0; border-radius:2px; padding:6px 12px; font:inherit; cursor:pointer; }
  .sec-transform-btn:disabled { opacity:.55; cursor:default; }
  .sec-transform-result { min-width:0; overflow-x:auto; }
  .sec-transform-block { margin:0 0 12px; }
  .sec-transform-caption { margin:0 0 4px; font-size:12px; font-weight:600; color:#333; }
  .sec-transform-table { width:100%; border-collapse:collapse; font-size:12px; }
  .sec-transform-table th, .sec-transform-table td { border-bottom:1px solid #eee; padding:4px 6px; text-align:left; vertical-align:top; word-break:break-word; }
  .sec-transform-table th { color:#666; font-weight:600; background:#fafafa; }
  .sec-transform-error { margin:0 0 8px; color:#8a1f11; background:#fff; border:1px solid #e5c4c0; padding:8px; white-space:pre-wrap; word-break:break-word; font-size:12px; }
  .sec-transform-empty { margin:0; color:#888; font-size:12px; }
  .sec-transform-hidden { display:none; }
  @media (max-width:720px) { .sec-transform-body { grid-template-columns:1fr; } }
</style>
<div class="sec-transform-root">
  <div class="sec-transform-tabs" role="tablist">
    <button type="button" class="sec-transform-tab sec-transform-on" data-tab="clean" role="tab" aria-selected="true">清洗</button>
    <button type="button" class="sec-transform-tab" data-tab="pipeline" role="tab" aria-selected="false">管道</button>
    <button type="button" class="sec-transform-tab" data-tab="wide" role="tab" aria-selected="false">宽表</button>
  </div>

  <section class="sec-transform-panel" data-panel="clean">
    <div class="sec-transform-body">
      <form class="sec-transform-form" data-form="clean">
        <label class="sec-transform-field"><span>源表</span><input class="sec-transform-input" data-field="source_table" autocomplete="off"></label>
        <label class="sec-transform-field"><span>目标表</span><input class="sec-transform-input" data-field="target_table" autocomplete="off"></label>
        <label class="sec-transform-field"><span>去重键</span><input class="sec-transform-input" data-field="dedup_keys" autocomplete="off" placeholder="id, order_id"></label>
        <p class="sec-transform-hint">多个列用逗号分隔。留空则不去重。</p>
        <label class="sec-transform-field"><span>空值填充</span><textarea class="sec-transform-textarea" data-field="fillna_rules" spellcheck="false" placeholder="amount=MEAN&#10;city=未知"></textarea></label>
        <p class="sec-transform-hint">每行「列名=MEAN」「列名=MEDIAN」「列名=MODE」或「列名=常数」。留空则不填充。</p>
        <label class="sec-transform-field"><span>缩尾</span><textarea class="sec-transform-textarea" data-field="outlier_clip_cols" spellcheck="false" placeholder="amount=0,100"></textarea></label>
        <p class="sec-transform-hint">每行「列名=最小值,最大值」，一边可以留空。留空则不缩尾。</p>
        <button type="submit" class="sec-transform-btn">开始清洗</button>
      </form>
      <div class="sec-transform-result" data-result="clean"><p class="sec-transform-empty">尚无结果</p></div>
    </div>
  </section>

  <section class="sec-transform-panel sec-transform-hidden" data-panel="pipeline">
    <p class="sec-transform-note">同一层的模型按顺序执行，不是并发。执行顺序表里的先后就是实际运行顺序。</p>
    <div class="sec-transform-body">
      <form class="sec-transform-form" data-form="pipeline">
        <label class="sec-transform-field"><span>动作</span>
          <select class="sec-transform-select" data-field="action">
            <option value="register">注册模型</option>
            <option value="run">执行管道</option>
          </select>
        </label>
        <div data-pipeline-fields>
          <label class="sec-transform-field"><span>模型名</span><input class="sec-transform-input" data-field="name" autocomplete="off" placeholder="stg_orders"></label>
          <label class="sec-transform-field"><span>SQL</span><textarea class="sec-transform-textarea" data-field="sql" spellcheck="false" placeholder="SELECT id, amount FROM orders"></textarea></label>
          <label class="sec-transform-field"><span>物化</span>
            <select class="sec-transform-select" data-field="materialization">
              <option value="table">表（table）</option>
              <option value="view">视图（view）</option>
              <option value="ephemeral">临时视图（ephemeral）</option>
              <option value="incremental">增量（incremental）</option>
            </select>
          </label>
          <label class="sec-transform-field"><span>依赖</span><input class="sec-transform-input" data-field="depends_on" autocomplete="off" placeholder="stg_orders, dim_user"></label>
          <p class="sec-transform-hint">留空时按 SQL 解析来源表。填写后的依赖不会被覆盖。多个名称用逗号分隔。</p>
          <label class="sec-transform-field"><span>说明</span><input class="sec-transform-input" data-field="description" autocomplete="off"></label>
          <label class="sec-transform-field"><span>unique_key</span><input class="sec-transform-input" data-field="unique_key" autocomplete="off" placeholder="id"></label>
          <p class="sec-transform-hint">增量物化时，已有表按该键合并；留空则整表刷新。</p>
        </div>
        <button type="submit" class="sec-transform-btn" data-pipeline-btn>注册模型</button>
      </form>
      <div class="sec-transform-result" data-result="pipeline">
        <div data-pipeline-feedback><p class="sec-transform-empty">尚无结果</p></div>
        <div data-pipeline-list></div>
      </div>
    </div>
  </section>

  <section class="sec-transform-panel sec-transform-hidden" data-panel="wide">
    <div class="sec-transform-body">
      <form class="sec-transform-form" data-form="wide">
        <label class="sec-transform-field"><span>目标表</span><input class="sec-transform-input" data-field="target_name" autocomplete="off" placeholder="orders_wide"></label>
        <label class="sec-transform-field"><span>事实表</span><input class="sec-transform-input" data-field="fact_table" autocomplete="off" placeholder="orders"></label>
        <label class="sec-transform-field"><span>维度连接</span><textarea class="sec-transform-textarea" data-field="dimension_joins" spellcheck="false" placeholder="dim_user | orders.user_id = dim_user.id | dim_user.city,dim_user.age"></textarea></label>
        <p class="sec-transform-hint">每行一张维表：维表 | 连接条件 | 选出的列。列可以留空。</p>
        <button type="submit" class="sec-transform-btn">生成宽表</button>
      </form>
      <div class="sec-transform-result" data-result="wide"><p class="sec-transform-empty">尚无结果</p></div>
    </div>
  </section>
</div>
`;

function bind(container, ctx) {
  let listToken = 0;

  container.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  });

  const pipelineForm = container.querySelector('[data-form="pipeline"]');
  pipelineForm.querySelector('[data-field="action"]').addEventListener("change", syncPipelineAction);
  syncPipelineAction();

  container.querySelector('[data-form="clean"]').addEventListener("submit", (event) => {
    event.preventDefault();
    submitClean(container, ctx);
  });
  pipelineForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitPipeline(container, ctx, () => refreshModels());
  });
  container.querySelector('[data-form="wide"]').addEventListener("submit", (event) => {
    event.preventDefault();
    submitWide(container, ctx);
  });

  function showTab(name) {
    container.querySelectorAll("[data-tab]").forEach((button) => {
      const on = button.dataset.tab === name;
      button.classList.toggle("sec-transform-on", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
    });
    container.querySelectorAll("[data-panel]").forEach((panel) => {
      panel.classList.toggle("sec-transform-hidden", panel.dataset.panel !== name);
    });
    if (name === "pipeline") refreshModels();
  }

  function syncPipelineAction() {
    const action = pipelineForm.querySelector('[data-field="action"]').value;
    const fields = pipelineForm.querySelector("[data-pipeline-fields]");
    const button = pipelineForm.querySelector("[data-pipeline-btn]");
    const register = action === "register";
    fields.classList.toggle("sec-transform-hidden", !register);
    if (!button.disabled) button.textContent = register ? "注册模型" : "执行管道";
  }

  async function refreshModels() {
    const token = ++listToken;
    const slot = container.querySelector("[data-pipeline-list]");
    slot.innerHTML = '<p class="sec-transform-empty">正在读取模型…</p>';
    const sid = sessionId(ctx);
    const listed = await callApi(ctx, "GET", withSession("/api/v1/transform/dag/models", sid));
    if (token !== listToken) return;
    slot.innerHTML = listed.ok ? renderModelList(listed.data) : errorHtml(listed.detail);
  }
}

async function submitClean(container, ctx) {
  const form = container.querySelector('[data-form="clean"]');
  const result = container.querySelector('[data-result="clean"]');
  const button = form.querySelector(".sec-transform-btn");
  if (button.disabled) return;
  let body;
  try {
    body = cleanBody(form, sessionId(ctx));
  } catch (err) {
    result.innerHTML = errorHtml(err.message);
    notify(ctx, err.message);
    return;
  }
  await runAction(button, result, ctx, "清洗完成", () => callApi(ctx, "POST", "/api/v1/transform/clean", body), renderClean);
}

function cleanBody(form, sid) {
  const source = field(form, "source_table");
  const target = field(form, "target_table");
  if (!source || !target) throw new Error("请填写源表和目标表");
  const body = { session_id: sid, source_table: source, target_table: target };
  const keys = splitList(field(form, "dedup_keys"));
  if (keys.length) body.dedup_keys = keys;
  const fill = parseFillna(field(form, "fillna_rules"));
  if (Object.keys(fill).length) body.fillna_rules = fill;
  const clip = parseClip(field(form, "outlier_clip_cols"));
  if (Object.keys(clip).length) body.outlier_clip_cols = clip;
  return body;
}

async function submitWide(container, ctx) {
  const form = container.querySelector('[data-form="wide"]');
  const result = container.querySelector('[data-result="wide"]');
  const button = form.querySelector(".sec-transform-btn");
  if (button.disabled) return;
  let body;
  try {
    body = wideBody(form, sessionId(ctx));
  } catch (err) {
    result.innerHTML = errorHtml(err.message);
    notify(ctx, err.message);
    return;
  }
  await runAction(button, result, ctx, "宽表已生成", () => callApi(ctx, "POST", "/api/v1/transform/wide", body), renderWide);
}

function wideBody(form, sid) {
  const target = field(form, "target_name");
  const fact = field(form, "fact_table");
  if (!target || !fact) throw new Error("请填写目标表和事实表");
  return {
    session_id: sid,
    target_name: target,
    fact_table: fact,
    dimension_joins: parseJoins(field(form, "dimension_joins"))
  };
}

async function submitPipeline(container, ctx, refreshModels) {
  const form = container.querySelector('[data-form="pipeline"]');
  const feedback = container.querySelector("[data-pipeline-feedback]");
  const button = form.querySelector("[data-pipeline-btn]");
  if (button.disabled) return;
  const sid = sessionId(ctx);
  if (field(form, "action") === "run") {
    await runAction(
      button,
      feedback,
      ctx,
      "管道已执行",
      () => callApi(ctx, "POST", withSession("/api/v1/transform/dag/run", sid)),
      renderRun
    );
    button.textContent = "执行管道";
    await refreshModels();
    return;
  }

  let body;
  try {
    body = modelBody(form);
  } catch (err) {
    feedback.innerHTML = errorHtml(err.message);
    notify(ctx, err.message);
    return;
  }
  await runAction(
    button,
    feedback,
    ctx,
    "模型已注册",
    () => callApi(ctx, "POST", withSession("/api/v1/transform/dag/models", sid), body),
    renderRegistered
  );
  button.textContent = "注册模型";
  await refreshModels();
}

function modelBody(form) {
  const name = field(form, "name");
  const sql = field(form, "sql");
  if (!name || !sql) throw new Error("请填写模型名和 SQL");
  const body = {
    name,
    sql,
    materialization: field(form, "materialization") || "table"
  };
  const depends = splitList(field(form, "depends_on"));
  if (depends.length) body.depends_on = depends;
  const description = field(form, "description");
  if (description) body.description = description;
  const uniqueKey = field(form, "unique_key");
  if (uniqueKey) body.unique_key = uniqueKey;
  return body;
}

async function runAction(button, slot, ctx, okText, request, render) {
  const previous = button.textContent;
  button.disabled = true;
  button.textContent = "处理中";
  try {
    const response = await request();
    if (!response.ok) {
      slot.innerHTML = errorHtml(response.detail);
      notify(ctx, response.detail);
      return;
    }
    slot.innerHTML = render(response.data);
    notify(ctx, okText);
  } finally {
    button.disabled = false;
    button.textContent = previous;
  }
}

function renderClean(data) {
  return kvTable("清洗结果", [
    ["源表", cell(data && data.source_table)],
    ["目标表", cell(data && data.target_table)],
    ["原始行数", cell(data && data.original_rows)],
    ["清洗后行数", cell(data && data.cleaned_rows)],
    ["去除重复", cell(data && data.removed_duplicates)]
  ]);
}

function renderWide(data) {
  const row = data || {};
  const summary = kvTable("宽表", [
    ["宽表", cell(row.wide_table_name)],
    ["行数", cell(row.row_count)],
    ["状态", cell(statusText(row.status))]
  ]);
  const columns = Array.isArray(row.columns) ? row.columns : [];
  if (!columns.length) return summary;
  return summary + dataTable("列", [{ label: "列名", value: (item) => cell(item) }], columns);
}

function renderRegistered(data) {
  return renderModelTable("本次注册", data ? [data] : []);
}

function renderRun(data) {
  const row = data || {};
  const summary = kvTable("执行摘要", [
    ["模型数", cell(row.total_models)],
    ["层数", cell(row.total_stages)],
    ["总耗时（毫秒）", cell(row.total_duration_ms)]
  ]);
  const order = dataTable(
    "执行顺序",
    [{ label: "序号", value: (_item, index) => String(index + 1) }, { label: "模型", value: (item) => cell(item) }],
    Array.isArray(row.execution_order) ? row.execution_order : []
  );
  const results = dataTable(
    "模型结果",
    [
      { label: "模型", value: (item) => cell(item && item.model_name) },
      { label: "物化", value: (item) => cell(item && item.materialization) },
      { label: "行数", value: (item) => cell(item && item.row_count) },
      { label: "耗时（毫秒）", value: (item) => cell(item && item.duration_ms) },
      { label: "状态", value: (item) => cell(statusText(item && item.status)) },
      { label: "增量方式", value: (item) => cell(mergeText(item && item.incremental_mode)) }
    ],
    Array.isArray(row.results) ? row.results : []
  );
  return summary + order + results;
}

function renderModelList(data) {
  const models = data && Array.isArray(data.models) ? data.models : [];
  const order = data && Array.isArray(data.execution_order) ? data.execution_order : [];
  if (!models.length) return '<p class="sec-transform-empty">尚未注册模型</p>';
  return renderModelTable("已登记模型", models) + dataTable(
    "执行顺序",
    [{ label: "序号", value: (_item, index) => String(index + 1) }, { label: "模型", value: (item) => cell(item) }],
    order
  );
}

function renderModelTable(caption, models) {
  return dataTable(caption, [
    { label: "模型", value: (item) => cell(item && item.name) },
    { label: "物化", value: (item) => cell(item && item.materialization) },
    { label: "unique_key", value: (item) => cell(item && item.unique_key) },
    { label: "依赖", value: (item) => cell(item && item.depends_on) },
    { label: "说明", value: (item) => cell(item && item.description) },
    { label: "SQL", value: (item) => cell(item && item.sql) }
  ], models);
}

function kvTable(caption, pairs) {
  return dataTable(caption, [
    { label: "项目", value: (item) => item[0] },
    { label: "值", value: (item) => item[1] }
  ], pairs);
}

function dataTable(caption, columns, rows) {
  if (!rows.length) return "";
  const head = columns.map((column) => `<th>${esc(column.label)}</th>`).join("");
  const body = rows.map((row, index) => {
    const cells = columns.map((column) => `<td>${esc(column.value(row, index))}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  return `<div class="sec-transform-block"><div class="sec-transform-caption">${esc(caption)}</div><table class="sec-transform-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function errorHtml(detail) {
  return `<div class="sec-transform-error">${esc(detail || "请求失败")}</div>`;
}

function field(form, name) {
  const node = form.querySelector(`[data-field="${name}"]`);
  return node ? node.value.trim() : "";
}

function splitList(text) {
  return String(text || "").split(/[,，]/).map((item) => item.trim()).filter(Boolean);
}

function parseFillna(text) {
  const rules = {};
  lines(text).forEach((line) => {
    const idx = line.indexOf("=");
    if (idx <= 0) throw new Error("填充规则应为「列名=MEAN|MEDIAN|MODE|常数」");
    const col = line.slice(0, idx).trim();
    const raw = line.slice(idx + 1).trim();
    if (!col || !raw) throw new Error("填充规则应为「列名=MEAN|MEDIAN|MODE|常数」");
    const upper = raw.toUpperCase();
    if (upper === "MEAN" || upper === "MEDIAN" || upper === "MODE") rules[col] = upper;
    else if (/^-?\d+(?:\.\d+)?$/.test(raw)) rules[col] = Number(raw);
    else rules[col] = raw;
  });
  return rules;
}

function parseClip(text) {
  const rules = {};
  lines(text).forEach((line) => {
    const idx = line.indexOf("=");
    if (idx <= 0) throw new Error("缩尾应为「列名=最小值,最大值」");
    const col = line.slice(0, idx).trim();
    const parts = line.slice(idx + 1).split(",");
    if (!col || parts.length !== 2) throw new Error("缩尾应为「列名=最小值,最大值」");
    const bounds = {};
    const min = parts[0].trim();
    const max = parts[1].trim();
    if (min) {
      if (!/^-?\d+(?:\.\d+)?$/.test(min)) throw new Error("缩尾边界必须是数字");
      bounds.min = Number(min);
    }
    if (max) {
      if (!/^-?\d+(?:\.\d+)?$/.test(max)) throw new Error("缩尾边界必须是数字");
      bounds.max = Number(max);
    }
    if (bounds.min === undefined && bounds.max === undefined) throw new Error("缩尾至少填写最小值或最大值");
    rules[col] = bounds;
  });
  return rules;
}

function parseJoins(text) {
  return lines(text).map((line) => {
    const parts = line.split("|").map((item) => item.trim());
    if (parts.length < 2 || !parts[0] || !parts[1]) throw new Error("维度连接应为「维表 | 连接条件 | 列1,列2」");
    const join = { dim_table: parts[0], on: parts[1] };
    const cols = parts.slice(2).join("|").split(/[,，]/).map((item) => item.trim()).filter(Boolean);
    if (cols.length) join.select_cols = cols;
    return join;
  });
}

function lines(text) {
  return String(text || "").split(/\n/).map((line) => line.trim()).filter(Boolean);
}

function cell(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  return String(value);
}

function statusText(value) {
  if (value === "SUCCESS") return "成功";
  return cell(value);
}

function mergeText(value) {
  if (value === "full_refresh") return "整表刷新";
  if (value === "merge") return "按键合并";
  return cell(value);
}

function sessionId(ctx) {
  if (!ctx || typeof ctx.sessionId !== "function") return "";
  const id = ctx.sessionId();
  return id == null ? "" : String(id);
}

function withSession(path, sid) {
  return path + "?session_id=" + encodeURIComponent(sid);
}

function notify(ctx, message) {
  if (!ctx || typeof ctx.notify !== "function") return;
  try { ctx.notify(message); } catch (_err) { /* 提示失败不影响结果区 */ }
}

async function callApi(ctx, method, path, body) {
  if (!ctx || typeof ctx.api !== "function") return { ok: false, detail: "未提供 ctx.api" };
  try {
    const data = body === undefined ? await ctx.api(method, path) : await ctx.api(method, path, body);
    if (data && typeof data === "object" && data.status === "error" && data.detail !== undefined) {
      return { ok: false, detail: formatDetail(data.detail) };
    }
    return { ok: true, data };
  } catch (err) {
    return { ok: false, detail: extractDetail(err) };
  }
}

function extractDetail(err) {
  if (err == null) return "请求失败";
  if (typeof err === "string") return err;
  if (err.detail !== undefined) return formatDetail(err.detail);
  if (err.data && err.data.detail !== undefined) return formatDetail(err.data.detail);
  if (err.body && err.body.detail !== undefined) return formatDetail(err.body.detail);
  if (typeof err.message === "string" && err.message) return err.message;
  return "请求失败";
}

function formatDetail(detail) {
  if (detail == null || detail === "") return "请求失败";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (item && typeof item === "object") {
        const loc = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
        const msg = item.msg || item.message || JSON.stringify(item);
        return loc ? loc + ": " + msg : msg;
      }
      return String(item);
    }).join("\n");
  }
  try { return JSON.stringify(detail); } catch (_err) { return String(detail); }
}

function esc(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[ch]));
}
