---
name: pitch-from-evidence
description: "Build a presentation, pitch, demo script, or report whose every number and claim has a source; preparing a talk, stakeholder update, investor or grant pitch, release note, paper, or results write-up"
---

# Pitch from evidence

Outcome: a pitch, demo script, or results write-up in which every number and
claim can be traced to a file, a run, or a commit, and every weakness has an
honest answer ready. Load this before preparing a talk, a demo, a stakeholder
or client update, an investor or grant pitch, release notes, or a results
report. The evidence rules live in
[`docs/verification.md`](../../../docs/verification.md); this skill is the order
of work.

## Steps

1. **Audience and format.** Write down who reads or listens, what they decide
   or care about, and the time or length available. The order follows from
   what they need first, not from the order the work was done in.
2. **Claim table first, slides second.** List every claim with its source:
   a file and line, a recorded run, or a commit. A number with no source is
   cut or marked as an estimate. Opinions are labelled as opinions.
3. **Attribute gains.** When showing improvement, name which step moved the
   number and by how much, measured the same way (one attempt against one
   attempt; [`experiments.md`](../../../docs/experiments.md#1-the-objective-exactly)).
4. **Caveats and questions.** Write the weaknesses a skeptic would raise and an
   honest answer to each, plus the likely questions with short answers.
5. **Do-not-claim list.** Write what the work does not show (untested cases,
   proxies, results of others) so nobody says it under pressure.
6. **Recount last.** Re-read every live number (scores, counts, dates) from its
   source right before presenting; numbers drift while work continues.

## Done when

- Every number in the deliverable appears in the claim table with a source
  that a teammate re-checked, and the caveat, question, and do-not-claim lists
  exist next to it.
