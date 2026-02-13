"""
Analysis module for FCD (Floating Car Data) processing.
Extracted from travel_time_from_fcd_Version2.ipynb
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
from math import isfinite
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for web
import matplotlib.pyplot as plt
import seaborn as sns
from shapely.geometry import LineString, shape, mapping
from pyproj import Geod
import io
import base64

# Visual defaults
sns.set_theme(style="whitegrid", context="talk")

# Geodesic model
geod = Geod(ellps="WGS84")

# Constants
KMH_TO_MPS = 1000.0 / 3600.0

TIME_PERIOD_DEFINITIONS = [
    ("Morning Peak (06–09)", 6, 9),
    ("Midday (09–15)", 9, 15),
    ("Afternoon Peak (15–19)", 15, 19),
    ("Evening (19–22)", 19, 22),
    ("Night (22–06)", 22, 24),
    ("Night (22–06)", 0, 6)
]

COLUMN_RENAMES = {
    "traj_id": "Trajectory ID",
    "Veh_ID": "Trip ID",
    "line_a_time": "Line A Crossing Time",
    "line_b_time": "Line B Crossing Time",
    "segment_weekday": "Segment Weekday (Mon=0)",
    "segment_time_period": "Segment Time of Day",
    "travel_time_seconds": "Segment Travel Time (s)",
    "travel_time": "Segment Travel Time",
    "distance_m_between_lines": "Distance Between Lines (m)",
    "avg_speed_kmh_between_lines": "Average Speed Between Lines (km/h)",
    "segment_max_speed_kmh": "Maximum Speed Between Lines (km/h)",
    "segment_stop_count": "Stops Between Lines (count)",
    "segment_stop_time_seconds": "Total Stop Time Between Lines (s)",
    "segment_stop_avg_seconds": "Average Stop Duration Between Lines (s)",
    "segment_stop_max_seconds": "Longest Stop Between Lines (s)",
    "segment_delay_from_stops_seconds": "Stop Delay Between Lines (s)",
    "segment_min_acc_mps2": "Minimum Acceleration Between Lines (m/s^2)",
    "segment_max_acc_mps2": "Maximum Acceleration Between Lines (m/s^2)",
    "segment_avg_acc_mps2": "Average Acceleration Between Lines (m/s^2)",
    "segment_avg_pos_acc_mps2": "Average Positive Acceleration Between Lines (m/s^2)",
    "segment_avg_neg_acc_mps2": "Average Braking Between Lines (m/s^2)",
    "line_a_lon": "Line A Crossing Longitude",
    "line_a_lat": "Line A Crossing Latitude",
    "line_b_lon": "Line B Crossing Longitude",
    "line_b_lat": "Line B Crossing Latitude",
    "Total_Stop_Time": "Trip Total Stop Time (s)",
    "Avg_Stop_Time": "Trip Average Stop Time (s)",
    "Max_Stop_Time": "Trip Longest Stop (s)",
    "Num_Stops": "Trip Number of Stops",
    "Traveltime": "Trip Travel Time (s)",
    "Departure": "Trip Departure Time",
    "Arrival": "Trip Arrival Time"
}


def parse_point_wkt(wkt: str):
    """Parse WKT POINT string to (lon, lat) tuple."""
    if isinstance(wkt, str):
        wkt = wkt.strip()
        if wkt.upper().startswith('POINT') and '(' in wkt and ')' in wkt:
            try:
                coord_part = wkt[wkt.find('(')+1:wkt.find(')')]
                lon_str, lat_str = coord_part.split()
                return float(lon_str), float(lat_str)
            except ValueError:
                return (np.nan, np.nan)
    return (np.nan, np.nan)


def geodesic_distance_m(lon1, lat1, lon2, lat2):
    """Calculate geodesic distance between two points in meters."""
    vals = (lon1, lat1, lon2, lat2)
    if any(v is None or not isfinite(v) for v in vals):
        return np.nan
    _, _, dist = geod.inv(lon1, lat1, lon2, lat2)
    return float(abs(dist))


def intersection_details(old_lon, old_lat, new_lon, new_lat, query_line):
    """Calculate intersection details between a segment and a query line."""
    vals = (old_lon, old_lat, new_lon, new_lat)
    if any(v is None or not isfinite(v) for v in vals):
        return None
    segment = LineString([(old_lon, old_lat), (new_lon, new_lat)])
    if segment.is_empty or segment.length == 0:
        return None
    inter = segment.intersection(query_line)
    if inter.is_empty:
        return None
    if inter.geom_type == 'Point':
        points = [inter]
    elif inter.geom_type == 'MultiPoint':
        points = list(inter.geoms)
    elif inter.geom_type in {'LineString', 'LinearRing'}:
        boundary = inter.boundary
        points = list(boundary.geoms) if hasattr(boundary, 'geoms') else [boundary]
    elif inter.geom_type == 'GeometryCollection':
        points = [g for g in inter.geoms if g.geom_type == 'Point']
        if not points:
            return None
    else:
        return None
    distances = [segment.project(pt) for pt in points]
    if not distances:
        return None
    distance_along = min(distances)
    fraction = distance_along / segment.length if segment.length != 0 else 0.0
    point = segment.interpolate(distance_along)
    lon_i, lat_i = point.x, point.y
    distance_from_start = geodesic_distance_m(old_lon, old_lat, lon_i, lat_i)
    return {
        'fraction': fraction,
        'point': (lon_i, lat_i),
        'distance_from_start_m': distance_from_start
    }


def weighted_average(values, weights):
    """Calculate weighted average."""
    mask = (~np.isnan(values)) & (~np.isnan(weights)) & (weights > 0)
    return float(np.average(values[mask], weights=weights[mask])) if mask.any() else np.nan


def determine_time_period(ts):
    """Determine time period from timestamp."""
    if pd.isna(ts):
        return np.nan
    hour = ts.hour + ts.minute / 60
    for label, start_hour, end_hour in TIME_PERIOD_DEFINITIONS:
        if start_hour <= end_hour:
            if start_hour <= hour < end_hour:
                return label
        else:
            if hour >= start_hour or hour < end_hour:
                return label
    return 'Night (22–06)'


def load_and_filter_fcd(csv_path, long_stop_threshold_s=600):
    """Load FCD CSV file and filter out trajectories with very long stops."""
    FCD = pd.read_csv(csv_path, sep=';')
    
    # Ensure numeric times
    FCD['t1'] = pd.to_numeric(FCD['t1'], errors='coerce')
    FCD['t2'] = pd.to_numeric(FCD['t2'], errors='coerce')
    
    # Remove trajectories with very long stops
    long_stops = FCD.groupby(['traj_id', 'x2']).apply(
        lambda x: (x['t2'].max() - x['t1'].min()) > long_stop_threshold_s
    )
    long_stop_ids = long_stops[long_stops].index.get_level_values(0).unique()
    FCD = FCD[~FCD['traj_id'].isin(long_stop_ids)].reset_index(drop=True)
    
    # Sort for all subsequent analyses
    FCD = FCD.sort_values(by=['traj_id', 'traj_seq']).reset_index(drop=True)
    
    # Calculate trip start/end and duration
    FCD_times = (
        FCD.groupby('traj_id')
          .agg(Departure=('t1', 'min'), Arrival=('t2', 'max'))
          .dropna()
          .assign(Traveltime=lambda df: df['Arrival'] - df['Departure'])
          .reset_index()
          .rename(columns={'traj_id': 'Veh_ID'})
    )
    FCD_times['Departure'] = pd.to_datetime(FCD_times['Departure'], unit='s')
    FCD_times['Arrival'] = pd.to_datetime(FCD_times['Arrival'], unit='s')
    
    return FCD, FCD_times


def detect_stops(FCD, stop_speed_threshold_kmh=0.1, min_stop_points=2):
    """Detect stops in FCD data."""
    FCD['v2'] = pd.to_numeric(FCD.get('v2'), errors='coerce')
    FCD['is_stop'] = FCD['v2'] < stop_speed_threshold_kmh
    FCD['stop_group'] = (FCD['is_stop'] != FCD['is_stop'].shift()).cumsum()
    FCD['stop_group_size'] = 0
    FCD['is_valid_stop'] = False
    
    stops_only = FCD[FCD['is_stop']].copy()
    if not stops_only.empty:
        group_sizes = stops_only.groupby(['traj_id', 'stop_group'])['is_stop'].transform('size')
        valid_mask = group_sizes >= min_stop_points
        FCD.loc[stops_only.index, 'stop_group_size'] = group_sizes
        FCD.loc[stops_only.index, 'is_valid_stop'] = valid_mask.values
    
    # Determine coordinate columns
    if 'y2' in FCD.columns:
        STOP_X_COL, STOP_Y_COL = 'x2', 'y2'
    else:
        coord_cols = [c for c in FCD.columns if c.lower().startswith('x')]
        if len(coord_cols) >= 2:
            STOP_X_COL, STOP_Y_COL = coord_cols[:2]
        elif len(coord_cols) == 1:
            STOP_X_COL = STOP_Y_COL = coord_cols[0]
        else:
            STOP_X_COL, STOP_Y_COL = None, None
    
    return FCD, STOP_X_COL, STOP_Y_COL


def parse_trajectory_points(FCD):
    """Parse WKT points from FCD and build trajectory point list."""
    # Find WKT columns
    old_wkt_candidates = [c for c in FCD.columns if 'wkt' in c.lower() and any(k in c.lower() for k in ['old','start'])]
    new_wkt_candidates = [c for c in FCD.columns if 'wkt' in c.lower() and any(k in c.lower() for k in ['new','end'])]
    
    if not old_wkt_candidates or not new_wkt_candidates:
        raise ValueError('No suitable WKT columns found for start/end.')
    
    old_wkt_col, new_wkt_col = old_wkt_candidates[0], new_wkt_candidates[0]
    
    # Parse coordinates
    FCD[['old_lon','old_lat']] = pd.DataFrame(
        FCD[old_wkt_col].apply(parse_point_wkt).tolist(), 
        index=FCD.index
    )
    FCD[['new_lon','new_lat']] = pd.DataFrame(
        FCD[new_wkt_col].apply(parse_point_wkt).tolist(), 
        index=FCD.index
    )
    
    # Build trajectory points
    traj_points_list = []
    for traj_id, group in FCD.groupby('traj_id', sort=False):
        group = group.sort_values('traj_seq')
        # First valid old point
        first_valid_old = None
        for lon, lat in group[['old_lon','old_lat']].to_numpy(dtype=float):
            if np.isfinite(lon) and np.isfinite(lat):
                first_valid_old = (lon, lat)
                break
        coords = []
        if first_valid_old is not None:
            coords.append(first_valid_old)
        for lon, lat in group[['new_lon','new_lat']].to_numpy(dtype=float):
            if np.isfinite(lon) and np.isfinite(lat):
                coords.append((lon, lat))
        if len(coords) < 2:
            continue
        traj_df = pd.DataFrame(coords, columns=['lon','lat'])
        traj_df['traj_id'] = traj_id
        traj_df['point_order'] = range(len(traj_df))
        traj_points_list.append(traj_df)
    
    traj_points = pd.concat(traj_points_list, ignore_index=True) if traj_points_list else pd.DataFrame(columns=['traj_id','point_order','lon','lat'])
    return FCD, traj_points


def sanity_check_and_fix_lines(FCD, line_a, line_b, max_traj=100):
    """Check if lines need to be swapped based on trajectory crossing order."""
    stats = {'A':0,'B':0,'both':0,'B_before_A':0,'checked':0}
    samples = []

    def _first_cross_order(g):
        first = None
        seenA = seenB = False
        g = g.sort_values('traj_seq')
        for _, r in g.iterrows():
            if not (np.isfinite([r.old_lon, r.old_lat, r.new_lon, r.new_lat]).all()):
                continue
            seg = LineString([(r.old_lon, r.old_lat), (r.new_lon, r.new_lat)])
            if seg.is_empty or not seg.is_valid:
                continue
            if seg.intersects(line_a) and not seenA:
                seenA = True
                if first is None:
                    first = 'A'
            if seg.intersects(line_b) and not seenB:
                seenB = True
                if first is None:
                    first = 'B'
            if seenA and seenB:
                break
        return first, seenA, seenB

    for tid, g in list(FCD.groupby('traj_id', sort=False))[:max_traj]:
        first, sa, sb = _first_cross_order(g)
        stats['A'] += int(sa)
        stats['B'] += int(sb)
        stats['both'] += int(sa and sb)
        stats['checked'] += 1
        if sa and sb and first == 'B':
            stats['B_before_A'] += 1
            if len(samples) < 2:
                samples.append(tid)

    print(f"Sanity: checked={stats['checked']} hitA={stats['A']} hitB={stats['B']} both={stats['both']} "
          f"B_before_A={stats['B_before_A']} samples={samples}")

    # If majority of 'both' cases have B before A, swap lines
    if stats['both'] > 0 and stats['B_before_A'] / stats['both'] > 0.7:
        print("Note: Many 'B before A' → Swapping lines (A<->B).")
        return line_b, line_a
    return line_a, line_b


def calculate_segments(FCD, FCD_times, line_a, line_b, STOP_X_COL, STOP_Y_COL):
    """Calculate segment crossings and statistics."""
    crossings = []
    segment_stop_details_records = []
    
    for traj_id, group in FCD.groupby('traj_id', sort=False):
        group_sorted = group.sort_values('traj_seq').reset_index(drop=True)
        line_a_info, line_b_info = None, None
        distance_accum = 0.0
        prev_point = None
        crossed_b_before_a = False

        for _, row in group_sorted.iterrows():
            old_lon, old_lat = row.old_lon, row.old_lat
            new_lon, new_lat = row.new_lon, row.new_lat
            t_start, t_end = row.t1, row.t2
            if any(v is None or not isfinite(v) for v in [old_lon, old_lat, new_lon, new_lat, t_start, t_end]):
                if line_a_info is not None:
                    prev_point = None
                continue

            detail_a = None
            if line_a_info is None:
                detail_a = intersection_details(old_lon, old_lat, new_lon, new_lat, line_a)
                if detail_a is not None:
                    fa = detail_a['fraction']
                    line_a_time = float(t_start + fa * (t_end - t_start))
                    line_a_info = {'time': line_a_time, 'point': detail_a['point'], 'fraction': fa}
                    prev_point = detail_a['point']
                    distance_accum = 0.0

            detail_b = intersection_details(old_lon, old_lat, new_lon, new_lat, line_b)
            if line_a_info is None and detail_b is not None:
                crossed_b_before_a = True
                break
            if line_a_info is None:
                continue

            same_segment_as_a = detail_a is not None
            if line_b_info is None and detail_b is not None:
                fb = detail_b['fraction']
                if (not same_segment_as_a) or (fb >= line_a_info['fraction']):
                    if prev_point is None:
                        prev_point = (old_lon, old_lat)
                    b_point = detail_b['point']
                    dist_inc = geodesic_distance_m(prev_point[0], prev_point[1], b_point[0], b_point[1])
                    if np.isfinite(dist_inc):
                        distance_accum += dist_inc
                    line_b_time = float(t_start + fb * (t_end - t_start))
                    line_b_info = {'time': line_b_time, 'point': b_point}
                    prev_point = b_point
                    break

            if line_b_info is None:
                if prev_point is None:
                    prev_point = (old_lon, old_lat)
                dist_inc = geodesic_distance_m(prev_point[0], prev_point[1], new_lon, new_lat)
                if np.isfinite(dist_inc):
                    distance_accum += dist_inc
                prev_point = (new_lon, new_lat)

        if crossed_b_before_a or line_a_info is None or line_b_info is None:
            continue

        travel_time_seconds = line_b_info['time'] - line_a_info['time']
        if travel_time_seconds <= 0:
            continue

        line_a_time = line_a_info['time']
        line_b_time = line_b_info['time']
        segment_mask = (group_sorted['t2'] > line_a_time) & (group_sorted['t1'] < line_b_time)
        segment_df = group_sorted.loc[segment_mask].copy()
        if not segment_df.empty:
            segment_df['segment_overlap_start'] = np.maximum(segment_df['t1'], line_a_time)
            segment_df['segment_overlap_end'] = np.minimum(segment_df['t2'], line_b_time)
            segment_df['segment_overlap_duration'] = np.maximum(0.0, segment_df['segment_overlap_end'] - segment_df['segment_overlap_start'])
        else:
            segment_df = group_sorted.iloc[0:0].copy()

        # Stops in time window
        segment_stop_count = 0
        segment_stop_time = 0.0
        segment_stop_max = 0.0
        segment_stop_avg = 0.0

        if {'is_valid_stop','stop_group'}.issubset(segment_df.columns):
            stop_df = segment_df[(segment_df['is_valid_stop']) & (segment_df['segment_overlap_duration'] > 0)]
            if not stop_df.empty:
                grouped_stops = stop_df.groupby('stop_group')
                stop_summary = grouped_stops.agg(overlap_start=('segment_overlap_start','min'), overlap_end=('segment_overlap_end','max'))
                stop_summary['stop_time'] = np.maximum(0.0, stop_summary['overlap_end'] - stop_summary['overlap_start'])
                stop_summary = stop_summary[stop_summary['stop_time'] > 0]
                if not stop_summary.empty:
                    segment_stop_count = int(stop_summary.shape[0])
                    segment_stop_time = float(stop_summary['stop_time'].sum())
                    segment_stop_max = float(stop_summary['stop_time'].max())
                    segment_stop_avg = float(segment_stop_time / segment_stop_count) if segment_stop_count else 0.0
                    detailed = stop_summary.copy()
                    if 'v2' in stop_df.columns:
                        detailed['mean_speed'] = grouped_stops['v2'].mean().astype(float)
                    if STOP_X_COL and STOP_X_COL in stop_df.columns:
                        detailed['mean_x'] = grouped_stops[STOP_X_COL].mean().astype(float)
                    if STOP_Y_COL and STOP_Y_COL in stop_df.columns:
                        detailed['mean_y'] = grouped_stops[STOP_Y_COL].mean().astype(float)
                    detailed['point_count'] = grouped_stops['segment_overlap_duration'].apply(lambda v: int((v > 0).sum())).astype(int)
                    detailed['traj_id'] = traj_id
                    detailed['segment_departure_time'] = line_a_time
                    detailed['segment_arrival_time'] = line_b_time
                    segment_stop_details_records.append(detailed.reset_index())

        # Acceleration
        acc_df = segment_df[segment_df['segment_overlap_duration'] > 0].copy()
        if not acc_df.empty:
            acc_df['v1_mps'] = pd.to_numeric(acc_df.get('v1'), errors='coerce') * KMH_TO_MPS
            acc_df['v2_mps'] = pd.to_numeric(acc_df.get('v2'), errors='coerce') * KMH_TO_MPS
            if 'time_diff' in acc_df.columns:
                acc_df['time_diff_s'] = pd.to_numeric(acc_df['time_diff'], errors='coerce')
            else:
                acc_df['time_diff_s'] = pd.to_numeric(acc_df['t2'], errors='coerce') - pd.to_numeric(acc_df['t1'], errors='coerce')
            acc_df['acc_mps2'] = np.where(acc_df['time_diff_s'] > 0, (acc_df['v2_mps'] - acc_df['v1_mps']) / acc_df['time_diff_s'], np.nan)
            valid_acc = acc_df[~acc_df['acc_mps2'].isna()]
            if not valid_acc.empty:
                weights = valid_acc['segment_overlap_duration'].to_numpy(dtype=float)
                acc_values = valid_acc['acc_mps2'].to_numpy(dtype=float)
                segment_avg_acc = weighted_average(acc_values, weights)
                segment_min_acc = float(acc_values.min())
                segment_max_acc = float(acc_values.max())
                pos_mask = acc_values > 0
                neg_mask = acc_values < 0
                segment_avg_pos_acc = weighted_average(acc_values[pos_mask], weights[pos_mask]) if pos_mask.any() else np.nan
                segment_avg_neg_acc = weighted_average(acc_values[neg_mask], weights[neg_mask]) if neg_mask.any() else np.nan
            else:
                segment_avg_acc = segment_min_acc = segment_max_acc = segment_avg_pos_acc = segment_avg_neg_acc = np.nan
        else:
            segment_avg_acc = segment_min_acc = segment_max_acc = segment_avg_pos_acc = segment_avg_neg_acc = np.nan

        # Maximum speed in segment window
        speed_df = segment_df[segment_df['segment_overlap_duration'] > 0].copy()
        if not speed_df.empty:
            speed_series = []
            for speed_col in ['v1','v2','speed','Velocity','vel','spd']:
                if speed_col in speed_df.columns:
                    speed_series.append(pd.to_numeric(speed_df[speed_col], errors='coerce'))
            if speed_series:
                combined_speed = pd.concat(speed_series, axis=1)
                segment_max_speed_kmh = float(np.nanmax(combined_speed.to_numpy()))
            else:
                segment_max_speed_kmh = np.nan
        else:
            segment_max_speed_kmh = np.nan

        crossings.append({
            'traj_id': traj_id,
            'line_a_time': line_a_time,
            'line_b_time': line_b_time,
            'travel_time_seconds': travel_time_seconds,
            'distance_m_between_lines': distance_accum,
            'line_a_lon': line_a_info['point'][0],
            'line_a_lat': line_a_info['point'][1],
            'line_b_lon': line_b_info['point'][0],
            'line_b_lat': line_b_info['point'][1],
            'segment_stop_count': segment_stop_count,
            'segment_stop_time_seconds': segment_stop_time,
            'segment_stop_max_seconds': segment_stop_max,
            'segment_stop_avg_seconds': segment_stop_avg,
            'segment_delay_from_stops_seconds': segment_stop_time,
            'segment_min_acc_mps2': segment_min_acc,
            'segment_max_acc_mps2': segment_max_acc,
            'segment_avg_acc_mps2': segment_avg_acc,
            'segment_avg_pos_acc_mps2': segment_avg_pos_acc,
            'segment_avg_neg_acc_mps2': segment_avg_neg_acc,
            'segment_max_speed_kmh': segment_max_speed_kmh
        })

    crossings_df = pd.DataFrame(crossings)

    if not crossings_df.empty:
        for col in ['line_a_time','line_b_time']:
            crossings_df[col] = pd.to_datetime(crossings_df[col], unit='s', utc=True).dt.tz_convert(None)
        crossings_df['travel_time_seconds'] = crossings_df['travel_time_seconds'].astype(float)
        crossings_df['travel_time'] = pd.to_timedelta(crossings_df['travel_time_seconds'], unit='s')
        crossings_df['distance_m_between_lines'] = crossings_df['distance_m_between_lines'].astype(float)
        crossings_df['segment_stop_time_seconds'] = crossings_df['segment_stop_time_seconds'].astype(float)
        crossings_df['segment_stop_max_seconds'] = crossings_df['segment_stop_max_seconds'].astype(float)
        crossings_df['segment_stop_avg_seconds'] = crossings_df['segment_stop_avg_seconds'].astype(float)
        crossings_df['segment_delay_from_stops_seconds'] = crossings_df['segment_delay_from_stops_seconds'].astype(float)
        crossings_df['segment_max_speed_kmh'] = crossings_df['segment_max_speed_kmh'].astype(float)

        crossings_df = crossings_df.merge(
            FCD_times, how='left', left_on='traj_id', right_on='Veh_ID', suffixes=('', '_full_trip')
        )
        crossings_df['avg_speed_kmh_between_lines'] = np.where(
            crossings_df['travel_time_seconds'] > 0,
            (crossings_df['distance_m_between_lines'] / crossings_df['travel_time_seconds']) * 3.6,
            np.nan
        )
        crossings_df['segment_weekday'] = crossings_df['line_a_time'].dt.weekday
        crossings_df['segment_time_period'] = crossings_df['line_a_time'].apply(determine_time_period)

        preferred_order = [
            'traj_id','Veh_ID','line_a_time','line_b_time','segment_weekday','segment_time_period',
            'travel_time_seconds','travel_time','distance_m_between_lines','avg_speed_kmh_between_lines',
            'segment_max_speed_kmh','segment_stop_count','segment_stop_time_seconds','segment_stop_avg_seconds',
            'segment_stop_max_seconds','segment_delay_from_stops_seconds','segment_min_acc_mps2','segment_max_acc_mps2',
            'segment_avg_acc_mps2','segment_avg_pos_acc_mps2','segment_avg_neg_acc_mps2','line_a_lon','line_a_lat','line_b_lon','line_b_lat',
            'Total_Stop_Time','Avg_Stop_Time','Max_Stop_Time','Num_Stops','Traveltime','Departure','Arrival'
        ]
        existing_preferred = [c for c in preferred_order if c in crossings_df.columns]
        remaining_cols = [c for c in crossings_df.columns if c not in existing_preferred]
        crossings_df = crossings_df[existing_preferred + sorted(remaining_cols)]
        crossings_df = crossings_df.rename(columns=COLUMN_RENAMES)
        crossings_df = crossings_df.sort_values(COLUMN_RENAMES['line_a_time']).reset_index(drop=True)

    return crossings_df


def apply_filters(crossings_df, distance_cut_m=700):
    """Apply filters to crossings data."""
    if crossings_df.empty:
        return crossings_df
    
    # Determine column names (handle both original and renamed)
    if "Line A Crossing Time" in crossings_df.columns:
        dep_col = "Line A Crossing Time"
    elif "line_a_time" in crossings_df.columns:
        dep_col = "line_a_time"
    else:
        dep_col = crossings_df.columns[2]  # Fallback
    
    if "Distance Between Lines (m)" in crossings_df.columns:
        dist_col = "Distance Between Lines (m)"
    elif "distance_m_between_lines" in crossings_df.columns:
        dist_col = "distance_m_between_lines"
    else:
        dist_col = None
    
    # Convert time column to datetime
    dep_ts = pd.to_datetime(crossings_df[dep_col], errors="coerce", utc=True).dt.tz_convert(None)
    
    # Filter: Tuesday, Wednesday, Thursday (1, 2, 3)
    mask_weekday = dep_ts.dt.weekday.isin([1, 2, 3])
    
    # Example holidays/breaks for 2021 (can be customized)
    ferien_2021 = [
        pd.date_range("2021-02-01", "2021-02-02"),
        pd.date_range("2021-03-29", "2021-04-09"),
        pd.to_datetime(["2021-05-14", "2021-05-25"]),
        pd.date_range("2021-07-22", "2021-09-01"),
        pd.date_range("2021-10-18", "2021-10-29"),
        pd.date_range("2021-12-23", "2022-01-07"),
    ]
    ferien_dates = pd.DatetimeIndex(
        np.concatenate([fr.values if hasattr(fr, "values") else np.array([fr.value]) for fr in ferien_2021])
    ).tz_localize("UTC").tz_convert(None).date
    
    feiertage_2021 = pd.to_datetime([
        "2021-01-01","2021-04-02","2021-04-05","2021-05-01","2021-05-13","2021-05-24",
        "2021-10-03","2021-10-31","2021-12-25","2021-12-26"
    ]).date
    
    dep_dates = dep_ts.dt.date
    mask_ferien = pd.Series(dep_dates).isin(ferien_dates).to_numpy()
    mask_feiertag = pd.Series(dep_dates).isin(feiertage_2021).to_numpy()
    
    mask_valid = mask_weekday & (~mask_ferien) & (~mask_feiertag)
    crossings_df_filtered = crossings_df.loc[mask_valid].reset_index(drop=True)
    
    # Apply distance cut if column exists
    if dist_col:
        dist_series = pd.to_numeric(crossings_df_filtered[dist_col], errors="coerce")
        crossings_df_filtered = crossings_df_filtered.loc[dist_series <= distance_cut_m].reset_index(drop=True)
    
    # Ensure 'Segment Time of Day' column exists
    if "Segment Time of Day" not in crossings_df_filtered.columns:
        if "Line A Crossing Time" in crossings_df_filtered.columns:
            time_col = "Line A Crossing Time"
        elif "line_a_time" in crossings_df_filtered.columns:
            time_col = "line_a_time"
        else:
            time_col = dep_col
        ts = pd.to_datetime(crossings_df_filtered[time_col], errors="coerce", utc=True).dt.tz_convert(None)
        crossings_df_filtered["Segment Time of Day"] = ts.apply(determine_time_period)
    
    return crossings_df_filtered


def fig_to_base64():
    """Convert current matplotlib figure to base64 string."""
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    buf.close()
    plt.close()
    return img_base64


def generate_plots(crossings_df_filtered):
    """Generate all analysis plots."""
    plots = {}
    
    if crossings_df_filtered.empty:
        return plots
    
    # 1. Distance distribution
    if 'Distance Between Lines (m)' in crossings_df_filtered.columns:
        valid_distances = crossings_df_filtered['Distance Between Lines (m)'].dropna()
        if not valid_distances.empty:
            fig, ax = plt.subplots(figsize=(9,5))
            sns.histplot(data=valid_distances, bins=100, kde=True, color='steelblue', edgecolor='none', alpha=0.7, ax=ax)
            mean_d, median_d = valid_distances.mean(), valid_distances.median()
            ax.axvline(mean_d, color='red', linestyle='--', linewidth=1.5, label=f'Mean: {mean_d:.1f} m')
            ax.axvline(median_d, color='orange', linestyle='-.', linewidth=1.5, label=f'Median: {median_d:.1f} m')
            ax.set_title('Distribution of Travel Distances')
            ax.set_xlabel('Travel Distance [m]')
            ax.set_ylabel('Count')
            ax.legend()
            ax.set_xlim(10, valid_distances.max()*1.05)
            plots['distance_distribution'] = fig_to_base64()
    
    # 2. Travel time distribution
    if 'Segment Travel Time (s)' in crossings_df_filtered.columns:
        valid_times = crossings_df_filtered['Segment Travel Time (s)'].dropna()
        if not valid_times.empty:
            fig, ax = plt.subplots(figsize=(9,5))
            sns.histplot(data=valid_times, bins=100, kde=True, color='steelblue', edgecolor='none', alpha=0.7, ax=ax)
            mean_tt, median_tt = valid_times.mean(), valid_times.median()
            ax.axvline(mean_tt, color='red', linestyle='--', linewidth=1.5, label=f'Mean: {mean_tt:.1f} s')
            ax.axvline(median_tt, color='orange', linestyle='-.', linewidth=1.5, label=f'Median: {median_tt:.1f} s')
            ax.set_title('Distribution of Travel Times')
            ax.set_xlabel('Travel Time [s]')
            ax.set_ylabel('Count')
            ax.legend()
            ax.set_xlim(10, valid_times.max()*1.05)
            plots['traveltime_distribution'] = fig_to_base64()
    
    # 3. Boxplot by time of day
    if 'Segment Time of Day' in crossings_df_filtered.columns and 'Segment Travel Time (s)' in crossings_df_filtered.columns:
        fig, ax = plt.subplots(figsize=(10,5))
        order = ['Morning Peak (06–09)','Midday (09–15)','Afternoon Peak (15–19)','Evening (19–22)','Night (22–06)']
        sns.boxplot(data=crossings_df_filtered, x='Segment Time of Day', y='Segment Travel Time (s)', order=order,
                    palette=sns.color_palette('crest', n_colors=5), width=0.6, fliersize=3, linewidth=1.2, ax=ax)
        ax.set_title('Travel Time by Time of Day')
        ax.set_xlabel('')
        ax.set_ylabel('Travel Time [s]')
        ax.tick_params(axis='x', rotation=0)
        sns.despine(trim=True)
        plots['traveltime_by_timeofday'] = fig_to_base64()
    
    # 4. Max speed distribution
    if 'Maximum Speed Between Lines (km/h)' in crossings_df_filtered.columns:
        series = pd.to_numeric(crossings_df_filtered['Maximum Speed Between Lines (km/h)'], errors='coerce').dropna()
        if not series.empty:
            cap = series.quantile(0.995)
            series_plot = series.clip(upper=cap)
            fig, ax = plt.subplots(figsize=(9,5))
            sns.histplot(data=series_plot, bins=100, kde=True, color='steelblue', edgecolor='none', alpha=0.7, ax=ax)
            ax.axvline(series.mean(), color='red', linestyle='--', linewidth=1.5, label=f"Mean: {series.mean():.1f} km/h")
            ax.axvline(series.median(), color='orange', linestyle='-.', linewidth=1.5, label=f"Median: {series.median():.1f} km/h")
            ax.set_title('Distribution of Max Travel Speeds')
            ax.set_xlabel('Max Travel Speed [km/h]')
            ax.set_ylabel('Count')
            ax.legend()
            ax.set_xlim(left=max(0, series_plot.min()*0.95), right=series_plot.max()*1.05)
            plots['maxspeed_distribution'] = fig_to_base64()
    
    # 5. Scatter: Travel time vs Distance
    if 'Distance Between Lines (m)' in crossings_df_filtered.columns and 'Segment Travel Time (s)' in crossings_df_filtered.columns:
        fig, ax = plt.subplots(figsize=(9,6))
        ax.scatter(crossings_df_filtered['Distance Between Lines (m)'], 
                  crossings_df_filtered['Segment Travel Time (s)'],
                  alpha=0.3, s=20, color='steelblue')
        ax.set_title('Travel Time vs Distance')
        ax.set_xlabel('Distance [m]')
        ax.set_ylabel('Travel Time [s]')
        ax.grid(True, alpha=0.3)
        plots['traveltime_vs_distance'] = fig_to_base64()
    
    # 6. Average speed boxplot by time of day
    if 'Segment Time of Day' in crossings_df_filtered.columns and 'Average Speed Between Lines (km/h)' in crossings_df_filtered.columns:
        fig, ax = plt.subplots(figsize=(10,5))
        order = ['Morning Peak (06–09)','Midday (09–15)','Afternoon Peak (15–19)','Evening (19–22)','Night (22–06)']
        sns.boxplot(data=crossings_df_filtered, x='Segment Time of Day', y='Average Speed Between Lines (km/h)', order=order,
                    palette=sns.color_palette('viridis', n_colors=5), width=0.6, fliersize=3, linewidth=1.2, ax=ax)
        ax.set_title('Average Speed by Time of Day')
        ax.set_xlabel('')
        ax.set_ylabel('Average Speed [km/h]')
        ax.tick_params(axis='x', rotation=0)
        sns.despine(trim=True)
        plots['avgspeed_by_timeofday'] = fig_to_base64()
    
    return plots


def get_statistics(crossings_df_filtered):
    """Get descriptive statistics."""
    if crossings_df_filtered.empty:
        return {}
    
    stats = {}
    
    # Travel time statistics
    if 'Segment Travel Time (s)' in crossings_df_filtered.columns:
        tt = crossings_df_filtered['Segment Travel Time (s)'].dropna()
        if not tt.empty:
            stats['travel_time'] = {
                'count': int(len(tt)),
                'mean': float(tt.mean()),
                'median': float(tt.median()),
                'std': float(tt.std()),
                'min': float(tt.min()),
                'max': float(tt.max())
            }
    
    # Distance statistics
    if 'Distance Between Lines (m)' in crossings_df_filtered.columns:
        dist = crossings_df_filtered['Distance Between Lines (m)'].dropna()
        if not dist.empty:
            stats['distance'] = {
                'count': int(len(dist)),
                'mean': float(dist.mean()),
                'median': float(dist.median()),
                'std': float(dist.std()),
                'min': float(dist.min()),
                'max': float(dist.max())
            }
    
    # Speed statistics
    if 'Average Speed Between Lines (km/h)' in crossings_df_filtered.columns:
        speed = crossings_df_filtered['Average Speed Between Lines (km/h)'].dropna()
        if not speed.empty:
            stats['avg_speed'] = {
                'count': int(len(speed)),
                'mean': float(speed.mean()),
                'median': float(speed.median()),
                'std': float(speed.std()),
                'min': float(speed.min()),
                'max': float(speed.max())
            }
    
    return stats
