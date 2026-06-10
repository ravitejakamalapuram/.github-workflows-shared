#!/usr/bin/env python3
"""
Rebase all PRs with conflicts to latest main
"""
import subprocess
import sys

GH_PATH = "/opt/homebrew/bin/gh"
REPO_PATH = "/Users/rkamalapuram/git-personal/.github-workflows-shared"

# PRs with merge conflicts and their branches
PRS_TO_REBASE = {
    56: "bolt-perf-js-syntax-check-121294076317037074",
    50: "palette-async-loading-spinners-11514664733346711547",
    49: "sentinel-fix-command-injection-validate-12648842882873609398",
    52: "feature/saturn-console-design-upgrades",
    60: "bolt-perf-jq-empty-batch-18333086668620136075",
    55: "palette-aria-disabled-tooltips-13444186981148953776",
    54: "palette-disabled-button-tooltip-4657474405725869901",
    51: "feature/centralized-app-registry-dashboard",
    48: "palette/accessible-disabled-tooltips-8328076913819324615"
}

def run_git(cmd):
    """Run git command"""
    full_cmd = f"cd {REPO_PATH} && {cmd}"
    result = subprocess.run(
        full_cmd,
        shell=True,
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def rebase_pr(pr_number, branch):
    """Rebase a PR branch onto main"""
    print(f"\n{'='*80}")
    print(f"Rebasing PR #{pr_number} ({branch})")
    print(f"{'='*80}")
    
    # Fetch latest
    print("  Fetching latest...")
    run_git("git fetch origin")
    
    # Checkout main and pull
    print("  Updating main...")
    run_git("git checkout main")
    run_git("git pull origin main")
    
    # Checkout PR branch
    print(f"  Checking out {branch}...")
    stdout, stderr, code = run_git(f"git checkout {branch}")
    if code != 0:
        print(f"  ❌ Failed to checkout: {stderr}")
        return False
    
    # Try to rebase
    print("  Rebasing onto main...")
    stdout, stderr, code = run_git("git rebase origin/main")
    
    if code == 0:
        print("  ✅ Rebase successful!")
        
        # Force push
        print("  Force pushing...")
        stdout, stderr, code = run_git(f"git push --force origin {branch}")
        if code == 0:
            print("  ✅ Force push successful!")
            return True
        else:
            print(f"  ❌ Force push failed: {stderr}")
            return False
    else:
        print(f"  ⚠️  Rebase has conflicts:")
        print(f"     {stderr}")
        
        # Abort rebase
        run_git("git rebase --abort")
        print("  ⚠️  Rebase aborted - manual intervention needed")
        return False

def main():
    print("=" * 80)
    print("REBASING ALL PRS WITH CONFLICTS")
    print("=" * 80)
    
    successful = []
    failed = []
    
    for pr_number, branch in PRS_TO_REBASE.items():
        success = rebase_pr(pr_number, branch)
        if success:
            successful.append(pr_number)
        else:
            failed.append(pr_number)
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully rebased: {successful}")
    print(f"❌ Failed (need manual fix): {failed}")
    
    # Go back to main
    run_git("git checkout main")

if __name__ == '__main__':
    main()
