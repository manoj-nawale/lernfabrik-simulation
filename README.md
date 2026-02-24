# Lernfabrik Simulation – Circular Production Digital Twin

📄 **Portfolio demo notes:** [docs/README.md](docs/README.md)

## At a glance
This project simulates a circular production system as a digital twin, combining forward manufacturing flow (new parts to customer delivery) and reverse remanufacturing flow (returns back into usable inventory).

It supports decisions on bottlenecks, capacity planning, buffer sizing, downtime impact, and return/reman integration strategy.

Outputs are produced as a CSV artifact bundle per run and explored through an interactive Dash dashboard.

## Demo (2 commands)
1. Run the baseline simulation:
   ```bash
   python -m apps.run_sim
   ```
2. Launch the dashboard:
   ```bash
   python -m apps.dashboard
   ```
Dashboard URL: `http://127.0.0.1:8052`  
Run outputs: `runs/YYYY-MM-DD_HHMMSS/`
Scenario run example:
```bash
python -m apps.run_sim --config configs/scenarios/returns_high.yaml
```

## Scenarios
- `configs/scenarios/downtime_high.yaml`: Stress-test throughput by increasing downtime severity at a critical forward station (`pressen_1`).
- `configs/scenarios/returns_high.yaml`: Increase reverse-flow pressure with larger and more frequent return batches.
- `configs/scenarios/capacity_relief.yaml`: Relieve congestion by increasing total worker capacity.

## Screenshots
- ![Dashboard overview](docs/img/dashboard_overview.png)
- ![Inventory time series](docs/img/inventory_timeseries.png)
- ![Cost breakdown](docs/img/cost_breakdown.png)

## Run artifacts
- `kpi_general.csv`: Overall run-level KPIs and aggregate production outcomes.
- `kpi_stations.csv`: Station-wise performance metrics such as utilization and flow.
- `kpi_wip_now.csv`: End-of-run WIP levels across process buffers.
- `kpi_wip_peak.csv`: Peak WIP observed across buffers during simulation.
- `inventory_ts.csv`: Time-series inventory/WIP trajectory for trend analysis.
- `resource_kpis.csv`: Resource and sustainability indicators (e.g., energy, air, emissions).
- `labor_kpis.csv`: Labor consumption and labor-related KPI outputs.
- `cost_kpis.csv`: Cost breakdown KPIs across major cost categories.
- `kpi_downtime.csv`: Downtime and reliability KPIs by station.

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
    - cost_kpis.csv
    - kpi_downtime.csv
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

`python_requires`: `>=3.10, <3.12` (tested with Python 3.10 and 3.11)

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
