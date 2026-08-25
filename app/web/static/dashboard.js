let funnelChart = null;
let flowChart = null;
let lineageChart = null;

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  loadOverviewData();
  startRealtimeStream();
});

function initTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      const target = tab.getAttribute('data-tab');
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.add('hidden'));
      const activePane = document.getElementById('pane-' + target);
      if (activePane) activePane.classList.remove('hidden');

      if (target === 'ontology') { loadOntologySchema(); loadOntologyAudits(); }
      if (target === 'catalog') { loadCatalogTables(); loadSemanticMetrics(); loadLineageGraph(); }
      if (target === 'transform') loadDagModels();
      if (target === 'funnel') loadFunnelData();
      if (target === 'flow') loadFlowData();
      if (target === 'retention') loadRetentionData();
      if (target === 'replay') loadSessionsList();
      if (target === 'traces') loadRealtimeLogs();
    });
  });
}

// 1. Overview
async function loadOverviewData() {
  try {
    const res = await fetch('/api/v1/analytics/pages');
    const data = await res.json();
    if (data.summary) {
      document.getElementById('stat-events').textContent = data.summary.total_events || 0;
      document.getElementById('stat-uv').textContent = data.summary.total_uv || 0;
      document.getElementById('stat-sessions').textContent = data.summary.total_sessions || 0;
      document.getElementById('stat-errors').textContent = data.summary.total_errors || 0;
    }

    const tbody = document.getElementById('page-table-body');
    tbody.innerHTML = '';
    (data.pages || []).forEach(p => {
      const tr = document.createElement('tr');
      tr.className = 'border-b border-slate-700/50 hover:bg-slate-700/30 text-sm';
      tr.innerHTML = `
        <td class="py-3 px-4 font-mono text-sky-400">${p.page_path}</td>
        <td class="py-3 px-4 font-semibold">${p.pv}</td>
        <td class="py-3 px-4 text-slate-300">${p.uv}</td>
        <td class="py-3 px-4 text-slate-300">${p.sessions}</td>
        <td class="py-3 px-4 text-emerald-400">${p.avg_dwell_seconds}s</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Failed to load overview:', err);
  }
}

// 2. Catalog & Lineage
async function loadCatalogTables() {
  try {
    const res = await fetch('/api/v1/catalog/tables');
    const data = await res.json();
    const list = document.getElementById('catalog-table-list');
    list.innerHTML = '';
    (data.tables || []).forEach(t => {
      const d = document.createElement('div');
      d.className = 'p-3 bg-slate-900/90 rounded border border-slate-800 text-xs space-y-1';
      d.innerHTML = `
        <div class="flex justify-between items-center">
          <span class="font-bold text-sky-400 font-mono">${t.dataset_name}</span>
          <span class="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">${t.table_type}</span>
        </div>
        <div class="text-slate-400">${t.description || '暂无描述'}</div>
        <div class="text-[11px] text-slate-500 font-mono">行数: ${t.row_count:,} | 列数: ${t.column_count} | 标签: ${(t.tags||[]).join(', ')}</div>
      `;
      list.appendChild(d);
    });
  } catch (e) {}
}

async function loadSemanticMetrics() {
  try {
    const res = await fetch('/api/v1/catalog/metrics');
    const data = await res.json();
    const list = document.getElementById('semantic-metrics-list');
    list.innerHTML = '';
    (data.metrics || []).forEach(m => {
      const d = document.createElement('div');
      d.className = 'p-3 bg-slate-900/90 rounded border border-slate-800 text-xs space-y-1';
      d.innerHTML = `
        <div class="flex justify-between items-center">
          <span class="font-bold text-indigo-400 font-mono">${m.name}</span>
          <span class="px-2 py-0.5 rounded text-[10px] bg-indigo-950 text-indigo-300">${m.aggregation_type}</span>
        </div>
        <div class="text-slate-300 font-mono">公式: <code class="text-amber-300">${m.formula}</code> (表: ${m.table_name})</div>
      `;
      list.appendChild(d);
    });
  } catch (e) {}
}

async function loadLineageGraph() {
  try {
    const res = await fetch('/api/v1/catalog/lineage');
    const data = await res.json();
    if (!lineageChart) {
      lineageChart = echarts.init(document.getElementById('lineage-graph-container'));
    }
    const option = {
      backgroundColor: 'transparent',
      tooltip: {},
      series: [
        {
          type: 'graph',
          layout: 'force',
          symbolSize: 40,
          roam: true,
          label: { show: true, color: '#e2e8f0', fontSize: 11 },
          edgeSymbol: ['circle', 'arrow'],
          edgeSymbolSize: [4, 8],
          edgeLabel: { fontSize: 10 },
          data: data.nodes || [],
          links: data.edges || [],
          lineStyle: { color: '#6366f1', curveness: 0.2, width: 2 }
        }
      ]
    };
    lineageChart.setOption(option);
  } catch (e) {}
}

// 3. Transform DAG
async function loadDagModels() {
  try {
    const res = await fetch('/api/v1/transform/dag/models');
    const data = await res.json();
    const container = document.getElementById('dag-models-container');
    container.innerHTML = '';
    (data.models || []).forEach(m => {
      const d = document.createElement('div');
      d.className = 'p-4 bg-slate-900 rounded-lg border border-slate-800 space-y-2 text-xs';
      d.innerHTML = `
        <div class="font-bold text-emerald-400 font-mono text-sm">${m.name}</div>
        <div class="text-slate-400">物化策略: <span class="uppercase text-slate-200">${m.materialization}</span></div>
        <div class="text-slate-500">依赖模型: ${(m.depends_on || []).join(', ') || '无 (Root)'}</div>
        <pre class="bg-slate-950 p-2 rounded text-[10px] text-slate-400 overflow-x-auto">${m.sql}</pre>
      `;
      container.appendChild(d);
    });
  } catch (e) {}
}

async function runDagPipeline() {
  try {
    const res = await fetch('/api/v1/transform/dag/run?session_id=default_session', { method: 'POST' });
    const data = await res.json();
    const box = document.getElementById('dag-execution-result');
    box.classList.remove('hidden');
    box.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    alert('DAG 执行失败，请确认 Session 状态');
  }
}

// 4. Reverse ETL
async function triggerReverseSync() {
  const source = document.getElementById('retl-source-table').value;
  const destUri = document.getElementById('retl-dest-uri').value;
  const destTable = document.getElementById('retl-dest-table').value;

  try {
    const res = await fetch('/api/v1/retl/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: 'default_session',
        source_table: source,
        dest_conn_str: destUri,
        dest_table_name: destTable
      })
    });
    const data = await res.json();
    document.getElementById('retl-sync-msg').textContent = `✅ 同步成功: 已同步 ${data.synced_rows || 0} 行至 ${destTable}`;
  } catch (e) {
    document.getElementById('retl-sync-msg').textContent = '❌ 同步失败: ' + e.message;
  }
}

async function triggerWebhookAlert() {
  const platform = document.getElementById('webhook-platform').value;
  const title = document.getElementById('webhook-title').value;
  const msg = document.getElementById('webhook-msg').value;

  try {
    const res = await fetch('/api/v1/retl/alert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        webhook_url: 'http://127.0.0.1:8000/api/v1/mock_webhook',
        platform: platform,
        title: title,
        message: msg,
        extra_metrics: { '转化率波动': '-12.5%', '核心拖累项': '华东大区-电子' }
      })
    });
    const data = await res.json();
    document.getElementById('webhook-send-msg').textContent = '✅ 告警卡片模拟下发成功 (Payload 已构建)';
  } catch (e) {
    document.getElementById('webhook-send-msg').textContent = '❌ 下发失败';
  }
}

// 5. Data Quality
async function runQualityAssertions() {
  try {
    const res = await fetch('/api/v1/observability/assert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: 'default_session',
        table: 'events',
        rules: [
          { type: 'not_null', column: 'event_id' },
          { type: 'not_null', column: 'event_name' },
          { type: 'unique', column: 'event_id' },
          { type: 'row_count', min_rows: 1, max_rows: 1000000 }
        ]
      })
    });
    const data = await res.json();
    const card = document.getElementById('quality-report-card');
    card.classList.remove('hidden');
    document.getElementById('quality-health-score').textContent = (data.data_health_score || 100) + '%';
    
    const list = document.getElementById('quality-rules-list');
    list.innerHTML = '';
    (data.assertion_results || []).forEach(r => {
      const p = document.createElement('div');
      p.className = 'p-2 rounded bg-slate-950 flex justify-between items-center';
      p.innerHTML = `
        <span class="text-slate-300">规则: ${r.assertion} (${r.column || '全表'})</span>
        <span class="${r.passed ? 'text-emerald-400' : 'text-rose-400'} font-bold">${r.passed ? 'PASSED ✅' : 'FAILED ❌ (异常数:' + r.unexpected_count + ')'}</span>
      `;
      list.appendChild(p);
    });
  } catch (e) {}
}

// 6. Realtime Logs & Traces
let liveInterval = null;
function startRealtimeStream() {
  if (liveInterval) clearInterval(liveInterval);
  liveInterval = setInterval(loadRealtimeLogs, 3000);
}

async function loadRealtimeLogs() {
  try {
    const res = await fetch('/api/v1/collect/realtime?limit=30');
    const data = await res.json();
    const container = document.getElementById('realtime-log-container');
    if (!container) return;
    
    container.innerHTML = '';
    (data.events || []).forEach(ev => {
      const row = document.createElement('div');
      row.className = 'p-2.5 bg-slate-900/90 rounded border border-slate-800 flex items-center justify-between text-xs font-mono';
      const isErr = ev.event_type === 'error';
      row.innerHTML = `
        <div class="flex items-center space-x-3">
          <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold ${isErr ? 'bg-rose-900/60 text-rose-300 border border-rose-700' : 'bg-sky-900/60 text-sky-300 border border-sky-700'}">
            ${ev.event_type}
          </span>
          <span class="text-slate-200 font-medium">${ev.event_name}</span>
          <span class="text-slate-400">${ev.page_path || '/'}</span>
          <span class="text-slate-500 text-[11px] cursor-pointer hover:text-indigo-400" onclick="inspectTrace('${ev.trace_id}')">Trace: ${ev.trace_id ? ev.trace_id.substring(0, 10) + '...' : 'N/A'}</span>
        </div>
        <span class="text-slate-500">${ev.created_at || ''}</span>
      `;
      container.appendChild(row);
    });
  } catch (e) {}
}

async function inspectTrace(traceId) {
  if (!traceId) return;
  document.getElementById('trace-id-input').value = traceId;
  searchTrace();
}

async function searchTrace() {
  const traceId = document.getElementById('trace-id-input').value.trim();
  if (!traceId) return;

  try {
    const res = await fetch(`/api/v1/analytics/trace/${traceId}`);
    const data = await res.json();
    const view = document.getElementById('trace-waterfall-view');
    view.innerHTML = '';

    if (!data.spans || data.spans.length === 0) {
      view.innerHTML = '<div class="text-slate-400 text-sm p-4">未找到该 Trace 对应的 Span 链路</div>';
      return;
    }

    data.spans.forEach((sp) => {
      const card = document.createElement('div');
      card.className = 'p-3 bg-slate-800 rounded-lg border border-slate-700 space-y-1';
      card.innerHTML = `
        <div class="flex justify-between items-center text-xs">
          <span class="font-bold text-sky-400">Span: ${sp.name} (${sp.service_name})</span>
          <span class="px-2 py-0.5 rounded text-[10px] ${sp.status_code === 'OK' ? 'bg-emerald-900 text-emerald-300' : 'bg-rose-900 text-rose-300'}">${sp.status_code}</span>
        </div>
        <div class="text-xs text-slate-400 font-mono">Span ID: ${sp.span_id} | Parent: ${sp.parent_span_id || 'Root'}</div>
        <div class="text-xs text-slate-300">Attributes: ${JSON.stringify(sp.attributes || {})}</div>
      `;
      view.appendChild(card);
    });
  } catch (err) {
    console.error(err);
  }
}

// 7. Funnel Analysis
async function loadFunnelData() {
  const stepsInput = document.getElementById('funnel-steps-input').value;
  const steps = stepsInput.split(',').map(s => s.trim()).filter(Boolean);

  try {
    const res = await fetch('/api/v1/analytics/funnel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ steps: steps })
    });
    const data = await res.json();

    document.getElementById('funnel-overall-rate').textContent = (data.overall_conversion_rate * 100).toFixed(1) + '%';
    document.getElementById('funnel-initial-users').textContent = data.initial_users || 0;
    document.getElementById('funnel-final-users').textContent = data.final_converted_users || 0;

    if (!funnelChart) {
      funnelChart = echarts.init(document.getElementById('funnel-chart-container'));
    }

    const chartData = (data.steps || []).map(s => ({
      name: `${s.step_name} (${s.user_count}人, ${(s.step_conversion_rate * 100).toFixed(1)}%)`,
      value: s.user_count
    }));

    const option = {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', formatter: '{b}' },
      series: [
        {
          name: '漏斗转化',
          type: 'funnel',
          left: '10%',
          top: 30,
          bottom: 30,
          width: '80%',
          minSize: '15%',
          maxSize: '100%',
          sort: 'descending',
          gap: 4,
          label: { show: true, position: 'inside', color: '#fff', fontSize: 12 },
          itemStyle: { borderColor: '#1e293b', borderWidth: 2 },
          data: chartData
        }
      ]
    };
    funnelChart.setOption(option);
  } catch (err) {
    console.error('Funnel error:', err);
  }
}

// 8. User Flow (Sankey)
async function loadFlowData() {
  try {
    const res = await fetch('/api/v1/analytics/flow');
    const data = await res.json();

    if (!flowChart) {
      flowChart = echarts.init(document.getElementById('flow-chart-container'));
    }

    if (!data.nodes || data.nodes.length === 0) {
      document.getElementById('flow-chart-container').innerHTML = '<div class="text-slate-400 p-8 text-center">暂无足够页面转移数据</div>';
      return;
    }

    const option = {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', triggerOn: 'mousemove' },
      series: [
        {
          type: 'sankey',
          layout: 'none',
          emphasis: { focus: 'adjacency' },
          data: data.nodes,
          links: data.links,
          lineStyle: { color: 'gradient', curveness: 0.5, opacity: 0.4 },
          label: { color: '#e2e8f0', fontSize: 11 }
        }
      ]
    };
    flowChart.setOption(option);
  } catch (err) {
    console.error('Flow error:', err);
  }
}

// 9. Retention Matrix
async function loadRetentionData() {
  try {
    const res = await fetch('/api/v1/analytics/retention?days=7');
    const data = await res.json();
    const thead = document.getElementById('retention-thead');
    const tbody = document.getElementById('retention-tbody');

    thead.innerHTML = '<th class="py-3 px-4 text-left">首次活跃日期</th><th class="py-3 px-4">新用户规模</th>';
    for (let i = 0; i <= (data.days_analyzed || 7); i++) {
      thead.innerHTML += `<th class="py-3 px-4">第${i}天</th>`;
    }

    tbody.innerHTML = '';
    (data.retention_matrix || []).forEach(row => {
      let tr = `<tr class="border-b border-slate-700/50 hover:bg-slate-700/30 text-sm">`;
      tr += `<td class="py-3 px-4 font-mono font-medium text-slate-200">${row.cohort_date}</td>`;
      tr += `<td class="py-3 px-4 text-center font-bold text-sky-400">${row.cohort_size}</td>`;
      for (let i = 0; i <= (data.days_analyzed || 7); i++) {
        const item = row[`day_${i}`] || { count: 0, rate: 0 };
        const percent = (item.rate * 100).toFixed(1);
        const opacity = Math.min(Math.max(item.rate, 0.05), 0.9);
        tr += `<td class="py-3 px-4 text-center text-xs font-mono" style="background-color: rgba(79, 70, 229, ${opacity}); color: #fff;">${percent}%<br><span class="text-[10px] text-slate-300">(${item.count})</span></td>`;
      }
      tr += `</tr>`;
      tbody.innerHTML += tr;
    });
  } catch (err) {
    console.error('Retention error:', err);
  }
}

// 10. Session Action Replay
async function loadSessionsList() {
  try {
    const res = await fetch('/api/v1/analytics/sessions');
    const data = await res.json();
    const sel = document.getElementById('replay-session-select');
    sel.innerHTML = '<option value="">-- 请选择要复盘的会话 Session --</option>';
    (data.sessions || []).forEach(s => {
      sel.innerHTML += `<option value="${s.session_id}">${s.session_id} (${s.user_id}) - ${s.event_count}事件 ${s.error_count > 0 ? '⚠️含异常' : ''}</option>`;
    });
  } catch (err) {}
}

async function loadSessionTimeline() {
  const sessionId = document.getElementById('replay-session-select').value;
  if (!sessionId) return;

  try {
    const res = await fetch(`/api/v1/analytics/replay/${sessionId}`);
    const data = await res.json();
    const container = document.getElementById('replay-timeline-container');
    container.innerHTML = '';

    (data.timeline || []).forEach((act) => {
      const isErr = act.event_type === 'error';
      const isClick = act.event_type === 'click';
      const isPv = act.event_type === 'pageview';

      const dotColor = isErr ? 'bg-rose-500' : (isClick ? 'bg-amber-400' : (isPv ? 'bg-sky-400' : 'bg-indigo-400'));

      const div = document.createElement('div');
      div.className = 'relative pl-8 pb-6 border-l-2 border-slate-700 last:border-l-0';
      div.innerHTML = `
        <div class="absolute -left-[9px] top-0 w-4 h-4 rounded-full ${dotColor} ring-4 ring-slate-900 flex items-center justify-center"></div>
        <div class="p-3 bg-slate-800/90 rounded-lg border border-slate-700 text-xs space-y-1">
          <div class="flex justify-between text-slate-400">
            <span class="font-bold text-slate-200 uppercase">${act.event_type}: ${act.event_name}</span>
            <span class="font-mono text-[11px]">${act.created_at}</span>
          </div>
          <div class="text-slate-300">页面: <span class="text-sky-400 font-mono">${act.page_path}</span></div>
          ${act.properties.selector ? `<div class="text-slate-400">点击元素: <code class="text-amber-300">${act.properties.selector}</code> (文本: "${act.properties.text || ''}")</div>` : ''}
          ${act.properties.message ? `<div class="text-rose-400 font-mono font-semibold">❌ 错误信息: ${act.properties.message}</div>` : ''}
        </div>
      `;
      container.appendChild(div);
    });
  } catch (err) {
    console.error(err);
  }
}

// 11. Palantir Ontology Functions
let ontologyChart = null;

async function loadOntologySchema() {
  try {
    const res = await fetch('/api/v1/ontology/schema');
    const data = await res.json();
    
    // Render Object Types
    const objList = document.getElementById('ontology-objects-list');
    objList.innerHTML = '';
    (data.object_types || []).forEach(o => {
      const d = document.createElement('div');
      d.className = 'p-3 bg-slate-900 rounded border border-slate-800 text-xs space-y-1.5';
      d.innerHTML = `
        <div class="flex justify-between items-center">
          <span class="font-bold text-sky-400 font-mono text-sm">${o.name}</span>
          <span class="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">PK: ${o.primary_key}</span>
        </div>
        <div class="text-slate-400">${o.description || '业务实体对象'}</div>
        <div class="text-[11px] text-slate-500 font-mono">属性: ${(o.properties||[]).join(', ')}</div>
        ${o.available_actions.length > 0 ? `<div class="text-[11px] text-indigo-400 font-mono">⚡ 动作: ${o.available_actions.join(', ')}</div>` : ''}
      `;
      objList.appendChild(d);
    });

    // Render Actions List
    const actRes = await fetch('/api/v1/ontology/actions');
    const actData = await actRes.json();
    const actList = document.getElementById('ontology-actions-list');
    actList.innerHTML = '';
    (actData.action_types || []).forEach(a => {
      const d = document.createElement('div');
      d.className = 'p-3 bg-slate-900 rounded border border-slate-800 text-xs space-y-1';
      d.innerHTML = `
        <div class="flex justify-between items-center">
          <span class="font-bold text-emerald-400 font-mono">${a.name}</span>
          <span class="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300">${a.target_object_type}</span>
        </div>
        <div class="text-slate-400">${a.description || '业务闭环动作'}</div>
        <div class="text-[11px] text-slate-500 font-mono">处理器: ${a.handler_type}</div>
      `;
      actList.appendChild(d);
    });

    // Render Ontology Graph
    if (!ontologyChart) {
      ontologyChart = echarts.init(document.getElementById('ontology-graph-container'));
    }

    const nodes = (data.object_types || []).map(o => ({
      id: o.name,
      name: `${o.name} (PK: ${o.primary_key})`,
      symbolSize: 45,
      itemStyle: { color: '#6366f1' }
    }));

    const links = (data.link_types || []).map(l => ({
      source: l.source,
      target: l.target,
      label: { show: true, formatter: l.name, fontSize: 10 }
    }));

    const option = {
      backgroundColor: 'transparent',
      tooltip: {},
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          label: { show: true, color: '#e2e8f0', fontSize: 11 },
          edgeSymbol: ['circle', 'arrow'],
          edgeSymbolSize: [4, 8],
          data: nodes,
          links: links,
          lineStyle: { color: '#38bdf8', curveness: 0.2, width: 2 }
        }
      ]
    };
    ontologyChart.setOption(option);
  } catch (e) {}
}

async function loadOntologyAudits() {
  try {
    const res = await fetch('/api/v1/ontology/audit');
    const data = await res.json();
    const list = document.getElementById('ontology-audit-list');
    list.innerHTML = '';
    (data.audits || []).forEach(a => {
      const d = document.createElement('div');
      d.className = 'p-2.5 bg-slate-900 rounded border border-slate-800 flex justify-between items-center text-[11px]';
      d.innerHTML = `
        <div>
          <span class="text-indigo-400 font-bold">${a.action_name}</span> 
          <span class="text-slate-400">-> [${a.target_object_type}#${a.target_instance_id}]</span>
        </div>
        <div class="flex items-center space-x-2">
          <span class="px-2 py-0.5 rounded text-[10px] ${a.status === 'SUCCESS' ? 'bg-emerald-950 text-emerald-400' : 'bg-amber-950 text-amber-400'}">${a.status}</span>
          <span class="text-slate-500">${a.executed_at}</span>
        </div>
      `;
      list.appendChild(d);
    });
  } catch (e) {}
}
