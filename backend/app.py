"""
app.py  —  Flask-SocketIO Server  |  Phase 3 + Historical Mode
--------------------------------------------------------------
Two simulation modes:
  GET /start-simulation          →  DNA real-time negotiation (data.json, 5 nodes)
  GET /start-historical?year=X  →  Historical replay (city_data.json, 10 nodes)

Install:
    pip install flask flask-socketio eventlet
"""

import json
import os
import threading
import time

from flask import Flask, jsonify, request
from flask_socketio import SocketIO

from agent import InfrastructureAgent
from historical_sim import run_historical_simulation, VALID_YEARS


# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["SECRET_KEY"] = "bengaluru-crisis-dna-phase3"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# ── Constants ─────────────────────────────────────────────────────────────────

DATA_FILE     = os.path.join(os.path.dirname(__file__), "data.json")
CRISIS_FACTOR = 0.50


# ── Helpers (DNA mode) ────────────────────────────────────────────────────────

def load_nodes(path: str) -> list[dict]:
    with open(path, "r") as fh:
        return json.load(fh)


def build_thought_log(agent: InfrastructureAgent) -> str:
    if agent.status == "SECURED":
        return (f"✅ {agent.agent_id} secured full allocation — "
                f"{agent.allocated_power:,.0f} kW granted. "
                f"Priority P{agent.priority_level} honoured.")
    elif agent.status == "CRITICAL":
        return (f"⚠️  {agent.agent_id} on CRITICAL threshold — "
                f"{agent.allocated_power:,.0f} kW "
                f"(reduced from {agent.base_power_demand:,.0f} kW base demand). "
                f"Minimum ops maintained.")
    else:
        return (f"🔴 {agent.agent_id} LOAD SHED — supply exhausted. "
                f"0 kW allocated. Node offline. "
                f"Priority P{agent.priority_level} insufficient.")


def emit_agent_update(agent: InfrastructureAgent) -> None:
    packet = {
        "agent_id"        : agent.agent_id,
        "type"            : agent.node_type,
        "priority_level"  : agent.priority_level,
        "status"          : agent.status,
        "allocated_power" : agent.allocated_power,
        "base_demand"     : agent.base_power_demand,
        "thought_log"     : build_thought_log(agent),
        "historical"      : False,      # flag so frontend knows which mode
    }
    socketio.emit("agent_update", packet)


# ── DNA Simulation ────────────────────────────────────────────────────────────

def run_simulation() -> None:
    nodes         = load_nodes(DATA_FILE)
    normal_supply = sum(n["base_power_demand"] for n in nodes)
    crisis_supply = normal_supply * CRISIS_FACTOR

    supply_ref  = [crisis_supply]
    supply_lock = threading.Lock()

    socketio.emit("simulation_start", {
        "total_nodes"  : len(nodes),
        "normal_supply": normal_supply,
        "crisis_supply": crisis_supply,
        "crisis_factor": CRISIS_FACTOR,
        "message"      : (f"⚡ DNA Crisis event active — grid at "
                          f"{crisis_supply:,.0f} kW "
                          f"({int(CRISIS_FACTOR * 100)}% of {normal_supply:,.0f} kW normal)"),
    })

    time.sleep(0.4)

    agents = [InfrastructureAgent(node, supply_ref, supply_lock) for node in nodes]
    agents.sort(key=lambda a: a.priority_level, reverse=True)

    for agent in agents:
        agent.start()

    reported = set()
    while len(reported) < len(agents):
        for agent in agents:
            if agent.agent_id not in reported and agent.status != "PENDING":
                emit_agent_update(agent)
                reported.add(agent.agent_id)
        time.sleep(0.05)

    for agent in agents:
        agent.join(timeout=5)

    total_allocated = sum(a.allocated_power for a in agents)
    shed_count      = sum(1 for a in agents if a.status == "LOAD_SHED")

    socketio.emit("simulation_end", {
        "total_allocated" : total_allocated,
        "remaining_supply": supply_ref[0],
        "shed_count"      : shed_count,
        "message"         : (f"✔ DNA Negotiation complete — "
                             f"{total_allocated:,.0f} kW allocated across "
                             f"{len(agents) - shed_count} nodes. "
                             f"{shed_count} node(s) shed."),
    })


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/start-simulation", methods=["GET"])
def start_simulation():
    """Trigger DNA real-time negotiation simulation."""
    t = threading.Thread(target=run_simulation, daemon=True)
    t.start()
    return jsonify({"status": "started", "mode": "dna"})


@app.route("/start-historical", methods=["GET"])
def start_historical():
    """
    Trigger historical disaster replay for a given year.
    Usage: GET /start-historical?year=2017
    Valid years: 2006, 2015, 2017, 2022, 2024
    """
    try:
        year = int(request.args.get("year", 2022))
    except ValueError:
        return jsonify({"error": "year must be an integer"}), 400

    if year not in VALID_YEARS:
        return jsonify({"error": f"year must be one of {VALID_YEARS}"}), 400

    t = threading.Thread(
        target=run_historical_simulation,
        args=(year, socketio),
        daemon=True
    )
    t.start()
    return jsonify({"status": "started", "mode": "historical", "year": year})


@app.route("/city-data", methods=["GET"])
def get_city_data():
    """Expose the full city_data.json to the frontend if needed."""
    city_file = os.path.join(os.path.dirname(__file__), "city_data.json")
    with open(city_file) as fh:
        return jsonify(json.load(fh))


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "online", "system": "Bengaluru Crisis Management API v3.1"})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)