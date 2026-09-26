import type { FeatureCollection, Geometry } from "geojson";

export interface NtaProps {
  nta2020: string;
  ntaname: string;
  boroname: string;
  hvi_rank: number | null;
  surface_temp: number | null;
  greenspace: number | null;
  pct_households_ac: number | null;
  median_income: number | null;
  mhlth: number | null;
  depression: number | null;
  trees_per_km2: number | null;
  heat_group: "low" | "mid" | "high" | null;
  distress_group: "low" | "mid" | "high" | null;
  overlap_flag: boolean;
}

export type NtaCollection = FeatureCollection<Geometry, NtaProps>;

export interface Corr {
  x: string;
  y: string;
  control?: string;
  controls?: string[];
  rho: number;
  p: number;
  n: number;
}

export interface Stats {
  trees_per_km2_vs_mhlth: Corr;
  hvi_rank_vs_mhlth: Corr;
  hvi_rank_vs_mhlth_partial_income: Corr;
  trees_per_km2_vs_mhlth_partial_income: Corr;
  hvi_rank_vs_mhlth_partial_income_pct_black: Corr;
  residential_nta_count: number;
}

export const BASEMAP = "https://tiles.openfreemap.org/styles/positron";
export const NYC_BOUNDS: [[number, number], [number, number]] = [[-74.26, 40.49], [-73.69, 40.92]];

const base = import.meta.env.BASE_URL;

export async function loadNtas(): Promise<NtaCollection> {
  const r = await fetch(`${base}data/nta.geojson`);
  if (!r.ok) throw new Error(`nta.geojson: HTTP ${r.status}`);
  return r.json();
}

export async function loadStats(): Promise<Stats> {
  const r = await fetch(`${base}data/stats.json`);
  if (!r.ok) throw new Error(`stats.json: HTTP ${r.status}`);
  return r.json();
}

const SUP: Record<string, string> = { "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹" };

// p to 3 significant figures; very small values in scientific notation.
export function fmtP(p: number): string {
  if (p >= 0.001) return `p = ${Number(p.toPrecision(3))}`;
  const [m, e] = p.toExponential(2).split("e");
  return `p = ${m} × 10${String(Number(e)).replace(/./g, (c) => SUP[c])}`;
}

export function fmtRho(c: Corr): string {
  return `ρ = ${c.rho.toFixed(2)}, n = ${c.n}, ${fmtP(c.p)}`;
}

export function fmtNum(v: number | null, digits = 1): string {
  return v == null ? "no data" : v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
