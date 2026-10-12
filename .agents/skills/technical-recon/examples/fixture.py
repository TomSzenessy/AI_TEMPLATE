"""Owned synthetic reservation service, not an external target or hardened server."""
from __future__ import annotations

import json
import sys


def capture(seed: int, actions: list[object]) -> dict:
    limit = 3 + seed % 4
    reserved = 0

    def observation():
        return {"capacity": limit, "used": reserved, "available": limit - reserved}

    initial = observation()
    trace = []
    for action in actions:
        result = "invalid-action"
        if isinstance(action, dict):
            operation, quantity = action.get("op"), action.get("amount")
            if operation in ("reserve", "release") and type(quantity) is int and quantity > 0:
                if operation == "reserve" and quantity <= limit - reserved:
                    reserved += quantity
                    result = "ok"
                elif operation == "release" and quantity <= reserved:
                    reserved -= quantity
                    result = "ok"
                else:
                    result = "rejected"
        trace.append({"action": action, "result": result, "observation": observation()})
    return {"initial": initial, "trace": trace}


if __name__ == "__main__":
    request = json.load(sys.stdin)
    print(json.dumps(capture(request["seed"], request["actions"]), sort_keys=True))
