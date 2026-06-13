#!/usr/bin/env python3
"""
Auto-merge PRs that pass standards and comment on those that don't
"""
import json
import subprocess
import sys

class PRMerger:
    def __init__(self):
        self.gh_path = "/opt/homebrew/bin/gh"
        
    def run_gh_command(self, args):
        """Run gh CLI command"""
        result = subprocess.run(
            [self.gh_path] + args,
            capture_output=True,
            text=True
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    
    def merge_pr(self, pr_number):
        """Merge a PR using squash merge"""
        print(f"\n✅ Merging PR #{pr_number}...")
        stdout, stderr, code = self.run_gh_command([
            'pr', 'merge', str(pr_number),
            '--squash'
        ])
        if code == 0:
            print(f"   Successfully merged PR #{pr_number}")
            return True
        else:
            print(f"   Failed to merge PR #{pr_number}: {stderr}")
            return False
    
    def comment_on_pr(self, pr_number, issues):
        """Add a review comment to a PR"""
        print(f"\n❌ Adding review comment to PR #{pr_number}...")
        
        comment = "## 🔍 PR Review - Issues Found\n\n"
        comment += "This PR cannot be merged yet because the following issues were detected:\n\n"
        
        for i, issue in enumerate(issues, 1):
            comment += f"{i}. {issue}\n"
        
        comment += "\n### 📋 Project Standards\n\n"
        comment += "Please ensure your PR follows these requirements:\n\n"
        comment += "- **Commit Messages**: Must follow [Conventional Commits](https://www.conventionalcommits.org/) format:\n"
        comment += "  - `feat:` - New feature\n"
        comment += "  - `fix:` - Bug fix\n"
        comment += "  - `docs:` - Documentation only\n"
        comment += "  - `style:` - Code style (formatting)\n"
        comment += "  - `refactor:` - Code refactoring\n"
        comment += "  - `test:` - Adding tests\n"
        comment += "  - `chore:` - Maintenance tasks\n"
        comment += "  - Or emoji prefixes: 🎨, ⚡, 🛡️\n\n"
        comment += "- **No Secrets**: No hardcoded passwords, API keys, tokens, or credentials\n"
        comment += "- **Documentation**: Update README.md when adding new actions\n"
        comment += "- **Testing**: All automated checks must pass\n\n"
        comment += "Please fix these issues and the PR will be re-reviewed.\n\n"
        comment += "---\n*Automated review by PR Review Bot*"
        
        stdout, stderr, code = self.run_gh_command([
            'pr', 'comment', str(pr_number),
            '--body', comment
        ])
        
        if code == 0:
            print(f"   Successfully commented on PR #{pr_number}")
            return True
        else:
            print(f"   Failed to comment on PR #{pr_number}: {stderr}")
            return False
    
    def close_empty_pr(self, pr_number):
        """Close PRs with no file changes"""
        print(f"\n🗑️  Closing empty PR #{pr_number}...")
        
        comment = "## 🚫 Closing Empty PR\n\n"
        comment += "This PR has no file changes and appears to be created in error. Closing automatically.\n\n"
        comment += "If this was a mistake, please feel free to reopen with actual changes.\n\n"
        comment += "---\n*Automated action by PR Review Bot*"
        
        # Add comment first
        self.run_gh_command([
            'pr', 'comment', str(pr_number),
            '--body', comment
        ])
        
        # Close the PR
        stdout, stderr, code = self.run_gh_command([
            'pr', 'close', str(pr_number)
        ])
        
        if code == 0:
            print(f"   Successfully closed PR #{pr_number}")
            return True
        else:
            print(f"   Failed to close PR #{pr_number}: {stderr}")
            return False

def main():
    # Load review results
    try:
        with open('pr-review-results.json', 'r') as f:
            results = json.load(f)
    except FileNotFoundError:
        print("Error: pr-review-results.json not found. Run review-prs.py first.")
        sys.exit(1)
    
    merger = PRMerger()
    
    print("="*80)
    print("AUTO-MERGE & COMMENT PROCESS")
    print("="*80)
    
    merged_count = 0
    commented_count = 0
    closed_count = 0
    
    for pr_number, result in results.items():
        pr_data = result['data']
        issues = result['issues']
        can_merge = result['can_merge']
        
        # Check if PR has no file changes (empty PR)
        if len(pr_data.get('files', [])) == 0:
            if merger.close_empty_pr(int(pr_number)):
                closed_count += 1
            continue
        
        if can_merge:
            if merger.merge_pr(int(pr_number)):
                merged_count += 1
        else:
            if merger.comment_on_pr(int(pr_number), issues):
                commented_count += 1
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"✅ Merged: {merged_count} PRs")
    print(f"💬 Commented: {commented_count} PRs")
    print(f"🗑️  Closed (empty): {closed_count} PRs")
    print(f"📊 Total processed: {len(results)} PRs")

if __name__ == '__main__':
    main()
