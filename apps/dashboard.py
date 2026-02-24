# apps/dashboard.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from dash import Dash, dcc, html, Input, Output, State, dash_table
import plotly.express as px
import plotly.graph_objects as go

# =========================
# Config & Styling
# =========================
RUNS_DIR = os.environ.get("LF_RUNS_DIR", "runs")
PLOT_BG = "#F0F7F9"
CARD_BG = "#FFFFFF"
BODY_BG = PLOT_BG
GRAPH_HEIGHT = 420
UIREV = "lock"  # <- NEW: freeze plot layout revisions

CARD_STYLE = {
    "background": CARD_BG,
    "padding": "12px",
    "borderRadius": "10px",
    "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
}

# =========================
# Utilities
# =========================
def ts_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def list_runs(runs_root: str = RUNS_DIR) -> List[str]:
    """List run folder names sorted by newest first (descending)."""
    if not os.path.isdir(runs_root):
        return []
    subdirs = [d for d in os.listdir(runs_root) if os.path.isdir(os.path.join(runs_root, d))]
    # Expect names like YYYY-MM-DD_HHMMSS — lexical sort works as desc recency
    return sorted(subdirs, reverse=True)

def _load_csv_safe(
    path: str,
    expected_cols: Optional[List[str]] = None,
    expected_dtypes: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Robust CSV reader:
    - If file missing → empty DF with expected columns.
    - Adds any missing expected columns with correct dtypes.
    - Reorders columns to expected order if provided.
    """
    try:
        if not os.path.exists(path):
            df = pd.DataFrame(columns=expected_cols or [])
        else:
            df = pd.read_csv(path)

        if expected_cols:
            for col in expected_cols:
                if col not in df.columns:
                    dtype = (expected_dtypes or {}).get(col, None)
                    if dtype == "float":
                        df[col] = pd.Series(dtype="float64")
                    elif dtype == "int":
                        df[col] = pd.Series(dtype="Int64")
                    elif dtype == "str":
                        df[col] = pd.Series(dtype="object")
                    else:
                        df[col] = pd.Series(dtype="object")
            df = df[expected_cols]

        if expected_dtypes:
            for c, dt in expected_dtypes.items():
                if c in df.columns and dt in ("float", "int"):
                    df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    except Exception as e:
        print(f"[{ts_now()}] WARN: failed reading {path}: {e}")
        return pd.DataFrame(columns=expected_cols or [])

def load_run_as_records(run_folder: str) -> Dict[str, List[dict]]:
    """Read all CSVs under a given run folder; return JSON-ready dict of records lists."""
    base = os.path.join(RUNS_DIR, run_folder)
    p = lambda name: os.path.join(base, name)

    kpi_general = _load_csv_safe(
        p("kpi_general.csv"),
        expected_cols=["KPI", "Value"],
        expected_dtypes={"KPI": "str", "Value": "float"},
    )
    kpi_stations = _load_csv_safe(
        p("kpi_stations.csv"),
        expected_cols=["Station", "Utilization %"],
        expected_dtypes={"Station": "str", "Utilization %": "float"},
    )
    kpi_wip_now = _load_csv_safe(
        p("kpi_wip_now.csv"),
        expected_cols=["In-Station WIP at", "Units"],
        expected_dtypes={"In-Station WIP at": "str", "Units": "float"},
    )
    kpi_wip_peak = _load_csv_safe(
        p("kpi_wip_peak.csv"),
        expected_cols=["Station", "Peak In-Process"],
        expected_dtypes={"Station": "str", "Peak In-Process": "float"},
    )
    resource_kpis = _load_csv_safe(
        p("resource_kpis.csv"),
        expected_cols=["Station", "kWh", "Air_m3", "CO2_kg"],
        expected_dtypes={"Station": "str", "kWh": "float", "Air_m3": "float", "CO2_kg": "float"},
    )
    labor_kpis = _load_csv_safe(
        p("labor_kpis.csv"),
        expected_cols=["Station", "Busy (min)", "Workers", "Labor €"],
        expected_dtypes={"Station": "str", "Busy (min)": "float", "Workers": "int", "Labor €": "float"},
    )
    cost_summary = _load_csv_safe(
        p("cost_kpis.csv"),
        expected_cols=["Component", "€"],
        expected_dtypes={"Component": "str", "€": "float"},
    )
    # inventory_ts is dynamic; just try to coerce time_min if present
    inventory_ts = _load_csv_safe(p("inventory_ts.csv"))
    if "time_min" in inventory_ts.columns:
        inventory_ts["time_min"] = pd.to_numeric(inventory_ts["time_min"], errors="coerce")

    downtime = _load_csv_safe(
        p("kpi_downtime.csv"),
        expected_cols=["Station", "Downtime (min)"],
        expected_dtypes={"Station": "str", "Downtime (min)": "float"},
    )

    print(f"[{ts_now()}] loaded run {run_folder}")

    return {
        "kpi_general": kpi_general.to_dict("records"),
        "kpi_stations": kpi_stations.to_dict("records"),
        "kpi_wip_now": kpi_wip_now.to_dict("records"),
        "kpi_wip_peak": kpi_wip_peak.to_dict("records"),
        "resource_kpis": resource_kpis.to_dict("records"),
        "labor_kpis": labor_kpis.to_dict("records"),
        "cost_summary": cost_summary.to_dict("records"),
        "inventory_ts": inventory_ts.to_dict("records"),
        "downtime": downtime.to_dict("records"),
    }

def records_to_df(data: Dict[str, List[dict]], key: str) -> pd.DataFrame:
    recs = data.get(key) or []
    return pd.DataFrame.from_records(recs) if recs else pd.DataFrame()

def _is_visible_inventory_series(col: str) -> bool:
    """Only show real stockpoints, not per-station plumbing or inproc series."""
    if col == "time_min":
        return False
    if col.startswith("after_"):
        return False
    if col.startswith("inproc_"):
        return False
    return True

def empty_msg(text: str = "No data") -> html.Div:
    return html.Div(text, style={"padding": "8px", "color": "#666", "fontStyle": "italic"})

def apply_figure_layout(fig: go.Figure, xangle: Optional[int] = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=GRAPH_HEIGHT,
        margin=dict(l=40, r=20, t=40, b=40),
        plot_bgcolor=PLOT_BG,
        paper_bgcolor=PLOT_BG,
        font=dict(family="'Open Sans', sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        uirevision=UIREV,  # <- NEW: freeze layout revision to prevent reflow loops
    )
    if xangle is not None:
        fig.update_xaxes(tickangle=xangle)
    return fig

def kpi_general_table(df: pd.DataFrame) -> html.Div:
    if df.empty:
        return empty_msg("No KPI data")
    df2 = df.copy()
    if "Value" in df2.columns:
        df2["Value"] = pd.to_numeric(df2["Value"], errors="coerce").round(3)
    return dash_table.DataTable(
        data=df2.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df2.columns],
        style_cell={"padding": "6px", "fontFamily": "Open Sans", "fontSize": 13},
        style_header={"fontWeight": "600", "backgroundColor": "#eef6f8"},
        page_size=12,
        style_table={"maxHeight": "320px", "overflowY": "auto"},  # <- NEW: fixed height + scroll
        fixed_rows={"headers": True},
    )

def generic_table(df: pd.DataFrame, page_size: int = 12) -> html.Div:
    if df.empty:
        return empty_msg()
    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        style_cell={"padding": "6px", "fontFamily": "Open Sans", "fontSize": 13},
        style_header={"fontWeight": "600", "backgroundColor": "#eef6f8"},
        page_size=page_size,
        style_table={"maxHeight": "320px", "overflowY": "auto"},  # <- NEW
        fixed_rows={"headers": True},
    )

# =========================
# App
# =========================
app = Dash(__name__, suppress_callback_exceptions=True)

# index_string with f-string and escaped braces for Jinja/CSS
app.index_string = f"""
<!DOCTYPE html>
<html>
  <head>
    {{%metas%}}
    <title>Lernfabrik Dashboard – Zirkuläre Produktion</title>
    <link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    {{%favicon%}}
    {{%css%}}
    <style>
      html, body {{ font-family: 'Open Sans', sans-serif; background: {BODY_BG}; }}
      .container {{ max-width: 1280px; margin: 0 auto; padding: 16px; }}
      .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
      .row-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }}
      .row-1 {{ display: grid; grid-template-columns: 1fr; gap: 12px; }}
      .controls {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
      .subtitle {{ color: #475569; margin-top: -6px; }}
    </style>
  </head>
  <body>
    {{%app_entry%}}
    <footer>
      {{%config%}}
      {{%scripts%}}
      {{%renderer%}}
    </footer>
  </body>
</html>
"""

# Header & controls
header = html.Div(
    className="container",
    children=[
        html.H1("Lernfabrik Dashboard – Zirkuläre Produktion"),
        html.Div("Simulation results for one 8h shift", className="subtitle"),
        html.Div(
            className="controls",
            children=[
                dcc.Dropdown(
                    id="run_select",
                    options=[{"label": r, "value": r} for r in list_runs()],
                    value=(list_runs()[0] if list_runs() else None),
                    placeholder="Select a run folder",
                    style={"minWidth": 360},
                ),
                html.Button("Reload", id="reload_btn", n_clicks=0, style={"height": "38px"}),
                dcc.Store(id="run_data"),
            ],
        ),
        html.Hr(),
    ],
)

# Tabs (static containers, shown/hidden by styles)
tabs = dcc.Tabs(
    id="tabs",
    value="overview",
    children=[
        dcc.Tab(label="Overview", value="overview"),
        dcc.Tab(label="Linear Process", value="linear"),
        dcc.Tab(label="Reman & Mix", value="reman"),
        dcc.Tab(label="Cost & Sustainability", value="cost"),
    ],
)

# Overview tab content
overview_tab = html.Div(
    id="tab_overview_container",
    children=[
        html.Div(
            className="row",
            children=[
                html.Div([html.H4("General KPIs"), html.Div(id="ov_gen_table_container")], style=CARD_STYLE),
                html.Div([
                    html.H4("Station Utilization (%)"),
                    dcc.Graph(
                        id="ov_util_graph",
                        figure=apply_figure_layout(go.Figure()),
                        style={"height": f"{GRAPH_HEIGHT}px"},
                        config={"responsive": False},
                    ),
                ], style=CARD_STYLE),
            ],
        ),
        html.Div(
            className="row-1",
            children=[
                html.Div([
                    html.H4("Resource Totals (kWh / m³ Air / kg CO₂)"),
                    dcc.Graph(
                        id="ov_resource_pie",
                        figure=apply_figure_layout(go.Figure()),
                        style={"height": f"{GRAPH_HEIGHT}px"},
                        config={"responsive": False},
                    ),
                ], style=CARD_STYLE),
            ],
        ),
    ],
)

# Linear Process tab content
linear_tab = html.Div(
    id="tab_linear_container",
    children=[
        html.Div(
            className="row",
            children=[
                html.Div([
                    html.H4("Inventory Time Series"),
                    dcc.Dropdown(id="lin_inv_series", options=[], value=None, placeholder="Select series"),
                    dcc.Graph(
                        id="lin_inv_graph",
                        figure=apply_figure_layout(go.Figure()),
                        style={"height": f"{GRAPH_HEIGHT}px"},
                        config={"responsive": False},
                    ),
                ], style=CARD_STYLE),
                html.Div([
                    html.H4("Utilization by Station"),
                    dcc.Graph(
                        id="lin_util_graph",
                        figure=apply_figure_layout(go.Figure()),
                        style={"height": f"{GRAPH_HEIGHT}px"},
                        config={"responsive": False},
                    ),
                    html.Hr(),
                    html.H5("In-Station WIP (live, end)"),
                    html.Div(id="lin_wip_table_container"),
                ], style=CARD_STYLE),
            ],
        ),
    ],
)

# Reman & Mix tab content
reman_tab = html.Div(
    id="tab_reman_container",
    children=[
        html.Div(
            className="row",
            children=[
                html.Div([
                    html.H4("Pressen_1 Source Mix"),
                    dcc.Graph(
                        id="reman_mix_pie",
                        figure=apply_figure_layout(go.Figure()),
                        style={"height": f"{GRAPH_HEIGHT}px"},
                        config={"responsive": False},
                    ),
                ], style=CARD_STYLE),
                html.Div([
                    html.H4("Downtime by Station"),
                    dcc.Graph(
                        id="reman_downtime_bar",
                        figure=apply_figure_layout(go.Figure()),
                        style={"height": f"{GRAPH_HEIGHT}px"},
                        config={"responsive": False},
                    ),
                ], style=CARD_STYLE),
            ],
        ),
        html.Div(
            className="row-1",
            children=[
                html.Div([
                    html.H4("Remanufacturing KPIs"),
                    html.Div(id="reman_table_container"),
                ], style=CARD_STYLE),
            ],
        ),
    ],
)

# Cost & Sustainability tab content
cost_tab = html.Div(
    id="tab_cost_container",
    children=[
        html.Div(
            className="row",
            children=[
                html.Div([
                    html.H4("Cost Breakdown – Waterfall"),
                    dcc.Graph(
                        id="cost_waterfall",
                        figure=apply_figure_layout(go.Figure()),
                        style={"height": f"{GRAPH_HEIGHT}px"},
                        config={"responsive": False},
                    ),
                ], style=CARD_STYLE),
                html.Div([
                    html.H4("Resources by Station"),
                    dcc.Graph(
                        id="sust_resource_grouped",
                        figure=apply_figure_layout(go.Figure()),
                        style={"height": f"{GRAPH_HEIGHT}px"},
                        config={"responsive": False},
                    ),
                ], style=CARD_STYLE),
            ],
        ),
        html.Div(
            className="row-1",
            children=[
                html.Div([
                    html.H4("Labor KPIs"),
                    html.Div(id="labor_table_container"),
                ], style=CARD_STYLE),
            ],
        ),
    ],
)

app.layout = html.Div(
    children=[
        header,
        html.Div(className="container", children=[tabs]),
        html.Div(className="container", children=[overview_tab, linear_tab, reman_tab, cost_tab]),
    ]
)

# =========================
# Callbacks
# =========================

# 1) Load run -> store
@app.callback(
    Output("run_data", "data"),
    Input("run_select", "value"),
    Input("reload_btn", "n_clicks"),
    prevent_initial_call=False,
)
def load_run_to_store(run_folder: Optional[str], _reload_clicks: Optional[int]):
    if not run_folder:
        return {}
    try:
        data = load_run_as_records(run_folder)
        return data
    except Exception as e:
        print(f"[{ts_now()}] ERROR loading run {run_folder}: {e}")
        return {}

# 2) Tab visibility
@app.callback(
    Output("tab_overview_container", "style"),
    Output("tab_linear_container", "style"),
    Output("tab_reman_container", "style"),
    Output("tab_cost_container", "style"),
    Input("tabs", "value"),
)
def toggle_tabs(tab_value: str):
    def show(v: str):
        return {"display": "block"} if tab_value == v else {"display": "none"}
    return show("overview"), show("linear"), show("reman"), show("cost")

# 3) Overview update
@app.callback(
    Output("ov_gen_table_container", "children"),
    Output("ov_util_graph", "figure"),
    Output("ov_resource_pie", "figure"),
    Input("run_data", "data"),
)
def update_overview(data: Dict):
    if not data:
        return empty_msg("Select a run"), apply_figure_layout(go.Figure()), apply_figure_layout(go.Figure())

    kpi_general = records_to_df(data, "kpi_general")
    kpi_stations = records_to_df(data, "kpi_stations")
    resource_kpis = records_to_df(data, "resource_kpis")

    # Table
    gen_table = kpi_general_table(kpi_general)

    # Utilization bar (horizontal)
    util_fig = go.Figure()
    if not kpi_stations.empty and {"Station", "Utilization %"}.issubset(kpi_stations.columns):
        sdf = kpi_stations.sort_values("Utilization %", ascending=True)
        util_fig = go.Figure(
            data=[go.Bar(x=sdf["Utilization %"], y=sdf["Station"], orientation="h", name="Utilization %")]
        )
    util_fig = apply_figure_layout(util_fig)

    # Resource totals pie
    pie_fig = go.Figure()
    if not resource_kpis.empty:
        totals = {
            "Energy kWh": resource_kpis.get("kWh", pd.Series(dtype=float)).sum(skipna=True),
            "Air m³": resource_kpis.get("Air_m3", pd.Series(dtype=float)).sum(skipna=True),
            "CO₂ kg": resource_kpis.get("CO2_kg", pd.Series(dtype=float)).sum(skipna=True),
        }
        if any(v > 0 for v in totals.values()):
            pie_fig = px.pie(names=list(totals.keys()), values=list(totals.values()), hole=0.35)
    pie_fig = apply_figure_layout(pie_fig)

    return gen_table, util_fig, pie_fig

# 4) Linear update (store change) — DO NOT output lin_inv_graph.figure here
@app.callback(
    Output("lin_inv_series", "options"),
    Output("lin_inv_series", "value"),
    Output("lin_util_graph", "figure"),
    Output("lin_wip_table_container", "children"),
    Input("run_data", "data"),
)
def update_linear_basics(data: Dict):
    if not data:
        return [], None, apply_figure_layout(go.Figure()), empty_msg("Select a run")

    inventory_ts = records_to_df(data, "inventory_ts")
    kpi_stations = records_to_df(data, "kpi_stations")
    kpi_wip_now = records_to_df(data, "kpi_wip_now")

    # Series options
    options: List[Dict[str, str]] = []
    default_value: Optional[str] = None
    if not inventory_ts.empty and "time_min" in inventory_ts.columns:
        series_cols = [c for c in inventory_ts.columns if _is_visible_inventory_series(c)]
        options = [{"label": c, "value": c} for c in series_cols]
        if series_cols:
            # Prefer a physically meaningful default if present
            preferred = ["neu_lager", "reman_lager", "lager1", "lager2", "warenannahme", "blaue_kisten", "scrap_bin"]
            default_value = next((p for p in preferred if p in series_cols), series_cols[0])

    # Utilization graph
    util_fig = go.Figure()
    if not kpi_stations.empty and {"Station", "Utilization %"}.issubset(kpi_stations.columns):
        sdf = kpi_stations.sort_values("Utilization %", ascending=False)
        util_fig = go.Figure(data=[go.Bar(x=sdf["Station"], y=sdf["Utilization %"], name="Utilization %")])
        util_fig = apply_figure_layout(util_fig, xangle=-30)
    else:
        util_fig = apply_figure_layout(util_fig)

    # WIP table
    wip_table = generic_table(kpi_wip_now) if not kpi_wip_now.empty else empty_msg("No WIP data")

    return options, default_value, util_fig, wip_table

# 5) Linear series change — ONLY owner of lin_inv_graph.figure
@app.callback(
    Output("lin_inv_graph", "figure"),
    Input("lin_inv_series", "value"),
    State("run_data", "data"),
)
def update_linear_series(series_value: Optional[str], data: Dict):
    fig = go.Figure()
    if not data:
        return apply_figure_layout(fig)

    inventory_ts = records_to_df(data, "inventory_ts")
    if inventory_ts.empty or "time_min" not in inventory_ts.columns or not series_value or series_value not in inventory_ts.columns:
        return apply_figure_layout(fig)

    x = pd.to_numeric(inventory_ts["time_min"], errors="coerce")
    y = pd.to_numeric(inventory_ts[series_value], errors="coerce")
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=series_value))
    fig.update_xaxes(title_text="time (min)")
    fig.update_yaxes(title_text=series_value)
    return apply_figure_layout(fig)

# 6) Reman & Mix update
@app.callback(
    Output("reman_mix_pie", "figure"),
    Output("reman_downtime_bar", "figure"),
    Output("reman_table_container", "children"),
    Input("run_data", "data"),
)
def update_reman(data: Dict):
    if not data:
        return apply_figure_layout(go.Figure()), apply_figure_layout(go.Figure()), empty_msg("Select a run")

    kpi_general = records_to_df(data, "kpi_general")
    downtime = records_to_df(data, "downtime")

    # Mix pie from kpi_general
    pie_fig = go.Figure()
    if not kpi_general.empty and {"KPI", "Value"}.issubset(kpi_general.columns):
        def get_val(name: str) -> float:
            row = kpi_general.loc[kpi_general["KPI"].astype(str).str.strip() == name, "Value"]
            return float(row.iloc[0]) if not row.empty else 0.0
        v_reman = get_val("Pressen_1 input from REMAN")
        v_new = get_val("Pressen_1 input from NEW")
        if (v_reman + v_new) > 0:
            pie_fig = px.pie(names=["REMAN", "NEW"], values=[v_reman, v_new], hole=0.35)
    pie_fig = apply_figure_layout(pie_fig)

    # Downtime horizontal bar
    dt_fig = go.Figure()
    if not downtime.empty and {"Station", "Downtime (min)"}.issubset(downtime.columns):
        ddf = downtime.sort_values("Downtime (min)", ascending=True)
        dt_fig = go.Figure(data=[go.Bar(x=ddf["Downtime (min)"], y=ddf["Station"], orientation="h")])
    dt_fig = apply_figure_layout(dt_fig)

    # Reman KPIs filtered table
    reman_df = pd.DataFrame()
    if not kpi_general.empty and "KPI" in kpi_general.columns:
        mask = kpi_general["KPI"].astype(str).str.contains(
            r"Reman|Returns|Scrap|Befundung|Pressen_1 input", case=False, regex=True, na=False
        )
        reman_df = kpi_general.loc[mask].copy()
        if "Value" in reman_df.columns:
            reman_df["Value"] = pd.to_numeric(reman_df["Value"], errors="coerce").round(3)
    reman_table = generic_table(reman_df) if not reman_df.empty else empty_msg("No Reman KPIs found")

    return pie_fig, dt_fig, reman_table

# 7) Cost & Sustainability update
@app.callback(
    Output("cost_waterfall", "figure"),
    Output("sust_resource_grouped", "figure"),
    Output("labor_table_container", "children"),
    Input("run_data", "data"),
)
def update_cost_sust(data: Dict):
    if not data:
        return apply_figure_layout(go.Figure()), apply_figure_layout(go.Figure()), empty_msg("Select a run")

    cost_summary = records_to_df(data, "cost_summary")
    resource_kpis = records_to_df(data, "resource_kpis")
    labor_kpis = records_to_df(data, "labor_kpis")

    # Waterfall
    wf_fig = go.Figure()
    if not cost_summary.empty and {"Component", "€"}.issubset(cost_summary.columns):
        cdf = cost_summary.copy()
        measures = ["relative"] * (len(cdf) - 1) + ["total"] if len(cdf) >= 1 else []
        wf_fig = go.Figure(go.Waterfall(x=cdf["Component"], y=cdf["€"], measure=measures))
    wf_fig = apply_figure_layout(wf_fig, xangle=-30)

    # Grouped bar: resources by station
    grp_fig = go.Figure()
    if not resource_kpis.empty and "Station" in resource_kpis.columns:
        rdf = resource_kpis.copy()
        traces = []
        for col, label in [("kWh", "kWh"), ("Air_m3", "Air m³"), ("CO2_kg", "CO₂ kg")]:
            if col in rdf.columns:
                traces.append(go.Bar(name=label, x=rdf["Station"], y=rdf[col]))
        if traces:
            grp_fig = go.Figure(data=traces)
            grp_fig.update_layout(barmode="group")
    grp_fig = apply_figure_layout(grp_fig, xangle=-30)

    # Labor table
    labor_table = generic_table(labor_kpis) if not labor_kpis.empty else empty_msg("No labor data")

    return wf_fig, grp_fig, labor_table

# =========================
# Main
# =========================
if __name__ == "__main__":
    if not os.path.isdir(RUNS_DIR):
        print(f"[{ts_now()}] NOTE: runs directory '{RUNS_DIR}' not found. The app will load but show empty state until runs are added.")
    # Prefer localhost for direct browsing; disable the reloader to reduce reflow noise
    app.run(debug=False, host="127.0.0.1", port=int(os.environ.get("PORT", 8050)))
