# Measuring the kit: fresh-agent evals and build trials

<!-- index: extend | Fresh-agent navigation evals and scored build trials | AGENTS.md, the docs, a skill, or a gate changed and needs fresh-agent evidence. -->
<!-- covers: tools/kit/evals.py tools/kit/trial.py .agents/evals/** .agents/trials/** -->

`.agents/evals/*.toml` holds navigation tasks with an expected-answer regex.
`make eval AGENT=claude` (or `codex`, `gemini`; `MODEL=` overrides, and Claude
defaults to the cheap `[kit].eval_model`, Haiku) runs each task in a fresh,
read-only headless session that cannot read `.agents/evals/` (its own answer key;
expectations are anchored regexes that reject negated answers) and has no MCP
servers, so runs stay fast and deterministic and records pass rate, turns, time, and cost under
`.agent/evals/`. Re-run it after changing `AGENTS.md`, the map, or the docs.
A change to the kit that lowers the pass rate or raises cost is a regression.

For changes to the skills or gates, also run a **build trial**:
`make trial NAME=<request>` copies this working tree into a fresh `make init`
project outside the repository (or, for `mode = "adopt"`, an existing codebase
from `seed` that then runs `make adopt`), gives `claude -p` (Sonnet by
default, `BUDGET=` caps spend) the owner's request from
`.agents/trials/<request>.toml`, and writes `.agent/trials/<run>/report.md`:
spend, turns, kit commands, every gate block, failed kit command, bypass, and
`Docs-Unaffected` trailer, and the product's final `make next` phase and
`make done` result. Judge each friction item with the blocking rule in
[`self-healing.md`](./self-healing.md#when-a-check-may-block): fix
the kit, make the check advisory, or justify it. `--analyze <transcript>
--project <dir>` reports on a run made by hand or with another host. Trial
evidence and friction findings are recorded as issues (e.g.,
[`#9`](https://github.com/TomSzenessy/AI_TEMPLATE/issues/9)), not on this page.

A host-side failure, such as an expired login, is recorded as an error rather
than as a wrong answer. Evals and trials start agents through one launcher
(`run_headless` in `tools/kit/evals.py`): it drops the launching session's host
variables, so a benchmark started from inside an agent session uses the CLI's
own login, as a truly fresh agent would, and it ignores `SIGTERM` while the
agent runs, because agents clean up with `pkill -f <name>`. Both commands
belong to the `measure` pack.
