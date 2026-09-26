import maplibregl from "./maplibre";
import "./style.css";
import { BASEMAP, NYC_BOUNDS, fmtNum, loadNtas, type NtaCollection, type NtaProps } from "./common";

type NumKey = "hvi_rank" | "mhlth" | "depression" | "trees_per_km2";

interface LayerDef {
  key: NumKey;
  label: string;
  unit: string;
  digits: number;
  colors: string[];
  discrete?: boolean;
}

// Single-hue sequential ramps (light to dark), one hue per layer.
const LAYERS: LayerDef[] = [
  { key: "hvi_rank", label: "Heat vulnerability (HVI rank)", unit: "", digits: 0, discrete: true,
    colors: ["#fee6ce", "#fdae6b", "#fd8d3c", "#e6550d", "#a63603"] },
  { key: "mhlth", label: "Frequent mental distress", unit: "%", digits: 1,
    colors: ["#f2f0f7", "#cbc9e2", "#9e9ac8", "#756bb1", "#54278f"] },
  { key: "depression", label: "Depression", unit: "%", digits: 1,
    colors: ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"] },
  { key: "trees_per_km2", label: "Street trees per km² (2015)", unit: "", digits: 0,
    colors: ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"] },
];

const ROWS: { key: keyof NtaProps; label: string; unit?: string; digits?: number; rank?: boolean }[] = [
  { key: "hvi_rank", label: "HVI rank (1–5)", digits: 0, rank: true },
  { key: "mhlth", label: "Frequent mental distress", unit: "%", digits: 1, rank: true },
  { key: "depression", label: "Depression", unit: "%", digits: 1, rank: true },
  { key: "trees_per_km2", label: "Street trees per km² (2015)", digits: 0, rank: true },
  { key: "surface_temp", label: "Surface temperature (°F)", digits: 1, rank: true },
  { key: "greenspace", label: "Green space", unit: "%", digits: 1, rank: true },
  { key: "pct_households_ac", label: "Households with AC", unit: "%", digits: 1, rank: true },
  { key: "median_income", label: "Median household income ($)", digits: 0, rank: true },
];

function quantileBreaks(values: number[], k: number): number[] {
  const s = [...values].sort((a, b) => a - b);
  const out: number[] = [];
  for (let i = 1; i < k; i++) out.push(s[Math.floor((i * s.length) / k)]);
  return out;
}

function breaksFor(layer: LayerDef, data: NtaCollection): number[] {
  if (layer.discrete) return [2, 3, 4, 5];
  const vals = data.features.map((f) => f.properties[layer.key]).filter((v): v is number => v != null);
  return quantileBreaks(vals, layer.colors.length);
}

function fillExpr(layer: LayerDef, breaks: number[]): maplibregl.ExpressionSpecification {
  const step: unknown[] = ["step", ["get", layer.key], layer.colors[0]];
  breaks.forEach((b, i) => step.push(b, layer.colors[i + 1]));
  return ["case", ["==", ["get", layer.key], null], cssVar("--nodata"), step] as unknown as maplibregl.ExpressionSpecification;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#cccccc";
}

function renderLegend(layer: LayerDef, breaks: number[]) {
  const el = document.getElementById("legend")!;
  const fmt = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: layer.digits });
  const labels = layer.discrete
    ? ["1", "2", "3", "4", "5"]
    : layer.colors.map((_, i) => (i === 0 ? `< ${fmt(breaks[0])}` : i === breaks.length ? `≥ ${fmt(breaks[i - 1])}` : `${fmt(breaks[i - 1])}–`));
  el.innerHTML = `
    <div>${layer.label}${layer.unit ? ` (${layer.unit})` : ""}${layer.discrete ? " · 5 = most vulnerable" : " · quintiles"}</div>
    <div class="swatches">
      ${layer.colors.map((c, i) => `<div class="sw"><span style="background:${c}"></span><small>${labels[i]}</small></div>`).join("")}
      <div class="sw nodata"><span></span><small>no data</small></div>
    </div>`;
}

function rankOf(data: NtaCollection, key: keyof NtaProps, value: number): { rank: number; n: number; tied: boolean } {
  const vals = data.features.map((f) => f.properties[key]).filter((v): v is number => typeof v === "number");
  const higher = vals.filter((v) => v > value).length;
  const same = vals.filter((v) => v === value).length;
  return { rank: higher + 1, n: vals.length, tied: same > 1 };
}

function renderPanel(data: NtaCollection, p: NtaProps) {
  const panel = document.getElementById("panel")!;
  const rows = ROWS.map((r) => {
    const v = p[r.key] as number | null;
    let rankTxt = "";
    if (r.rank && v != null) {
      const { rank, n, tied } = rankOf(data, r.key, v);
      rankTxt = `<small>rank ${rank}${tied ? " (tied)" : ""} of ${n}</small>`;
    }
    const val = v == null ? "no data" : `${fmtNum(v, r.digits ?? 1)}${r.unit ?? ""}`;
    return `<dt>${r.label}</dt><dd>${val}${rankTxt}</dd>`;
  }).join("");
  panel.innerHTML = `
    <button class="close" aria-label="Close">×</button>
    <h2>${p.ntaname}</h2>
    <p class="sub">${p.boroname} · ${p.nta2020}</p>
    <dl>
      ${rows}
      <dt>Heat group</dt><dd>${p.heat_group ?? "no data"}</dd>
      <dt>Distress group (tertile)</dt><dd>${p.distress_group ?? "no data"}</dd>
    </dl>
    <p class="flag">${p.overlap_flag ? "In the overlap group: high heat vulnerability and top-third frequent mental distress." : "Not in the overlap group."}</p>
    <p class="hint">Rank 1 = highest value among ${data.features.length} residential neighborhoods.</p>`;
  panel.hidden = false;
  panel.querySelector<HTMLButtonElement>(".close")!.onclick = () => {
    panel.hidden = true;
    selectNta(null);
  };
}

let map: maplibregl.Map;
function selectNta(code: string | null) {
  map.setFilter("nta-selected", ["==", ["get", "nta2020"], code ?? ""]);
}

async function main() {
  const data = await loadNtas();
  map = new maplibregl.Map({
    container: "map",
    style: BASEMAP,
    bounds: NYC_BOUNDS,
    attributionControl: false,
  });
  map.addControl(new maplibregl.AttributionControl({ compact: false }));
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");

  const layerBox = document.getElementById("layers")!;
  LAYERS.forEach((l, i) => {
    const label = document.createElement("label");
    label.innerHTML = `<input type="radio" name="layer" value="${l.key}" ${i === 0 ? "checked" : ""}/> ${l.label}`;
    layerBox.appendChild(label);
  });

  map.on("load", () => {
    const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
    map.addSource("nta", { type: "geojson", data, promoteId: "nta2020" });
    const layer0 = LAYERS[0];
    const b0 = breaksFor(layer0, data);
    map.addLayer({ id: "nta-fill", type: "fill", source: "nta",
      paint: { "fill-color": fillExpr(layer0, b0), "fill-opacity": 0.82 } }, firstLabel);
    map.addLayer({ id: "nta-line", type: "line", source: "nta",
      paint: { "line-color": "#ffffff", "line-width": 0.6, "line-opacity": 0.8 } }, firstLabel);
    map.addLayer({ id: "nta-selected", type: "line", source: "nta", filter: ["==", ["get", "nta2020"], ""],
      paint: { "line-color": "#111111", "line-width": 2.5 } });
    renderLegend(layer0, b0);

    layerBox.addEventListener("change", (e) => {
      const key = (e.target as HTMLInputElement).value;
      const l = LAYERS.find((x) => x.key === key)!;
      const b = breaksFor(l, data);
      map.setPaintProperty("nta-fill", "fill-color", fillExpr(l, b));
      renderLegend(l, b);
    });

    map.on("click", "nta-fill", (e) => {
      const code = e.features?.[0]?.properties?.nta2020 as string | undefined;
      const f = data.features.find((x) => x.properties.nta2020 === code);
      if (!f) return;
      selectNta(f.properties.nta2020);
      renderPanel(data, f.properties);
    });
    map.on("mouseenter", "nta-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "nta-fill", () => (map.getCanvas().style.cursor = ""));
  });
}

main().catch((err) => {
  document.getElementById("map")!.textContent = `Could not load map data: ${err.message}`;
});
