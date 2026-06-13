#!/usr/bin/env python3
"""
Fix remaining PRs and merge them
"""
import subprocess
import sys

GH_PATH = "/opt/homebrew/bin/gh"

def run_command(cmd):
    """Run command and return result"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd="/Users/rkamalapuram/git-personal/.github-workflows-shared"
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def main():
    print("=" * 80)
    print("FIXING REMAINING PRS")
    print("=" * 80)
    
    # Fix PR #52 title
    print("\n[1/2] Updating PR #52 title...")
    stdout, stderr, code = run_command(
        f'{GH_PATH} pr edit 52 --title "refactor: upgrade Saturn Console dashboard styling and logs visualizer"'
    )
    if code == 0:
        print("✅ Updated PR #52 title")
    else:
        print(f"❌ Failed to update PR #52 title: {stderr}")
    
    # Try to merge all fixed PRs
    print("\n[2/2] Merging fixed PRs...")
    fixed_prs = [59, 56, 50, 49, 52]
    
    merged = []
    failed = []
    
    for pr in fixed_prs:
        print(f"\n  Merging PR #{pr}...")
        stdout, stderr, code = run_command(f'{GH_PATH} pr merge {pr} --squash')
        if code == 0:
            print(f"  ✅ Merged PR #{pr}")
            merged.append(pr)
        else:
            print(f"  ❌ Failed: {stderr}")
            failed.append(pr)
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Merged: {merged}")
    print(f"❌ Failed: {failed}")
    
    # Show remaining open PRs
    print("\nRemaining open PRs:")
    stdout, stderr, code = run_command(f'{GH_PATH} pr list --state open --json number,title')
    if code == 0:
        import json
        try:
            prs = json.loads(stdout)
            for pr in prs:
                print(f"  PR #{pr['number']}: {pr['title']}")
        except:
            print(stdout)

if __name__ == '__main__':
    main()
