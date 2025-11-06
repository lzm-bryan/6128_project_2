# docker pull hqzqaq/fmm:1.0


# $env:PROJ_LIB  = "$env:CONDA_PREFIX\Library\share\proj"
# $env:GDAL_DATA = "$env:CONDA_PREFIX\Library\share\gdal"


from pyproj import CRS, datadir
import os, pathlib
print("PROJ_LIB =", os.environ.get("PROJ_LIB"))
print("GDAL_DATA=", os.environ.get("GDAL_DATA"))
print("proj.db exists =", pathlib.Path(datadir.get_data_dir() or "").joinpath("proj.db").exists())
print("CRS 4326 =", CRS.from_epsg(4326))