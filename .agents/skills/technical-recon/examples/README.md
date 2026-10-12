# Owned-fixture contract trial

This is a small **synthetic reservation service**, not a proxy for any real app
or an implementation of REA. It shows how to test one recovered behavior
contract before using its reconstruction for agent experiments. Python 3.11+
and the standard library are sufficient; no downloads, accounts or native tools.

From the project root, explicitly select only the bundled owned fixture:

```sh
python3 .agents/skills/technical-recon/examples/trial.py --run-owned-fixture
```

The JSON artifact contains the authority/model digests, observations and
predictions, one training case, three fixed held-out cases, one held-out
four-decision agent comparison, reset/replay and divergence results. Fixed
identical-action transition comparisons live in `traces`; independently generated
agent actions and outputs live separately in `agent_comparison`. `verified: true` applies only to those
finite synthetic claims. Save it to an ignored local evidence path if useful;
these fixtures contain no user or target data. Run without the selector to
observe `scope-required`: no child starts. The selector authorizes this example
only; it neither approves another target nor provides security isolation.

## What was reconstructed

`fixture.py` is the owned authority, executed in a separate isolated-Python
subprocess with a minimal environment. `trial.py` independently models its
state transitions. The declared contract is: positive integer reservations fit
available capacity; releases fit used capacity; invalid types/operations are
rejected without changing state; reset(seed) recreates the initial capacity.
The transition tests obtain capacity from the reset observation, not private
state; the reactive model independently implements the seed-to-capacity reset.
This is a source/observation-informed hand-written model, not automatic learning.

The small policy reserves all observed available capacity, or releases all
observed used capacity when full. The **same policy runs independently** through
interchangeable `reset(seed)`, `observe()`, `step(action)` adapters. Each run
chooses its own four actions from its own observations; neither action sequence
is supplied to the other run. The report compares both generated actions and
outputs, so changed feedback can change subsequent decisions and be detected.
Fixed held-out transition cases separately exercise sequence, seed and
malformed-action edges; identical actions there are not a reactive comparison.

The authority adapter resets with a fresh fixture subprocess and caches its
observation. Each step starts another fresh subprocess and replays **only that
authority run's** accumulated action prefix. This is valid only because the owned
fixture is deterministic and side-effect-free under a seed. It is not a persistent
session, streaming transport, timing/concurrency model or arbitrary-execution
adapter; replay would be unsuitable for nondeterministic or externally
side-effecting targets. The reactive trial is bounded to four decisions; it
replays at most four actions in any one subprocess. All child calls share a
three-second enclosing deadline and a minimal environment; timeout, malformed
output or failed execution produces `status: unknown`, never a fidelity pass.

Try a deliberately wrong model:

```sh
python3 .agents/skills/technical-recon/examples/trial.py --run-owned-fixture --inject-drift
```

It allows over-reservation. The report must be unverified with named divergent
transition cases and exit nonzero. This control need not change the policy's
actions, because the policy itself never deliberately over-reserves.

To falsify the reactive comparison specifically:

```sh
python3 .agents/skills/technical-recon/examples/trial.py --run-owned-fixture --inject-observation-drift
```

This model still rejects over-reservation, but falsely observes one free slot
when full. For seed 7 the authority chooses reserve(6), release(6), reserve(6),
release(6); the model chooses reserve(6), reserve(1), reserve(1), reserve(1).
`held-out-agent-actions` and `held-out-agent-outputs` must be mismatches, with
`verified: false` and exit 1. The fixed transition cases remain independently
reported and are unaffected by this observation-only control. This negative control tests the comparison oracle, not
an alternate deployable behavior. The scripts only launch the bundled fixture;
they are not general process launchers, hardened parsers or an OS sandbox.

For a real project, replace the example with an authorized target adapter,
record scope and source/trace identities, select held-out cases independently,
and declare any normalization/tolerances and unmodeled dynamics. Follow
[the contract reference](../references/contract.md), then use
[experiment-lab](../../experiment-lab/SKILL.md) for measured fidelity and tuning.
Matching this toy does not establish target parity or real-environment gains.
