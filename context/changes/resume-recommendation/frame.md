# Frame Brief: Homepage Resume Recommendation

> Framing step before /10x-plan. This document separates the observed homepage gap
> from the initial idea for addressing it.

## Reported Observation

After login, the homepage shows the project list but does not recommend which project
to resume. The user wants one recommendation above the list, with changing encouraging
messages. If there is no unfinished work, the recommendation should show the last
changed project and encourage starting work.

## Initial Framing (preserved)

- **User's stated cause or approach:** Choose a project randomly, possibly using the
  last edited project as an alternative rule.
- **User's proposed direction:** Add one recommendation section above the project list
  on the signed-in homepage, with varied encouraging copy.
- **Pre-dispatch narrowing:** Only unfinished projects enter the random pool; when no
  work has been started, show the last changed project; the card opens a concrete
  element; changing on every refresh is acceptable if per-visit stability needs extra
  machinery.

## Dimension Map

The observation could originate at these dimensions:

1. **Progress signal** — the app may not know which projects have meaningful unfinished
   work or which element should be resumed.
2. **Candidate selection** — random selection may be motivating, but unrestricted random
   selection could surface a completed or irrelevant project.
3. **Action target** — a project can contain multiple elements, so a project-only link
   may not actually resume work.
4. **Recommendation lifecycle** — changing on refresh is simple but may feel unstable;
   keeping one choice per visit needs client/session state.

## Hypothesis Investigation

| Hypothesis | Evidence | Verdict |
| --- | --- | --- |
| Progress signal is absent | `RowState.state` has `in_progress`, `done`, and `not_started` in `app/models/progress.py:8-27`; element progress is already derived in `app/routes/projects.py:521-565`. | NONE |
| Unrestricted random selection is appropriate | The homepage currently only queries and orders projects by `Project.updated_at` in `app/main.py:47-67`; no recommendation pool exists. `updated_at` also changes for ordinary edits, so it is not a pure work signal. | WEAK |
| A concrete element target is needed | Projects can contain multiple elements; element rows and progress are rendered separately in `app/routes/projects.py:524-572`. The homepage currently links only to the project in `app/templates/index.html:33-43`. | STRONG |
| Per-visit stability is required | No existing session or recommendation state exists. Existing random or last-viewed behavior is not present for homepage recommendations. | NONE |

## Narrowing Signals

- The user chose one recommendation, not a list.
- The random pool is limited to started-but-unfinished projects; a project with no
  started row is handled by the last-changed fallback.
- The recommendation must open a concrete element.
- The user accepts changing the recommendation on each refresh if that is simpler.
- With no unfinished work, the fallback is the last changed project with encouraging
  copy to begin work.

## Cross-System Convention

The project already treats current progress as derived state: row status is authoritative
and repetition completion is computed from row states. `Project.updated_at` is suitable
for a recent-edit fallback, but the codebase documents no historical last-worked event.
An archived repeats decision chose last-viewed repetition for a different, per-element
navigation problem; the current homepage recommendation is a new user decision and
explicitly prioritizes unfinished work instead.

## Reframed (or Confirmed) Problem Statement

> **The actual problem to plan around is:** the signed-in homepage lacks an actionable,
> progress-aware starting point that takes the user directly to unfinished work.

The random message is a presentation choice, not the core problem. The core is selecting
an unfinished element safely and linking directly to it. Randomness should operate within
that meaningful candidate set; the recent-project fallback covers users who have not yet
started work or whose work is complete.

## Confidence

- **HIGH** — current progress and project timestamps are directly available, the homepage
  insertion point is clear, and the user resolved the key selection and fallback choices.

## What Changes for /10x-plan

The plan should define a homepage recommendation query/context that selects one concrete
element from a started-but-unfinished project, supplies varied copy, and falls back to
the most recently changed project when no such candidate exists. It should preserve
ownership filtering, handle empty/new projects, and avoid adding persistence unless
per-visit stability proves necessary.

## References

- Source files: `app/main.py:47-67`, `app/templates/index.html:26-45`,
  `app/models/project.py:7-44`, `app/models/progress.py:8-27`,
  `app/routes/projects.py:521-572`
- Related decision: `context/archive/2026-08-01-repeats-and-stitch-position/plan-brief.md:15-25`
- Investigation tasks: `ses_f98d3aabaffeBxTwLSeruMH7j3`, `ses_f98d3aa71ffeeo1Pun5E9Ylksj`
