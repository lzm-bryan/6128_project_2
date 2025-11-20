# task6_simple_no_gdal.py
# -*- coding: utf-8 -*-
"""
Task 6 (Bonus): Map Matching Quality Analysis - Simplified Version
No GDAL/Fiona dependency - Uses only pandas, shapely, folium
"""

import json, re, argparse, warnings
from pathlib import Path
import pandas as pd
from shapely import wkt
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import nearest_points
import folium
import numpy as np

warnings.filterwarnings('ignore')


def sniff_sep(p: Path) -> str:
    """Detect CSV separator"""
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        head = f.readline()
    if ";" in head and "," not in head:
        return ";"
    if "," in head and ";" not in head:
        return ","
    return ","


def parse_geom_safe(wkt_text):
    """Parse WKT geometry string safely"""
    if not isinstance(wkt_text, str):
        return None
    s = wkt_text.strip().strip('"').strip("'")
    if not s or s.upper().endswith("EMPTY"):
        return None
    try:
        return wkt.loads(s)
    except Exception:
        # Fix common WKT issues
        s2 = re.sub(r',\s*\)', ')', s)
        try:
            return wkt.loads(s2)
        except Exception:
            return None


def load_original_gps(train_csv: Path, max_trips=None):
    """Load original GPS trajectories from train.csv"""
    df = pd.read_csv(train_csv)
    if max_trips:
        df = df.head(max_trips)

    gps_data = {}
    for idx, row in df.iterrows():
        polyline_str = row.get("POLYLINE", "")
        if not polyline_str or pd.isna(polyline_str):
            continue

        try:
            pts = json.loads(polyline_str) if isinstance(polyline_str, str) else polyline_str
        except:
            try:
                import ast
                pts = ast.literal_eval(polyline_str)
            except:
                continue

        if pts and len(pts) >= 2:
            valid_pts = []
            for p in pts:
                if isinstance(p, (list, tuple)) and len(p) == 2:
                    lon, lat = float(p[0]), float(p[1])
                    if -180 <= lon <= 180 and -90 <= lat <= 90:
                        valid_pts.append((lon, lat))
            if len(valid_pts) >= 2:
                gps_data[idx] = valid_pts

    return gps_data


def calculate_matching_quality(gps_points, matched_geom):
    """
    Calculate quality metrics:
    1. Average distance from GPS to matched route (meters)
    2. Coverage ratio (points within 50m threshold)
    3. Route continuity score
    """
    if matched_geom is None or not gps_points:
        return {
            'avg_distance': 999,
            'max_distance': 999,
            'coverage': 0.0,
            'continuity': 0.0,
            'quality_score': 0.0,
            'num_gps_points': len(gps_points),
            'route_length': 0
        }

    # Calculate distances (approximate: 1 degree ≈ 111km)
    distances = []
    for lon, lat in gps_points:
        pt = Point(lon, lat)
        try:
            nearest = nearest_points(pt, matched_geom)[1]
            # Convert degrees to meters (approximate)
            dist = pt.distance(nearest) * 111000
            distances.append(dist)
        except:
            distances.append(999)

    avg_dist = np.mean(distances) if distances else 999
    max_dist = np.max(distances) if distances else 999

    # Coverage: percentage within 50m
    within_threshold = sum(1 for d in distances if d < 50)
    coverage = within_threshold / len(distances) if distances else 0

    # Continuity: check if matched route is continuous
    continuity = 1.0
    if isinstance(matched_geom, MultiLineString):
        # Penalize fragmented routes
        continuity = 1.0 / len(matched_geom.geoms)

    # Route length
    route_length = matched_geom.length * 111000  # Convert to meters

    # Combined quality score (0-1)
    # Penalize: high avg distance, low coverage, fragmentation
    distance_score = max(0, 1 - avg_dist / 100)  # 100m as reference
    quality_score = (0.5 * distance_score +
                     0.4 * coverage +
                     0.1 * continuity)

    return {
        'avg_distance': round(avg_dist, 2),
        'max_distance': round(max_dist, 2),
        'coverage': round(coverage, 3),
        'continuity': round(continuity, 3),
        'quality_score': round(quality_score, 3),
        'num_gps_points': len(gps_points),
        'route_length': round(route_length, 1)
    }


def identify_poor_matches(matched_csv: Path, train_csv: Path,
                          threshold=0.6, max_trips=None):
    """Identify trips with poor matching quality"""
    print(f"Loading matched results from: {matched_csv}")
    sep = sniff_sep(matched_csv)
    df_matched = pd.read_csv(matched_csv, sep=sep, engine="python")
    df_matched.columns = [str(c).strip().strip('"').strip("'")
                          for c in df_matched.columns]

    if max_trips:
        df_matched = df_matched.head(max_trips)

    print(f"Loading original GPS data from: {train_csv}")
    gps_data = load_original_gps(train_csv, max_trips)

    print(f"\nAnalyzing {len(df_matched)} trips...")

    results = []
    for idx, row in df_matched.iterrows():
        trip_id = row.get('id', idx)
        matched_geom_str = str(row.get('mgeom', ''))
        matched_geom = parse_geom_safe(matched_geom_str)
        gps_points = gps_data.get(trip_id, [])

        metrics = calculate_matching_quality(gps_points, matched_geom)

        # Classify quality
        q_score = metrics['quality_score']
        if q_score >= 0.8:
            quality_class = "Excellent"
        elif q_score >= threshold:
            quality_class = "Good"
        elif q_score >= 0.4:
            quality_class = "Fair"
        else:
            quality_class = "Poor"

        results.append({
            'trip_id': trip_id,
            'quality_class': quality_class,
            'is_poor': q_score < threshold,
            **metrics
        })

    df_results = pd.DataFrame(results)

    # Summary statistics
    poor_matches = df_results[df_results['is_poor']]
    excellent = df_results[df_results['quality_class'] == 'Excellent']
    good = df_results[df_results['quality_class'] == 'Good']
    fair = df_results[df_results['quality_class'] == 'Fair']

    print(f"\n{'=' * 70}")
    print(f"MAP MATCHING QUALITY ANALYSIS REPORT")
    print(f"{'=' * 70}")
    print(f"\nTotal trips analyzed: {len(df_results)}")
    print(f"\nQuality Distribution:")
    print(f"  Excellent (≥0.8): {len(excellent):3d} ({len(excellent) / len(df_results) * 100:5.1f}%)")
    print(f"  Good (≥{threshold}):      {len(good):3d} ({len(good) / len(df_results) * 100:5.1f}%)")
    print(f"  Fair (≥0.4):      {len(fair):3d} ({len(fair) / len(df_results) * 100:5.1f}%)")
    print(f"  Poor (<{threshold}):      {len(poor_matches):3d} ({len(poor_matches) / len(df_results) * 100:5.1f}%)")

    print(f"\nOverall Metrics:")
    print(f"  Average quality score: {df_results['quality_score'].mean():.3f}")
    print(f"  Average distance:      {df_results['avg_distance'].mean():.1f} m")
    print(f"  Average coverage:      {df_results['coverage'].mean():.1%}")

    if len(poor_matches) > 0:
        print(f"\n{'=' * 70}")
        print(f"POOR MATCHES (Quality Score < {threshold}):")
        print(f"{'=' * 70}")
        cols = ['trip_id', 'quality_score', 'avg_distance', 'max_distance',
                'coverage', 'num_gps_points']
        print(poor_matches[cols].to_string(index=False))

        # Identify common issues
        high_dist = poor_matches[poor_matches['avg_distance'] > 100]
        low_cov = poor_matches[poor_matches['coverage'] < 0.3]
        fragmented = poor_matches[poor_matches['continuity'] < 0.5]

        print(f"\nCommon Issues:")
        print(f"  High distance error (>100m):     {len(high_dist)} trips")
        print(f"  Low coverage (<30%):              {len(low_cov)} trips")
        print(f"  Fragmented routes:                {len(fragmented)} trips")

    return df_results, poor_matches


def visualize_comparison(matched_csv: Path, train_csv: Path,
                         trip_id: int, out_html: Path):
    """Create comparison map: GPS points vs matched route"""
    sep = sniff_sep(matched_csv)
    df_matched = pd.read_csv(matched_csv, sep=sep, engine="python")
    df_matched.columns = [str(c).strip().strip('"').strip("'")
                          for c in df_matched.columns]

    # Load GPS and matched route
    gps_data = load_original_gps(train_csv)
    gps_points = gps_data.get(trip_id, [])

    if 'id' in df_matched.columns:
        row = df_matched[df_matched['id'] == trip_id].iloc[0]
    else:
        row = df_matched.iloc[trip_id]

    matched_geom = parse_geom_safe(str(row.get('mgeom', '')))

    # Calculate center
    if gps_points:
        center_lat = np.mean([lat for _, lat in gps_points])
        center_lon = np.mean([lon for lon, _ in gps_points])
    else:
        center_lat, center_lon = 41.15, -8.61

    # Create map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=15,
        tiles="CartoDB positron"
    )

    # Add GPS points with sequence numbers
    for i, (lon, lat) in enumerate(gps_points):
        folium.CircleMarker(
            [lat, lon],
            radius=4,
            color='red',
            fill=True,
            fillColor='red',
            fillOpacity=0.7,
            popup=f"GPS Point {i + 1}",
            tooltip=f"Point {i + 1}"
        ).add_to(m)

    # Add GPS trajectory line
    if len(gps_points) >= 2:
        gps_line = [(lat, lon) for lon, lat in gps_points]
        folium.PolyLine(
            gps_line,
            color='red',
            weight=2,
            opacity=0.5,
            dash_array='5, 5',
            tooltip="Original GPS Track"
        ).add_to(m)

    # Add matched route
    if matched_geom:
        if isinstance(matched_geom, LineString):
            coords = [(lat, lon) for lon, lat in matched_geom.coords]
            folium.PolyLine(
                coords,
                color='blue',
                weight=5,
                opacity=0.8,
                tooltip="Matched Route"
            ).add_to(m)
        elif isinstance(matched_geom, MultiLineString):
            for i, geom in enumerate(matched_geom.geoms):
                coords = [(lat, lon) for lon, lat in geom.coords]
                folium.PolyLine(
                    coords,
                    color='blue',
                    weight=5,
                    opacity=0.8,
                    tooltip=f"Matched Segment {i + 1}"
                ).add_to(m)

    # Add start and end markers
    if gps_points:
        # Start (green)
        folium.Marker(
            [gps_points[0][1], gps_points[0][0]],
            popup="Start",
            icon=folium.Icon(color='green', icon='play')
        ).add_to(m)
        # End (red)
        folium.Marker(
            [gps_points[-1][1], gps_points[-1][0]],
            popup="End",
            icon=folium.Icon(color='red', icon='stop')
        ).add_to(m)

    # Add legend
    legend_html = '''
    <div style="position: fixed; top: 10px; right: 10px; width: 220px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:13px; padding: 10px; border-radius: 5px">
    <p style="margin: 0 0 10px 0"><strong>Trip ''' + str(trip_id) + ''' Comparison</strong></p>
    <p style="margin: 5px 0"><span style="color: red;">●━━</span> Original GPS Track</p>
    <p style="margin: 5px 0"><span style="color: blue;">━━━</span> Matched Route</p>
    <p style="margin: 5px 0"><span style="color: green;">▶</span> Start Point</p>
    <p style="margin: 5px 0"><span style="color: red;">■</span> End Point</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save
    m.save(str(out_html))
    print(f"\n✓ Saved comparison map: {out_html}")


def main():
    parser = argparse.ArgumentParser(
        description="Task 6: Map Matching Quality Analysis (Simplified - No GDAL)"
    )
    parser.add_argument("--matched", type=Path, default=Path("matched.csv"),
                        help="Matched results CSV file")
    parser.add_argument("--train", type=Path, default=Path("train-1500.csv"),
                        help="Original GPS trajectory data")
    parser.add_argument("--threshold", type=float, default=0.6,
                        help="Quality threshold for poor matches (default: 0.6)")
    parser.add_argument("--max-trips", type=int, default=None,
                        help="Maximum number of trips to analyze (for testing)")
    parser.add_argument("--out", type=Path, default=Path("quality_analysis.csv"),
                        help="Output CSV with quality metrics")
    parser.add_argument("--visualize", type=int, nargs='*',
                        help="Trip IDs to visualize (space-separated)")
    args = parser.parse_args()

    # Check input files
    if not args.matched.exists():
        print(f"Error: Matched file not found: {args.matched}")
        return
    if not args.train.exists():
        print(f"Error: Train file not found: {args.train}")
        return

    # Analyze quality
    df_results, poor_matches = identify_poor_matches(
        args.matched, args.train, args.threshold, args.max_trips
    )

    # Save results
    df_results.to_csv(args.out, index=False)
    print(f"\n✓ Saved quality analysis: {args.out}")

    if len(poor_matches) > 0:
        poor_file = args.out.with_name("poor_matches.csv")
        poor_matches.to_csv(poor_file, index=False)
        print(f"✓ Saved poor matches: {poor_file}")

    # Visualize if requested
    if args.visualize:
        out_dir = Path("comparison_maps")
        out_dir.mkdir(exist_ok=True)
        print(f"\nGenerating comparison maps...")
        for trip_id in args.visualize:
            try:
                out_file = out_dir / f"trip_{trip_id}_comparison.html"
                visualize_comparison(args.matched, args.train, trip_id, out_file)
            except Exception as e:
                print(f"✗ Error visualizing trip {trip_id}: {e}")

    print(f"\n{'=' * 70}")
    print("Analysis complete!")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
