#!/usr/bin/env python3
"""
Automatically fix input interpolation in composite actions.
Reads YAML, finds ${{ inputs.* }} patterns, adds env blocks, and updates run scripts.
"""

import re
import sys
from pathlib import Path

def extract_inputs_from_run(run_content):
    """Extract all ${{ inputs.* }} references from a run script."""
    pattern = r'\$\{\{\s*inputs\.([a-zA-Z0-9_-]+)\s*\}\}'
    return set(re.findall(pattern, run_content))

def input_to_env_name(input_name):
    """Convert input-name to ENV_NAME."""
    return input_name.replace('-', '_').upper()

def fix_action_file_text(file_path):
    """
    Fix input interpolation using text manipulation.
    This preserves YAML formatting better than yaml.dump().
    """
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    modified = False
    i = 0
    new_lines = []
    
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        
        # Look for run: |
        if re.match(r'\s+-\s+name:.*', line):
            # Start of a step
            step_indent = len(line) - len(line.lstrip())
            step_start = i
            
            # Look for the run: | line in this step
            run_line_idx = None
            env_line_idx = None
            j = i + 1
            while j < len(lines) and (lines[j].strip() == '' or len(lines[j]) - len(lines[j].lstrip()) > step_indent):
                if re.match(r'\s+run:\s*\|', lines[j]):
                    run_line_idx = j
                if re.match(r'\s+env:', lines[j]):
                    env_line_idx = j
                j += 1
            
            if run_line_idx and not env_line_idx:
                # Extract run content
                run_content_lines = []
                k = run_line_idx + 1
                run_indent = None
                while k < len(lines):
                    if run_indent is None and lines[k].strip():
                        run_indent = len(lines[k]) - len(lines[k].lstrip())
                    if run_indent and lines[k].strip() and len(lines[k]) - len(lines[k].lstrip()) < run_indent:
                        break
                    run_content_lines.append(lines[k])
                    k += 1
                
                run_content = ''.join(run_content_lines)
                inputs_used = extract_inputs_from_run(run_content)
                
                if inputs_used:
                    # Create env block
                    env_indent = '      '  # Standard 6-space indent for env:
                    env_lines = [f'{env_indent}env:\n']
                    for input_name in sorted(inputs_used):
                        env_name = input_to_env_name(input_name)
                        env_lines.append(f'{env_indent}  {env_name}: ${{{{ inputs.{input_name} }}}}\n')
                    
                    # Insert env block before run
                    for env_line in env_lines:
                        new_lines.append(env_line)
                    
                    # Update run content to use env vars
                    for input_name in inputs_used:
                        env_name = input_to_env_name(input_name)
                        run_content = re.sub(
                            rf'\$\{{\{{\s*inputs\.{re.escape(input_name)}\s*\}}\}}',
                            f'${env_name}',
                            run_content
                        )
                    
                    # Skip ahead and write modified run content
                    i = run_line_idx
                    new_lines.append(lines[i])  # run: |
                    i += 1
                    # Write modified run content
                    new_lines.extend(run_content.splitlines(keepends=True))
                    # Skip original run content
                    while i < k:
                        i += 1
                    i -= 1  # Will be incremented at end of loop
                    modified = True
        
        i += 1
    
    if modified:
        with open(file_path, 'w') as f:
            f.writelines(new_lines)
        return True
    return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 auto-fix-inputs.py <action.yml>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    if fix_action_file_text(file_path):
        print(f"✅ Fixed: {file_path}")
    else:
        print(f"ℹ️  No changes: {file_path}")
