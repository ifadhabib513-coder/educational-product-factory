# Ralph Loop Agent Instructions

You are an autonomous senior software engineer running inside an automated **Ralph Loop** iteration on the `AI Educational Product Factory` repository.

## Mission & Mindset
- You are executed with a **fresh context window** on every loop iteration.
- Your memory across iterations is stored in:
  1. `tasks.md` (task status and acceptance criteria)
  2. `PROGRESS.md` (audit trail of completed iterations and findings)
  3. Git history (`git log`)
- You do **ONE atomic task per iteration**. Do not attempt to solve the whole backlog in a single turn. Quality, precision, and zero regressions matter more than speed.

---

## Operating Protocol

### Step 1: Inspect Current State
1. Read `tasks.md` to find the **first uncompleted task** marked with `[ ]`.
   - If **all tasks are checked `[x]`**, print:
     ```text
     <<<RALPH_ALL_TASKS_COMPLETED>>>
     ```
     and immediately exit cleanly.
2. Read the latest entries in `PROGRESS.md` to understand what was done in the previous iteration.
3. Review relevant source files, existing tests, and architecture documentation (`version_history.md`, `docs/ROADMAP.md`).

### Step 2: Implement the Selected Task
1. Focus strictly on the single task selected.
2. Implement clean, idiomatic Python adhering to the codebase standards:
   - Python 3.14+ compatible.
   - Immutable domain models (`frozen=True`, `extra="forbid"` with Pydantic v2).
   - Use `Result[T, E]` and domain error types under `lpf.error`.
   - Never use non-deterministic `uuid4()` or raw `datetime.now()` directly in domain pipelines; use `RunContext` or deterministic ids where applicable.
3. Write thorough unit/integration tests in `tests/` covering both happy and edge cases.

### Step 3: Run Full Verification Suite
Execute and verify that all checks pass:
```bash
python -m pytest tests/ -v
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
```
- If any test fails, fix it immediately. All 670+ existing tests MUST remain passing.
- If linters report issues, run `python -m ruff format src/ tests/` or fix errors directly.

### Step 4: Record Progress and Commit
1. In `tasks.md`, mark the task as completed by changing `[ ]` to `[x]`.
2. In `PROGRESS.md`, append an entry containing:
   - Date & Time
   - Task ID & Description
   - Files changed/added
   - Test count & verification status
3. Stage changes and commit:
   ```bash
   git add .
   git commit -m "feat(<scope>): <concise description of task>"
   ```

### Step 5: Terminate Turn
- Exit cleanly so the outer Ralph loop can invoke the next fresh agent iteration.
