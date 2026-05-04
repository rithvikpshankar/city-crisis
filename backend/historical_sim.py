"""
historical_sim.py
-----------------
Replays actual Bengaluru disaster events from city_data.json.
Instead of a DNA negotiation, this module reads the real percentage_failure
and outage_hours for a chosen year and emits them as if the crisis is
happening live — node by node, with staggered timing for drama.

Supported years: 2006, 2015, 2017, 2022, 2024
"""

import json
import os
import time
import random

# ── Constants ─────────────────────────────────────────────────────────────────

CITY_DATA_FILE = os.path.join(os.path.dirname(__file__), "city_data.json")

# Maps node type to a priority label for display
TYPE_PRIORITY = {
    "Hospital"       : {"label": "CRITICAL",    "color": "red",    "level": 10},
    "Water Treatment": {"label": "CRITICAL",    "color": "red",    "level": 8},
    "Residential"    : {"label": "RESIDENTIAL", "color": "yellow", "level": 5},
    "IT Park"        : {"label": "COMMERCIAL",  "color": "blue",   "level": 3},
}

VALID_YEARS = [2006, 2015, 2017, 2022, 2024]


def load_city_data() -> list[dict]:
    """Load the full 10-node Bengaluru city dataset."""
    with open(CITY_DATA_FILE, "r") as fh:
        return json.load(fh)


def get_failure_record(node: dict, year: int) -> dict | None:
    """Pull the disaster record for a specific year from a node."""
    for record in node.get("disaster_impact_history", []):
        if record["year"] == year:
            return record
    return None


def classify_failure(pct: float) -> str:
    """
    Convert percentage_failure into a status string matching the DNA system.
    0–20%  → SECURED   (minor disruption, node stayed operational)
    21–50% → CRITICAL  (significant stress, partial outage)
    51%+   → LOAD_SHED (major failure, node went down)
    """
    if pct <= 20:
        return "SECURED"
    elif pct <= 50:
        return "CRITICAL"
    else:
        return "LOAD_SHED"


def build_historical_thought_log(node: dict, record: dict, status: str) -> str:
    """Build a human-readable sentence from the historical record."""
    node_id  = node["id"]
    year     = record["year"]
    pct      = record["percentage_failure"]
    cause    = record["cause"]
    hours    = record["outage_hours"]
    notes    = record["notes"]

    if status == "SECURED":
        return (f"✅ [{year}] {node_id} — {pct}% failure recorded. "
                f"Cause: {cause}. Node remained operational. "
                f"Outage: {hours}h. Note: {notes}")
    elif status == "CRITICAL":
        return (f"⚠️  [{year}] {node_id} — {pct}% failure. "
                f"Cause: {cause}. Partial outage for {hours}h. "
                f"Note: {notes}")
    else:
        return (f"🔴 [{year}] {node_id} — {pct}% failure. "
                f"Cause: {cause}. Full outage {hours}h. "
                f"Note: {notes}")


def run_historical_simulation(year: int, socketio) -> None:
    """
    Main historical replay engine.

    For each node in city_data.json:
      1. Find its disaster record for the chosen year
      2. Classify failure severity → status
      3. Compute simulated power impact
      4. Emit an agent_update packet (same schema as DNA sim)
         so the frontend renders it identically
      5. Stagger emissions with a short sleep for live-replay feel

    Parameters
    ----------
    year     : int      one of [2006, 2015, 2017, 2022, 2024]
    socketio : SocketIO Flask-SocketIO instance for emitting events
    """

    if year not in VALID_YEARS:
        socketio.emit("simulation_end", {
            "total_allocated" : 0,
            "remaining_supply": 0,
            "shed_count"      : 0,
            "message"         : f"❌ Year {year} not in dataset. Choose from {VALID_YEARS}."
        })
        return

    nodes = load_city_data()

    # Compute total normal MW demand across all 10 nodes (convert MW → kW)
    total_normal_kw = sum(n["base_demand_mw"] * 1000 for n in nodes)

    # Estimate crisis supply: use average failure % of that year across nodes
    failure_records = [get_failure_record(n, year) for n in nodes]
    valid_records   = [r for r in failure_records if r is not None]
    avg_failure_pct = sum(r["percentage_failure"] for r in valid_records) / len(valid_records)
    crisis_supply   = total_normal_kw * (1 - avg_failure_pct / 100)

    # ── Emit simulation_start ─────────────────────────────────────────────────
    year_labels = {
        2006: "Early urbanisation flood season",
        2015: "Koramangala lake breach event",
        2017: "Bellandur lake fire + widespread flooding",
        2022: "September extreme rainfall — ₹300 Cr damage event",
        2024: "Summer grid overload + flash flood combination",
    }

    socketio.emit("simulation_start", {
        "total_nodes"   : len(nodes),
        "normal_supply" : total_normal_kw,
        "crisis_supply" : crisis_supply,
        "crisis_factor" : round(1 - avg_failure_pct / 100, 2),
        "message"       : (f"📅 Replaying {year} disaster — "
                           f"{year_labels.get(year, '')}. "
                           f"Avg grid failure: {avg_failure_pct:.1f}%"),
    })

    time.sleep(0.5)

    # ── Sort nodes: Hospitals first, then Water, Residential, IT Parks ────────
    priority_order = {"Hospital": 0, "Water Treatment": 1, "Residential": 2, "IT Park": 3}
    nodes_sorted   = sorted(nodes, key=lambda n: priority_order.get(n["type"], 9))

    total_allocated = 0.0
    shed_count      = 0

    # ── Emit one packet per node ───────────────────────────────────────────────
    for node in nodes_sorted:
        record = get_failure_record(node, year)

        if record is None:
            # No data for this node in this year — skip gracefully
            continue

        pct_failure    = record["percentage_failure"]
        base_kw        = node["base_demand_mw"] * 1000
        allocated_kw   = base_kw * (1 - pct_failure / 100)
        status         = classify_failure(pct_failure)
        meta           = TYPE_PRIORITY.get(node["type"], {"level": 5})
        thought_log    = build_historical_thought_log(node, record, status)

        if status == "LOAD_SHED":
            shed_count += 1
            allocated_kw = 0.0
        else:
            total_allocated += allocated_kw

        packet = {
            # ── Same schema as DNA agent_update so frontend needs no changes ──
            "agent_id"       : node["id"],
            "type"           : node["type"],
            "priority_level" : meta["level"],
            "status"         : status,
            "allocated_power": round(allocated_kw, 1),
            "base_demand"    : base_kw,
            "thought_log"    : thought_log,

            # ── Extra historical fields (used by frontend's history panel) ────
            "historical"     : True,
            "year"           : year,
            "percentage_failure": pct_failure,
            "outage_hours"   : record["outage_hours"],
            "cause"          : record["cause"],
            "valley"         : node["valley"],
            "risk_index"     : node["historical_risk_index"],
            "coordinates"    : node["coordinates"],
            "notes"          : record["notes"],
        }

        socketio.emit("agent_update", packet)
        time.sleep(random.uniform(0.3, 0.7))    # stagger for live-replay feel

    # ── Final summary ─────────────────────────────────────────────────────────
    socketio.emit("simulation_end", {
        "total_allocated" : round(total_allocated, 1),
        "remaining_supply": round(crisis_supply - total_allocated, 1),
        "shed_count"      : shed_count,
        "message"         : (f"✔ {year} replay complete — "
                             f"{shed_count} node(s) failed. "
                             f"Avg grid stress: {avg_failure_pct:.1f}%. "
                             f"{total_allocated:,.0f} kW remained operational."),
    })