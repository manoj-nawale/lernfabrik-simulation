# Portfolio Demo: Lernfabrik Circular Production Digital Twin

## What this project is
This project is a digital twin of a circular production system built with SimPy, modeling both forward production flow and reverse remanufacturing flow. It is designed to evaluate throughput, bottlenecks, inventory dynamics, cost structure, and sustainability performance from one simulation backbone.

## Quick demo steps
1. Run the baseline simulation:
   ```bash
   python -m apps.run_sim
   ```
2. Launch the dashboard:
   ```bash
   python -m apps.dashboard
   ```
3. Review generated outputs in timestamped run folders under:
   ```text
   runs/YYYY-MM-DD_HHMMSS/
   ```

## Key KPIs
- `kpi_general.csv`: High-level run KPIs such as total throughput, overall WIP summaries, and aggregate performance indicators.
- `kpi_stations.csv`: Station-level metrics (utilization, flow counts, and local performance values per station).
- `kpi_wip_now.csv`: End-of-run WIP state across buffers and process stages.
- `kpi_wip_peak.csv`: Peak WIP observed per buffer/stage during the run.
- `inventory_ts.csv`: Time-series of inventory and WIP levels for trend and bottleneck analysis.
- `resource_kpis.csv`: Resource and sustainability metrics (e.g., energy, compressed air, CO2-related indicators).
- `labor_kpis.csv`: Labor usage KPIs (time-based labor consumption and derived labor cost signals).
- `cost_kpis.csv`: Cost breakdown KPIs across major categories (material, labor, energy/utilities, scrap/disposal, and net effects).
- `kpi_downtime.csv`: Reliability and downtime metrics per station (failure/repair impact over the run).

## Screenshots
Screenshots in `docs/img/` were captured from the dashboard using the latest run folder under `runs/YYYY-MM-DD_HHMMSS/`.
- ![Dashboard overview](img/dashboard_overview.png)
- ![Inventory time series](img/inventory_timeseries.png)
- ![Cost breakdown](img/cost_breakdown.png)

## Reproduce the demo
1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Run the baseline simulation:
   ```bash
   python -m apps.run_sim
   ```
3. Run one scenario:
   ```bash
   python -m apps.run_sim --config configs/scenarios/downtime_high.yaml
   ```
4. Start the dashboard:
   ```bash
   python -m apps.dashboard
   ```

## Architecture (ASCII)
```text
configs/*.yaml
     |
     v
[SimPy Simulation Engine]
(learning_factory + apps.run_sim)
     |
     v
CSV artifacts in runs/YYYY-MM-DD_HHMMSS/
(kpi_general, kpi_stations, inventory_ts, cost_kpis, ...)
     |
     v
[Dash Dashboard]
(apps.dashboard)
```
