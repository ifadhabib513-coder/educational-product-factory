#!/usr/bin/env bash
# Ralph Autonomous Development Loop for POSIX / Bash / WSL
set -euo pipefail

MAX_ITERATIONS="${1:-10}"
AGENT_COMMAND="${2:-opencode run --auto}"
PROMPT_FILE="${3:-PROMPT.md}"
TASKS_FILE="${4:-tasks.md}"

echo "=========================================================="
echo "               RALPH AUTONOMOUS CODING LOOP               "
echo "=========================================================="
echo "Target Tasks:    $TASKS_FILE"
echo "Prompt File:     $PROMPT_FILE"
echo "Agent Command:   $AGENT_COMMAND"
echo "Max Iterations:  $MAX_ITERATIONS"
echo "=========================================================="

if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "Error: Prompt file '$PROMPT_FILE' not found!" >&2
    exit 1
fi

if [[ ! -f "$TASKS_FILE" ]]; then
    echo "Error: Tasks file '$TASKS_FILE' not found!" >&2
    exit 1
fi

PROMPT_CONTENT=$(cat "$PROMPT_FILE")

for ((i=1; i<=MAX_ITERATIONS; i++)); do
    echo -e "\n>>> [Iteration $i of $MAX_ITERATIONS] Starting Ralph Cycle..."

    # Find the first incomplete task
    FIRST_TASK=$(grep -m 1 -E '^\s*-\s*\[\s*\]' "$TASKS_FILE" || true)

    if [[ -z "$FIRST_TASK" ]]; then
        echo -e "\nAll tasks in $TASKS_FILE are completed! Exiting loop."
        break
    fi

    echo "Next backlog item: $FIRST_TASK"

    ITERATION_PROMPT=$(cat <<EOF
$PROMPT_CONTENT

---
Current Ralph Loop Iteration: $i of $MAX_ITERATIONS.
Selected Target Task: $FIRST_TASK
Please execute this task thoroughly, verify tests, update tasks.md, log in PROGRESS.md, and commit.
EOF
)

    echo "Invoking agent with fresh context..."
    OUTPUT=$($AGENT_COMMAND "$ITERATION_PROMPT" 2>&1 || true)
    echo "$OUTPUT"

    if echo "$OUTPUT" | grep -q "<<<RALPH_ALL_TASKS_COMPLETED>>>"; then
        echo -e "\nSignal received: <<<RALPH_ALL_TASKS_COMPLETED>>>. Halting loop."
        break
    fi

    if [[ -n $(git status --porcelain) ]]; then
        echo "Notice: Uncommitted changes detected after iteration $i. Check git diff."
    else
        echo "Git working tree clean. Iteration $i committed successfully."
    fi

    sleep 2
done

echo -e "\n=========================================================="
echo "               RALPH LOOP FINISHED                        "
echo "=========================================================="
