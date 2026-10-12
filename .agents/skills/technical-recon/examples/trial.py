"""Finite contract trial against only the bundled owned fixture; not a sandbox/analyzer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

FIXTURE = Path(__file__).with_name("fixture.py")


class Model:
    """Independent reconstruction of the observed reservation contract."""
    def __init__(self, capacity: int, drift: bool = False):
        self.capacity, self.used, self.drift = capacity, 0, drift

    def observe(self):
        return {"capacity": self.capacity, "used": self.used, "available": self.capacity - self.used}

    def step(self, action):
        result = "invalid-action"
        if isinstance(action, dict):
            op, amount = action.get("op"), action.get("amount")
            if op in ("reserve", "release") and type(amount) is int and amount > 0:
                delta = amount if op == "reserve" else -amount
                proposed = self.used + delta
                if 0 <= proposed <= self.capacity or (self.drift and op == "reserve"):
                    self.used = proposed
                    result = "ok"
                else:
                    result = "rejected"
        return {"action": action, "result": result, "observation": self.observe()}


def action(op, amount):
    return {"op": op, "amount": amount}


def run_trial(approved=False, inject_drift=False, runner=None, timeout_s=3.0):
    report = {"verified": False, "status": "scope-required", "evidence_type": "synthetic",
              "limitations": "finite owned-fixture claims; not real-target parity or a REA runtime trial"}
    if not approved:
        return report  # explicit scope covers this bundled fixture only; nothing launches
    deadline = time.monotonic() + timeout_s
    runner = runner or subprocess.run

    def capture(seed, actions):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(["owned-fixture"], timeout_s)
        result = runner([sys.executable, "-I", "-B", str(FIXTURE)],
                        input=json.dumps({"seed": seed, "actions": actions}),
                        capture_output=True, text=True, check=True, timeout=remaining,
                        env={"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"})
        return json.loads(result.stdout)

    try:
        report["target_digest"] = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        report["model_digest"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        # Training is one documented observed/source-derived contract, not automatic learning.
        cases = [
            ("training", 0, [action("reserve", 1), action("release", 1)]),
            ("held-out-sequence", 1, [action("reserve", 3), action("reserve", 2),
                                     action("release", 2), action("reserve", 2), action("release", 3)]),
            ("held-out-seed", 9, [action("reserve", 4), action("reserve", 1),
                                 action("release", 4), action("release", 1)]),
            ("held-out-invalid", 2, [action("reserve", 0), action("reserve", True),
                                    action("reserve", -1), action("release", 0.5),
                                    action("unknown", 1), "malformed"]),
        ]
        initial = capture(7, [])["initial"]
        agent = Model(initial["capacity"])
        agent_actions = []
        for _ in range(4):
            obs = agent.observe()
            chosen = action("reserve", obs["available"]) if obs["available"] else action("release", obs["used"])
            agent_actions.append(chosen)
            agent.step(chosen)
        cases.append(("held-out-agent", 7, agent_actions))
        traces, mismatches = [], []
        for name, seed, actions in cases:
            observed = capture(seed, actions)
            model = Model(observed["initial"]["capacity"], drift=inject_drift)
            predicted = {"initial": model.observe(), "trace": [model.step(item) for item in actions]}
            if observed != predicted:
                mismatches.append(name)
            traces.append({"case": name, "seed": seed, "observed": observed, "predicted": predicted})
        replay_equal = capture(cases[1][1], cases[1][2]) == traces[1]["observed"]
        if not replay_equal:
            mismatches.append("reset-replay")
        report.update(status="compared", verified=not mismatches, training_cases=1, held_out_cases=4,
                      agent_actions=len(agent_actions), replay_equal=replay_equal, mismatches=mismatches, traces=traces)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # An unreadable/partial artifact is unknown, never an empty successful comparison.
        report.update(status="unknown", error=type(error).__name__)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-owned-fixture", action="store_true", help="only execute the bundled synthetic fixture")
    parser.add_argument("--inject-drift", action="store_true", help="negative control: let the model over-reserve")
    args = parser.parse_args()
    report = run_trial(approved=args.run_owned_fixture, inject_drift=args.inject_drift)
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["verified"] else 1)
