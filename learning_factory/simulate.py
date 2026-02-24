# learning_factory/simulate.py
from __future__ import annotations
from typing import Dict, Any
import random
import simpy
import pandas as pd
from pathlib import Path
from datetime import datetime

from learning_factory.flows import new_orders_source, returns_source
from learning_factory.stations import run_serial_station, run_priority_station

def step_cfg(cfg: Dict[str, Any], step_id: str) -> Dict[str, Any]:
    return next(s for s in cfg["forward_flow"] if s.get("id") == step_id)

def ensure_buffer(env, buffers: dict, name: str, cap: int = 999999):
    if name not in buffers:
        buffers[name] = simpy.Store(env, capacity=cap)
    return buffers[name]

def total_route_time_min(cfg: Dict[str, Any]) -> float:
    secs = 0.0
    for s in cfg["forward_flow"]:
        if s.get("type", "process") != "process":
            continue
        secs += float(s.get("cycle_time_s", 0))
    return secs / 60.0

# reverse shortcut kept for completeness (you may be on the “real reverse” already)
def reverse_shortcut(env, buffers, metrics, delay_min: float = 5.0):
    wa = buffers["warenannahme"]; rem = buffers["reman_lager"]
    while True:
        item = yield wa.get()
        yield env.timeout(delay_min)
        yield rem.put(item)

def reman_merge_feeder(env, buffers):
    rem = buffers["reman_lager"]; l1 = buffers["lager1"]; l2 = buffers["lager2"]
    toggle = 0
    while True:
        item = yield rem.get()
        yield (l1.put(item) if (toggle % 2 == 0) else l2.put(item))
        toggle += 1

def sampler(env, buffers, metrics, sample_every_min: float, inventory_rows: list):
    while True:
        row = {"time_min": env.now}
        for bname, store in buffers.items():
            row[bname] = len(store.items)
        for st, n in metrics.get("inproc_now", {}).items():
            row[f"inproc_{st}"] = n
        inventory_rows.append(row)
        yield env.timeout(sample_every_min)

def _reliability_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("reliability", {}) or {}

def _station_workers_lookup(cfg: Dict[str, Any]) -> Dict[str, int]:
    m = {}
    for s in cfg["forward_flow"]:
        if s.get("type", "process") == "process":
            m[s["id"]] = int(s.get("workers_required", 0))
    return m

def run_simulation(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # RNG seed
    random.seed(cfg["meta"].get("seed", 42))
    env = simpy.Environment()

    # Buffers
    buffers: dict[str, simpy.Store] = {
        name: simpy.Store(env, capacity=spec["capacity"])
        for name, spec in cfg["buffers"].items()
    }

    # Worker pool
    workers_total = int(cfg["resources"].get("workers_total", 0))
    workers_pool = simpy.Container(env, init=workers_total, capacity=workers_total) if workers_total > 0 else None

    # Metrics
    metrics = {
        "arrivals_new": 0,
        "lost_new_due_to_neu_lager_full": 0,
        "arrivals_returns": 0,
        "throughput_kunde": 0,
        "station_output": {},
        "station_busy_time": {},
        "station_downtime": {},  # NEW
        # resources: {"kwh":{st:..}, "air_m3":{st:..}} gets filled in stations
    }

    # Intensities
    defaults = cfg.get("intensity_defaults", {})
    station_intensity = {}
    for s in cfg["forward_flow"]:
        if s.get("type", "process") != "process": continue
        sid = s["id"]
        station_intensity[sid] = {
            "kwh_per_unit": float(s.get("kwh_per_unit", defaults.get("kwh_per_unit", 0.0))),
            "air_m3_per_unit": float(s.get("air_m3_per_unit", defaults.get("air_m3_per_unit", 0.0))),
        }
    metrics["station_intensity"] = station_intensity

    # Factors & costs
    factors = cfg.get("factors", {})
    ef_co2_per_kwh = float(factors.get("ef_co2_per_kwh", 0.35))
    kwh_per_m3_air = float(factors.get("kwh_per_m3_air", 0.12))

    costs = cfg.get("costs", {})
    eur_per_kwh = float(costs.get("energy_eur_per_kwh", 0.0))
    eur_per_m3  = float(costs.get("air_eur_per_m3", 0.0))
    eur_per_min = float(costs.get("labor_eur_per_min", 0.0))
    eur_mat_new   = float(costs.get("material_new_eur_per_unit", 0.0))
    eur_mat_reman = float(costs.get("material_reman_eur_per_unit", 0.0))
    eur_scrap     = float(costs.get("scrap_disposal_eur_per_unit", 0.0))
    eur_return_premium = float(costs.get("return_premium_eur_per_unit", 0.0))

    # Knobs
    horizon = float(cfg["meta"]["horizon_min"])
    warmdown = float(cfg["meta"].get("warmdown_min", 0))
    sample_every = float(cfg["meta"].get("sample_every_min", 10))
    route_min = total_route_time_min(cfg)
    stop_new_at = max(0.0, horizon - route_min)

    # Sources
    env.process(new_orders_source(env, cfg, buffers, metrics, stop_at=stop_new_at))
    env.process(returns_source(env, cfg, buffers, metrics, stop_at=horizon))

    # Reverse: if you’re on “real reverse” already, keep those processes;
    # else keep the shortcut + merge feeder enabled:
    rev_delay = float(cfg.get("reverse_flow", {}).get("shortcut_delay_min", 5.0))
    env.process(reverse_shortcut(env, buffers, metrics, delay_min=rev_delay))
    env.process(reman_merge_feeder(env, buffers))

    # Forward chain with reliability hook & workers lookup
    prev_buffer_name = "neu_lager"
    final_wip_buffer_name = prev_buffer_name
    rel_cfg = _reliability_cfg(cfg)
    station_workers = _station_workers_lookup(cfg)

    for step in cfg["forward_flow"]:
        step_id = step["id"]; step_type = step.get("type", "process")

        if step_type == "sink":
            def sink_consumer(env, input_store, metrics):
                while True:
                    _ = yield input_store.get()
                    metrics["throughput_kunde"] += 1
            env.process(sink_consumer(env, buffers[prev_buffer_name], metrics))
            final_wip_buffer_name = prev_buffer_name
            break

        out_name = f"after_{step_id}"
        out_store = ensure_buffer(env, buffers, out_name, cap=999999)

        machines = int(step.get("machines", 1))
        workers_required = int(step.get("workers_required", 0))
        ct_s = float(step.get("cycle_time_s", 60))

        if step_id == "pressen_1":
            in_stores = [buffers["lager1"], buffers["lager2"], buffers["neu_lager"]]
            env.process(
                run_priority_station(
                    env=env,
                    name="pressen_1",
                    input_stores_in_priority=in_stores,
                    output_store=out_store,
                    cycle_time_s=ct_s,
                    workers_required=workers_required,
                    workers_pool=workers_pool,
                    metrics=metrics,
                    poll_dt_min=0.1,
                    reliability_cfg=rel_cfg,   # NEW
                )
            )
        else:
            for m in range(machines):
                name = step_id if machines == 1 else f"{step_id}#{m+1}"
                env.process(
                    run_serial_station(
                        env=env,
                        name=name,
                        input_store=buffers[prev_buffer_name],
                        output_store=out_store,
                        cycle_time_s=ct_s,
                        workers_required=workers_required,
                        workers_pool=workers_pool,
                        metrics=metrics,
                        reliability_cfg=rel_cfg,  # NEW
                    )
                )

        prev_buffer_name = out_name

    # Sampler
    inventory_rows: list = []
    env.process(sampler(env, buffers, metrics, sample_every, inventory_rows))

    # Run
    env.run(until=horizon)
    if warmdown > 0:
        env.run(until=horizon + warmdown)

    # ---------- KPIs ----------
    denom_time = horizon + warmdown

    # Utilization
    util_rows = [
        {"Station": st, "Utilization %": round(100.0 * busy / denom_time, 2)}
        for st, busy in metrics["station_busy_time"].items()
    ]
    kpi_stations = pd.DataFrame(util_rows) if util_rows else pd.DataFrame(columns=["Station", "Utilization %"])

    # End-of-line WIP
    end_wip = len(buffers[final_wip_buffer_name].items) if final_wip_buffer_name in buffers else 0

    # Live WIP + peaks
    inproc_now = metrics.get("inproc_now", {}); inproc_peak = metrics.get("inproc_peak", {})
    live_wip_total = int(sum(v for v in inproc_now.values() if v > 0))
    kpi_wip_now = pd.DataFrame(
        [{"In-Station WIP at": st, "Units": n} for st, n in inproc_now.items() if n > 0]
    ).sort_values("In-Station WIP at").reset_index(drop=True)
    kpi_wip_peak = pd.DataFrame(
        [{"Station": st, "Peak In-Process": n} for st, n in inproc_peak.items() if n > 0]
    ).sort_values("Station").reset_index(drop=True)

    # Simple delta-estimate cross-check
    stage_pairs = [
        ("pressen_1","pressen_2"), ("pressen_2","pressen_3"), ("pressen_3","pressen_4"),
        ("pressen_4","fuegen_1"), ("fuegen_1","magnetisieren"), ("magnetisieren","schrauben_1"),
        ("schrauben_1","fuegen_2"), ("fuegen_2","schrauben_2"), ("schrauben_2","pruefstand"),
    ]
    so = metrics["station_output"]
    est_wip_total = sum(max(0, so.get(a, 0) - so.get(b, 0)) for a, b in stage_pairs)

    # Reman mix
    reman = metrics.get("pressen1_from_reman", 0); new_ = metrics.get("pressen1_from_new", 0)
    mix_total = reman + new_; reman_share = round(100.0 * reman / mix_total, 2) if mix_total > 0 else 0.0

    # Downtime KPIs
    dt_map = metrics.get("station_downtime", {})
    kpi_downtime = pd.DataFrame(
        [{"Station": st, "Downtime (min)": round(dt, 3)} for st, dt in dt_map.items() if dt > 0]
    ).sort_values("Station").reset_index(drop=True)

    # Resource KPIs
    res_maps = metrics.get("resources", {}); kwh_map = res_maps.get("kwh", {}); air_map = res_maps.get("air_m3", {})
    stations_with_any = sorted(set(kwh_map.keys()) | set(air_map.keys()))
    resource_rows = []
    kwh_total = air_total = co2_total = 0.0
    for st in stations_with_any:
        k = float(kwh_map.get(st, 0.0)); a = float(air_map.get(st, 0.0))
        co2 = k * ef_co2_per_kwh + a * kwh_per_m3_air * ef_co2_per_kwh
        resource_rows.append({"Station": st, "kWh": round(k, 3), "Air_m3": round(a, 3), "CO2_kg": round(co2, 3)})
        kwh_total += k; air_total += a; co2_total += co2
    resource_kpis = (pd.DataFrame(resource_rows).sort_values("Station").reset_index(drop=True)
                     if resource_rows else pd.DataFrame(columns=["Station","kWh","Air_m3","CO2_kg"]))

    # COSTS
    # 1) material at pressen_1 input
    cost_material = reman * eur_mat_reman + new_ * eur_mat_new
    # 2) energy & air
    cost_energy = kwh_total * eur_per_kwh
    cost_air    = air_total * eur_per_m3
    # 3) labor ~ workers_required * busy_time * €/min
    station_workers = _station_workers_lookup(cfg)
    labor_rows = []
    labor_total = 0.0
    for st, busy in metrics["station_busy_time"].items():
        wrk = station_workers.get(st, 0)
        c = wrk * busy * eur_per_min
        labor_rows.append({"Station": st, "Busy (min)": round(busy,3), "Workers": wrk, "Labor €": round(c,2)})
        labor_total += c
    labor_kpis = pd.DataFrame(labor_rows).sort_values("Station").reset_index(drop=True) if labor_rows else pd.DataFrame()

    # 4) scrap disposal (use any scrap counters you maintain; fall back to 0)
    scrap_units = int(metrics.get("scrap_befundung1", 0))
    cost_scrap = scrap_units * eur_scrap

    # 5) return premium
    cost_premium = float(metrics.get("arrivals_returns", 0)) * eur_return_premium

    # cost summary
    cost_rows = [
        {"Component": "Material (new+reman)", "€": round(cost_material, 2)},
        {"Component": "Energy",               "€": round(cost_energy, 2)},
        {"Component": "Compressed Air",       "€": round(cost_air, 2)},
        {"Component": "Labor",                "€": round(labor_total, 2)},
        {"Component": "Scrap disposal",       "€": round(cost_scrap, 2)},
        {"Component": "Return premium (credit)", "€": -round(cost_premium, 2)},
    ]
    cost_total = sum(r["€"] for r in cost_rows)
    cost_rows.append({"Component": "Total", "€": round(cost_total, 2)})
    cost_kpis = pd.DataFrame(cost_rows)

    # General KPIs
    kpi_general = pd.DataFrame(
        [
            {"KPI": "New orders arrived", "Value": float(metrics["arrivals_new"])},
            {"KPI": "Returns arrived", "Value": float(metrics["arrivals_returns"])},
            {"KPI": "Throughput to Kunde", "Value": float(metrics["throughput_kunde"])},
            {"KPI": "Neu-Lager level (end)", "Value": float(len(buffers["neu_lager"].items))},
            {"KPI": "Reman-Lager level (end)", "Value": float(len(buffers["reman_lager"].items))},
            {"KPI": "Lager1 level (end)", "Value": float(len(buffers["lager1"].items))},
            {"KPI": "Lager2 level (end)", "Value": float(len(buffers["lager2"].items))},
            {"KPI": f"{final_wip_buffer_name} level (end)", "Value": float(end_wip)},
            {"KPI": "In-Station WIP (live, end)", "Value": float(live_wip_total)},
            {"KPI": "In-Station WIP (delta estimate, end)", "Value": float(est_wip_total)},
            {"KPI": "% Reman feed at Pressen_1", "Value": float(reman_share)},
            {"KPI": "Pressen_1 input from REMAN", "Value": float(reman)},
            {"KPI": "Pressen_1 input from NEW",   "Value": float(new_)},
            {"KPI": "Lost due to Neu-Lager full", "Value": float(metrics["lost_new_due_to_neu_lager_full"])},
            {"KPI": "Energy total (kWh)", "Value": round(kwh_total, 3)},
            {"KPI": "Compressed air total (m³)", "Value": round(air_total, 3)},
            {"KPI": "CO2 total (kg)", "Value": round(co2_total, 3)},
        ]
    )

    # Inventory time series
    inventory_ts = pd.DataFrame(inventory_rows) if len(inventory_rows) > 0 else pd.DataFrame(columns=["time_min", *buffers.keys()])

    log = "Forward chain + reliability + costs + (reverse path + merge + priority pull)."
    if warmdown > 0: log += f"\n(Warm-down: {int(warmdown)} min)"

    # (optional) pack a default output path to make run_sim.py saving trivial
    outdir = Path("runs") / datetime.now().strftime("%Y-%m-%d_%H%M%S")

    return {
        "kpi_general": kpi_general,
        "kpi_stations": kpi_stations,
        "kpi_wip_now": kpi_wip_now,
        "kpi_wip_peak": kpi_wip_peak,
        "kpi_downtime": kpi_downtime,
        "resource_kpis": resource_kpis,
        "labor_kpis": labor_kpis,
        "cost_kpis": cost_kpis,
        "inventory_ts": inventory_ts,
        "buffers": list(buffers.keys()),
        "log": log,
        "outdir": outdir.as_posix(),  # for CSV persistence
    }
