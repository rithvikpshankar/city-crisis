"""
main.py
-------
Execution engine for the Bengaluru Crisis Management System.

Pipeline
--------
1. Load data.json  →  instantiate InfrastructureAgent threads
2. Compute normal-grid and crisis-grid totals
3. Fire all threads (MTPBS — Multi-Threaded Priority-Based Scheduler)
4. Stream a real-time Thought Log to the console as threads settle
5. Print a final allocation report

Run with:   python main.py
Requires:   Python 3.8+  (stdlib only — no pip installs needed)
"""

import json
import threading
import time
import os

from agent import InfrastructureAgent


# ── Config ────────────────────────────────────────────────────────────────────

DATA_FILE     = os.path.join(os.path.dirname(__file__), "data.json")
CRISIS_FACTOR = 0.50      # grid drops to 50% during the crisis event
POLL_INTERVAL = 0.05      # seconds between Thought Log refresh cycles
COL_WIDTH     = 60        # console separator width


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_nodes(path: str) -> list[dict]:
    """Read and return the list of node configs from data.json."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Cannot find '{path}'. "
                                "Place data.json in the same directory as main.py.")
    with open(path, "r") as fh:
        data = json.load(fh)
    print(f"[LOADER]  Loaded {len(data)} nodes from '{path}'")
    return data


def separator(char: str = "─", label: str = "") -> None:
    """Print a styled console separator."""
    if label:
        side = (COL_WIDTH - len(label) - 2) // 2
        print(f"{'─' * side} {label} {'─' * side}")
    else:
        print(char * COL_WIDTH)


def status_icon(status: str) -> str:
    """Map agent status to a compact emoji for the Thought Log."""
    return {"SECURED": "✅", "CRITICAL": "⚠️ ", "LOAD_SHED": "🔴", "PENDING": "⏳"}.get(status, "❓")


# ── MTPBS — Multi-Threaded Priority-Based Scheduler ──────────────────────────

def mtpbs_schedule(agents: list[InfrastructureAgent]) -> list[InfrastructureAgent]:
    """
    Sort agents by priority descending so high-priority threads are started
    first and naturally win the race to claim power from the shared pool.

    Final order:
        P10  Hospital_01       → funded unconditionally
        P8   WaterTreatment_01 → funded unconditionally
        P5   Residential_01    → negotiates on critical threshold
        P3   ITpark_01         → sheds immediately
        P2   ITpark_02         → sheds immediately
    """
    return sorted(agents, key=lambda a: a.priority_level, reverse=True)


# ── Thought Log streamer ──────────────────────────────────────────────────────

def stream_thought_log(agents: list[InfrastructureAgent]) -> None:
    """
    Poll each agent's status while threads are alive and print decisions as
    they arrive. Stops once every agent has moved out of PENDING.
    """
    reported = set()

    while True:
        for agent in agents:
            if agent.agent_id in reported:
                continue
            if agent.status != "PENDING":
                icon = status_icon(agent.status)
                kw   = f"{agent.allocated_power:>10,.0f} kW"

                if agent.status == "SECURED":
                    verdict = "secured full power allocation"
                elif agent.status == "CRITICAL":
                    verdict = "running on CRITICAL threshold only"
                else:
                    verdict = "shedding load — insufficient supply"

                print(f"  {icon}  [{agent.agent_id:<20}]  P{agent.priority_level}  "
                      f"{kw}   → {verdict}")
                reported.add(agent.agent_id)

        if len(reported) == len(agents):
            break

        time.sleep(POLL_INTERVAL)


# ── Final report ──────────────────────────────────────────────────────────────

def print_report(agents: list[InfrastructureAgent],
                 normal_supply: float,
                 crisis_supply: float,
                 remaining_supply: list) -> None:
    """Summarise the post-negotiation grid state."""

    separator(label="ALLOCATION REPORT")
    print(f"  {'Agent':<22} {'Type':<14} {'Priority':>8}   "
          f"{'Allocated kW':>13}   {'Status'}")
    separator()

    total_allocated = 0.0
    shed_count      = 0

    for agent in sorted(agents, key=lambda a: a.priority_level, reverse=True):
        icon  = status_icon(agent.status)
        total_allocated += agent.allocated_power
        if agent.status == "LOAD_SHED":
            shed_count += 1
        print(f"  {icon} {agent.agent_id:<22} {agent.node_type:<14} "
              f"{'P' + str(agent.priority_level):>8}   "
              f"{agent.allocated_power:>13,.0f}   {agent.status}")

    separator()
    print(f"  Normal grid supply  : {normal_supply:>13,.0f} kW")
    print(f"  Crisis grid supply  : {crisis_supply:>13,.0f} kW  "
          f"(−{(1 - CRISIS_FACTOR)*100:.0f}% event)")
    print(f"  Total allocated     : {total_allocated:>13,.0f} kW")
    print(f"  Remaining in pool   : {remaining_supply[0]:>13,.0f} kW")
    print(f"  Nodes shedding load : {shed_count} / {len(agents)}")
    separator()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    separator(label="BENGALURU CRISIS MANAGEMENT SYSTEM")
    print("  DNA — Decentralised Negotiation Algorithm  |  MTPBS Scheduler\n")

    # ── 1. Load node data ─────────────────────────────────────────────────────
    nodes = load_nodes(DATA_FILE)

    # ── 2. Compute supply figures ─────────────────────────────────────────────
    normal_supply = sum(n["base_power_demand"] for n in nodes)
    crisis_supply = normal_supply * CRISIS_FACTOR

    print(f"\n[GRID]    Normal total demand : {normal_supply:,.0f} kW")
    print(f"[GRID]    Crisis supply (50%)  : {crisis_supply:,.0f} kW")

    # ── 3. Shared supply pool ─────────────────────────────────────────────────
    supply_ref  = [crisis_supply]
    supply_lock = threading.Lock()

    # ── 4. Instantiate agents ─────────────────────────────────────────────────
    agents = [
        InfrastructureAgent(node, supply_ref, supply_lock)
        for node in nodes
    ]

    # ── 5. MTPBS: sort by priority, then start all threads ───────────────────
    agents = mtpbs_schedule(agents)

    separator(label="CRISIS EVENT TRIGGERED")
    print(f"  ⚡  Grid supply collapsed to {crisis_supply:,.0f} kW "
          f"({CRISIS_FACTOR*100:.0f}% of normal)\n")
    print("  Priority tiers active:")
    print("    P8–P10  Hospital, Water Treatment → funded unconditionally")
    print("    P5–P7   Residential               → negotiate on critical threshold")
    print("    P1–P4   IT Parks                  → yield immediately\n")

    separator(label="THOUGHT LOG  —  real-time agent decisions")

    for agent in agents:
        agent.start()

    # ── 6. Stream Thought Log ─────────────────────────────────────────────────
    stream_thought_log(agents)

    # ── 7. Wait for all threads ───────────────────────────────────────────────
    for agent in agents:
        agent.join(timeout=5)

    # ── 8. Final report ───────────────────────────────────────────────────────
    print()
    print_report(agents, normal_supply, crisis_supply, supply_ref)
    print("\n  System stabilised. Negotiation complete.\n")


if __name__ == "__main__":
    main()