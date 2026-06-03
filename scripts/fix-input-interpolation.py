#!/usr/bin/env python3
"""
Fix direct input interpolation in composite actions.
Converts ${{ inputs.* }} to environment variables for security.
"""

import os
import re
import yaml
from pathlib import Path

def fix_action_file(action_path):
    """Fix input interpolation in a single action.yml file."""
    print(f"\n🔧 Processing: {action_path.parent}")
    
    with open(action_path, 'r') as f:
        content = f.read()
        original_content = content
    
    try:
        action = yaml.safe_load(content)
    except yaml.YAMLError as e:
        print(f"  ❌ YAML error: {e}")
        return False
    
    if 'runs' not in action or 'steps' not in action['runs']:
        print(f"  ℹ️  No steps found, skipping")
        return False
    
    modified = False
    steps = action['runs']['steps']
    
    for idx, step in enumerate(steps):
        if 'run' not in step:
            continue
        
        run_content = step['run']
        
        # Find all ${{ inputs.* }} patterns
        input_pattern = r'\$\{\{\s*inputs\.([a-zA-Z0-9_-]+)\s*\}\}'
        inputs_used = re.findall(input_pattern, run_content)
        
        if not inputs_used:
            continue
        
        print(f"  📝 Step {idx+1}: Found {len(inputs_used)} input interpolations")
        
        # Check if step already has env block
        has_env = 'env' in step and step['env']
        
        # Create env mapping for all inputs used in this step
        env_vars = {}
        for input_name in set(inputs_used):
            # Convert kebab-case to SCREAMING_SNAKE_CASE
            env_name = input_name.replace('-', '_').upper()
            env_vars[env_name] = f"${{{{ inputs.{input_name} }}}}"
        
        # Add env block if needed
        if env_vars and not has_env:
            # Find the step in the YAML content and add env block
            # This is complex, so we'll rebuild the action
            modified = True
            
            # Add env to step
            step['env'] = env_vars
            
            # Update run content to use env vars
            for input_name in set(inputs_used):
                env_name = input_name.replace('-', '_').upper()
                # Replace ${{ inputs.input-name }} with $ENV_NAME
                run_content = re.sub(
                    rf'\$\{{\{{\s*inputs\.{re.escape(input_name)}\s*\}}\}}',
                    f'${env_name}',
                    run_content
                )
            
            step['run'] = run_content
            print(f"    ✅ Added env block with {len(env_vars)} variables")
        elif env_vars:
            print(f"    ℹ️  Step already has env block, skipping")
    
    if modified:
        # Write back the modified YAML
        with open(action_path, 'w') as f:
            yaml.dump(action, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        print(f"  ✅ Fixed {action_path.parent}")
        return True
    else:
        print(f"  ℹ️  No changes needed")
        return False

def main():
    fixed_count = 0
    
    # Find all action.yml files
    composite_actions = Path("composite-actions")
    if not composite_actions.exists():
        print("Error: composite-actions directory not found")
        return 1
    
    action_files = sorted(composite_actions.rglob("action.yml"))
    print(f"Found {len(action_files)} actions to process")
    
    for action_file in action_files:
        if fix_action_file(action_file):
            fixed_count += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Fixed {fixed_count}/{len(action_files)} actions")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
