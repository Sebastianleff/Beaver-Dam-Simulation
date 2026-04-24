# Beaver Dam Simulation

[![Python Version](https://img.shields.io/badge/Python-3.13%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/github/actions/workflow/status/Sebastianleff/Beaver-Dam-Simulation/python-app.yml?branch=main&label=Tests)](https://github.com/Sebastianleff/Beaver-Dam-Simulation/actions/workflows/python-app.yml)
[![GitHub Release](https://img.shields.io/github/v/release/Sebastianleff/Beaver-Dam-Simulation?label=Release)](https://github.com/Sebastianleff/Beaver-Dam-Simulation/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Last Commit](https://img.shields.io/github/last-commit/Sebastianleff/Beaver-Dam-Simulation.svg?label=Last%20Commit)](https://github.com/Sebastianleff/Beaver-Dam-Simulation/commits/main)




A stochastic simulation system for modeling beaver dam creation, breakage, and catastrophic flooding across river networks.

---

## Overview

This project simulates how dam dynamics influence flooding over time using a stepwise probabilistic model on a directed river network.

### Features

- Single simulation (interactive)
- Batch simulation (CSV input/output)
- Step-by-step result inspection
- Fully reproducible simulations via seeded randomness

---

## Installation

### Option 1 — Download Prebuilt Executable (Recommended)

Download the latest version:

- Windows: [Download](https://github.com/Sebastianleff/Beaver-Dam-Simulation/releases/latest/download/BeaverDamSimulation_Win.zip)
- macOS: [Download](https://github.com/Sebastianleff/Beaver-Dam-Simulation/releases/latest/download/BeaverDamSimulation_Mac.zip)

After downloading:

1. Extract the `.zip`

2. Run the application:
   - Windows: open `BeaverDamSimulation.exe`
   - macOS: run the `BeaverDamSimulation` executable

> **macOS Note:**  
> You may need to manually authorize the application the first time you run it.  
> See Apple’s guide: https://support.apple.com/en-mo/guide/mac-help/mchleab3a043/mac

---

### Option 2 — Run from Source (Development)

#### Requirements

- Python 3.13+
- PySide6
- PySide6_Addons
- PySide6_Essentials
- shiboken6
- NumPy

#### Install Dependencies

```bash
pip install -r requirements.txt
```
#### Run the Program

```bash
python console.py
```
---
## Usage

### Single Simulation

Run the program and select:

```text
1) Run a single simulation
```

Enter parameters when prompted.

### Batch Simulation

Prepare a CSV file with simulation parameters and select:

```text
2) Run a batch simulation
```

You will provide:

- Input CSV path
- Output CSV path

**Be sure to provide them as an absolute path**

### CSV Formats
#### CSV Input:
Only CSV files are valid, any other type of spreadsheet format will be rejected.
The program will only except CSV files formated exactly in the following manner.

| Column                     | Type  | Required          | Valid Range    |
|----------------------------|-------|-------------------|----------------|
| `dam_creation_probability` | float | Yes               | `0.0` to `1.0` |
| `dam_break_probability`    | float | Yes               | `0.0` to `1.0` |
| `flood_probability`        | float | Yes               | `0.0` to `1.0` |
| `flood_break_probability`  | float | Yes               | `0.0` to `1.0` |
| `stabilization_time`       | int   | Yes               | `> 0`          |
| `years`                    | int   | Yes               | `> 0`          |
| `random_seed`              | int   | Yes               | Any integer    |
| `meadow_probability`       | float | No, defaults to 0 | `0.0` to `1.0` |

#### CSV Output:

| Column          | Type | Meaning                              |
|-----------------|------|--------------------------------------|
| `simulation_id` | int  | 1-based index of simulation in batch |
| `year`          | int  | Step number                          |
| `cells_flooded` | int  | Count of flooded cells at that step  |
| `dams_created`  | int  | Count of dams created at that step   |
| `dams_broken`   | int  | Count of dams broken at that step    |

---

## Project Structure & Info
```text
beaver_dam_sim/
├── simulation/
│   ├── simulation.py       # Core simulation engine
│   ├── models.py           # Data models and river network
├── UI/
│   ├── console.py          # CLI interface
├── service.py              # Service layer handling simulations
```
Note: Internal IDs and position-based counts are 1-based; simulation steps (`year`/`step`) are 0-based and start at 0.
## License

This project is licensed under the MIT License. See the [License](LICENSE) file for details.

---

## Authors
- Sebastian Leff - Team Lead and Simulation Dev
- Jaden Clark - UI Dev
- Bryan Martin - Services Dev
