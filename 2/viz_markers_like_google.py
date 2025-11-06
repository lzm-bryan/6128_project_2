# -*- coding: utf-8 -*-
import argparse, json
from pathlib import Path
import pandas as pd
import folium
from folium.plugins import MarkerCluster

# 可选：更漂亮的“水滴图钉”，没有则自动降级为蓝色圆图钉
try:
    from folium.plugins import BeautifyIcon
    HAS_BEAUTIFY = True
except Exception:
    HAS_BEAUTIFY = False


def _parse_polyline(s):
    """POLYLINE 是 JSON 字符串：[[lon,lat], ...]"""
    if isinstance(s, str):
        try:
            coords = json.loads(s)
        except Exception:
            import ast
            coords = ast.literal_eval(s)
    else:
        coords = s
    if not coords:
        return []
    # 统一为 (lon, lat) float
    return [(float(lon), float(lat)) for lon, lat in coords]


def load_points(csv_file: Path, n: int = 15):
    """读取前 n 条轨迹 -> 点列表 + 轨迹列表"""
    df = pd.read_csv(csv_file, dtype={"TRIP_ID": str}).head(n).copy()

    points = []
    trajs = []  # [(trip_id, [(lon,lat), ...]), ...]
    for i, row in df.iterrows():
        coords = _parse_polyline(row["POLYLINE"])
        if not coords:
            continue
        trip_id = row.get("TRIP_ID", f"traj_{i}")
        trajs.append((trip_id, coords))
        L = len(coords)
        for k, (lon, lat) in enumerate(coords):
            points.append(
                {
                    "trip_id": trip_id,
                    "idx": k,
                    "lat": lat,
                    "lon": lon,
                    "is_start": k == 0,
                    "is_end": k == L - 1,
                }
            )
    if not points:
        raise RuntimeError("没有有效轨迹点。")
    return points, trajs


def _bounds_from_points(points):
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    pad_lat = (max(lats) - min(lats)) * 0.05 or 0.001
    pad_lon = (max(lons) - min(lons)) * 0.05 or 0.001
    # Leaflet 的 fitBounds 是 [[south, west], [north, east]]
    return [[min(lats) - pad_lat, min(lons) - pad_lon],
            [max(lats) + pad_lat, max(lons) + pad_lon]]


def _icon_blue_pin():
    if HAS_BEAUTIFY:
        return BeautifyIcon(
            icon_shape="marker",
            border_color="#1B4F72",
            border_width=1,
            text_color="white",
            background_color="#2E86DE",
        )
    else:
        return folium.Icon(color="blue", icon="info-sign")  # 基础圆图钉


def _icon_taxi():
    # FontAwesome Taxi
    return folium.Icon(color="orange", icon="taxi", prefix="fa")


def _icon_flag():
    # 方格旗终点
    return folium.Icon(color="red", icon="flag-checkered", prefix="fa")


def build_map(points, trajs, out_html: Path, draw_lines=True, add_stamen=False):
    # 初始中心（稍后用 fit_bounds 精准适配）
    m = folium.Map(location=[points[0]["lat"], points[0]["lon"]],
                   zoom_start=12, tiles=None)

    # —— 底图（全部带 attribution，合规不报错） ——
    folium.TileLayer(
        "OpenStreetMap", name="OSM",
        attr="© OpenStreetMap contributors"
    ).add_to(m)
    folium.TileLayer(
        "CartoDB positron", name="Light",
        attr="© OpenStreetMap contributors, © CARTO"
    ).add_to(m)
    folium.TileLayer(
        "CartoDB dark_matter", name="Dark",
        attr="© OpenStreetMap contributors, © CARTO"
    ).add_to(m)
    if add_stamen:
        # Stamen Toner（服务不稳定，慎用；需要 attribution）
        folium.TileLayer(
            tiles="https://stamen-tiles.a.ssl.fastly.net/toner/{z}/{x}/{y}.png",
            name="Toner (Stamen)",
            attr="Map tiles by Stamen Design, CC BY 3.0 — Map data © OpenStreetMap contributors",
        ).add_to(m)

    # —— 图层：起点/终点/中间点（聚合） ——
    layer_starts = folium.FeatureGroup(name="Start (Taxi)", show=True)
    layer_ends   = folium.FeatureGroup(name="End (Flag)", show=True)
    cluster_mids = MarkerCluster(
        name="Intermediate Points", show=True, disableClusteringAtZoom=15
    )

    # 点标注
    for p in points:
        pt = (p["lat"], p["lon"])
        if p["is_start"]:
            folium.Marker(pt, icon=_icon_taxi(),
                          tooltip=f"Trip {p['trip_id']} — START").add_to(layer_starts)
        elif p["is_end"]:
            folium.Marker(pt, icon=_icon_flag(),
                          tooltip=f"Trip {p['trip_id']} — END").add_to(layer_ends)
        else:
            folium.Marker(pt, icon=_icon_blue_pin(),
                          tooltip=f"Trip {p['trip_id']} — idx {p['idx']}").add_to(cluster_mids)

    layer_starts.add_to(m)
    layer_ends.add_to(m)
    cluster_mids.add_to(m)

    # 轨迹折线（可关）
    if draw_lines:
        from itertools import cycle
        colors = cycle([
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
        ])
        layer_lines = folium.FeatureGroup(name="Trajectories", show=True)
        for trip_id, coords in trajs:
            latlons = [(lat, lon) for (lon, lat) in coords]
            folium.PolyLine(latlons, color=next(colors), weight=3, opacity=0.7).add_to(layer_lines)
        layer_lines.add_to(m)

    # 控件 & 视野
    folium.LayerControl(collapsed=False, position="topleft").add_to(m)
    m.fit_bounds(_bounds_from_points(points))

    out_html.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_html))
    return out_html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True, help="CSV 路径（含 POLYLINE 列）")
    ap.add_argument("--out", type=Path, default=Path("porto_markers.html"))
    ap.add_argument("--n", type=int, default=15, help="取前 n 条轨迹")
    ap.add_argument("--no-lines", action="store_true", help="不画折线")
    ap.add_argument("--stamen", action="store_true", help="加 Stamen Toner 底图（带 attribution）")
    args = ap.parse_args()

    points, trajs = load_points(args.csv, n=args.n)
    out = build_map(points, trajs, args.out, draw_lines=not args.no_lines, add_stamen=args.stamen)
    print("Saved:", out)


if __name__ == "__main__":
    main()

# python viz_markers_like_google.py --csv ./data/processed/train-1500.csv --out ./data/plots/porto_markers.html
#
# 想要 Toner 风格（有 attribution，服务不稳定）：
# python viz_markers_like_google.py --csv ./data/processed/train-1500.csv --out ./data/plots/porto_markers.html --stamen
#
# 不画轨迹折线（只看图钉）：
# python viz_markers_like_google.py --csv ./data/processed/train-1500.csv --out ./data/plots/porto_markers.html --no-lines

