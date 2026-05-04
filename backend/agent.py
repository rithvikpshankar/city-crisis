"""
agent.py
--------
InfrastructureAgent — one self-contained DNA negotiation unit per city node.
Inherits from threading.Thread; each instance runs its own negotiate() call.

Priority tiers (Phase 3):
    HIGH   P >= 8  → Hospital, Water Treatment — always funded, full demand
    MEDIUM P >= 5  → Residential               — negotiate on critical threshold
    LOW    P <  5  → IT Parks                  — yield immediately, no pool access
"""

import threading
import time
import random


# ── Tier cutoffs ──────────────────────────────────────────────────────────────
HIGH_PRIORITY_CUTOFF   = 8   # P8–P10: full demand, non-negotiable
MEDIUM_PRIORITY_CUTOFF = 5   # P5–P7:  ask for critical_threshold only
                              # P1–P4:  shed immediately without touching pool


class InfrastructureAgent(threading.Thread):
    """
    Attributes
    ----------
    agent_id          : str
    node_type         : str    'Critical' | 'Commercial' | 'Residential'
    priority_level    : int    1–10
    base_power_demand : float  kW — normal operating load
    critical_threshold: float  kW — minimum to stay operational
    status            : str    'PENDING' → 'SECURED' | 'CRITICAL' | 'LOAD_SHED'
    allocated_power   : float  kW actually granted after negotiation
    """

    STATUS_SECURED   = "SECURED"
    STATUS_CRITICAL  = "CRITICAL"
    STATUS_LOAD_SHED = "LOAD_SHED"

    def __init__(self, config: dict, supply_ref: list, supply_lock: threading.Lock):
        super().__init__(name=config["agent_id"], daemon=True)

        self.agent_id           = config["agent_id"]
        self.location           = config.get("location", "Unknown")
        self.node_type          = config["type"]
        self.priority_level     = config["priority_level"]
        self.base_power_demand  = config["base_power_demand"]
        self.critical_threshold = config["critical_threshold"]

        self.status          = "PENDING"
        self.allocated_power = 0.0
        self._lock           = threading.Lock()     # guards this agent's own state

        self._supply_ref  = supply_ref              # shared pool reference
        self._supply_lock = supply_lock             # shared pool lock

        # Random jitter simulates natural network/processing latency
        self._jitter = random.uniform(0.05, 0.35)

    # ── Thread entry ──────────────────────────────────────────────────────────

    def run(self):
        time.sleep(self._jitter)    # simulate latency before negotiating
        self.negotiate()

    # ── DNA negotiation core ──────────────────────────────────────────────────

    def negotiate(self):
        """
        Three-tier Decentralised Negotiation Algorithm:

        Tier 1 — HIGH   (P >= 8): demand full base load unconditionally.
                                   Hospital / Water Treatment always win.

        Tier 2 — MEDIUM (P >= 5): demand only critical_threshold (conservative ask).
                                   Residential gets power if Tier 1 leaves enough.

        Tier 3 — LOW    (P <  5): shed immediately — never touch the supply pool.
                                   IT Parks yield so pool stays intact for others.
        """

        # ── Tier 3: yield without competing ───────────────────────────────────
        if self.priority_level < MEDIUM_PRIORITY_CUTOFF:
            self._set_state(self.STATUS_LOAD_SHED, 0.0)
            return

        demand = self._decide_demand()

        # ── Tier 1 & 2: atomic read-modify-write on shared pool ───────────────
        with self._supply_lock:
            available = self._supply_ref[0]

            if available >= demand:
                # Full demand met
                self._supply_ref[0] -= demand
                self._set_state(self.STATUS_SECURED, demand)

            elif available >= self.critical_threshold:
                # Only threshold available — take minimum, stay operational
                self._supply_ref[0] -= self.critical_threshold
                self._set_state(self.STATUS_CRITICAL, self.critical_threshold)

            else:
                # Even threshold unavailable — shed
                self._set_state(self.STATUS_LOAD_SHED, 0.0)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _decide_demand(self) -> float:
        """
        HIGH  priority → ask for full base_power_demand (non-negotiable).
        MEDIUM priority → ask only for critical_threshold (conservative).
        LOW   priority → never reaches this method (shed before calling).
        """
        if self.priority_level >= HIGH_PRIORITY_CUTOFF:
            return self.base_power_demand
        return self.critical_threshold

    def _set_state(self, status: str, power: float):
        """Thread-safe write to status and allocated_power."""
        with self._lock:
            self.status          = status
            self.allocated_power = power

    def __repr__(self):
        return (f"<Agent {self.agent_id} | P{self.priority_level} "
                f"| {self.status} | {self.allocated_power:,.0f} kW>")