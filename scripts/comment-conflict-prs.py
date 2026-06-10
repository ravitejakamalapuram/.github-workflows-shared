#!/usr/bin/env python3
"""
Comment on PRs with merge conflicts
"""
import subprocess

def run_gh_command(args):
    """Run gh CLI command"""
    gh_path = "/opt/homebrew/bin/gh"
    result = subprocess.run(
        [gh_path] + args,
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def comment_on_conflict_pr(pr_number):
    """Add a comment about merge conflicts"""
    comment = f"""## ⚠️ Merge Conflicts Detected

This PR has merge conflicts that need to be resolved before it can be merged.

### How to Resolve:

1. **Pull the latest main branch:**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Merge main into your branch:**
   ```bash
   git checkout <your-branch>
   git merge main
   ```

3. **Resolve conflicts:**
   - Open the conflicted files
   - Look for conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
   - Choose which changes to keep
   - Remove the conflict markers

4. **Commit and push:**
   ```bash
   git add .
   git commit -m "fix: resolve merge conflicts"
   git push origin <your-branch>
   ```

Once the conflicts are resolved and all checks pass, this PR can be merged.

---
*Automated review by PR Review Bot*"""
    
    stdout, stderr, code = run_gh_command([
        'pr', 'comment', str(pr_number),
        '--body', comment
    ])
    
    if code == 0:
        print(f"✅ Commented on PR #{pr_number} about merge conflicts")
        return True
    else:
        print(f"❌ Failed to comment on PR #{pr_number}: {stderr}")
        return False

# PRs with merge conflicts from the previous run
conflict_prs = [60, 55, 54, 51, 48]

print("Adding merge conflict comments to remaining PRs...")
for pr in conflict_prs:
    comment_on_conflict_pr(pr)

print(f"\n✅ Done! Commented on {len(conflict_prs)} PRs with merge conflicts.")
