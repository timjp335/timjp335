# FCD Travel Time Analysis - Web Application

A web-based tool for analyzing Floating Car Data (FCD) to calculate travel times and traffic statistics between measurement lines.

## Overview

This web application converts the functionality of the `travel_time_from_fcd_Version2.ipynb` Jupyter Notebook into an easy-to-use web interface. Users can upload FCD data, draw measurement lines on an interactive map, and visualize comprehensive travel time analysis results.

## Features

- **CSV Upload**: Upload FCD data files with semicolon-separated values
- **Configurable Parameters**: Adjust analysis parameters (stop thresholds, distance cuts, etc.)
- **Interactive Map**: Draw measurement lines using Leaflet.js with Draw plugin
- **Automatic Analysis**: Calculate segment crossings, travel times, speeds, stops, and acceleration
- **Comprehensive Visualizations**: View multiple plots including:
  - Distance and travel time distributions
  - Travel time by time of day
  - Speed statistics
  - Scatter plots
- **Export Results**: Download analysis results as CSV
- **Filtering**: Automatic filtering for weekdays (Tue-Thu) and holidays

## Installation

### Prerequisites

- Python 3.9 or higher (tested with Python 3.9-3.12)
- pip (Python package manager)

**Note:** For best compatibility, Python 3.10 or 3.11 is recommended. If you encounter installation issues, see the Troubleshooting section below.

### Setup

1. Navigate to the application directory:
   ```bash
   cd fcd_web_app
   ```

2. (Optional) Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install required dependencies:
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

## Usage

### Starting the Application

**Development Mode** (with debug enabled):
```bash
export FLASK_DEBUG=true
python app.py
```

**Production Mode** (debug disabled, recommended):
```bash
python app.py
```

2. Open your web browser and navigate to:
   ```
   http://localhost:5000
   ```

### Workflow

The application follows a 3-step workflow:

#### Step 1: Upload & Configure
- Upload your FCD CSV file (semicolon-separated)
- Configure analysis parameters:
  - **Long Stop Threshold**: Duration (seconds) to filter out trajectories with very long stops (default: 600)
  - **Stop Speed Threshold**: Speed (km/h) below which movement is considered a stop (default: 0.1)
  - **Minimum Stop Points**: Consecutive points required to validate a stop (default: 2)
  - **Maximum Distance**: Filter segments with distance greater than this (meters, default: 700)

#### Step 2: Draw Measurement Lines
- An interactive map displays centered on your data
- Use the drawing tools to create exactly 2 polylines:
  - **Line A**: Start measurement line
  - **Line B**: End measurement line
- The application automatically checks line order (swaps if needed)
- Click "Start Analysis" when ready

#### Step 3: View Results
- View comprehensive statistics:
  - Travel time statistics (mean, median, std, min, max)
  - Distance statistics
  - Speed statistics
- Explore visualizations:
  - Distribution plots for distance, travel time, and speed
  - Boxplots by time of day
  - Scatter plots
- Download results as CSV

## CSV File Format

The input CSV file must be semicolon-separated (`;`) and contain the following columns:

- `traj_id`: Trajectory identifier
- `traj_seq`: Sequence number within trajectory
- `old_lon`, `old_lat`: Start point coordinates
- `new_lon`, `new_lat`: End point coordinates
- `old_point_wkt`, `new_point_wkt`: WKT POINT representations
- `x1`, `x2`: Location identifiers
- `t1`, `t2`: Unix timestamps (start/end)
- `v1`, `v2`: Velocities (km/h)
- `time_diff`: Time difference (seconds)

## Analysis Details

### Data Processing

1. **Filtering**: Removes trajectories with very long stops at one location
2. **Stop Detection**: Identifies stops based on speed threshold and consecutive points
3. **Trajectory Parsing**: Extracts and validates WKT point coordinates
4. **Segment Calculation**: Finds intersections with measurement lines and calculates:
   - Travel time between lines
   - Distance traveled
   - Average and maximum speeds
   - Stop statistics (count, duration, delay)
   - Acceleration statistics

### Filtering Rules

Results are automatically filtered for:
- **Weekdays**: Tuesday, Wednesday, Thursday only
- **Holidays**: German holidays for 2021 (hardcoded in `analysis.py`, can be modified for other years)
- **School breaks**: German school breaks for 2021 (hardcoded in `analysis.py`, can be modified for other years)
- **Distance**: Segments exceeding the configured maximum distance

**Note:** The holiday and school break dates are currently hardcoded for 2021. To analyze data from other years, modify the `ferien_2021` and `feiertage_2021` lists in the `apply_filters()` function in `analysis.py`.

### Time Periods

Analysis categorizes data into time periods:
- Morning Peak (06:00-09:00)
- Midday (09:00-15:00)
- Afternoon Peak (15:00-19:00)
- Evening (19:00-22:00)
- Night (22:00-06:00)

## Project Structure

```
fcd_web_app/
├── app.py                  # Flask application with routes
├── analysis.py             # Analysis logic extracted from notebook
├── templates/
│   ├── index.html          # Upload page
│   ├── map.html            # Interactive map
│   └── results.html        # Results dashboard
├── static/
│   └── css/
│       └── style.css       # Styling
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Technology Stack

- **Backend**: Flask (Python web framework)
- **Data Processing**: pandas, numpy
- **Geospatial**: shapely, pyproj
- **Visualization**: matplotlib, seaborn
- **Frontend**: HTML, CSS, JavaScript
- **Mapping**: Leaflet.js, Leaflet.Draw

## Production Deployment

For production use, consider:

1. **Use a production WSGI server** (e.g., Gunicorn):
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

2. **Set up a reverse proxy** (e.g., Nginx) for better performance and security

3. **Configure session storage** with a persistent backend (e.g., Redis)

4. **Set up proper file storage** for uploads (e.g., S3, persistent volume)

5. **Enable HTTPS** for secure communication

6. **Adjust Flask configuration**:
   ```bash
   # Set secret key via environment variable
   export FLASK_SECRET_KEY='your-secure-secret-key-here'
   ```
   ```python
   # In production, set debug to False
   app.debug = False
   ```

7. **Update holiday dates** in `analysis.py` for the year(s) of your data

## Troubleshooting

### Installation Issues

#### "subprocess-exited-with-error" or build failures

If you encounter errors during `pip install -r requirements.txt`:

1. **Update pip, setuptools, and wheel first**:
   ```bash
   pip install --upgrade pip setuptools wheel
   ```

2. **Use a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

3. **Check Python version**:
   ```bash
   python3 --version  # Should be 3.9 or higher
   ```
   If you're using Python 3.13+, some packages may not have pre-built wheels yet. Use Python 3.10-3.12 for best compatibility.

4. **Install system dependencies** (Linux/macOS):
   Some geospatial packages may require system libraries:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install -y python3-dev build-essential libgeos-dev libproj-dev

   # macOS (with Homebrew)
   brew install geos proj
   ```

5. **Install packages individually** to identify the problematic package:
   ```bash
   pip install flask
   pip install pandas
   pip install numpy
   pip install shapely
   pip install pyproj
   pip install matplotlib
   pip install seaborn
   ```

6. **Use conda as an alternative** (if pip continues to fail):
   ```bash
   conda create -n fcd_app python=3.11
   conda activate fcd_app
   conda install -c conda-forge flask pandas numpy shapely pyproj matplotlib seaborn
   ```

### Common Runtime Issues

1. **Import errors**: Ensure all dependencies are installed: `pip install -r requirements.txt`
2. **Port already in use**: Change the port in `app.py` or stop the conflicting process
3. **Large file uploads fail**: Adjust `MAX_CONTENT_LENGTH` in `app.py`
4. **Memory issues**: For very large datasets, consider processing in chunks or increasing available memory

### Getting Help

If you continue to experience issues:
1. Check the Python version: `python3 --version`
2. Check the pip version: `pip --version`
3. Try creating a fresh virtual environment
4. Check the full error message for specific package names

## Original Notebook

The original Jupyter Notebook (`travel_time_from_fcd_Version2.ipynb`) is preserved in the repository root for reference.

## License

This tool is provided as-is for research and analysis purposes.

## Support

For issues or questions, please refer to the original notebook documentation or contact the repository maintainer.
