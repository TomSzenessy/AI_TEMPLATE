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
predictions, one training case, four held-out cases, a four-action agent policy,
reset/replay and divergence results. `verified: true` applies only to those
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
The model obtains capacity from the reset observation, not private state.
This is a source/observation-informed hand-written model, not automatic learning.

The small policy alternates reserving all observed available capacity and
releasing all used capacity. The same actions run through the authority and
model; held-out cases also exercise sequence, seed and malformed-action edges.
The authority adapter resets by starting a fresh fixture process. All child
calls share a three-second enclosing deadline; timeout, malformed output or
failed execution produces `status: unknown`, never a fidelity pass.

Try a deliberately wrong model:

```sh
python3 .agents/skills/technical-recon/examples/trial.py --run-owned-fixture --inject-drift
```

It allows over-reservation. The report must be unverified with named divergent
cases and exit nonzero. This negative control tests the comparison oracle, not
an alternate deployable behavior. The scripts only launch the bundled fixture;
they are not general process launchers, hardened parsers or an OS sandbox.

For a real project, replace the example with an authorized target adapter,
record scope and source/trace identities, select held-out cases independently,
and declare any normalization/tolerances and unmodeled dynamics. Follow
[the contract reference](../references/contract.md), then use
[experiment-lab](../../experiment-lab/SKILL.md) for measured fidelity and tuning.
Matching this toy does not establish target parity or real-environment gains.
