# task4_visualize_routes.py
# -*- coding: utf-8 -*-
import argparse, json, re
from pathlib import Path
import pandas as pd
from shapely import wkt
from shapely.geometry import LineString, MultiLineString, mapping
import folium

# 20 色调色板（不依赖 matplotlib）
PALETTE = [
    "#e41a1c","#377eb8","#4daf4a","#984ea3","#ff7f00",
    "#ffff33","#a65628","#f781bf","#999999","#66c2a5",
    "#fc8d62","#8da0cb","#e78ac3","#a6d854","#ffd92f",
    "#e5c494","#b3b3b3","#1b9e77","#d95f02","#7570b3"
]

def sniff_sep(p: Path) -> str:
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        head = f.readline()
    if ";" in head and "," not in head: return ";"
    if "," in head and ";" not in head: return ","
    return ","  # 两个都有时，多数是逗号

_fix_tail_comma = re.compile(r',\s*\)')  # 修 "..., )"

def parse_geom_safe(s: str):
    if not isinstance(s, str): return None
    w = s.strip().strip('"').strip("'")
    if not w or w.upper().endswith("EMPTY"): return None
    try:
        return wkt.loads(w)
    except Exception:
        w2 = _fix_tail_comma.sub(")", w)
        try:
            return wkt.loads(w2)
        except Exception:
            return None

def to_features(df: pd.DataFrame):
    feats, per_route = [], {}
    for ridx, r in df.iterrows():
        g = parse_geom_safe(str(r.get("mgeom", "")))
        if g is None:
            continue
        route_id = r.get("id", ridx)  # 输出没携带 id 时用行号
        props = {k: r[k] for k in df.columns if k != "mgeom"}
        props["route_id"] = route_id
        if isinstance(g, LineString):
            geoms = [g]
        elif isinstance(g, MultiLineString):
            geoms = list(g.geoms)
        else:
            continue
        for geom in geoms:
            feat = {"type":"Feature","geometry":mapping(geom),"properties":props}
            feats.append(feat)
            per_route.setdefault(route_id, []).append(feat)
    return feats, per_route

def draw_feature(f, m, color):
    g = f["geometry"]
    if g["type"] == "LineString":
        coords = [(lat, lon) for lon, lat in g["coordinates"]]
        folium.PolyLine(coords, weight=3, opacity=0.9, color=color).add_to(m)
    elif g["type"] == "MultiLineString":
        for line in g["coordinates"]:
            coords = [(lat, lon) for lon, lat in line]
            folium.PolyLine(coords, weight=3, opacity=0.9, color=color).add_to(m)

def make_map(per_route, out_html: Path):
    m = folium.Map(location=[41.15,-8.61], zoom_start=12,
                   tiles="CartoDB positron",
                   attr="© OpenStreetMap contributors, © CARTO")
    bounds = []
    for i, (rid, feats) in enumerate(sorted(per_route.items(), key=lambda x: x[0])):
        color = PALETTE[i % len(PALETTE)]
        layer = folium.FeatureGroup(name=f"Route {rid}", overlay=True, show=True)
        for f in feats:
            draw_feature(f, layer, color)
            geom = f["geometry"]
            if geom["type"] == "LineString":
                bounds += geom["coordinates"]
            elif geom["type"] == "MultiLineString":
                for line in geom["coordinates"]:
                    bounds += line
        layer.add_to(m)
    if bounds:
        lats = [lat for (lon, lat) in bounds]
        lons = [lon for (lon, lat) in bounds]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(out_html))

def save_split_maps(per_route, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, (rid, feats) in enumerate(per_route.items()):
        m = folium.Map(location=[41.15,-8.61], zoom_start=12,
                       tiles="CartoDB positron",
                       attr="© OpenStreetMap contributors, © CARTO")
        color = PALETTE[i % len(PALETTE)]
        bounds = []
        for f in feats:
            draw_feature(f, m, color)
            g = f["geometry"]
            if g["type"] == "LineString":
                bounds += g["coordinates"]
            elif g["type"] == "MultiLineString":
                for line in g["coordinates"]:
                    bounds += line
        if bounds:
            lats = [lat for (lon, lat) in bounds]
            lons = [lon for (lon, lat) in bounds]
            m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
        m.save(str(out_dir / f"route_{rid}.html"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=Path("matched_15.csv"))
    ap.add_argument("--out", type=Path, default=Path("routes_all.html"))
    ap.add_argument("--split", action="store_true", help="分别导出每条路线")
    ap.add_argument("--outdir", type=Path, default=Path("routes_split"))
    args = ap.parse_args()

    sep = sniff_sep(args.csv)
    df = pd.read_csv(args.csv, sep=sep, engine="python")
    df.columns = [str(c).strip().strip('"').strip("'") for c in df.columns]
    if "mgeom" not in df.columns:
        raise SystemExit(f"[FATAL] mgeom 不在列里：{df.columns.tolist()}")

    feats, per_route = to_features(df)
    # 保存 GeoJSON（可交作业）
    fc = {"type":"FeatureCollection","features":feats}
    Path(args.out).with_suffix(".geojson").write_text(json.dumps(fc), encoding="utf-8")

    # 合并图
    make_map(per_route, args.out)

    # 单条图（可选）
    if args.split:
        save_split_maps(per_route, args.outdir)

    print(f"OK -> {args.out}（以及同名 .geojson）")
    if args.split:
        print(f"单条路线 → {args.outdir}/route_*.html")

if __name__ == "__main__":
    main()

# (也可以matched_1500)
# # 同图不同色（含图层开关）
# python .\task4_visualize_routes.py --csv .\matched_15.csv --out .\routes_all.html
#
# # 可选：分别导出 15 个 html
# python .\task4_visualize_routes.py --csv .\matched_15.csv --split --outdir .\routes_split
