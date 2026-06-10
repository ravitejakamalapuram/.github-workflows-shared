#!/bin/bash

# Fix remaining PRs - Update PR titles and try to merge

GH=/opt/homebrew/bin/gh

echo "=========================================="
echo "Fixing PR #52 - Updating title"
echo "=========================================="
$GH pr edit 52 --title "refactor: upgrade Saturn Console dashboard styling and logs visualizer"

echo ""
echo "=========================================="
echo "Now let's try to merge all fixed PRs"
echo "=========================================="

# List of PRs that should now be ready (commit messages fixed)
FIXED_PRS="59 56 50 49"

for pr in $FIXED_PRS; do
    echo ""
    echo "Attempting to merge PR #$pr..."
    $GH pr merge $pr --squash 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Successfully merged PR #$pr"
    else
        echo "❌ Failed to merge PR #$pr"
    fi
done

echo ""
echo "=========================================="
echo "Attempting to merge PR #52 (title fixed)"
echo "=========================================="
$GH pr merge 52 --squash 2>&1

echo ""
echo "Done! Checking remaining open PRs..."
$GH pr list --state open --json number,title

