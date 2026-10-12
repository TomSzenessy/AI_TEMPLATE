# Behavior contract and handoff

Recover one agent-critical workflow, not an entire product. Fill this in from
observations; an empty field is **unknown**, not a default you invented.

| Contract field | Required evidence |
|---|---|
| Scope | Target/version/digest, authorization basis, allowed actions/artifacts, runtime/network bounds, retention and budget |
| Questions | Each claim's distinguishing probe, supporting/contradicting trace IDs, coverage and status |
| Input/action | Names, schema/types, valid choices, boundaries and action preconditions |
| Observation | Visible output/schema, normalization/tolerances fixed before comparison, hidden state that stays unknown |
| State | Initial state, persistence, transitions and which actions change it |
| Reset/seed | Reproducible setup and nondeterministic sources; if real reset is unavailable, say so rather than mutating a live account |
| Errors | Rejection vs transport failure vs timeout, side effects and retry/idempotency behavior |
| Environment | External dependencies, permissions, timing, concurrency and resource caps |
| Reconstruction | Independent implementation, deliberate simplifications, unmodeled dynamics and adapter boundary |
| Validation | Training vs held-out sequences, repeated reset/replay, same-agent comparison, drift/failure control and residual unknowns |

For an environment adapter, separate deterministic `reset(seed)`, `observe()` and
`step(action)` from the agent's policy. `step` returns the observed result plus
state/termination information actually supported by the target. Rewards are
optional and come from the task's objective, not an invented target property.
Use real isolation for executable targets; this interface is not a sandbox.

Start with an observation baseline and one changed factor. Keep probe order and
state transitions in the trace so a later action is not mistaken for an isolated
function call. Preserve original observations locally where allowed; document
any redaction/normalization and its effect on comparability. For stochastic
behavior declare tolerances and confidence instead of claiming exact replay.

A comparison report names the target and model identities, cases and comparable
fields, divergence locations, rejected/invalid actions, reset/seed replay result,
timeouts and unknown coverage. Include one deliberately wrong model or altered
trace to show the oracle detects drift. Passing only the observed training
sequences is insufficient; finite matching cases do not establish universal
parity. Hand this report and the contract to
[experiment-lab](../../experiment-lab/SKILL.md) for the measured improvement loop.
Do not promote a simulator-only gain as a confirmed real-environment gain.
