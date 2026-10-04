/* =========================================================
   charts.js — shared Chart.js setup + thin helpers for the
   analytics / cost-analysis / dashboard / profile chart sections.

   Loaded AFTER the Chart.js UMD bundle. Exposes a single global
   `Charts` with palette colours and bar/line/doughnut builders
   that each no-op safely if their target <canvas> is absent.
   ========================================================= */
(function () {
  "use strict";

  if (typeof window.Chart === "undefined") {
    window.Charts = { ok: false, bar: noop, line: noop, doughnut: noop, render: noop };
    return;
  }
  function noop() { return null; }

  // Palette — brand hues from style.css :root, then distinct extensions.
  var PALETTE = [
    "#4f46e5", "#0284c7", "#16a34a", "#ca8a04", "#dc2626",
    "#7c3aed", "#0891b2", "#65a30d", "#db2777", "#334155"
  ];
  var COLORS = {
    primary: "#4f46e5", info: "#0284c7", success: "#16a34a",
    warn: "#ca8a04", danger: "#dc2626", muted: "#94a3b8",
    grid: "rgba(148,163,184,.20)"
  };

  Chart.defaults.font.family = "'Inter', system-ui, -apple-system, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = "#64748b";
  Chart.defaults.responsive = true;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.legend.labels.padding = 14;

  var nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  var nf2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function hexToRgba(hex, a) {
    if (hex[0] !== "#" || hex.length < 7) return hex;
    var n = parseInt(hex.slice(1, 7), 16);
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
  }
  function colorAt(i) { return PALETTE[i % PALETTE.length]; }

  function ctx(id) {
    var el = document.getElementById(id);
    return el ? el.getContext("2d") : null;
  }

  function moneyTicks() {
    return { callback: function (v) { return nf0.format(v); } };
  }
  function moneyTooltip(label) {
    return function (item) {
      var name = item.dataset.label ? item.dataset.label + ": " : "";
      var val = item.parsed.y != null ? item.parsed.y : item.parsed;
      return name + (label || "") + nf2.format(val);
    };
  }

  /* ---- bar -------------------------------------------------------------
     opts: { labels, datasets:[{label,data,color?}], horizontal?, stacked?,
             money?, legend?(bool), diverging?(bool) }                     */
  function bar(id, opts) {
    var c = ctx(id);
    if (!c) return null;
    opts = opts || {};
    var datasets = (opts.datasets || []).map(function (d, i) {
      var col = d.color || colorAt(i);
      return {
        label: d.label,
        data: d.data,
        backgroundColor: Array.isArray(col) ? col : hexToRgba(col, 0.82),
        borderColor: Array.isArray(col) ? col : col,
        borderWidth: 1,
        borderRadius: 3,
        maxBarThickness: 46
      };
    });
    var scales = {};
    var valAxis = opts.horizontal ? "x" : "y";
    var catAxis = opts.horizontal ? "y" : "x";
    scales[catAxis] = { grid: { display: false }, stacked: !!opts.stacked };
    scales[valAxis] = {
      grid: { color: COLORS.grid },
      stacked: !!opts.stacked,
      beginAtZero: true,
      ticks: opts.money ? moneyTicks() : { precision: 0 }
    };
    return new Chart(c, {
      type: "bar",
      data: { labels: opts.labels || [], datasets: datasets },
      options: {
        indexAxis: opts.horizontal ? "y" : "x",
        plugins: {
          legend: { display: opts.legend !== false && datasets.length > 1, position: "bottom" },
          tooltip: opts.money ? { callbacks: { label: moneyTooltip() } } : {}
        },
        scales: scales
      }
    });
  }

  /* ---- line ----------------------------------------------------------- */
  function line(id, opts) {
    var c = ctx(id);
    if (!c) return null;
    opts = opts || {};
    var datasets = (opts.datasets || []).map(function (d, i) {
      var col = d.color || colorAt(i);
      return {
        label: d.label,
        data: d.data,
        borderColor: col,
        backgroundColor: hexToRgba(col, opts.fill ? 0.14 : 0.0),
        fill: !!opts.fill,
        tension: opts.step ? 0 : 0.28,
        stepped: opts.step ? true : false,
        pointRadius: (opts.labels && opts.labels.length > 24) ? 0 : 2.5,
        pointHoverRadius: 4,
        borderWidth: 2
      };
    });
    return new Chart(c, {
      type: "line",
      data: { labels: opts.labels || [], datasets: datasets },
      options: {
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: opts.legend !== false && datasets.length > 1, position: "bottom" },
          tooltip: opts.money ? { callbacks: { label: moneyTooltip() } } : {}
        },
        scales: {
          x: { grid: { display: false } },
          y: {
            grid: { color: COLORS.grid },
            beginAtZero: opts.beginAtZero !== false,
            ticks: opts.money ? moneyTicks() : { precision: 0 }
          }
        }
      }
    });
  }

  /* ---- doughnut -----------------------------------------------------------
     opts: { labels, values, colors?, money? }                              */
  function doughnut(id, opts) {
    var c = ctx(id);
    if (!c) return null;
    opts = opts || {};
    var cols = opts.colors || opts.labels.map(function (_, i) { return colorAt(i); });
    return new Chart(c, {
      type: "doughnut",
      data: {
        labels: opts.labels || [],
        datasets: [{ data: opts.values || [], backgroundColor: cols, borderWidth: 2, borderColor: "#fff" }]
      },
      options: {
        cutout: "58%",
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: function (item) {
                var v = item.parsed;
                return " " + item.label + ": " + (opts.money ? nf2.format(v) : nf0.format(v));
              }
            }
          }
        }
      }
    });
  }

  /* escape hatch: full Chart.js config */
  function render(id, config) {
    var c = ctx(id);
    return c ? new Chart(c, config) : null;
  }

  window.Charts = {
    ok: true,
    palette: PALETTE,
    colors: COLORS,
    colorAt: colorAt,
    fmtMoney: function (v) { return nf2.format(v); },
    bar: bar,
    line: line,
    doughnut: doughnut,
    render: render
  };
})();
