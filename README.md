# Beaver Dam Simulation

[![Python Version](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub last commit](https://img.shields.io/github/last-commit/Sebastianleff/Beaver-Dam-Simulation.svg)](https://github.com/Sebastianleff/Beaver-Dam-Simulation/commits/main)

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

### Requirements

- Python 3.13+
- PySide6
- PySide6_Addons
- PySide6_Essentials
- shiboken6
- NumPy

### Install Dependencies

```bash
pip install -r requirements.txt
```
### Run the Program

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

---

## Project Structure
```text
beaver_dam_sim/
├── simulation/
│   ├── simulation.py       # Core simulation engine
│   ├── models.py           # Data models and river network
├── UI/
│   ├── console.py          # CLI interface
├── service.py              # Service layer handling simulations
```
---
## License

This project is licensed under the MIT License. See the [License](LICENSE) file for details.

---

## Authors
- Sebastian Leff - Team Lead and Simulation Dev
- Jaden Clark - UI Dev
- Bryan Martin - Services Dev
