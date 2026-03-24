# WaferSort

Filter and search ShabLab wafers by transport properties, aluminium characteristics, and availability — powered by live data from Google Sheets.

## Quick Start

```bash
git clone https://github.com/lukasinthelab/WaferSort.git
cd WaferSort
pip install -r requirements.txt
python run.py
```

**On a Mac?**
```bash
python run.py --mac
```

This automatically fixes a Safari compatibility issue with column labels.

No API keys or authentication needed — the app reads directly from the public Google Sheet.

## Features

- **Filter by**: mobility, electron density, mean free path, Al on/off, Al resistance, Al thickness, sample number range, availability
- **Compare wafer**: look up any wafer outside your filter criteria — failed criteria are highlighted red
- **Detail panel**: click any wafer to see transport, Al, AFM roughness, growth info, and sample tracker history
- **Custom sheets**: paste any publicly viewable Google Sheet URL
- **CLI mode**: `python wafer_sort.py --help` for command-line filtering

## CLI Examples

```bash
# High-mobility wafers with Al and low resistance
python wafer_sort.py --min-mobility 10000 --has-al --max-al-resistance 10

# Wafers JS750–JS823 without Al, available only
python wafer_sort.py --sample-min 750 --sample-max 823 --no-al --available

# Search for a specific wafer
python wafer_sort.py --search JS959
```

## Requirements

- Python 3.9+
- The Google Sheet must be shared as "Anyone with the link" (Viewer)
