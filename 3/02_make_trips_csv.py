# -*- coding: utf-8 -*-
import pandas as pd, json
from pathlib import Path

SRC = Path("train-1500.csv")   # 你的原始数据文件名
OUT = Path("trips.csv")

df = pd.read_csv(SRC)
rows = []
for i, s in enumerate(df["POLYLINE"].tolist()):
    coords = json.loads(s) if isinstance(s, str) else s
    if not coords or len(coords) < 2:
        continue
    wkt = "LINESTRING(" + ",".join(f"{lon} {lat}" for lon, lat in coords) + ")"
    rows.append({"id": i, "geom": wkt})
pd.DataFrame(rows)[["id","geom"]].to_csv(OUT, sep=";", index=False)
print("Wrote", OUT.resolve(), "rows:", len(rows))
