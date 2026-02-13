# Installation Guide / Installationsanleitung

## English

### Quick Start

1. **Check Python version** (3.9 or higher required):
   ```bash
   python3 --version
   ```

2. **Create virtual environment** (recommended):
   ```bash
   cd fcd_web_app
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```

### If Installation Fails

See the detailed troubleshooting section in [README.md](README.md#troubleshooting).

---

## Deutsch

### Schnellstart

1. **Python-Version prüfen** (mindestens 3.9):
   ```bash
   python3 --version
   ```

2. **Virtuelle Umgebung erstellen** (empfohlen):
   ```bash
   cd fcd_web_app
   python3 -m venv venv
   source venv/bin/activate  # Unter Windows: venv\Scripts\activate
   ```

3. **Abhängigkeiten installieren**:
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

4. **Anwendung starten**:
   ```bash
   python app.py
   ```

### Bei Installationsfehlern

#### Fehler: "subprocess-exited-with-error"

Dieser Fehler tritt auf, wenn Pakete nicht korrekt installiert werden können. Lösungen:

1. **Pip, setuptools und wheel aktualisieren**:
   ```bash
   pip install --upgrade pip setuptools wheel
   ```

2. **Virtuelle Umgebung verwenden** (empfohlen):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Unter Windows: venv\Scripts\activate
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

3. **Python-Version prüfen**:
   ```bash
   python3 --version  # Sollte 3.9 oder höher sein
   ```
   Für beste Kompatibilität Python 3.10-3.12 verwenden.

4. **System-Abhängigkeiten installieren** (Linux/macOS):
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install -y python3-dev build-essential libgeos-dev libproj-dev

   # macOS (mit Homebrew)
   brew install geos proj
   ```

5. **Pakete einzeln installieren** um das problematische Paket zu finden:
   ```bash
   pip install flask
   pip install pandas
   pip install numpy
   pip install shapely
   pip install pyproj
   pip install matplotlib
   pip install seaborn
   ```

6. **Conda als Alternative verwenden**:
   ```bash
   conda create -n fcd_app python=3.11
   conda activate fcd_app
   conda install -c conda-forge flask pandas numpy shapely pyproj matplotlib seaborn
   ```

### Weitere Hilfe

Siehe die ausführliche Fehlerbehebung in [README.md](README.md#troubleshooting).

## Common Error Messages / Häufige Fehlermeldungen

### "error: subprocess-exited-with-error"
- **Ursache**: Paketinstallation schlägt fehl, meist beim Kompilieren
- **Lösung**: Pip/setuptools aktualisieren, virtuelle Umgebung verwenden, System-Abhängigkeiten installieren

### "Preparing metadata (pyproject.toml) did not run successfully"
- **Ursache**: Probleme beim Bauen des Pakets aus dem Quellcode
- **Lösung**: Pip auf die neueste Version aktualisieren, pre-built wheels verwenden

### "No matching distribution found"
- **Ursache**: Paket nicht verfügbar für Ihre Python-Version oder Architektur
- **Lösung**: Python-Version wechseln (3.10-3.12 empfohlen)

### "ImportError" nach Installation
- **Ursache**: Pakete nicht im richtigen Environment installiert
- **Lösung**: Virtuelle Umgebung verwenden und aktivieren
