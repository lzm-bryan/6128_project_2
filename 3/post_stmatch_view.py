# post_stmatch_view.py
# -*- coding: utf-8 -*-
import argparse, json, re
from pathlib import Path
import pandas as pd
from shapely import wkt
from shapely.geometry import LineString, MultiLineString, mapping
import folium

def sniff_sep(csv_path: Path) -> str:
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        head = f.readline()
    if ";" in head and "," not in head: return ";"
    if "," in head and ";" not in head: return ","
    # 两个都有时，多数是逗号
    return ","

def load_matched(csv_path: Path) -> pd.DataFrame:
    sep = sniff_sep(csv_path)
    df = pd.read_csv(csv_path, sep=sep, engine="python")
    df.columns = [str(c).strip().strip('"').strip("'") for c in df.columns]
    if "mgeom" not in df.columns:
        raise ValueError(f"'mgeom' column not found. Columns = {df.columns.tolist()}")
    return df

_fix_tail_comma = re.compile(r',\s*\)')   # 把 ", )" 修成 ")"

def parse_geom_safe(wkt_text: str):
    if not isinstance(wkt_text, str): return None
    s = wkt_text.strip().strip('"').strip("'")
    if not s or s.upper().endswith("EMPTY"):  # LINESTRING EMPTY 直接跳过
        return None
    # 尝试原样解析
    try:
        return wkt.loads(s)
    except Exception:
        # 修补常见坏格式：末尾多逗号，如 "LINESTRING(..., )"
        s2 = _fix_tail_comma.sub(")", s)
        if s2 != s:
            try:
                return wkt.loads(s2)
            except Exception:
                return None
        return None

def df_to_geojson(df: pd.DataFrame) -> (dict, int, int, list):
    feats, ok, bad = [], 0, 0
    bounds = []  # 用于 fit_bounds
    for _, r in df.iterrows():
        g = parse_geom_safe(str(r.get("mgeom", "")))
        if g is None:
            bad += 1
            continue
        props = {k: r[k] for k in df.columns if k != "mgeom"}
        if isinstance(g, LineString):
            feats.append({"type":"Feature","geometry":mapping(g),"properties":props})
            bounds.extend(list(g.coords))
        elif isinstance(g, MultiLineString):
            for seg in g.geoms:
                feats.append({"type":"Feature","geometry":mapping(seg),"properties":props})
                bounds.extend(list(seg.coords))
        else:
            # 其他几何类型很少见，忽略
            bad += 1
            continue
        ok += 1
    fc = {"type":"FeatureCollection","features":feats}
    return fc, ok, bad, bounds

def make_map(geojson_fc: dict, bounds_xy, out_html: Path):
    # 默认波尔图中心；有边界就 fit_bounds
    m = folium.Map(location=[41.15, -8.61], zoom_start=12,
                   tiles="CartoDB positron",
                   attr="© OpenStreetMap contributors, © CARTO")
    for f in geojson_fc["features"]:
        g = f["geometry"]
        if g["type"] == "LineString":
            coords = [(lat, lon) for lon, lat in g["coordinates"]]
            folium.PolyLine(coords, weight=3, opacity=0.85).add_to(m)
        elif g["type"] == "MultiLineString":
            for line in g["coordinates"]:
                coords = [(lat, lon) for lon, lat in line]
                folium.PolyLine(coords, weight=3, opacity=0.85).add_to(m)
    if bounds_xy:
        lats = [lat for (lon, lat) in bounds_xy]
        lons = [lon for (lon, lat) in bounds_xy]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    m.save(str(out_html))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=Path("matched_15.csv"))
    ap.add_argument("--geojson", type=Path, default=Path("matched_15.geojson"))
    ap.add_argument("--html", type=Path, default=Path("matched_15.html"))
    args = ap.parse_args()

    df = load_matched(args.csv)
    fc, ok, bad, bounds = df_to_geojson(df)
    args.geojson.write_text(json.dumps(fc), encoding="utf-8")
    make_map(fc, bounds, args.html)
    print(f"Wrote: {args.geojson} and {args.html}  | parsed={ok}, skipped={bad}")

if __name__ == "__main__":
    main()

# python .\post_stmatch_view.py --csv .\matched_15.csv --geojson .\matched_15.geojson --html .\matched_15.html
