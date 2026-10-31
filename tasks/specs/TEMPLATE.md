# <task id> — <short title>

> Spec for a development or fix task. One file per task, named `<task id>.md` (e.g.
> `t1040.md`). The task itself lives in the task log (`tasks/store.py`); this file carries the
> description and the test cases the owner asked every task to have (2026-10-31). Commits for
> the task reference its id.

## Problem / goal

What is wrong or what is being added, and why. For a fix: the concrete failure — given these
inputs or this state, this wrong thing happens. For a feature: what it must do.

## Test cases

The behaviour that proves the task is done. Each becomes a real test under `tests/`.

- **TC1 —** given … when … then … (for a fix: this is the regression test, it fails before
  the change and passes after)
- **TC2 —** …
- **TC3 — edge:** …

## Approach

How it is solved, briefly. What was deliberately left out of scope.

## Done when

- [ ] test cases above written under `tests/test_<area>.py` and passing
- [ ] `./.venv-voice/bin/pytest` green
- [ ] committed referencing the task id
