#!/usr/bin/env python3
"""
PR Review Script - Checks PRs against project standards
"""
import json
import subprocess
import sys
import re
from pathlib import Path

class PRReviewer:
    def __init__(self):
        self.gh_path = "/opt/homebrew/bin/gh"
        self.standards = self.load_standards()
        
    def load_standards(self):
        """Load project standards for validation"""
        return {
            'commit_prefixes': ['feat:', 'fix:', 'docs:', 'style:', 'refactor:', 'test:', 'chore:', '🎨', '⚡', '🛡️'],
            'required_checks': [
                'validate-actions',
                'validate-workflows',
                'validate-scripts',
                'validate-configs',
                'validate-security'
            ]
        }
    
    def run_gh_command(self, args):
        """Run gh CLI command"""
        result = subprocess.run(
            [self.gh_path] + args,
            capture_output=True,
            text=True
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    
    def get_pr_details(self, pr_number):
        """Get detailed PR information"""
        stdout, stderr, code = self.run_gh_command([
            'pr', 'view', str(pr_number),
            '--json', 'number,title,body,commits,files,reviews,statusCheckRollup,isDraft,author'
        ])
        if code == 0:
            return json.loads(stdout)
        return None
    
    def check_title_format(self, title):
        """Check if title follows conventional commits"""
        issues = []
        valid_prefix = any(title.startswith(prefix) for prefix in self.standards['commit_prefixes'])
        if not valid_prefix:
            issues.append(f"Title should start with conventional commit prefix (feat:, fix:, docs:, etc.) or emoji prefix")
        return issues
    
    def check_commits(self, commits):
        """Check if commits follow conventions"""
        issues = []
        for commit in commits:
            message = commit.get('messageHeadline', '')
            valid = any(message.startswith(prefix) for prefix in self.standards['commit_prefixes'])
            if not valid:
                issues.append(f"Commit '{message[:50]}...' doesn't follow conventional commits")
        return issues
    
    def check_files_for_secrets(self, pr_number):
        """Check PR files for potential secrets"""
        stdout, stderr, code = self.run_gh_command([
            'pr', 'diff', str(pr_number)
        ])
        issues = []
        if code == 0:
            # Check for hardcoded passwords, tokens, keys
            dangerous_patterns = [
                (r'password\s*=\s*["\'][^$]', 'Potential hardcoded password'),
                (r'api[_-]?key\s*=\s*["\'][^$]', 'Potential hardcoded API key'),
                (r'secret\s*=\s*["\'][^$]', 'Potential hardcoded secret'),
                (r'token\s*=\s*["\'][^$]', 'Potential hardcoded token'),
            ]
            for pattern, message in dangerous_patterns:
                if re.search(pattern, stdout, re.IGNORECASE):
                    # Exclude lines with ${{ secrets.* }} or ${{ inputs.* }}
                    matches = re.finditer(pattern, stdout, re.IGNORECASE)
                    for match in matches:
                        context = stdout[max(0, match.start()-50):match.end()+50]
                        if '${{' not in context:
                            issues.append(message)
                            break
        return issues
    
    def check_status_checks(self, status_rollup):
        """Check if CI/CD checks passed"""
        issues = []
        if not status_rollup:
            issues.append("No status checks found - CI/CD might not have run")
            return issues
            
        for check in status_rollup:
            status = check.get('status')
            conclusion = check.get('conclusion')
            name = check.get('name', 'Unknown check')
            
            if status == 'COMPLETED' and conclusion != 'SUCCESS':
                issues.append(f"Check '{name}' failed with status: {conclusion}")
            elif status != 'COMPLETED':
                issues.append(f"Check '{name}' is still {status}")
        
        return issues
    
    def check_documentation(self, files):
        """Check if documentation is updated when needed"""
        issues = []
        has_code_changes = any(
            f['path'].endswith(('.yml', '.yaml', '.py', '.sh'))
            for f in files
        )
        has_readme_update = any(
            'README' in f['path'].upper()
            for f in files
        )
        
        # For new actions, README should be updated
        new_actions = [f for f in files if '/composite-actions/' in f['path'] and f.get('additions', 0) > f.get('deletions', 0)]
        if new_actions and not has_readme_update:
            issues.append("New composite action added but README.md not updated")
        
        return issues
    
    def review_pr(self, pr_number):
        """Review a single PR"""
        print(f"\n{'='*80}")
        print(f"Reviewing PR #{pr_number}")
        print(f"{'='*80}")
        
        pr_data = self.get_pr_details(pr_number)
        if not pr_data:
            return None, ["Failed to fetch PR details"]
        
        issues = []
        
        # Check title
        issues.extend(self.check_title_format(pr_data['title']))
        
        # Check commits
        if pr_data.get('commits'):
            issues.extend(self.check_commits(pr_data['commits']))
        
        # Check for secrets
        issues.extend(self.check_files_for_secrets(pr_number))
        
        # Check status checks
        if pr_data.get('statusCheckRollup'):
            issues.extend(self.check_status_checks(pr_data['statusCheckRollup']))
        
        # Check documentation
        if pr_data.get('files'):
            issues.extend(self.check_documentation(pr_data['files']))
        
        return pr_data, issues

def main():
    reviewer = PRReviewer()
    
    # Get all open PRs
    stdout, stderr, code = reviewer.run_gh_command([
        'pr', 'list', '--state', 'open', '--json', 'number', '--limit', '100'
    ])
    
    if code != 0:
        print(f"Error fetching PRs: {stderr}")
        sys.exit(1)
    
    prs = json.loads(stdout)
    print(f"Found {len(prs)} open PRs")
    
    results = {}
    for pr in prs:
        pr_number = pr['number']
        pr_data, issues = reviewer.review_pr(pr_number)
        results[pr_number] = {
            'data': pr_data,
            'issues': issues,
            'can_merge': len(issues) == 0
        }
    
    # Summary
    print(f"\n{'='*80}")
    print("REVIEW SUMMARY")
    print(f"{'='*80}")
    
    can_merge = [num for num, result in results.items() if result['can_merge']]
    needs_work = [num for num, result in results.items() if not result['can_merge']]
    
    print(f"\n✅ Can be merged ({len(can_merge)}): {can_merge}")
    print(f"\n❌ Needs work ({len(needs_work)}): {needs_work}")
    
    # Save results
    with open('pr-review-results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to pr-review-results.json")
    
    return results

if __name__ == '__main__':
    main()
