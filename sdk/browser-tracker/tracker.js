/**
 * OpenTelemetry-Compliant Web Telemetry & User Analytics SDK
 * (Zero external dependencies, highly resilient, automatic instrumentation)
 */
(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.OpenTracker = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  function randomHex(len) {
    var hex = '';
    while (hex.length < len) {
      hex += Math.floor(Math.random() * 16).toString(16);
    }
    return hex.substring(0, len);
  }

  // Generate W3C Trace Context IDs
  function generateTraceId() {
    return randomHex(32); // 128-bit hex
  }

  function generateSpanId() {
    return randomHex(16); // 64-bit hex
  }

  function getOrSetId(key, generator) {
    try {
      var val = localStorage.getItem(key);
      if (!val) {
        val = generator();
        localStorage.setItem(key, val);
      }
      return val;
    } catch (e) {
      return generator();
    }
  }

  var Tracker = function (options) {
    this.options = Object.assign({
      endpoint: '/api/v1/collect/events',
      serviceName: 'frontend-web-app',
      appId: 'default-app',
      batchSize: 10,
      flushIntervalMs: 3000,
      enableAutoClick: true,
      enableAutoPageview: true,
      enableWebVitals: true,
      enableErrorCapture: true,
      maxBreadcrumbs: 50
    }, options || {});

    this.userId = getOrSetId('otel_user_id', function () { return 'u_' + randomHex(12); });
    this.sessionId = getOrSetId('otel_session_id', function () { return 's_' + randomHex(16); });
    this.currentTraceId = generateTraceId();
    this.currentSpanId = generateSpanId();
    
    this.queue = [];
    this.breadcrumbs = [];
    this.pageStartTime = Date.now();
    this.lastUrl = window.location.href;

    this.init();
  };

  Tracker.prototype.init = function () {
    var self = this;

    // 1. Start periodic flushing
    this.flushTimer = setInterval(function () {
      self.flush();
    }, this.options.flushIntervalMs);

    // 2. Auto Pageview & SPA Routing
    if (this.options.enableAutoPageview) {
      this.trackPageview();
      this.hookSpaRouting();
    }

    // 3. Auto Click & Interaction
    if (this.options.enableAutoClick) {
      this.hookUserInteractions();
    }

    // 4. Auto Error Capture
    if (this.options.enableErrorCapture) {
      this.hookErrorCapture();
    }

    // 5. Web Vitals
    if (this.options.enableWebVitals) {
      this.hookWebVitals();
    }

    // 6. Page Unload Flush (sendBeacon)
    window.addEventListener('beforeunload', function () {
      self.trackPageLeave();
      self.flush(true);
    });

    window.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') {
        self.flush(true);
      }
    });
  };

  Tracker.prototype.addBreadcrumb = function (category, message, data) {
    var item = {
      timestamp: Date.now(),
      category: category,
      message: message,
      data: data || {}
    };
    this.breadcrumbs.push(item);
    if (this.breadcrumbs.length > this.options.maxBreadcrumbs) {
      this.breadcrumbs.shift();
    }
  };

  Tracker.prototype.emit = function (eventType, eventName, properties, spanName) {
    var spanId = generateSpanId();
    var now = Date.now();
    
    var eventPayload = {
      event_id: 'ev_' + randomHex(16),
      trace_id: this.currentTraceId,
      span_id: spanId,
      parent_span_id: this.currentSpanId,
      session_id: this.sessionId,
      user_id: this.userId,
      event_type: eventType, // pageview, click, error, performance, custom
      event_name: eventName,
      service_name: this.options.serviceName,
      page_url: window.location.href,
      page_path: window.location.pathname,
      page_title: document.title,
      referrer: document.referrer,
      user_agent: navigator.userAgent,
      screen_resolution: window.screen.width + 'x' + window.screen.height,
      language: navigator.language || 'zh-CN',
      created_at: new Date(now).toISOString(),
      timestamp_ms: now,
      properties: properties || {},
      breadcrumbs: this.breadcrumbs.slice(-10) // attach last 10 actions for trace replay
    };

    this.queue.push(eventPayload);
    this.addBreadcrumb(eventType, eventName, { path: window.location.pathname });

    if (this.queue.length >= this.options.batchSize) {
      this.flush();
    }
  };

  Tracker.prototype.trackPageview = function () {
    this.currentSpanId = generateSpanId();
    this.pageStartTime = Date.now();
    this.emit('pageview', '$pageview', {
      title: document.title,
      url: window.location.href,
      path: window.location.pathname
    });
  };

  Tracker.prototype.trackPageLeave = function () {
    var dwellTime = Math.round((Date.now() - this.pageStartTime) / 1000);
    this.emit('pageview', '$page_leave', {
      dwell_time_seconds: dwellTime,
      url: this.lastUrl
    });
  };

  Tracker.prototype.trackEvent = function (eventName, properties) {
    this.emit('custom', eventName, properties || {});
  };

  Tracker.prototype.hookSpaRouting = function () {
    var self = this;
    var origPushState = history.pushState;
    var origReplaceState = history.replaceState;

    history.pushState = function () {
      origPushState.apply(this, arguments);
      self.onUrlChange();
    };

    history.replaceState = function () {
      origReplaceState.apply(this, arguments);
      self.onUrlChange();
    };

    window.addEventListener('popstate', function () {
      self.onUrlChange();
    });

    window.addEventListener('hashchange', function () {
      self.onUrlChange();
    });
  };

  Tracker.prototype.onUrlChange = function () {
    if (window.location.href !== this.lastUrl) {
      this.trackPageLeave();
      this.lastUrl = window.location.href;
      this.trackPageview();
    }
  };

  Tracker.prototype.hookUserInteractions = function () {
    var self = this;
    document.addEventListener('click', function (e) {
      var target = e.target;
      if (!target || target === document || target === window) return;

      var tag = target.tagName.toLowerCase();
      var trackName = target.getAttribute('data-track') || target.getAttribute('id') || target.getAttribute('name');
      var text = (target.innerText || target.value || '').trim().substring(0, 50);

      // Build compact CSS selector path
      var selector = tag;
      if (target.id) selector += '#' + target.id;
      if (target.className && typeof target.className === 'string') {
        selector += '.' + target.className.trim().split(/\s+/).slice(0, 2).join('.');
      }

      self.emit('click', '$click', {
        tag: tag,
        selector: selector,
        text: text,
        track_name: trackName,
        x: e.clientX,
        y: e.clientY
      });
    }, true);
  };

  Tracker.prototype.hookErrorCapture = function () {
    var self = this;
    window.addEventListener('error', function (e) {
      self.emit('error', '$error', {
        message: e.message || 'Script error',
        filename: e.filename || '',
        lineno: e.lineno || 0,
        colno: e.colno || 0,
        stack: e.error ? (e.error.stack || '') : ''
      });
    });

    window.addEventListener('unhandledrejection', function (e) {
      self.emit('error', '$unhandled_rejection', {
        reason: e.reason ? (e.reason.message || String(e.reason)) : 'Promise rejected',
        stack: e.reason && e.reason.stack ? e.reason.stack : ''
      });
    });
  };

  Tracker.prototype.hookWebVitals = function () {
    var self = this;
    if (window.PerformanceObserver) {
      try {
        var observer = new PerformanceObserver(function (list) {
          list.getEntries().forEach(function (entry) {
            if (entry.entryType === 'paint' && entry.name === 'first-contentful-paint') {
              self.emit('performance', '$fcp', { value_ms: Math.round(entry.startTime) });
            } else if (entry.entryType === 'largest-contentful-paint') {
              self.emit('performance', '$lcp', { value_ms: Math.round(entry.startTime) });
            }
          });
        });
        observer.observe({ type: 'paint', buffered: true });
        observer.observe({ type: 'largest-contentful-paint', buffered: true });
      } catch (e) {}
    }
  };

  Tracker.prototype.flush = function (isBeacon) {
    if (this.queue.length === 0) return;

    var payload = this.queue.slice();
    this.queue = [];
    var dataStr = JSON.stringify({ events: payload });

    if (isBeacon && navigator.sendBeacon) {
      var blob = new Blob([dataStr], { type: 'application/json' });
      navigator.sendBeacon(this.options.endpoint, blob);
    } else {
      if (typeof fetch === 'function') {
        fetch(this.options.endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'traceparent': '00-' + this.currentTraceId + '-' + this.currentSpanId + '-01'
          },
          body: dataStr,
          keepalive: true
        }).catch(function (err) {
          console.warn('[OpenTracker] Ingestion failed:', err);
        });
      }
    }
  };

  return Tracker;
}));
