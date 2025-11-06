# task5_route_analysis.py
# -*- coding: utf-8 -*-
import json, re, argparse
from pathlib import Path
import pandas as pd
import geopandas as gpd
from shapely import wkt
import folium

def sniff_sep(p: Path) -> str:
    head = p.open("r", encoding="utf-8", errors="ignore").readline()
    if ";" in head and "," not in head: return ";"
    if "," in head and ";" not in head: return ","
    return ","  # 两个都有时，多数是逗号

def parse_edge_seq(s: str):
    """把 cpath/opath 字段解析为 edge id 序列（尽量鲁棒）。"""
    if not isinstance(s, str) or not s.strip():
        return []
    # 常见形式：'[1,2,3]'、'1,2,3'、'1|2|3'、'(1 2 3)' ——统一抽取数字
    return [int(x) for x in re.findall(r"-?\d+", s)]

def load_edge_lengths(edges_shp: Path) -> pd.DataFrame:
    gdf = gpd.read_file(edges_shp)
    if gdf.crs is None or gdf.crs.to_string().upper() in ("EPSG:4326", "WGS84", "EPSG:4269"):
        gdfm = gdf.to_crs(3857)   # WebMercator 近似米
    else:
        gdfm = gdf.to_crs(3857)
    gdf["length_m"] = gdfm.length
    return gdf[["id", "source", "target", "geometry", "length_m"]]

def build_id_time_dict(train_csv: Path, ids_needed: set, sample_interval_s=15):
    """从 train-1500.csv 中取与 matched 同样的 id（我们当初把 id 设为原始行号）。"""
    id2time = {}
    df = pd.read_csv(train_csv)
    for i, s in enumerate(df["POLYLINE"].tolist()):
        if i not in ids_needed:
            continue
        try:
            pts = json.loads(s) if isinstance(s, str) else s
        except Exception:
            import ast; pts = ast.literal_eval(s)
        n = len(pts) if pts else 0
        if n >= 2:
            id2time[i] = (n - 1) * sample_interval_s
    return id2time

def folium_map_for_edges(edges_gdf: gpd.GeoDataFrame, top_df: pd.DataFrame, color: str, out_html: Path, title: str):
    m = folium.Map(location=[41.15, -8.61], zoom_start=12,
                   tiles="CartoDB positron",
                   attr="© OpenStreetMap contributors, © CARTO")
    bounds = []
    joined = edges_gdf.merge(top_df, on="id", how="inner")
    for _, r in joined.iterrows():
        coords = [(lat, lon) for lon, lat in r.geometry.coords]
        folium.PolyLine(coords, weight=6, opacity=0.9, color=color,
                        tooltip=f"id={r.id} | freq={r.get('freq','')} | avg_time_s={round(r.get('avg_time_s',0),1)}"
                        ).add_to(m)
        bounds += list(r.geometry.coords)
    if bounds:
        lats = [lat for (lon, lat) in bounds]; lons = [lon for (lon, lat) in bounds]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    title_html = folium.Element(f"<h3 style='margin:8px'>{title}</h3>")
    m.get_root().html.add_child(title_html)
    m.save(str(out_html))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edges", type=Path, default=Path("edges.shp"))
    ap.add_argument("--matched", type=Path, default=Path("matched.csv"))
    ap.add_argument("--train", type=Path, default=Path("train-1500.csv"))
    ap.add_argument("--topk", type=int, default=10)
    args = ap.parse_args()

    # 1) 读路网 + 边长度
    edges = load_edge_lengths(args.edges)
    id2len = dict(zip(edges.id, edges.length_m))

    # 2) 读贴路结果
    sep = sniff_sep(args.matched)
    mm = pd.read_csv(args.matched, sep=sep, engine="python")
    mm.columns = [str(c).strip().strip('"').strip("'") for c in mm.columns]
    use_field = "cpath" if "cpath" in mm.columns else ("opath" if "opath" in mm.columns else None)
    if not use_field:
        raise SystemExit(f"找不到 cpath/opath 字段，现有列：{mm.columns.tolist()}")

    # 3) 统计频次 & 为平均时间准备 id->route_time
    freq = {}
    ids_needed = set(x for x in mm.get("id", pd.Series([], dtype=int)).tolist() if pd.notna(x))
    id2time = build_id_time_dict(args.train, ids_needed, sample_interval_s=15)

    time_sum = {}     # 每条边累积的时间
    time_count = {}   # 每条边被分配时间的次数（用于求平均）

    for _, r in mm.iterrows():
        path_edges = parse_edge_seq(str(r[use_field]))
        if not path_edges:
            continue
        # 频次
        for e in path_edges:
            freq[e] = freq.get(e, 0) + 1

        # 平均时间：按边长比例把该轨迹总时长分配到路径各边
        rid = int(r["id"]) if "id" in mm.columns and pd.notna(r["id"]) else None
        total_time = id2time.get(rid, None)
        if total_time is None:
            continue
        lengths = [id2len.get(e, 0.0) for e in path_edges]
        total_len = sum(lengths)
        if total_len <= 0:
            continue
        for e, l in zip(path_edges, lengths):
            if l <= 0:
                continue
            dt = total_time * (l / total_len)
            time_sum[e] = time_sum.get(e, 0.0) + dt
            time_count[e] = time_count.get(e, 0) + 1

    # (1) 前 10 频次最高的边
    freq_df = (pd.DataFrame([{"id": e, "freq": c} for e, c in freq.items()])
               .sort_values("freq", ascending=False).head(args.topk))
    # (2) 平均旅行时间最大的 10 条边（忽略从未被分配到的边）
    avg_df = (pd.DataFrame([{"id": e, "avg_time_s": time_sum[e] / time_count[e]}
                            for e in time_sum if time_count.get(e, 0) > 0])
              .sort_values("avg_time_s", ascending=False).head(args.topk))

    # 保存榜单
    freq_out = Path("task5_topfreq.csv"); avg_out = Path("task5_toptime.csv")
    freq_df.to_csv(freq_out, index=False)
    avg_df.to_csv(avg_out, index=False)

    # 可视化 (3)
    folium_map_for_edges(edges, freq_df, color="#d62728", out_html=Path("task5_topfreq.html"),
                         title=f"Top {args.topk} most traversed segments")
    folium_map_for_edges(edges, avg_df, color="#6a3d9a", out_html=Path("task5_toptime.html"),
                         title=f"Top {args.topk} segments by avg travel time")

    print("=== Task 5 Results ===")
    print("Top segments by frequency:\n", freq_df.to_string(index=False))
    print("\nTop segments by avg travel time (seconds):\n", avg_df.to_string(index=False))
    print("\nFiles written:")
    print(" -", freq_out, "and task5_topfreq.html")
    print(" -", avg_out, "and task5_toptime.html")

if __name__ == "__main__":
    main()
