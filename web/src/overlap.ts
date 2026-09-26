import maplibregl from "./maplibre";
import "./style.css";
import { BASEMAP, NYC_BOUNDS, fmtNum, fmtP, fmtRho, loadNtas, loadStats, type NtaCollection, type Corr, type NtaProps, type Stats } from "./common";

const GROUPS = ["low", "mid", "high"] as const;
type Group = (typeof GROUPS)[number];

// 3x3 bivariate scheme, BIVAR[distress][heat].
const BIVAR: Record<Group, Record<Group, string>> = {
  low: { low: "#e8e8e8", mid: "#e4acac", high: "#c85a5a" },
  mid: { low: "#b0d5df", mid: "#ad9ea5", high: "#985356" },
  high: { low: "#64acbe", mid: "#627f8c", high: "#574249" },
};

// Categorical slots 1-3 of the validated palette (all-pairs safe).
const HEAT_COLORS: Record<Group, string> = { low: "#2a78d6", mid: "#1baf7a", high: "#eb6834" };

const tooltip = document.getElementById("tooltip")!;
function showTip(html: string, x: number, y: number) {
  tooltip.innerHTML = html;
  tooltip.hidden = false;
  const w = tooltip.offsetWidth;
  const left = Math.min(x + 12, window.innerWidth - w - 8);
  tooltip.style.left = `${Math.max(8, left)}px`;
  tooltip.style.top = `${y + 14}px`;
}
function hideTip() {
  tooltip.hidden = true;
}

const PLACES_METHODS = "https://www.cdc.gov/places/methodology/index.html";

// Adjustment sequence under the headline. Every value comes from stats.json.
function renderExhibit(s: Stats) {
  const adjusted = s.hvi_rank_vs_mhlth_partial_income_pct_black;
  const rows: [string, Corr, string][] = [
    ["Heat risk vs distress, unadjusted", s.hvi_rank_vs_mhlth, ""],
    ["Adjusted for median income", s.hvi_rank_vs_mhlth_partial_income, ""],
    ["Adjusted for income and racial composition", adjusted,
      adjusted.p >= 0.05 ? "not statistically significant at 0.05" : ""],
    ["Street trees per km² (2015) vs distress", s.trees_per_km2_vs_mhlth, ""],
  ];
  document.getElementById("exhibit")!.innerHTML = rows
    .map(([label, c, note]) => `<li><b>${label}:</b> <span>ρ = ${c.rho.toFixed(2)}, ${fmtP(c.p)}</span>${note ? ` <em>(${note})</em>` : ""}</li>`)
    .join("");
  document.getElementById("exhibit-note")!.innerHTML =
    `Heat risk is the city's Heat Vulnerability Index rank; distress is the PLACES estimate of frequent mental distress; n = ${s.residential_nta_count} residential neighborhoods.
    Racial composition is percent Black population, an HVI input and one of the variables the
    <a href="${PLACES_METHODS}">PLACES models</a> can draw on. It is used only for this adjustment and is not mapped.`;
}

function renderBivariate(data: NtaCollection) {
  const withColor = {
    ...data,
    features: data.features.map((f) => {
      const { heat_group: h, distress_group: d } = f.properties;
      return { ...f, properties: { ...f.properties, bivar: h && d ? BIVAR[d][h] : null } };
    }),
  };
  const map = new maplibregl.Map({ container: "bimap", style: BASEMAP, bounds: NYC_BOUNDS, attributionControl: false });
  map.addControl(new maplibregl.AttributionControl({ compact: false }));
  // The card can change width after first layout (fonts, grid); keep the canvas in step.
  new ResizeObserver(() => map.resize()).observe(map.getContainer());
  map.on("load", () => {
    const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
    map.addSource("nta", { type: "geojson", data: withColor });
    map.addLayer({ id: "bi-fill", type: "fill", source: "nta",
      paint: { "fill-color": ["coalesce", ["get", "bivar"], "#cccccc"], "fill-opacity": 0.9 } }, firstLabel);
    map.addLayer({ id: "bi-line", type: "line", source: "nta",
      paint: { "line-color": "#ffffff", "line-width": 0.5 } }, firstLabel);
    map.on("mousemove", "bi-fill", (e) => {
      const p = e.features?.[0]?.properties as NtaProps | undefined;
      if (!p) return;
      map.getCanvas().style.cursor = "pointer";
      showTip(`<b>${p.ntaname}</b><br>Heat group: ${p.heat_group}<br>Distress group: ${p.distress_group}`,
        e.originalEvent.clientX, e.originalEvent.clientY);
    });
    map.on("mouseleave", "bi-fill", () => {
      map.getCanvas().style.cursor = "";
      hideTip();
    });
  });

  const cells = [...GROUPS].reverse()
    .map((d) => GROUPS.map((h) => `<div style="background:${BIVAR[d][h]}" title="heat ${h}, distress ${d}"></div>`).join(""))
    .join("");
  document.getElementById("bilegend")!.innerHTML = `
    <div class="bigrid" role="img" aria-label="3 by 3 legend: heat group across, distress group up">${cells}</div>
    <div class="axes">
      <span>→ Heat group (HVI rank 1–2 low, 3 mid, 4–5 high)</span>
      <span>↑ Distress group (tertiles of frequent mental distress)</span>
      <span>Darkest corner: high heat and top-third distress</span>
    </div>`;
}

function niceMax(v: number, step: number) {
  return Math.ceil(v / step) * step;
}

function renderScatter(data: NtaCollection, s: Stats) {
  const pts = data.features
    .map((f) => f.properties)
    .filter((p) => p.trees_per_km2 != null && p.mhlth != null && p.heat_group != null);
  const W = 520, H = 380, m = { t: 10, r: 12, b: 44, l: 46 };
  const xMax = niceMax(Math.max(...pts.map((p) => p.trees_per_km2!)), 500);
  const yMin = Math.floor(Math.min(...pts.map((p) => p.mhlth!)) / 2) * 2;
  const yMax = niceMax(Math.max(...pts.map((p) => p.mhlth!)), 2);
  const x = (v: number) => m.l + (v / xMax) * (W - m.l - m.r);
  const y = (v: number) => H - m.b - ((v - yMin) / (yMax - yMin)) * (H - m.t - m.b);

  const xt: number[] = [];
  for (let v = 0; v <= xMax; v += 500) xt.push(v);
  const yt: number[] = [];
  for (let v = yMin; v <= yMax; v += 2) yt.push(v);

  const grid = [
    ...yt.map((v) => `<g class="tick"><line stroke="var(--grid)" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text></g>`),
    ...xt.map((v) => `<g class="tick"><text x="${x(v)}" y="${H - m.b + 16}" text-anchor="middle">${v.toLocaleString("en-US")}</text></g>`),
  ].join("");
  // Draw high-heat points last so the smaller groups are not hidden underneath.
  const order: Record<Group, number> = { low: 0, mid: 1, high: 2 };
  const dots = [...pts]
    .sort((a, b) => order[a.heat_group!] - order[b.heat_group!])
    .map((p) => `<circle r="4.5" cx="${x(p.trees_per_km2!).toFixed(1)}" cy="${y(p.mhlth!).toFixed(1)}" fill="${HEAT_COLORS[p.heat_group!]}" data-id="${p.nta2020}"><title>${p.ntaname}</title></circle>`)
    .join("");

  const el = document.getElementById("scatter")!;
  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Scatter plot of street trees per square kilometre (2015) against frequent mental distress, one dot per neighborhood">
      <g class="grid">${grid}</g>
      <line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}" stroke="var(--axis)"/>
      <text class="axis-title" x="${(m.l + W - m.r) / 2}" y="${H - 6}" text-anchor="middle">Street trees per km² (2015)</text>
      <text class="axis-title" transform="translate(12 ${(m.t + H - m.b) / 2}) rotate(-90)" text-anchor="middle">Frequent mental distress (%)</text>
      <g>${dots}</g>
    </svg>`;

  const byId = new Map(pts.map((p) => [p.nta2020, p]));
  el.querySelectorAll<SVGCircleElement>("circle").forEach((c) => {
    c.querySelector("title")?.remove();
    c.addEventListener("mouseenter", (e) => {
      const p = byId.get(c.dataset.id!)!;
      c.classList.add("on");
      showTip(`<b>${p.ntaname}</b><br>${fmtNum(p.trees_per_km2, 0)} street trees per km² (2015)<br>${fmtNum(p.mhlth, 1)}% frequent mental distress<br>Heat group: ${p.heat_group}`,
        e.clientX, e.clientY);
    });
    c.addEventListener("mouseleave", () => {
      c.classList.remove("on");
      hideTip();
    });
  });

  const counts = GROUPS.map((g) => pts.filter((p) => p.heat_group === g).length);
  document.getElementById("scatter-keys")!.innerHTML = GROUPS
    .map((g, i) => `<span><i style="background:${HEAT_COLORS[g]}"></i>${g} heat (${counts[i]})</span>`)
    .join("");
  document.getElementById("scatter-stats")!.textContent =
    `Street trees per km² (2015) vs distress: Spearman ${fmtRho(s.trees_per_km2_vs_mhlth)}. Income-adjusted: ${fmtRho(s.trees_per_km2_vs_mhlth_partial_income)}. One dot per residential neighborhood.`;
}

async function main() {
  const [data, stats] = await Promise.all([loadNtas(), loadStats()]);
  renderExhibit(stats);
  renderBivariate(data);
  renderScatter(data, stats);
}

main().catch((err) => {
  document.getElementById("exhibit")!.textContent = `Could not load data: ${err.message}`;
});
