// Analyze stage. Tabs call existing /api/v1 routes only.
// mount(container, ctx) uses ctx.sessionId(), ctx.api(method, path, body), ctx.notify(message).
(function () {
  'use strict';

  var STYLE_ID = 'sec-analyze-style';
  var MAX_ROWS = 40;
  var MAX_NESTED = 24;
  var vegaLoading = null;
  var echartsLoading = null;
  var rememberedTab = 'eda';
  var rememberedDataset = '';
  var mountSeq = 0;

  var AGG = [
    ['SUM', 'SUM'],
    ['AVG', 'AVG'],
    ['COUNT', 'COUNT'],
    ['MIN', 'MIN'],
    ['MAX', 'MAX']
  ];

  var TEST_TYPES = [
    ['independent_t_test', '独立样本 t 检验'],
    ['paired_t_test', '配对 t 检验'],
    ['one_way_anova', '单因素方差'],
    ['two_way_anova', '双因素方差'],
    ['chi_square', '卡方'],
    ['mann_whitney', 'Mann-Whitney']
  ];

  var TITLES = {
    hierarchy: '层级',
    branches: '分支',
    columns: '列',
    steps: '步骤',
    forecasts: '预测值',
    historical_preview: '历史序列',
    outliers: '异常点',
    top_contributors: '头部贡献',
    series_preview: '序列预览',
    sun_shapley: 'Sun-Shapley',
    top_positive_drivers: '正向驱动',
    top_negative_drivers: '负向驱动',
    change_points: '变点',
    nodes: '节点',
    links: '流转',
    retention_matrix: '留存矩阵',
    cohorts: '队列',
    quantiles: '分位数',
    top_categories: '高频类别',
    evidence: '证据',
    sql: 'SQL',
    caveats: '说明',
    coefficients: '系数',
    holdout: '留出比较'
  };

  var TABS = [
    {
      id: 'eda',
      label: 'EDA',
      method: 'POST',
      path: '/api/v1/tools/eda',
      hint: '列级画像、分位数与质量分。',
      fields: []
    },
    {
      id: 'olap',
      label: 'OLAP',
      method: 'POST',
      path: '/api/v1/tools/olap',
      hint: '勾选 cube 时服务端按 GROUP BY CUBE 聚合；只勾上卷时按 ROLLUP。两者都勾选时以 cube 为准。',
      fields: [
        { name: 'dimensions', label: '维度', type: 'list', required: true, placeholder: 'region, category' },
        { name: 'metrics', label: '指标', type: 'list', required: true, placeholder: 'sales, profit' },
        { name: 'agg_funcs', label: '聚合函数', type: 'list', placeholder: 'SUM, AVG', options: '与指标一一对应，留空则全部为 SUM' },
        { name: 'filters', label: '过滤', type: 'text', placeholder: "region = 'east'" },
        { name: 'order_by', label: '排序', type: 'text', placeholder: 'sales_sum DESC' },
        { name: 'limit', label: '行数上限', type: 'number', defaultValue: '100', min: '1', step: '1' },
        { name: 'rollup', label: '上卷 ROLLUP', type: 'checkbox' },
        { name: 'cube', label: '立方体 CUBE', type: 'checkbox' }
      ]
    },
    {
      id: 'driver',
      label: '归因',
      method: 'POST',
      path: '/api/v1/tools/driver_analysis',
      hint: '结果含证据与瀑布图。',
      note: '比率列和体量列都填写时，才按 Laspeyres 做比率×体量拆分，且只使用维度路径的第一维。后续维度不会做比率分解。只填其中一列时，仍按指标做聚合比较。',
      fields: [
        { name: 'target_metric', label: '指标', type: 'text', required: true, placeholder: 'sales' },
        { name: 'dimension_path', label: '维度路径', type: 'list', required: true, placeholder: 'region, category' },
        { name: 'base_filter', label: '基期条件', type: 'text', required: true, placeholder: 'month = 1' },
        { name: 'current_filter', label: '当期条件', type: 'text', required: true, placeholder: 'month = 2' },
        { name: 'agg_func', label: '聚合', type: 'select', options: AGG, defaultValue: 'SUM' },
        { name: 'top_k', label: '每层条数', type: 'number', defaultValue: '5', min: '1', step: '1' },
        { name: 'rate_col', label: '比率列', type: 'text', placeholder: 'price' },
        { name: 'volume_col', label: '体量列', type: 'text', placeholder: 'qty' }
      ]
    },
    {
      id: 'test',
      label: '检验',
      method: 'POST',
      path: '/api/v1/tools/spss_test',
      hint: '配对 t 检验时，分组列是第二列数值。双因素方差需要第二因子。Mann-Whitney 需要恰好两组。',
      fields: [
        { name: 'test_type', label: '检验', type: 'select', required: true, options: TEST_TYPES, defaultValue: 'independent_t_test' },
        { name: 'dependent_var', label: '因变量', type: 'text', required: true, placeholder: 'sales' },
        { name: 'group_var', label: '分组列', type: 'text', required: true, placeholder: 'region' },
        { name: 'factor_b', label: '第二因子', type: 'text', placeholder: 'category' },
        { name: 'alpha', label: '显著性水平', type: 'number', defaultValue: '0.05', min: '0', max: '1', step: '0.01' }
      ]
    },
    {
      id: 'regression',
      label: '回归',
      method: 'POST',
      path: '/api/v1/tools/spss_regression',
      hint: '线性或逻辑回归。响应不含散点图。',
      fields: [
        { name: 'dependent_var', label: '因变量', type: 'text', required: true, placeholder: 'sales' },
        { name: 'independent_vars', label: '自变量', type: 'list', required: true, placeholder: 'price, qty' },
        { name: 'model_type', label: '模型', type: 'select', options: [['ols', '线性 OLS'], ['logistic', '逻辑回归']], defaultValue: 'ols' }
      ]
    },
    {
      id: 'variance',
      label: '方差分解',
      method: 'POST',
      path: '/api/v1/tools/variance_decomposition',
      hint: '指标列不要同时写进维度。',
      fields: [
        { name: 'metric', label: '指标', type: 'text', required: true, placeholder: 'sales' },
        { name: 'dimensions', label: '维度', type: 'list', required: true, placeholder: 'region, category' },
        { name: 'filters', label: '过滤', type: 'text', placeholder: "month = 2" }
      ]
    },
    {
      id: 'outliers',
      label: '异常',
      method: 'POST',
      path: '/api/v1/insights/outliers',
      hint: 'z 分数、四分位距或孤立森林。',
      fields: [
        { name: 'metric', label: '指标', type: 'text', required: true, placeholder: 'sales' },
        { name: 'dimension_cols', label: '维度列', type: 'list', placeholder: 'region, category' },
        { name: 'method', label: '方法', type: 'select', options: [['z_score', 'z 分数'], ['iqr', '四分位距'], ['isolation_forest', '孤立森林']], defaultValue: 'z_score' },
        { name: 'threshold', label: '阈值', type: 'number', defaultValue: '3', step: '0.1' },
        { name: 'top_k', label: '样本条数', type: 'number', defaultValue: '10', min: '1', step: '1' }
      ]
    },
    {
      id: 'trends',
      label: '趋势',
      method: 'POST',
      path: '/api/v1/insights/trends',
      hint: '按时间汇总指标后做线性趋势。',
      fields: [
        { name: 'time_col', label: '时间列', type: 'text', required: true, placeholder: 'month' },
        { name: 'metric', label: '指标', type: 'text', required: true, placeholder: 'sales' },
        { name: 'group_col', label: '分组列', type: 'text', placeholder: 'region' }
      ]
    },
    {
      id: 'dominance',
      label: '支配',
      method: 'POST',
      path: '/api/v1/insights/dominance',
      hint: '类别集中度与基尼系数。',
      fields: [
        { name: 'category_col', label: '类别列', type: 'text', required: true, placeholder: 'region' },
        { name: 'metric', label: '指标', type: 'text', required: true, placeholder: 'sales' },
        { name: 'top_k', label: '头部个数', type: 'number', defaultValue: '5', min: '1', step: '1' }
      ]
    },
    {
      id: 'funnel',
      label: '漏斗',
      method: 'POST',
      path: '/api/v1/analytics/funnel',
      hint: '按事件名顺序计算转化。需要带 event_name 与 user_id 的轨迹表。',
      fields: [
        { name: 'steps', label: '步骤', type: 'list', required: true, placeholder: 'view_item, add_to_cart, purchase_success' },
        { name: 'date_from', label: '开始时间', type: 'text', placeholder: '2024-01-01' },
        { name: 'date_to', label: '结束时间', type: 'text', placeholder: '2024-01-31' }
      ]
    },
    {
      id: 'flow',
      label: '用户流',
      method: 'GET',
      path: '/api/v1/analytics/flow',
      hint: '页面流转。图为桑基，统计量在右侧表格。',
      fields: [
        { name: 'limit', label: '路径条数', type: 'number', defaultValue: '15', min: '1', step: '1' }
      ],
      request: function (common, values) {
        return { method: 'GET', path: withQuery('/api/v1/analytics/flow', {
          session_id: common.sessionId,
          dataset_name: common.dataset,
          limit: values.limit != null ? values.limit : 15
        }) };
      }
    },
    {
      id: 'retention',
      label: '留存',
      method: 'GET',
      path: '/api/v1/analytics/retention',
      hint: '队列留存。图为热力，矩阵在右侧表格。',
      fields: [
        { name: 'days', label: '天数', type: 'number', defaultValue: '7', min: '1', step: '1' }
      ],
      request: function (common, values) {
        return { method: 'GET', path: withQuery('/api/v1/analytics/retention', {
          session_id: common.sessionId,
          dataset_name: common.dataset,
          days: values.days != null ? values.days : 7
        }) };
      }
    },
    {
      id: 'forecast',
      label: '时序预测',
      method: 'POST',
      path: '/api/v1/tools/timeseries',
      hint: '至少 10 个时间点。非 ARIMA 时服务端用指数平滑。',
      fields: [
        { name: 'time_col', label: '时间列', type: 'text', required: true, placeholder: 'month' },
        { name: 'value_col', label: '数值列', type: 'text', required: true, placeholder: 'sales' },
        { name: 'horizon', label: '预测步数', type: 'number', defaultValue: '12', min: '1', step: '1' },
        { name: 'model_type', label: '模型', type: 'select', options: [['arima', 'ARIMA'], ['holt', '指数平滑']], defaultValue: 'arima' }
      ]
    }
  ];

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      '.sec-analyze-root{background:#fff;color:#1a1d21;font:13px/1.45 "IBM Plex Sans","PingFang SC","Noto Sans SC",sans-serif;padding:2px;}',
      '.sec-analyze-root *{box-sizing:border-box;}',
      '.sec-analyze-tabs{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 10px;}',
      '.sec-analyze-tab{appearance:none;border:1px solid #d5d9de;background:#fff;color:#3c434c;border-radius:3px;padding:3px 8px;font:inherit;font-size:12px;line-height:1.3;cursor:pointer;}',
      '.sec-analyze-tab-active{background:#1a1d21;border-color:#1a1d21;color:#fff;}',
      '.sec-analyze-layout{display:grid;grid-template-columns:minmax(240px,300px) minmax(0,1fr);gap:12px;align-items:start;}',
      '@media (max-width:800px){.sec-analyze-layout{grid-template-columns:1fr;}}',
      '.sec-analyze-form,.sec-analyze-result{border:1px solid #e4e7eb;background:#fff;padding:10px;min-width:0;}',
      '.sec-analyze-result{min-height:240px;}',
      '.sec-analyze-session,.sec-analyze-endpoint,.sec-analyze-hint,.sec-analyze-note,.sec-analyze-empty{font-size:12px;color:#5c6570;margin:0 0 8px;}',
      '.sec-analyze-note{color:#3c434c;}',
      '.sec-analyze-session code,.sec-analyze-endpoint{font-family:ui-monospace,SFMono-Regular,monospace;color:#1a1d21;}',
      '.sec-analyze-field{display:flex;flex-direction:column;gap:2px;margin:0 0 8px;}',
      '.sec-analyze-field label,.sec-analyze-check{font-size:12px;color:#5c6570;}',
      '.sec-analyze-field input,.sec-analyze-field select{border:1px solid #d5d9de;background:#fff;color:#1a1d21;border-radius:3px;padding:4px 6px;font:inherit;font-size:12px;width:100%;}',
      '.sec-analyze-check{display:flex;align-items:center;gap:6px;margin:0 0 8px;}',
      '.sec-analyze-check input{margin:0;}',
      '.sec-analyze-run{border:1px solid #1a1d21;background:#1a1d21;color:#fff;border-radius:3px;padding:5px 10px;font:inherit;font-size:12px;cursor:pointer;}',
      '.sec-analyze-run:disabled{opacity:.55;cursor:default;}',
      '.sec-analyze-tab:focus-visible,.sec-analyze-run:focus-visible,.sec-analyze-field input:focus-visible,.sec-analyze-field select:focus-visible{outline:2px solid #1a1d21;outline-offset:1px;}',
      '.sec-analyze-summary{margin:0 0 8px;font-size:13px;white-space:pre-wrap;}',
      '.sec-analyze-kicker{font-size:12px;font-weight:650;margin:0 0 4px;}',
      '.sec-analyze-block{margin:0 0 8px;}',
      '.sec-analyze-block-title{margin:8px 0 4px;font-size:12px;font-weight:650;}',
      '.sec-analyze-table{width:100%;border-collapse:collapse;font-size:12px;margin:0 0 8px;}',
      '.sec-analyze-table th,.sec-analyze-table td{border-bottom:1px solid #e4e7eb;text-align:left;padding:3px 6px;vertical-align:top;word-break:break-word;}',
      '.sec-analyze-table th{color:#5c6570;font-weight:600;background:#fafbfc;}',
      '.sec-analyze-pre{margin:0 0 8px;max-height:140px;overflow:auto;background:#fafbfc;border:1px solid #e4e7eb;padding:6px;font:11px/1.4 ui-monospace,SFMono-Regular,monospace;white-space:pre-wrap;}',
      '.sec-analyze-chart{width:100%;height:280px;margin:0 0 8px;}',
      '.sec-analyze-error{border:1px solid #e7b4ae;background:#fff;color:#9d2c23;padding:8px;}',
      '.sec-analyze-error-label{font-size:11px;letter-spacing:.04em;margin:0 0 4px;}',
      '.sec-analyze-error pre{margin:0;white-space:pre-wrap;font:12px/1.4 ui-monospace,SFMono-Regular,monospace;color:#9d2c23;}'
    ].join('');
    document.head.appendChild(style);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function titleOf(key) {
    if (TITLES[key]) return TITLES[key];
    return String(key);
  }

  function isScalar(value) {
    return value == null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';
  }

  function clip(text, limit) {
    var value = String(text);
    return value.length > limit ? value.slice(0, limit) + '…' : value;
  }

  function cellText(value) {
    if (value == null) return '—';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') return String(value);
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return clip(value.map(cellText).join(', '), 400);
    if (typeof value === 'object') {
      var keys = Object.keys(value);
      if (keys.length && keys.every(function (key) { return isScalar(value[key]); })) {
        return clip(keys.map(function (key) { return key + ': ' + cellText(value[key]); }).join('; '), 400);
      }
      try { return clip(JSON.stringify(value), 400); } catch (err) { return ''; }
    }
    return String(value);
  }

  function withQuery(path, params) {
    var query = new URLSearchParams();
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (value != null && value !== '') query.set(key, String(value));
    });
    return path + '?' + query.toString();
  }

  function formatDetail(detail) {
    if (detail == null || detail === '') return '请求失败';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map(function (item) {
        if (item && typeof item === 'object') {
          var loc = Array.isArray(item.loc) ? item.loc.filter(function (part) { return part !== 'body'; }).join('.') : '';
          var msg = item.msg || item.message || '';
          if (!msg) {
            try { msg = JSON.stringify(item); } catch (err) { msg = String(item); }
          }
          return loc ? loc + ': ' + msg : msg;
        }
        return String(item);
      }).join('\n');
    }
    if (typeof detail === 'object') {
      if (detail.detail != null && detail.detail !== detail) return formatDetail(detail.detail);
      if (detail.message) return formatDetail(detail.message);
      try { return JSON.stringify(detail, null, 2); } catch (err) { return '请求失败'; }
    }
    return String(detail);
  }

  function failureDetail(err) {
    if (!err) return '请求失败';
    if (err.detail != null) return err.detail;
    if (err.message != null) return err.message;
    return err;
  }

  function currentSession(ctx) {
    if (!ctx || typeof ctx.sessionId !== 'function') return '';
    try {
      var id = ctx.sessionId();
      return id == null ? '' : String(id);
    } catch (err) {
      return '';
    }
  }

  function notify(ctx, message) {
    if (!ctx || typeof ctx.notify !== 'function') return;
    try { ctx.notify(message); } catch (err) { /* shell toast is optional */ }
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var selector = 'script[data-sec-analyze-src="' + src + '"]';
      var existing = document.querySelector(selector);
      if (existing && existing.getAttribute('data-sec-analyze-loaded') === '1') {
        resolve();
        return;
      }
      if (existing) {
        existing.addEventListener('load', function () { resolve(); }, { once: true });
        existing.addEventListener('error', function () { reject(new Error('无法加载图表脚本')); }, { once: true });
        return;
      }
      var script = document.createElement('script');
      script.src = src;
      script.async = false;
      script.setAttribute('data-sec-analyze-src', src);
      script.onload = function () {
        script.setAttribute('data-sec-analyze-loaded', '1');
        resolve();
      };
      script.onerror = function () { reject(new Error('无法加载图表脚本')); };
      document.head.appendChild(script);
    });
  }

  function ensureVega() {
    if (window.vegaEmbed) return Promise.resolve();
    if (!vegaLoading) {
      vegaLoading = Promise.resolve()
        .then(function () { return window.vega ? null : loadScript('https://cdn.jsdelivr.net/npm/vega@5'); })
        .then(function () { return window.vegaLite ? null : loadScript('https://cdn.jsdelivr.net/npm/vega-lite@5'); })
        .then(function () { return window.vegaEmbed ? null : loadScript('https://cdn.jsdelivr.net/npm/vega-embed@6'); })
        .catch(function (err) { vegaLoading = null; throw err; });
    }
    return vegaLoading;
  }

  function ensureEcharts() {
    if (window.echarts) return Promise.resolve();
    if (!echartsLoading) {
      echartsLoading = loadScript('https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js')
        .catch(function (err) { echartsLoading = null; throw err; });
    }
    return echartsLoading;
  }

  function chartKind(spec) {
    if (!spec || typeof spec !== 'object' || Array.isArray(spec)) return '';
    var schema = String(spec.$schema || '');
    if (schema.indexOf('vega') !== -1 || spec.mark || spec.encoding || spec.layer) return 'vega';
    if (spec.series || spec.xAxis || spec.yAxis) return 'echarts';
    return '';
  }

  function clearChartNode(node) {
    if (node._secAnalyzeChart && typeof node._secAnalyzeChart.dispose === 'function') {
      node._secAnalyzeChart.dispose();
    }
    if (node._secAnalyzeResize) node._secAnalyzeResize.disconnect();
    node._secAnalyzeChart = null;
    node._secAnalyzeResize = null;
    node.textContent = '';
  }

  function renderChart(node, spec) {
    var kind = chartKind(spec);
    clearChartNode(node);
    if (!kind) {
      node.textContent = '响应里的 chart_spec 无法识别。';
      return Promise.resolve();
    }
    if (kind === 'vega') {
      return ensureVega().then(function () {
        var view = Object.assign({}, spec);
        if (!view.width) view.width = 'container';
        return window.vegaEmbed(node, view, { actions: false, renderer: 'svg' });
      });
    }
    return ensureEcharts().then(function () {
      var chart = window.echarts.init(node);
      chart.setOption(spec);
      node._secAnalyzeChart = chart;
      if (typeof ResizeObserver === 'function') {
        var observer = new ResizeObserver(function () { chart.resize(); });
        observer.observe(node);
        node._secAnalyzeResize = observer;
      }
    });
  }

  function kvTable(obj) {
    var table = el('table', 'sec-analyze-table');
    var body = document.createElement('tbody');
    Object.keys(obj).forEach(function (key) {
      var row = document.createElement('tr');
      row.appendChild(el('th', '', titleOf(key)));
      row.appendChild(el('td', '', cellText(obj[key])));
      body.appendChild(row);
    });
    table.appendChild(body);
    return table;
  }

  function rowsTable(rows) {
    var columns = [];
    var seen = {};
    rows.forEach(function (row) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) return;
      Object.keys(row).forEach(function (key) {
        if (!seen[key]) {
          seen[key] = true;
          columns.push(key);
        }
      });
    });
    var table = el('table', 'sec-analyze-table');
    var head = document.createElement('thead');
    var headRow = document.createElement('tr');
    columns.forEach(function (key) { headRow.appendChild(el('th', '', titleOf(key))); });
    head.appendChild(headRow);
    table.appendChild(head);
    var body = document.createElement('tbody');
    rows.slice(0, MAX_ROWS).forEach(function (row) {
      var tr = document.createElement('tr');
      columns.forEach(function (key) {
        tr.appendChild(el('td', '', cellText(row && typeof row === 'object' ? row[key] : row)));
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    return table;
  }

  function appendBlock(parent, value, title, depth) {
    var section = el('section', 'sec-analyze-block');
    if (title) section.appendChild(el('h4', 'sec-analyze-block-title', titleOf(title)));
    if (value == null) {
      section.appendChild(el('p', 'sec-analyze-empty', '—'));
      parent.appendChild(section);
      return;
    }
    if (depth > 6) {
      var dumped = '';
      try { dumped = JSON.stringify(value, null, 2); } catch (err) { dumped = ''; }
      section.appendChild(el('pre', 'sec-analyze-pre', clip(dumped, 2000)));
      parent.appendChild(section);
      return;
    }
    if (Array.isArray(value)) {
      if (!value.length) {
        section.appendChild(el('p', 'sec-analyze-empty', '（空）'));
      } else if (value.every(isScalar)) {
        section.appendChild(el('pre', 'sec-analyze-pre', value.map(cellText).join('\n\n')));
      } else if (value.every(function (row) {
        return row && typeof row === 'object' && !Array.isArray(row) && !Object.keys(row).some(function (key) {
          return row[key] != null && typeof row[key] === 'object';
        });
      })) {
        section.appendChild(rowsTable(value));
        if (value.length > MAX_ROWS) {
          section.appendChild(el('p', 'sec-analyze-empty', '仅显示前 ' + MAX_ROWS + ' 行，共 ' + value.length + ' 行。'));
        }
      } else {
        var items = value.slice(0, MAX_NESTED);
        items.forEach(function (item, index) {
          appendBlock(section, item, (title ? titleOf(title) : '项') + ' ' + (index + 1), depth + 1);
        });
        if (value.length > items.length) {
          section.appendChild(el('p', 'sec-analyze-empty', '仅展开前 ' + items.length + ' 项，共 ' + value.length + ' 项。'));
        }
      }
      parent.appendChild(section);
      return;
    }
    if (typeof value === 'object') {
      var scalars = {};
      var nested = [];
      Object.keys(value).forEach(function (key) {
        if (isScalar(value[key])) scalars[key] = value[key];
        else nested.push([key, value[key]]);
      });
      if (Object.keys(scalars).length) section.appendChild(kvTable(scalars));
      nested.slice(0, MAX_NESTED).forEach(function (pair) {
        appendBlock(section, pair[1], pair[0], depth + 1);
      });
      if (nested.length > MAX_NESTED) {
        section.appendChild(el('p', 'sec-analyze-empty', '仅展开前 ' + MAX_NESTED + ' 组，共 ' + nested.length + ' 组。'));
      }
      if (!Object.keys(scalars).length && !nested.length) {
        section.appendChild(el('p', 'sec-analyze-empty', '（空）'));
      }
      parent.appendChild(section);
      return;
    }
    section.appendChild(el('p', 'sec-analyze-summary', cellText(value)));
    parent.appendChild(section);
  }

  function statsSource(data) {
    if (!data || typeof data !== 'object') return null;
    var skip = {
      chart_spec: true,
      status: true,
      session_id: true,
      summary_text: true,
      metadata: true,
      data_preview: true,
      statistics: true
    };
    var copy = {};
    Object.keys(data).forEach(function (key) {
      var value = data[key];
      if (skip[key] || value == null) return;
      if (Array.isArray(value) && !value.length) return;
      copy[key] = value;
    });
    return copy;
  }

  function paintResult(resultEl, data) {
    resultEl.textContent = '';
    if (!data || typeof data !== 'object') {
      resultEl.appendChild(el('p', 'sec-analyze-empty', '没有可展示的统计量。'));
      return;
    }
    if (data.summary_text) {
      var summary = el('section', 'sec-analyze-block');
      summary.appendChild(el('h4', 'sec-analyze-block-title', '摘要'));
      summary.appendChild(el('p', 'sec-analyze-summary', String(data.summary_text)));
      resultEl.appendChild(summary);
    }
    var spec = data.chart_spec;
    if (spec && typeof spec === 'object') {
      var chartBlock = el('section', 'sec-analyze-block');
      chartBlock.appendChild(el('h4', 'sec-analyze-block-title', '图表'));
      var chartNode = el('div', 'sec-analyze-chart');
      chartBlock.appendChild(chartNode);
      var chartError = el('p', 'sec-analyze-empty');
      chartBlock.appendChild(chartError);
      resultEl.appendChild(chartBlock);
      renderChart(chartNode, spec).catch(function (err) {
        chartError.textContent = err && err.message ? err.message : '图表渲染失败';
      });
    }
    if (data.statistics && typeof data.statistics === 'object') {
      var evidence = data.statistics.evidence;
      var rest = {};
      Object.keys(data.statistics).forEach(function (key) {
        if (key === 'evidence' || key === 'chart_spec') return;
        rest[key] = data.statistics[key];
      });
      if (evidence && typeof evidence === 'object') appendBlock(resultEl, evidence, '证据', 0);
      if (Object.keys(rest).length) appendBlock(resultEl, rest, '统计量', 0);
    } else {
      var raw = statsSource(data) || {};
      if (Object.keys(raw).length) appendBlock(resultEl, raw, '统计量', 0);
      if (Array.isArray(data.data_preview)) appendBlock(resultEl, data.data_preview, '预览', 0);
      if (data.metadata && typeof data.metadata === 'object' && Object.keys(data.metadata).length) {
        appendBlock(resultEl, data.metadata, '元数据', 0);
      }
    }
    if (!resultEl.childNodes.length) {
      resultEl.appendChild(el('p', 'sec-analyze-empty', '没有可展示的统计量。'));
    }
  }

  function showError(resultEl, label, detail) {
    resultEl.textContent = '';
    var box = el('div', 'sec-analyze-error');
    box.setAttribute('role', 'alert');
    box.appendChild(el('div', 'sec-analyze-error-label', label));
    box.appendChild(el('pre', '', formatDetail(detail)));
    resultEl.appendChild(box);
  }

  function readValues(form, fields) {
    var values = {};
    var missing = [];
    fields.forEach(function (field) {
      var node = form.querySelector('[name="' + field.name + '"]');
      if (!node) return;
      if (field.type === 'checkbox') {
        values[field.name] = !!node.checked;
        return;
      }
      var raw = String(node.value || '').trim();
      if (field.type === 'list') {
        var list = raw.split(/[,，]/).map(function (part) { return part.trim(); }).filter(Boolean);
        if (!list.length) {
          if (field.required) missing.push(field.label);
          return;
        }
        values[field.name] = list;
        return;
      }
      if (field.type === 'number') {
        if (!raw) return;
        var num = Number(raw);
        if (!Number.isFinite(num)) {
          missing.push(field.label);
          return;
        }
        values[field.name] = num;
        return;
      }
      if (!raw) {
        if (field.required) missing.push(field.label);
        return;
      }
      values[field.name] = raw;
    });
    return { values: values, missing: missing };
  }

  function callApi(ctx, method, path, body) {
    if (!ctx || typeof ctx.api !== 'function') {
      var missing = new Error('缺少 ctx.api');
      missing.detail = '缺少 ctx.api';
      return Promise.reject(missing);
    }
    return Promise.resolve().then(function () {
      return ctx.api(method, path, body);
    }).then(function (result) {
      if (result && typeof result === 'object' && typeof result.ok === 'boolean' && typeof result.json === 'function') {
        return result.json().catch(function () { return {}; }).then(function (data) {
          if (!result.ok) {
            var httpError = new Error(formatDetail(data && data.detail != null ? data.detail : data));
            httpError.detail = data && data.detail != null ? data.detail : data;
            throw httpError;
          }
          return data;
        });
      }
      return result;
    }).catch(function (err) {
      if (err && err.detail != null) throw err;
      var wrapped = new Error(formatDetail(failureDetail(err)));
      wrapped.detail = failureDetail(err);
      throw wrapped;
    });
  }

  function tabById(id) {
    for (var i = 0; i < TABS.length; i += 1) {
      if (TABS[i].id === id) return TABS[i];
    }
    return TABS[0];
  }

  function fieldNode(field) {
    if (field.type === 'checkbox') {
      var check = el('label', 'sec-analyze-check');
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.name = field.name;
      box.checked = !!field.defaultValue;
      check.appendChild(box);
      check.appendChild(document.createTextNode(field.label));
      return check;
    }
    var wrap = el('div', 'sec-analyze-field');
    var input;
    if (field.type === 'select') {
      input = document.createElement('select');
      (field.options || []).forEach(function (option) {
        var opt = document.createElement('option');
        opt.value = option[0];
        opt.textContent = option[1];
        if (option[0] === field.defaultValue) opt.selected = true;
        input.appendChild(opt);
      });
    } else {
      input = document.createElement('input');
      input.type = field.type === 'number' ? 'number' : 'text';
      if (field.defaultValue != null) input.value = field.defaultValue;
      if (field.placeholder) input.placeholder = field.placeholder;
      if (field.min != null) input.min = field.min;
      if (field.max != null) input.max = field.max;
      if (field.step) input.step = field.step;
    }
    input.name = field.name;
    input.id = (field.uid || 'sec-analyze') + '-' + field.name;
    input.autocomplete = 'off';
    input.spellcheck = false;
    var label = el('label', '', field.label);
    label.htmlFor = input.id;
    wrap.appendChild(label);
    wrap.appendChild(input);
    if (field.options && field.type !== 'select' && typeof field.options === 'string') {
      wrap.appendChild(el('div', 'sec-analyze-hint', field.options));
    }
    return wrap;
  }

  function mount(container, ctx) {
    if (!container) return;
    ensureStyle();
    ctx = ctx || {};
    var activeId = rememberedTab;
    var runToken = 0;
    var uid = 'sec-analyze-m' + (++mountSeq);
    container.textContent = '';
    container.classList.add('sec-analyze-root');

    var tabs = el('div', 'sec-analyze-tabs');
    tabs.setAttribute('role', 'tablist');
    var layout = el('div', 'sec-analyze-layout');
    var form = el('form', 'sec-analyze-form');
    form.setAttribute('novalidate', 'novalidate');
    var result = el('div', 'sec-analyze-result');
    layout.appendChild(form);
    layout.appendChild(result);
    container.appendChild(tabs);
    container.appendChild(layout);

    function renderForm() {
      var tab = tabById(activeId);
      rememberedTab = tab.id;
      form.textContent = '';
      var session = el('p', 'sec-analyze-session');
      session.appendChild(document.createTextNode('会话 '));
      session.appendChild(el('code', '', currentSession(ctx) || '（无）'));
      form.appendChild(session);
      form.appendChild(el('p', 'sec-analyze-endpoint', tab.method + ' ' + tab.path));
      if (tab.hint) form.appendChild(el('p', 'sec-analyze-hint', tab.hint));

      var datasetWrap = el('div', 'sec-analyze-field');
      var datasetInput = document.createElement('input');
      datasetInput.type = 'text';
      datasetInput.name = 'dataset_name';
      datasetInput.id = uid + '-dataset';
      datasetInput.placeholder = 'dataset_name';
      datasetInput.autocomplete = 'off';
      datasetInput.spellcheck = false;
      datasetInput.value = rememberedDataset;
      datasetInput.addEventListener('input', function () { rememberedDataset = datasetInput.value.trim(); });
      var datasetLabel = el('label', '', '数据集');
      datasetLabel.htmlFor = datasetInput.id;
      datasetWrap.appendChild(datasetLabel);
      datasetWrap.appendChild(datasetInput);
      form.appendChild(datasetWrap);

      tab.fields.forEach(function (field) {
        form.appendChild(fieldNode(Object.assign({ uid: uid }, field)));
      });
      if (tab.note) form.appendChild(el('p', 'sec-analyze-note', tab.note));
      var button = el('button', 'sec-analyze-run', '运行');
      button.type = 'submit';
      form.appendChild(button);
    }

    function selectTab(id) {
      activeId = id;
      Array.prototype.forEach.call(tabs.children, function (button) {
        var on = button.getAttribute('data-sec-analyze-tab') === id;
        button.className = on ? 'sec-analyze-tab sec-analyze-tab-active' : 'sec-analyze-tab';
        button.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      renderForm();
    }

    TABS.forEach(function (tab) {
      var button = el('button', 'sec-analyze-tab', tab.label);
      button.type = 'button';
      button.setAttribute('role', 'tab');
      button.setAttribute('data-sec-analyze-tab', tab.id);
      button.addEventListener('click', function () { selectTab(tab.id); });
      tabs.appendChild(button);
    });

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var tab = tabById(activeId);
      var sessionId = currentSession(ctx);
      var datasetInput = form.querySelector('[name="dataset_name"]');
      var dataset = datasetInput ? datasetInput.value.trim() : '';
      rememberedDataset = dataset;
      var parsed = readValues(form, tab.fields);
      var missing = parsed.missing.slice();
      if (!sessionId) missing.unshift('会话');
      if (!dataset) missing.unshift('数据集');
      if (missing.length) {
        showError(result, '无法提交', '请填写：' + missing.join('、'));
        return;
      }
      var request = typeof tab.request === 'function'
        ? tab.request({ sessionId: sessionId, dataset: dataset }, parsed.values)
        : {
          method: 'POST',
          path: tab.path,
          body: Object.assign({ session_id: sessionId, dataset_name: dataset }, parsed.values)
        };
      var token = ++runToken;
      var button = form.querySelector('.sec-analyze-run');
      if (button) {
        button.disabled = true;
        button.textContent = '运行中';
      }
      result.textContent = '';
      result.appendChild(el('p', 'sec-analyze-empty', '正在计算…'));
      callApi(ctx, request.method, request.path, request.body).then(function (data) {
        if (token !== runToken) return;
        paintResult(result, data);
        notify(ctx, tab.label + ' 已完成');
      }).catch(function (err) {
        if (token !== runToken) return;
        var detail = failureDetail(err);
        showError(result, 'detail', detail);
        notify(ctx, formatDetail(detail));
      }).then(function () {
        if (token !== runToken) return;
        if (button) {
          button.disabled = false;
          button.textContent = '运行';
        }
      });
    });

    result.appendChild(el('p', 'sec-analyze-empty', '填写左侧条件后运行。统计量和图表显示在这里。'));
    selectTab(activeId);
  }

  window.DashboardSections = window.DashboardSections || {};
  window.DashboardSections.analyze = { mount: mount };
})();
