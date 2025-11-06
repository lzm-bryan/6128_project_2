cd D:\pythonproject\uc\3
docker run --rm -v "$((Get-Location).Path):/work" hqzqaq/fmm:1.0 stmatch --network /work/edges.shp --network_id id --source source --target target --gps /work/trips_15_clean.csv -k 32 -r 0.005 -e 0.0005 --vmax 0.0002 --output /work/matched_15.csv --output_fields mgeom,cpath,opath,error
