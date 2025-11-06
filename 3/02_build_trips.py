# build_trips_15_strict.py
import json, csv, math
from pathlib import Path
import pandas as pd

SRC = Path("train-1500.csv")     # 原始数据
OUT = Path("trips.csv") # 只含前15条、严格校验

def to_wkt(poly):
    # 解析 POLYLINE 为 [(lon,lat), ...]，逐点校验
    if isinstance(poly, str):
        try:
            pts = json.loads(poly)
        except Exception:
            import ast; pts = ast.literal_eval(poly)
    else:
        pts = poly
    ok = []
    for it in pts:
        if isinstance(it, (list, tuple)) and len(it) == 2:
            lon, lat = it
            if all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lon, lat)) \
               and -180 <= float(lon) <= 180 and -90 <= float(lat) <= 90:
                ok.append((float(lon), float(lat)))
    # 去重相邻重复点
    dedup = []
    for xy in ok:
        if not dedup or xy != dedup[-1]:
            dedup.append(xy)
    if len(dedup) < 2:
        return None
    return "LINESTRING(" + ",".join(f"{lon:.6f} {lat:.6f}" for lon, lat in dedup) + ")"

df = pd.read_csv(SRC)
rows = []
for i, s in enumerate(df["POLYLINE"].tolist()):
    w = to_wkt(s)
    if w:
        rows.append({"id": i, "geom": w})
    if len(rows) == 1500:
        break

with OUT.open("w", newline="", encoding="utf-8") as f:
    # 关键修改：用 QUOTE_MINIMAL，表头不会被加引号；分隔符为 ;
    writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(["id", "geom"])   # 表头 => id;geom
    for r in rows:
        writer.writerow([r["id"], r["geom"]])

print("Wrote", OUT.resolve(), "rows:", len(rows))
