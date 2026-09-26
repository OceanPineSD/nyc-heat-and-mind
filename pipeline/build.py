#!/usr/bin/env python3
"""Build NTA-level heat, mental health and tree indicators from data/raw/.

Writes data/processed/ (tables and a build report) and web/public/data/
(nta.geojson, stats.json). Every assertion here is a hard failure.
"""
import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr, t as t_dist
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
WEB = ROOT / "web" / "public" / "data"
MAX_GEOJSON = 2 * 1024 * 1024
MAX_RUNTIME = 600
SQFT_TO_KM2 = 0.09290304 / 1e6

PROPS = [
    "nta2020", "ntaname", "boroname", "hvi_rank", "surface_temp", "greenspace",
    "pct_households_ac", "median_income", "mhlth", "depression", "trees_per_km2",
    "heat_group", "distress_group", "overlap_flag",
]

report = {}
t0 = time.monotonic()


def log(key, value):
    report[key] = value
    print(f"{key}: {value}")


def load_ntas():
    nta = gpd.read_file(RAW / "nta.geojson")
    log("nta_boundaries_all", len(nta))
    res = nta[nta["ntatype"] == "0"].copy()
    log("nta_residential", len(res))
    assert res["nta2020"].is_unique
    return nta, res


def load_hvi(res):
    hvi = pd.read_csv(RAW / "hvi-nta-2020.csv", dtype={"NTACode": str, "GEOCODE": str})
    log("hvi_rows", len(hvi))
    dup_codes = sorted(hvi.loc[hvi["NTACode"].duplicated(keep=False), "NTACode"].unique())
    log("hvi_duplicate_codes", dup_codes)
    assert dup_codes == ["BX0802"], f"expected only BX0802 duplicated, got {dup_codes}"
    dup = hvi[hvi["NTACode"] == "BX0802"]
    others = [c for c in hvi.columns if c != "GEOCODE"]
    assert len(dup) == 2, f"BX0802 appears {len(dup)} times"
    assert dup[others].nunique(dropna=False).max() == 1, "BX0802 rows differ outside GEOCODE"
    log("hvi_bx0802_geocodes", dup["GEOCODE"].tolist())
    hvi = hvi.drop_duplicates(subset="NTACode", keep="first")
    log("hvi_rows_deduped", len(hvi))

    hvi = hvi.rename(columns={
        "NTACode": "nta2020", "HVI_RANK": "hvi_rank", "SURFACE_TEMP": "surface_temp",
        "GREENSPACE": "greenspace", "PCT_HOUSEHOLDS_AC": "pct_households_ac",
        "MEDIAN_INCOME": "median_income", "PCT_BLACK_POP": "pct_black_pop",
    })[["nta2020", "hvi_rank", "surface_temp", "greenspace", "pct_households_ac", "median_income", "pct_black_pop"]]
    merged = res.merge(hvi, on="nta2020", how="left", validate="one_to_one")
    missing = merged.loc[merged["hvi_rank"].isna(), "nta2020"].tolist()
    log("residential_with_hvi", int(merged["hvi_rank"].notna().sum()))
    log("residential_missing_hvi", missing)
    log("hvi_codes_not_residential", sorted(set(hvi["nta2020"]) - set(res["nta2020"])))
    return merged


def load_mental_health(res):
    places = pd.DataFrame(json.loads((RAW / "places.json").read_text()))
    equiv = pd.DataFrame(json.loads((RAW / "equiv.json").read_text()))
    log("places_rows", len(places))
    log("places_unique_tracts", int(places["tractfips"].nunique()))
    log("equiv_rows", len(equiv))
    log("equiv_unique_geoid", int(equiv["geoid"].nunique()))
    assert places["tractfips"].is_unique and equiv["geoid"].is_unique

    for c in ["totalpopulation", "mhlth_crudeprev", "depression_crudeprev"]:
        places[c] = pd.to_numeric(places[c])
    j = places.merge(equiv[["geoid", "ntacode", "ntatype"]], left_on="tractfips",
                     right_on="geoid", how="inner", validate="one_to_one")
    log("places_matched_to_equiv", len(j))
    log("places_unmatched_to_equiv", len(places) - len(j))
    j = j[j["ntacode"].isin(res["nta2020"])]
    log("places_tracts_in_residential_ntas", len(j))
    log("places_tracts_zero_population_in_residential", int((j["totalpopulation"] == 0).sum()))

    def wmean(g, col):
        w = g["totalpopulation"]
        return np.nan if w.sum() == 0 else float((g[col] * w).sum() / w.sum())

    agg = j.groupby("ntacode").apply(lambda g: pd.Series({
        "mhlth": wmean(g, "mhlth_crudeprev"),
        "depression": wmean(g, "depression_crudeprev"),
        "mh_tracts": len(g),
    }), include_groups=False).reset_index().rename(columns={"ntacode": "nta2020"})
    out = res.merge(agg, on="nta2020", how="left", validate="one_to_one")
    nodata = out.loc[out["mhlth"].isna(), ["nta2020", "ntaname"]]
    log("residential_with_mental_health", int(out["mhlth"].notna().sum()))
    log("residential_no_mental_health", nodata.values.tolist())
    return out.drop(columns=["mh_tracts"])


def load_trees(all_ntas):
    expected = json.loads((RAW / "trees_expected.json").read_text())["expected_alive"]
    rows = pd.DataFrame(json.loads((RAW / "trees.json").read_text()))
    log("trees_expected", expected)
    log("trees_fetched", len(rows))
    assert rows["tree_id"].is_unique
    rows["latitude"] = pd.to_numeric(rows.get("latitude"), errors="coerce")
    rows["longitude"] = pd.to_numeric(rows.get("longitude"), errors="coerce")
    has_xy = rows["latitude"].notna() & rows["longitude"].notna()
    log("trees_missing_coords", int((~has_xy).sum()))

    pts = gpd.GeoDataFrame(
        rows.loc[has_xy, ["tree_id"]],
        geometry=gpd.points_from_xy(rows.loc[has_xy, "longitude"], rows.loc[has_xy, "latitude"]),
        crs="EPSG:4326",
    )
    polys = all_ntas[["nta2020", "geometry"]].to_crs("EPSG:4326")
    hit = gpd.sjoin(pts, polys, how="inner", predicate="intersects")
    multi = int(hit["tree_id"].duplicated().sum())
    log("trees_on_shared_boundaries_deduped", multi)
    hit = hit.drop_duplicates(subset="tree_id", keep="first")

    assigned = len(hit)
    unassigned = len(rows) - assigned
    log("trees_assigned", assigned)
    log("trees_unassigned", unassigned)
    assert assigned + unassigned == expected, "assigned + unassigned != expected total"
    return hit.groupby("nta2020").size().rename("tree_count")


def partial_spearman(d, x, y, controls):
    """Rank x, y and the controls; regress ranks of x and y on the control ranks; Pearson r of the residuals.

    The p-value uses a t-test with n - 2 - k degrees of freedom (k controls).
    """
    controls = [controls] if isinstance(controls, str) else list(controls)
    rx, ry = rankdata(d[x]), rankdata(d[y])
    design = np.column_stack([np.ones(len(d))] + [rankdata(d[c]) for c in controls])
    resid = [v - design @ np.linalg.lstsq(design, v, rcond=None)[0] for v in (rx, ry)]
    r = float(np.corrcoef(resid[0], resid[1])[0, 1])
    n = len(d)
    df_ = n - 2 - len(controls)
    tstat = r * np.sqrt(df_ / (1 - r * r))
    p = float(2 * t_dist.sf(abs(tstat), df_))
    out = {"x": x, "y": y}
    if len(controls) == 1:
        out["control"] = controls[0]
    else:
        out["controls"] = controls
    out.update({"rho": round(r, 4), "p": float(f"{p:.4g}"), "n": int(n), "df": df_})
    return out


def main():
    all_ntas, res = load_ntas()
    df = load_hvi(res)
    mh = load_mental_health(res)
    df = df.merge(mh[["nta2020", "mhlth", "depression"]], on="nta2020", how="left", validate="one_to_one")
    counts = load_trees(all_ntas)
    df = df.merge(counts, left_on="nta2020", right_index=True, how="left")
    df["tree_count"] = df["tree_count"].fillna(0).astype(int)
    df["area_km2"] = df.to_crs("EPSG:2263").geometry.area * SQFT_TO_KM2
    df["trees_per_km2"] = df["tree_count"] / df["area_km2"]
    log("residential_trees_assigned", int(df["tree_count"].sum()))
    log("residential_zero_trees", df.loc[df["tree_count"] == 0, "nta2020"].tolist())

    df["heat_group"] = pd.cut(df["hvi_rank"], bins=[0, 2, 3, 5], labels=["low", "mid", "high"]).astype(object)
    has_mh = df["mhlth"].notna()
    df.loc[has_mh, "distress_group"] = pd.qcut(df.loc[has_mh, "mhlth"], 3, labels=["low", "mid", "high"]).astype(object)
    cuts = df.loc[has_mh, "mhlth"].quantile([1 / 3, 2 / 3]).round(3).tolist()
    log("distress_tertile_cutoffs", cuts)
    log("distress_group_counts", df["distress_group"].value_counts(dropna=False).to_dict())
    log("heat_group_counts", df["heat_group"].value_counts(dropna=False).to_dict())
    df["overlap_flag"] = (df["heat_group"] == "high") & (df["distress_group"] == "high")
    ov = df.loc[df["overlap_flag"], ["nta2020", "ntaname", "boroname"]].sort_values("nta2020")
    log("overlap_count", len(ov))
    log("overlap_ntas", ov.values.tolist())

    stats = {}
    for key, x in [("trees_per_km2_vs_mhlth", "trees_per_km2"), ("hvi_rank_vs_mhlth", "hvi_rank")]:
        d = df[[x, "mhlth"]].dropna()
        r = spearmanr(d[x], d["mhlth"])
        stats[key] = {"x": x, "y": "mhlth", "rho": round(float(r.statistic), 4),
                      "p": float(f"{r.pvalue:.4g}"), "n": int(len(d))}
    for key, x in [("hvi_rank_vs_mhlth_partial_income", "hvi_rank"),
                   ("trees_per_km2_vs_mhlth_partial_income", "trees_per_km2")]:
        d = df[[x, "mhlth", "median_income"]].dropna()
        stats[key] = partial_spearman(d, x, "mhlth", "median_income")
    # A6: pct_black_pop is used only for this adjustment; it is not a map property.
    d = df[["hvi_rank", "mhlth", "median_income", "pct_black_pop"]].dropna()
    stats["hvi_rank_vs_mhlth_partial_income_pct_black"] = partial_spearman(
        d, "hvi_rank", "mhlth", ["median_income", "pct_black_pop"])
    log("spearman", stats)
    stats["residential_nta_count"] = int(len(df))
    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")

    PROC.mkdir(parents=True, exist_ok=True)
    df.drop(columns="geometry").to_csv(PROC / "nta_table.csv", index=False)

    out = df[PROPS + ["geometry"]].to_crs("EPSG:4326").copy()
    out["hvi_rank"] = out["hvi_rank"].astype("Int64")
    for c in ["surface_temp", "greenspace", "pct_households_ac", "mhlth", "depression", "trees_per_km2"]:
        out[c] = out[c].round(2)
    out["median_income"] = out["median_income"].round(0).astype("Int64")

    def feature_props(row):
        p = {}
        for c in PROPS:
            v = row[c]
            if v is pd.NA or (isinstance(v, float) and np.isnan(v)):
                v = None
            elif isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = float(v)
            elif isinstance(v, (np.bool_,)):
                v = bool(v)
            p[c] = v
        return p

    def rounded(coords):
        if isinstance(coords[0], (float, int)):
            return [round(coords[0], 5), round(coords[1], 5)]
        return [rounded(c) for c in coords]

    tol = 0.0
    while True:
        geoms = out.geometry if tol == 0 else out.geometry.simplify(tol, preserve_topology=True)
        feats = []
        for (_, row), g in zip(out.iterrows(), geoms):
            gm = mapping(g)
            feats.append({"type": "Feature", "properties": feature_props(row),
                          "geometry": {"type": gm["type"], "coordinates": rounded(gm["coordinates"])}})
        text = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"))
        size = len(text.encode())
        print(f"simplify tolerance {tol}: {size} bytes")
        if size <= MAX_GEOJSON:
            break
        tol = 0.00001 if tol == 0 else tol * 2
        assert tol < 0.01, "could not get nta.geojson under 2 MB"
    (WEB / "nta.geojson").write_text(text)
    log("geojson_features", len(feats))
    log("geojson_simplify_tolerance_deg", tol)
    log("geojson_bytes", size)

    elapsed = time.monotonic() - t0
    log("runtime_seconds", round(elapsed, 1))
    (PROC / "build_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    if elapsed > MAX_RUNTIME:
        sys.exit("HARD LIMIT: pipeline run > 10 minutes")


if __name__ == "__main__":
    main()
