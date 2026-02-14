# Lernfabrik Simulation – Circular Production Digital Twin

## Overview
This project develops a digital twin simulation of a learning factory with a circular production network.

The simulation is built with Python (SimPy) and models both the forward flow (new parts → assembly → customer) and the reverse flow (returns → inspection → remanufacturing).

The goal is to provide industrial engineers and production planners with a tool to analyze throughput, utilization, resource consumption, costs, and sustainability impacts.

## Features

- Forward Flow: Pressing, Fügen, Schrauben, Magnetisieren, Prüfen → Customer.
- Reverse Flow: Warenannahme → Befundung → Demontage → Reinigung → Reman-Lager.
- Priority Pull: Pressen_1 prioritizes reman parts over new parts.
- Merge Logic: Remanufactured parts merged into Lager1/Lager2 before main line.

## Key KPIs

- Throughput to customer (output per shift)
- Station utilization (%)
- Work-in-progress (WIP, live and peak)
- Buffer levels (Neu-Lager, Reman-Lager, etc.)
- Scrap rates at inspection/befundung
- Source mix (Reman vs New feed at Pressen_1)

## Resource & Sustainability

- Energy consumption (kWh)
- Compressed air demand (m³)
- CO₂ emissions (kg CO₂eq, via energy factors)

## Reliability

- MTBF / MTTR simulation for station downtimes
- Downtime KPIs per station

## Cost Model

- Material cost (new vs reman)
- Labor cost (worker minutes × €/min)
- Energy & compressed air costs
- Scrap disposal cost
- Return premiums (credit per returned product)
- Net total cost breakdown

## Data Export

- Results saved to /runs/timestamp/ as CSVs:
    - kpi_general.csv
    - kpi_stations.csv
    - kpi_wip_now.csv
    - kpi_wip_peak.csv
    - resource_kpis.csv
    - labor_kpis.csv
    - cost_summary.csv
    - downtime.csv
    - inventory_ts.csv (time-series buffer/WIP snapshot)

## Dashboard

- Interactive Dash dashboard with tabs for:
- Overview KPIs & utilization
- Linear process (inventory time-series, WIP)
- Remanufacturing & scrap analysis
- Cost & sustainability (waterfall, stacked bars)

## Project Structure
```text
lern-fabrik-simulation/
│
├── apps/                   # Run scripts & dashboards
│   ├── run_sim.py          # Main simulation runner
│   └── dashboard.py        # Dash dashboard (WIP)
│
├── learning_factory/       
│   ├── config.py           # YAML config loader
│   ├── simulate.py         # Simulation orchestration
│   ├── stations.py         # Station logic
│   ├── flows.py            # Arrival & flow logic
│
├── configs/                # Scenario configs (YAML)
│   └── stellmotor_baseline.yaml
│
├── runs/                   # Auto-saved results per run
│
└── README.md
```
## Installation

### Install Environment
```bash
pip install -r requirements.txt
```

### Run Simulation
```bash
python -m apps.run_sim
```

### Launch Dashboard
```bash
python -m apps.dashboard
```
Open your browser at http://127.0.0.1:8052

## Tech Stack

- Python 3.11+
- SimPy – Discrete event simulation
- Pandas – Data handling & export
- Plotly Dash – Interactive dashboards
- YAML – Config-driven model setup

## Authors

Manoj Nawale – Designed and implemented the simulation framework, developed production system logic (forward and reverse flows), integrated KPIs (throughput, utilization, WIP, resource use, costs), and built CSV export for data-driven analysis.

Supervision: Moritz Hörger, WBK KIT
