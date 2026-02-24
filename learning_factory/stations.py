# learning_factory/stations.py
from __future__ import annotations
import simpy
import random
from typing import List, Optional, Dict, Any

# ---------- small helpers ----------

def _add_resources(metrics: dict, station_name: str, kwh: float, air: float) -> None:
    r = metrics.setdefault("resources", {})
    r.setdefault("kwh", {}).setdefault(station_name, 0.0)
    r["kwh"][station_name] += float(kwh)
    r.setdefault("air_m3", {}).setdefault(station_name, 0.0)
    r["air_m3"][station_name] += float(air)

def _ensure_inproc_metrics(metrics: dict, station_name: str) -> None:
    metrics.setdefault("inproc_now", {})
    metrics.setdefault("inproc_peak", {})
    metrics["inproc_now"].setdefault(station_name, 0)
    metrics["inproc_peak"].setdefault(station_name, 0)

def _begin_processing(metrics: dict, station_name: str) -> None:
    _ensure_inproc_metrics(metrics, station_name)
    metrics["inproc_now"][station_name] += 1
    if metrics["inproc_now"][station_name] > metrics["inproc_peak"][station_name]:
        metrics["inproc_peak"][station_name] = metrics["inproc_now"][station_name]

def _end_processing(metrics: dict, station_name: str) -> None:
    _ensure_inproc_metrics(metrics, station_name)
    metrics["inproc_now"][station_name] = max(0, metrics["inproc_now"][station_name] - 1)

def _reliab_for(station_id: str, cfg_rel: Dict[str, Any]) -> Dict[str, Any]:
    dflt = cfg_rel.get("default", {})
    per  = cfg_rel.get("stations", {}).get(station_id, {})
    out = dict(dflt)
    out.update(per)
    # sensible fallbacks
    out.setdefault("mtbf_min", 999999.0)
    out.setdefault("mttr_min", 0.0)
    out.setdefault("mttr_dist", "fixed")
    out.setdefault("mttr_sigma_min", 0.0)
    return out

def _draw_mttr_min(spec: Dict[str, Any]) -> float:
    if spec.get("mttr_dist", "fixed") == "normal":
        mu = float(spec.get("mttr_min", 0.0))
        sigma = float(spec.get("mttr_sigma_min", 0.0))
        # truncated at 0
        val = random.gauss(mu, sigma)
        return max(0.0, val)
    return float(spec.get("mttr_min", 0.0))

# ---------- core station runners ----------

def run_serial_station(env: simpy.Environment,
                       name: str,
                       input_store: simpy.Store,
                       output_store: simpy.Store,
                       cycle_time_s: float,
                       workers_required: int,
                       workers_pool: Optional[simpy.Container],
                       metrics: dict,
                       reliability_cfg: Optional[Dict[str, Any]] = None):
    """
    Single-input station with simple reliability:
    - Failures modeled between jobs (post-processing) via exponential MTBF.
    - Repair time drawn per mttr_* spec. Downtime accumulated in metrics['station_downtime'].
    Also charges per-unit kWh / air and tracks in-process live/peak.
    """
    busy = 0.0
    produced = 0.0
    downtime = 0.0

    base_id = name.split("#", 1)[0]
    rel_spec = _reliab_for(base_id, reliability_cfg or {})
    mtbf_min = float(rel_spec.get("mtbf_min", 999999.0))
    # draw initial time-to-failure
    ttf = random.expovariate(1.0 / mtbf_min) if mtbf_min > 0 else float("inf")

    while True:
        item = yield input_store.get()

        # reserve workers
        if workers_pool is not None and workers_required > 0:
            yield workers_pool.get(workers_required)

        # process
        _begin_processing(metrics, base_id)
        start = env.now
        ct_min = cycle_time_s / 60.0
        yield env.timeout(ct_min)
        busy += (env.now - start)
        _end_processing(metrics, base_id)

        # release workers
        if workers_pool is not None and workers_required > 0:
            yield workers_pool.put(workers_required)

        # output
        yield output_store.put(item)
        produced += 1

        # resources per unit
        ints = metrics.get("station_intensity", {}).get(base_id, {})
        _add_resources(metrics, base_id,
                       kwh=ints.get("kwh_per_unit", 0.0),
                       air=ints.get("air_m3_per_unit", 0.0))

        # reliability: decrement ttf by job time; if expired, repair
        ttf -= ct_min
        if ttf <= 0.0:
            repair = _draw_mttr_min(rel_spec)
            if repair > 0:
                yield env.timeout(repair)
                downtime += repair
            # draw next TTF
            ttf = random.expovariate(1.0 / mtbf_min) if mtbf_min > 0 else float("inf")

        # metrics update
        metrics.setdefault("station_output", {})[base_id] = int(produced)
        metrics.setdefault("station_busy_time", {})[base_id] = float(busy)
        metrics.setdefault("station_downtime", {})[base_id] = float(downtime)

def run_priority_station(env: simpy.Environment,
                         name: str,
                         input_stores_in_priority: List[simpy.Store],
                         output_store: simpy.Store,
                         cycle_time_s: float,
                         workers_required: int,
                         workers_pool: Optional[simpy.Container],
                         metrics: dict,
                         poll_dt_min: float = 0.1,
                         reliability_cfg: Optional[Dict[str, Any]] = None):
    """
    Multi-input station with priority + same reliability model (between jobs).
    Also tracks pressen_1 source mix (reman vs new).
    """
    busy = 0.0
    produced = 0.0
    downtime = 0.0

    base_id = name.split("#", 1)[0]
    rel_spec = _reliab_for(base_id, reliability_cfg or {})
    mtbf_min = float(rel_spec.get("mtbf_min", 999999.0))
    ttf = random.expovariate(1.0 / mtbf_min) if mtbf_min > 0 else float("inf")

    reman_sources = set(input_stores_in_priority[:2])

    while True:
        # select source by priority
        src = None
        while src is None:
            for st in input_stores_in_priority:
                if len(st.items) > 0:
                    src = st
                    break
            if src is None:
                yield env.timeout(poll_dt_min)

        item = yield src.get()

        # reserve workers
        if workers_pool is not None and workers_required > 0:
            yield workers_pool.get(workers_required)

        # process
        _begin_processing(metrics, base_id)
        start = env.now
        ct_min = cycle_time_s / 60.0
        yield env.timeout(ct_min)
        busy += (env.now - start)
        _end_processing(metrics, base_id)

        # release workers
        if workers_pool is not None and workers_required > 0:
            yield workers_pool.put(workers_required)

        # output
        yield output_store.put(item)
        produced += 1

        # resources per unit
        ints = metrics.get("station_intensity", {}).get(base_id, {})
        _add_resources(metrics, base_id,
                       kwh=ints.get("kwh_per_unit", 0.0),
                       air=ints.get("air_m3_per_unit", 0.0))

        # pressen_1 mix
        if base_id == "pressen_1":
            if src in reman_sources:
                metrics["pressen1_from_reman"] = metrics.get("pressen1_from_reman", 0) + 1
            else:
                metrics["pressen1_from_new"] = metrics.get("pressen1_from_new", 0) + 1

        # reliability
        ttf -= ct_min
        if ttf <= 0.0:
            repair = _draw_mttr_min(rel_spec)
            if repair > 0:
                yield env.timeout(repair)
                downtime += repair
            ttf = random.expovariate(1.0 / mtbf_min) if mtbf_min > 0 else float("inf")

        # metrics update
        metrics.setdefault("station_output", {})[base_id] = int(produced)
        metrics.setdefault("station_busy_time", {})[base_id] = float(busy)
        metrics.setdefault("station_downtime", {})[base_id] = float(downtime)
