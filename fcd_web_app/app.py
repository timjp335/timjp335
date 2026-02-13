"""
Flask Web Application for FCD Travel Time Analysis
"""

from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
import os
import json
import tempfile
from pathlib import Path
from shapely.geometry import shape
import pandas as pd

import analysis

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max upload
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()


@app.route('/')
def index():
    """Upload page with parameter configuration."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    """Handle CSV upload and initial processing."""
    # Get uploaded file
    if 'csv_file' not in request.files:
        return "No file uploaded", 400
    
    file = request.files['csv_file']
    if file.filename == '':
        return "No file selected", 400
    
    if not file.filename.endswith('.csv'):
        return "Only CSV files are allowed", 400
    
    # Get parameters
    long_stop_threshold = int(request.form.get('long_stop_threshold', 600))
    stop_speed_threshold = float(request.form.get('stop_speed_threshold', 0.1))
    min_stop_points = int(request.form.get('min_stop_points', 2))
    distance_cut = int(request.form.get('distance_cut', 700))
    
    # Save uploaded file temporarily
    temp_csv_path = os.path.join(app.config['UPLOAD_FOLDER'], f"fcd_upload_{os.getpid()}.csv")
    file.save(temp_csv_path)
    
    try:
        # Step 1: Load and filter data
        FCD, FCD_times = analysis.load_and_filter_fcd(temp_csv_path, long_stop_threshold)
        
        # Step 2: Detect stops
        FCD, STOP_X_COL, STOP_Y_COL = analysis.detect_stops(FCD, stop_speed_threshold, min_stop_points)
        
        # Step 3: Parse trajectory points
        FCD, traj_points = analysis.parse_trajectory_points(FCD)
        
        # Save intermediate data
        fcd_path = os.path.join(app.config['UPLOAD_FOLDER'], f"fcd_processed_{os.getpid()}.pkl")
        fcd_times_path = os.path.join(app.config['UPLOAD_FOLDER'], f"fcd_times_{os.getpid()}.pkl")
        traj_points_path = os.path.join(app.config['UPLOAD_FOLDER'], f"traj_points_{os.getpid()}.pkl")
        
        FCD.to_pickle(fcd_path)
        FCD_times.to_pickle(fcd_times_path)
        traj_points.to_pickle(traj_points_path)
        
        # Calculate map center from trajectory points
        if not traj_points.empty:
            center_lon = float(traj_points['lon'].median())
            center_lat = float(traj_points['lat'].median())
        else:
            center_lon, center_lat = 10.5302, 52.2658  # Default coordinates
        
        # Store paths and parameters in session
        session['fcd_path'] = fcd_path
        session['fcd_times_path'] = fcd_times_path
        session['traj_points_path'] = traj_points_path
        session['stop_x_col'] = STOP_X_COL
        session['stop_y_col'] = STOP_Y_COL
        session['distance_cut'] = distance_cut
        session['center_lon'] = center_lon
        session['center_lat'] = center_lat
        session['num_trajectories'] = int(FCD['traj_id'].nunique())
        
        return redirect(url_for('map_view'))
    
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_csv_path):
            os.remove(temp_csv_path)
        return f"Error processing CSV file: {str(e)}", 500


@app.route('/map')
def map_view():
    """Interactive map for drawing measurement lines."""
    if 'fcd_path' not in session:
        return redirect(url_for('index'))
    
    center_lon = session.get('center_lon', 10.5302)
    center_lat = session.get('center_lat', 52.2658)
    num_trajectories = session.get('num_trajectories', 0)
    
    return render_template('map.html', 
                          center_lon=center_lon, 
                          center_lat=center_lat,
                          num_trajectories=num_trajectories)


@app.route('/analyze', methods=['POST'])
def analyze():
    """Process drawn lines and calculate segments."""
    if 'fcd_path' not in session:
        return jsonify({'error': 'No data loaded'}), 400
    
    # Get drawn lines from request
    data = request.get_json()
    if not data or 'lines' not in data:
        return jsonify({'error': 'No lines provided'}), 400
    
    lines_geojson = data['lines']
    
    # Parse GeoJSON lines
    line_geoms = []
    for feat in lines_geojson.get('features', []):
        geom = shape(feat['geometry'])
        if geom.geom_type == 'LineString':
            line_geoms.append(geom)
    
    if len(line_geoms) < 2:
        return jsonify({'error': 'At least 2 lines are required'}), 400
    
    line_a, line_b = line_geoms[0], line_geoms[1]
    
    try:
        # Load intermediate data
        FCD = pd.read_pickle(session['fcd_path'])
        FCD_times = pd.read_pickle(session['fcd_times_path'])
        STOP_X_COL = session['stop_x_col']
        STOP_Y_COL = session['stop_y_col']
        distance_cut = session['distance_cut']
        
        # Sanity check and fix lines if needed
        line_a, line_b = analysis.sanity_check_and_fix_lines(FCD, line_a, line_b)
        
        # Calculate segments
        crossings_df = analysis.calculate_segments(FCD, FCD_times, line_a, line_b, STOP_X_COL, STOP_Y_COL)
        
        if crossings_df.empty:
            return jsonify({'error': 'No valid segments found. Please check your lines.'}), 400
        
        # Apply filters
        crossings_df_filtered = analysis.apply_filters(crossings_df, distance_cut)
        
        if crossings_df_filtered.empty:
            return jsonify({'error': 'No segments remain after filtering.'}), 400
        
        # Save results
        results_path = os.path.join(app.config['UPLOAD_FOLDER'], f"results_{os.getpid()}.pkl")
        crossings_df_filtered.to_pickle(results_path)
        session['results_path'] = results_path
        
        return jsonify({'success': True, 'num_segments': len(crossings_df_filtered)})
    
    except Exception as e:
        return jsonify({'error': f'Analysis error: {str(e)}'}), 500


@app.route('/results')
def results():
    """Display analysis results."""
    if 'results_path' not in session:
        return redirect(url_for('index'))
    
    try:
        # Load results
        crossings_df = pd.read_pickle(session['results_path'])
        
        # Generate plots
        plots = analysis.generate_plots(crossings_df)
        
        # Get statistics
        stats = analysis.get_statistics(crossings_df)
        
        return render_template('results.html', 
                              plots=plots, 
                              stats=stats,
                              num_segments=len(crossings_df))
    
    except Exception as e:
        return f"Error displaying results: {str(e)}", 500


@app.route('/download')
def download():
    """Download results as CSV."""
    if 'results_path' not in session:
        return redirect(url_for('index'))
    
    try:
        # Load results
        crossings_df = pd.read_pickle(session['results_path'])
        
        # Select export columns
        export_cols = [
            'Trajectory ID','Trip ID','Line A Crossing Time','Segment Time of Day','Segment Travel Time (s)',
            'Distance Between Lines (m)','Average Speed Between Lines (km/h)','Maximum Speed Between Lines (km/h)',
            'Line A Crossing Longitude','Line A Crossing Latitude','Line B Crossing Longitude','Line B Crossing Latitude',
            'Stops Between Lines (count)','Total Stop Time Between Lines (s)','Average Stop Duration Between Lines (s)',
            'Longest Stop Between Lines (s)','Stop Delay Between Lines (s)','Minimum Acceleration Between Lines (m/s^2)',
            'Maximum Acceleration Between Lines (m/s^2)','Average Positive Acceleration Between Lines (m/s^2)',
            'Average Braking Between Lines (m/s^2)'
        ]
        
        # Filter available columns
        available_export_cols = [col for col in export_cols if col in crossings_df.columns]
        export_df = crossings_df[available_export_cols].copy()
        
        # Rename Line A Crossing Time to Departure Time
        if 'Line A Crossing Time' in export_df.columns:
            export_df = export_df.rename(columns={'Line A Crossing Time': 'Departure Time'})
        
        # Save to temporary file
        csv_path = os.path.join(app.config['UPLOAD_FOLDER'], f"fcd_export_{os.getpid()}.csv")
        export_df.to_csv(csv_path, index=False)
        
        return send_file(csv_path, as_attachment=True, download_name='fcd_analysis_results.csv')
    
    except Exception as e:
        return f"Error generating download: {str(e)}", 500


@app.route('/reset')
def reset():
    """Clear session and start over."""
    # Clean up temporary files
    temp_files = ['fcd_path', 'fcd_times_path', 'traj_points_path', 'results_path']
    for key in temp_files:
        if key in session:
            path = session[key]
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
    
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
