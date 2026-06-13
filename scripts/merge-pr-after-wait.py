#!/usr/bin/env python3
"""
Try to merge a PR, waiting for GitHub to recalculate merge status
"""
import subprocess
import time
import sys

GH_PATH = "/opt/homebrew/bin/gh"
REPO_PATH = "/Users/rkamalapuram/git-personal/.github-workflows-shared"

def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=REPO_PATH
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def try_merge_pr(pr_number, max_attempts=5):
    """Try to merge a PR, retrying if base branch changed"""
    for attempt in range(1, max_attempts + 1):
        print(f"\nAttempt {attempt}/{max_attempts} to merge PR #{pr_number}...")
        
        # Wait a bit for GitHub to recalculate
        if attempt > 1:
            print(f"  Waiting 10 seconds for GitHub to recalculate...")
            time.sleep(10)
        
        stdout, stderr, code = run_cmd(f"{GH_PATH} pr merge {pr_number} --squash")
        
        if code == 0:
            print(f"✅ Successfully merged PR #{pr_number}!")
            return True
        elif "Base branch was modified" in stderr:
            print(f"  ⚠️  Base branch modified, retrying...")
            continue
        elif "Pull Request is not mergeable" in stderr:
            print(f"  ⚠️  PR not mergeable yet, retrying...")
            continue
        else:
            print(f"  ❌ Failed: {stderr}")
            return False
    
    print(f"❌ Failed to merge PR #{pr_number} after {max_attempts} attempts")
    return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 merge-pr-after-wait.py <pr_number>")
        sys.exit(1)
    
    pr_num = int(sys.argv[1])
    success = try_merge_pr(pr_num)
    sys.exit(0 if success else 1)
