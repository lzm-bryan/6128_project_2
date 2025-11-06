# -*- coding: utf-8 -*-
import os, sys
from pathlib import Path

def ensure_proj():
    # 尽量避免 Windows 下 pyproj 找不到 proj.db
    if os.name == "nt":
        prefix = os.environ.get("CONDA_PREFIX") or sys.prefix
        proj = Path(prefix) / "Library" / "share" / "proj"
        if proj.exists():
            os.environ.setdefault("PROJ_LIB", str(proj))

ensure_proj()

import osmnx as ox
import geopandas as gpd

OUT = Path("edges.shp")

print("Downloading road network: Porto, Portugal (drive)…")
G = ox.graph_from_place("Porto, Portugal", network_type="drive")
edges = ox.graph_to_gdfs(G, nodes=False, edges=True).reset_index()

# FMM 需要字段名
edges = edges.rename(columns={"u": "source", "v": "target"})
edges["id"] = range(len(edges))

edges[["id", "source", "target", "geometry"]].to_file(OUT)
print("Wrote", OUT.resolve(), "edges:", len(edges))
