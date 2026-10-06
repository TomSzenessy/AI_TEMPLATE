# Project Context

This glossary gives agents and designers shared language for an evolving
product. It defines meaning, not implementation or task status.

## Language

**Project**: a versioned product or creative work with a declared purpose and
quality bar.
_Avoid_: codebase when the product is not primarily code.

**Surface**: an independently owned and verifiable part of a project, such as a
web app, game runtime, render pipeline, data set, or public service.
_Avoid_: component when the unit of ownership and verification is meant.

**Module**: an implementation behind a small interface that hides complexity
and concentrates change.
_Avoid_: layer, component, or service when no interface is intended.

**Interface**: the complete knowledge a caller needs: inputs, outputs,
invariants, ordering, configuration, failure modes, and performance promises.
_Avoid_: signature when only the type-level surface is meant.

**Seam**: the location where an interface can be changed or an adapter chosen.
_Avoid_: boundary when the location of substitution is meant.

**Source of truth**: the one authoritative home for a changing fact; code or
configuration may own executable truth, while a document may own rationale.
_Avoid_: source, reference, or documentation without naming the owner.

**Quality oracle**: the independent, observable test or review that decides
whether a surface meets its declared bar.
_Avoid_: “looks good”, “works”, or “perfect” without an oracle.

**Regression record**: a durable test or incident artifact that demonstrates a
failure and prevents its return.
_Avoid_: log entry, screenshot, or issue without reproducible evidence.

**Write-ahead record**: the issue-backed intent, scope, and acceptance boundary
written before a change and reconciled with evidence afterward.
_Avoid_: permanent agent event log or duplicate task document.

**Handover**: a focused continuation record for a fresh actor, containing only
state and evidence that cannot be reconstructed from committed artifacts.
_Avoid_: full conversation transcript.

**Launch gate**: an external or operational condition that blocks a release
until named evidence exists.
_Avoid_: TODO, best effort, or “ready”.

**Skill**: a reviewed, versioned instruction package with a clear capability,
provenance, and safe invocation contract.
_Avoid_: prompt dump, untrusted script, or popular add-on.

**Binding**: a document's `<!-- covers: -->` declaration of the paths whose
behavior it explains; it makes the document checkable against the code.
_Avoid_: "related docs" or a manual cross-reference list.

**Adapter**: a generated, content-free host file (for example under `.claude/`)
that redirects a specific agent host to the canonical `.agents/` source.
_Avoid_: copying skill or role text into a host directory.

**Role**: a host-neutral subagent definition with an access boundary, a model
tier, and a fixed report format, used by the orchestrator for bounded work.
_Avoid_: persona or ad-hoc prompt.

## Resolution rule

When a term is ambiguous, choose one canonical word here and link the old term
to it in the relevant design note. Do not make two words carry the same concept.
