# Adding a capability

<!-- index: extend | How to add, find, or switch off a capability or pack, and the configuration policy | You add, find, or switch off a skill, role, doc, rule, check, command, MCP route, or pack. -->
<!-- covers: tools/kit/capabilities.py tools/kit/scaffold.py tools/kit/config.py -->

Skills, agent roles, docs, rules, checks, commands, MCP routes, and packs are
all capabilities: one file each, read by one loader
(`tools/kit/registry.py`). Adding the file adds the capability; nothing is
registered by hand. What each file declares (the fields and carriers) is the
model decided in [ADR 0002](./adr/0002-one-capability-model.md); this page is
how the kit works with them.

`make similar Q="<need>"` answers first, across every kind and pack; the
reuse-or-create thresholds are owned by [`skills.md`](./skills.md).
`make new KIND=skill|agent|doc|rule|check|command|mcp|pack NAME=<kebab> DESC="<what>; <when>" [PACK=<pack>]`
is the one way to add one. It refuses a near-duplicate of the same kind
(`FORCE=1` overrides), writes valid metadata, registers a first-party skill in
`[capabilities].local_skills`, regenerates every derived file, and leaves
`FILL-IN:` lines for the content. Refining a capability is an ordinary edit of
its file; the after-edit hook regenerates what depends on it.
Agent-instruction paths are `high` risk, so changes to them get a critic.

| Kind | What the kit does with it |
|---|---|
| rule | no scope: one line in `AGENTS.md`; scoped: the after-edit hook delivers it once per session when a matching path is edited, and `make where <path>` lists it |
| check | runs in `make check` and the gates when it blocks, in `make garden` otherwise; a blocking check without a reason fails to load (the blocking rule in [`self-healing.md`](./self-healing.md#when-a-check-may-block)) |
| command | becomes `repoctl <name>` and, after `make sync`, `make <name> X=...`; make variables reach it as quoted data |
| mcp | rendered into host config when enabled (see [`resources.md`](./resources.md)) |
| pack | groups capabilities; `project.toml [packs]` overrides the pack's declared default |

A check is a function of a context (`root`, `project`, `files`, `bindings`)
that returns findings, each naming its fix. Kit checks live in
`tools/kit/checks.py` and kit commands in `tools/kit/commands.py`; a project's
own go in `.agents/`, so `make kit-update` never conflicts with them.

**Packs** keep rarely needed capabilities out of every session.
`project.toml [packs]` maps a pack name to `true` or `false` and overrides that pack's
declared `default` (`on` or `off` in `.agents/packs/<name>.md`). A pack that is
off contributes no host stubs, no `AGENTS.md` rule lines, no running checks,
and no `make help` lines, and its commands refuse with the line that switches
it on; it still appears in `make capabilities`, `make where`, and
`make similar`. The kit ships `product` (on: the product driver in
[`building.md`](./building.md)) and `measure` (off: `make eval`, `make trial`;
the template switches it on). A third-party skill, whose files are pinned by
digest, records its pack in its `[[skills]]` provenance entry.

## Configuration

Policy a project may change lives in `project.toml`, with built-in defaults
when a key is absent: `[packs]` (switch packs on or off), `[kit]` (docs index groups, unbound-doc exemptions,
overlap limit, deprecation warning window, skill review age, UI project kinds,
eval model, Playwright version, previewable kinds for `make ui-review`, and
`project_mode` — `"new"`, or `"adopt"` for a repository that already had a
product, which `make adopt` records), `[adapters.claude]`
(tier-to-model and access-to-tools maps, pre-approved commands), `[risk]`
(tier globs and optional ceremony text), and `[checks.<name>]` (downgrade one blocking check to
`severity = "advisory"` with a required `reason`; rules in
[downgrading a check](#downgrading-a-check)), and `[budgets]` (byte limits for any
glob, including product code). `[budgets]` keeps the files agents load often
within a byte limit (about 4 bytes per token); an over-budget file is reported
by `make check` and `make garden` (advisory), so detail belongs in a linked owner document, not in the router.

### Downgrading a check

A check that misfires in one repository is made advisory in `project.toml`, not
edited out of the kit (so `make kit-update` still applies):

```toml
[checks.dead-bindings]
severity = "advisory"
reason = "docs cover build output that exists only in CI"
```

The check still runs and its findings print as advisory (`make check`,
`make garden`); `make capabilities` and `make garden` list every downgrade with
its reason. `advisory` is the only accepted value, the reason is required, an
unknown or already-advisory check name is an error, and nothing removes or skips
a check. Deleting the entry restores blocking. Blocking rules:
[`self-healing.md`](./self-healing.md#when-a-check-may-block).

### Exempting one path from file-hygiene

`file-hygiene` blocks a tracked `.env*`, key file, or a literal credential. An
app repository that handles tokens, ships a test key fixture, or commits a
public `.env.production` (a publishable key) exempts those paths without
downgrading the whole check:

```toml
[checks.file-hygiene]
allow_paths = [
  { glob = "site/.env.production", reason = "publishable Clerk key, public by design" },
  { glob = "tests/fixtures/*.pem", reason = "throwaway key for signature tests" },
]
```

A `reason` (10+ characters) is mandatory and an entry without one is a
configuration error that stops `make check`; so is a glob such as `**` that
exempts everything, or any key other than `glob` and `reason`. A matching file is
skipped for the `.env`, key-file, and content findings only (a symlink that
escapes the repository is never exemptable) and is listed by the advisory
`file-hygiene-allowed` check with its reason, so the exemption stays visible; a
glob that matches no file is listed too, to be deleted. `allow_paths` does not
downgrade the check, and it can be combined with `severity = "advisory"` only
when the whole check really misfires. The content scan itself flags a credential
only when a secret-looking literal is assigned (`api_key = "k3y9..."`, an
`API_TOKEN=...` line, an `Authorization: Bearer <literal>` header), private key
blocks, and known token formats; code that reads `token` from a variable or the
environment, or builds `Authorization: Bearer ${token}`, is not a finding. See
[`security.md`](./security.md#secure-defaults).
