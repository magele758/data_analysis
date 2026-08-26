// Pipeline-centric dashboard. Every stage runs against ONE analytical session, so
// the DB-connector path and the trace path share the same engine. Telemetry
// collection is NOT here — it is an optional demo under examples/.

const SESSION_ID = 'dashboard-' + Math.random().toString(36).slice(2, 8);
const TRACE_DS = 'demo_traces';
const BIZ_DS = 'demo_sales';

// Sample trace/telemetry spans used as the Path-B data source for the demo.
const SAMPLE_TRACES = [
  { event_name:'$pageview', event_type:'pageview', user_id:'u1', session_id:'s1', trace_id:'t1', span_id:'a1', page_path:'/home', timestamp_ms:1 },
  { event_name:'view_item', event_type:'custom', user_id:'u1', session_id:'s1', trace_id:'t1', span_id:'a2', parent_span_id:'a1', page_path:'/product', timestamp_ms:2, duration_ms:120 },
  { event_name:'add_to_cart', event_type:'custom', user_id:'u1', session_id:'s1', trace_id:'t1', span_id:'a3', parent_span_id:'a2', page_path:'/cart', timestamp_ms:3, duration_ms:80 },
  { event_name:'purchase_success', event_type:'custom', user_id:'u1', session_id:'s1', trace_id:'t1', span_id:'a4', parent_span_id:'a3', page_path:'/success', timestamp_ms:4, duration_ms:200 },
  { event_name:'$pageview', event_type:'pageview', user_id:'u2', session_id:'s2', trace_id:'t2', span_id:'b1', page_path:'/home', timestamp_ms:1 },
  { event_name:'view_item', event_type:'custom', user_id:'u2', session_id:'s2', trace_id:'t2', span_id:'b2', parent_span_id:'b1', page_path:'/product', timestamp_ms:2, duration_ms:90 },
  { event_name:'add_to_cart', event_type:'custom', user_id:'u2', session_id:'s2', trace_id:'t2', span_id:'b3', parent_span_id:'b2', page_path:'/cart', timestamp_ms:3, duration_ms:75 },
  { event_name:'$error', event_type:'error', user_id:'u3', session_id:'s3', trace_id:'t3', span_id:'c1', page_path:'/cart', timestamp_ms:1, properties:{ message:'NullPointer' } },
];

let ingested = false;

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('session-badge').textContent = SESSION_ID;
  document.querySelectorAll('.stage-pill').forEach(p =>
    p.addEventListener('click', () => showStage(p.dataset.stage)));
  showStage('ingest');
});

function showStage(stage) {
  document.querySelectorAll('[data-stage-pane]').forEach(p => p.classList.add('hidden'));
  const pane = document.getElementById('pane-' + stage);
  if (pane) pane.classList.remove('hidden');
  document.querySelectorAll('.stage-pill').forEach(p =>
    p.classList.toggle('active', p.dataset.stage === stage));
}

function markDone(stage) {
  const pill = document.querySelector(`.stage-pill[data-stage="${stage}"]`);
  if (pill) pill.classList.add('done');
}

function setOut(id, text, ok = true) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('text-emerald-400', ok);
  el.classList.toggle('text-rose-500', !ok);
}

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || (`HTTP ${res.status}`));
  return data;
}

function pretty(obj) { return JSON.stringify(obj, null, 2); }

// ---- 01 Ingest ----
async function ingestTraces() {
  try {
    const r = await api('POST', '/api/v1/import/traces', {
      records: SAMPLE_TRACES, dataset_name: TRACE_DS, session_id: SESSION_ID,
    });
    ingested = true;
    markDone('ingest');
    setOut('out-ingest', `✔ Path B: 导入 ${r.row_count} 条 trace span/event → 表 '${r.dataset_name}'\n列: ${r.columns.join(', ')}`);
  } catch (e) { setOut('out-ingest', '✘ 摄取失败: ' + e.message, false); }
}

async function ingestBusiness() {
  try {
    // Path A demo without external DB: materialize a business fact table in-session.
    const sql = `SELECT * FROM (VALUES
      ('East','Electronics',120.5,3),('West','Electronics',90.0,2),
      ('East','Grocery',200.0,5),('West','Grocery',75.5,1),
      ('North','Electronics',300.0,7)) AS t(region, category, sales, qty)`;
    await api('POST', '/api/v1/tools/sql', { session_id: SESSION_ID, sql_query: `CREATE OR REPLACE TABLE ${BIZ_DS} AS ${sql}`, limit: 1 })
      .catch(async () => { await ingestTraces(); }); // sandbox blocks CREATE; fall back to trace path
    setOut('out-ingest', `✔ Path A 示例业务表尝试建立（若沙箱只读则回退 trace 导入）。会话: ${SESSION_ID}`);
    markDone('ingest');
  } catch (e) { setOut('out-ingest', '业务数据入口: ' + e.message, false); }
}

async function ensureIngested() { if (!ingested) await ingestTraces(); }

// ---- 02 Transform ----
async function runTransform() {
  try {
    await ensureIngested();
    const r = await api('POST', '/api/v1/transform/clean', {
      session_id: SESSION_ID, source_table: TRACE_DS, target_table: TRACE_DS + '_clean',
      dedup_keys: ['event_id'],
    });
    markDone('transform');
    setOut('out-transform', '✔ 清洗完成:\n' + pretty(r));
  } catch (e) { setOut('out-transform', '清洗: ' + e.message, false); }
}

// ---- 03 Model ----
async function loadModel() {
  try {
    const tables = await api('GET', '/api/v1/catalog/tables');
    const metrics = await api('GET', '/api/v1/catalog/metrics');
    const el = document.getElementById('out-model');
    const trows = (tables.tables || []).map(t =>
      `<div class="flex justify-between border-b border-white/5 py-1"><span class="mono text-indigo-400">${t.dataset_name}</span><span class="text-slate-500">${t.row_count ?? '?'} 行 · ${(t.tags||[]).join(',')}</span></div>`).join('');
    const mrows = (metrics.metrics || []).map(m =>
      `<span class="inline-block px-2 py-0.5 rounded bg-slate-800 text-slate-300 mr-1 mb-1 mono">${m.name || m.metric_name}</span>`).join('') || '<span class="text-slate-500">（暂无指标）</span>';
    el.innerHTML = `<div class="font-semibold text-slate-200 mb-1">数据资产目录</div>${trows || '<span class="text-slate-500">空</span>'}<div class="font-semibold text-slate-200 mt-3 mb-1">语义指标</div>${mrows}`;
    markDone('model');
  } catch (e) { document.getElementById('out-model').textContent = '建模: ' + e.message; }
}

// ---- 04 Analyze ----
async function runEDA() {
  try {
    await ensureIngested();
    const r = await api('POST', '/api/v1/tools/eda', { session_id: SESSION_ID, dataset_name: TRACE_DS });
    markDone('analyze');
    setOut('out-analyze', '✔ EDA 画像:\n' + (r.summary_text || pretty(r.statistics)).slice(0, 900), true);
  } catch (e) { setOut('out-analyze', 'EDA: ' + e.message, false); }
}

async function runFunnel() {
  try {
    await ensureIngested();
    const r = await api('POST', '/api/v1/analytics/funnel', {
      session_id: SESSION_ID, dataset_name: TRACE_DS,
      steps: ['view_item', 'add_to_cart', 'purchase_success'],
    });
    markDone('analyze');
    setOut('out-analyze', `✔ 漏斗 (trace 数据上运行):\n总转化率 ${(r.overall_conversion_rate*100).toFixed(1)}% · 起始 ${r.initial_users} → 成单 ${r.final_converted_users}\n` + pretty(r.steps), true);
  } catch (e) { setOut('out-analyze', '漏斗: ' + e.message, false); }
}

async function runWaterfall() {
  try {
    await ensureIngested();
    const r = await api('GET', `/api/v1/analytics/trace/t1?session_id=${SESSION_ID}&dataset_name=${TRACE_DS}`);
    markDone('analyze');
    setOut('out-analyze', `✔ Trace t1 span 瀑布 (${r.total_spans} spans):\n` + pretty(r.spans), true);
  } catch (e) { setOut('out-analyze', '瀑布: ' + e.message, false); }
}

// ---- 05 Quality ----
async function runQuality() {
  try {
    await ensureIngested();
    const r = await api('POST', '/api/v1/observability/assert', {
      session_id: SESSION_ID, table: TRACE_DS,
      rules: [
        { type: 'not_null', column: 'event_id' },
        { type: 'unique', column: 'event_id' },
        { type: 'not_null', column: 'trace_id' },
      ],
    });
    markDone('quality');
    setOut('out-quality', '✔ 质量断言:\n' + pretty(r), true);
  } catch (e) { setOut('out-quality', '质量: ' + e.message, false); }
}

// ---- 06 Activate ----
async function runActivate() {
  try {
    await ensureIngested();
    const r = await api('POST', '/api/v1/retl/audience', {
      session_id: SESSION_ID, source_table: TRACE_DS,
      filter_sql: "event_type = 'error'", format_type: 'json', limit: 50,
    });
    markDone('activate');
    setOut('out-activate', '✔ 受众导出 (error 事件人群):\n' + pretty(r), true);
  } catch (e) { setOut('out-activate', '激活: ' + e.message, false); }
}

// ---- One-click end-to-end ----
async function runFullPipeline() {
  await ingestTraces();
  await runTransform();
  await loadModel();
  await runFunnel();
  await runQuality();
  await runActivate();
  showStage('analyze');
}
