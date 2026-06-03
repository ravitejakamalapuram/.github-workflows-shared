#!/usr/bin/env python3
"""
Validate composite actions against project standards.
Based on docs/CONTRIBUTING.md requirements.
"""

import os
import sys
import yaml
from pathlib import Path

class ActionValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def validate_action(self, action_path):
        """Validate a single action.yml file."""
        action_name = str(action_path.parent)
        
        print(f"\n🔍 Validating: {action_name}")
        
        with open(action_path, 'r') as f:
            try:
                action = yaml.safe_load(f)
            except yaml.YAMLError as e:
                self.errors.append(f"{action_name}: Invalid YAML - {e}")
                return
        
        # Check required fields
        self._check_required_fields(action, action_name)
        self._check_inputs(action, action_name)
        self._check_outputs(action, action_name)
        self._check_steps(action, action_name)
        self._check_branding(action, action_name)
        
    def _check_required_fields(self, action, name):
        """Check for required top-level fields."""
        required = ['name', 'description', 'runs']
        for field in required:
            if field not in action:
                self.errors.append(f"{name}: Missing required field '{field}'")
        
        if 'author' not in action:
            self.warnings.append(f"{name}: Missing 'author' field (recommended)")
    
    def _check_inputs(self, action, name):
        """Check inputs have proper descriptions."""
        if 'inputs' in action:
            for input_name, input_def in action['inputs'].items():
                if not isinstance(input_def, dict):
                    continue
                if 'description' not in input_def:
                    self.errors.append(f"{name}: Input '{input_name}' missing description")
    
    def _check_outputs(self, action, name):
        """Check outputs have descriptions."""
        if 'outputs' in action:
            for output_name, output_def in action['outputs'].items():
                if not isinstance(output_def, dict):
                    continue
                if 'description' not in output_def:
                    self.errors.append(f"{name}: Output '{output_name}' missing description")
    
    def _check_steps(self, action, name):
        """Check steps have shell specified."""
        if 'runs' not in action or 'steps' not in action['runs']:
            return
        
        for idx, step in enumerate(action['runs']['steps']):
            if 'run' in step and 'shell' not in step:
                self.errors.append(f"{name}: Step {idx+1} has 'run' but missing 'shell'")
            
            # Check for security issues
            if 'run' in step:
                run_content = step['run']
                # Check for direct input interpolation without env vars
                if '${{ inputs.' in run_content and 'env:' not in str(step):
                    self.warnings.append(f"{name}: Step {idx+1} uses direct input interpolation - consider using env vars for security")
    
    def _check_branding(self, action, name):
        """Check branding is present."""
        if 'branding' not in action:
            self.warnings.append(f"{name}: Missing 'branding' (recommended)")
        else:
            branding = action['branding']
            if 'icon' not in branding:
                self.warnings.append(f"{name}: Branding missing 'icon'")
            if 'color' not in branding:
                self.warnings.append(f"{name}: Branding missing 'color'")
    
    def print_results(self):
        """Print validation results."""
        print("\n" + "="*60)
        print("VALIDATION RESULTS")
        print("="*60)
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        if not self.errors and not self.warnings:
            print("\n✅ All actions pass validation!")
        
        return len(self.errors) == 0

def main():
    validator = ActionValidator()
    
    # Find all action.yml files
    composite_actions = Path("composite-actions")
    if not composite_actions.exists():
        print("Error: composite-actions directory not found")
        sys.exit(1)
    
    action_files = list(composite_actions.rglob("action.yml"))
    print(f"Found {len(action_files)} actions to validate")
    
    for action_file in sorted(action_files):
        validator.validate_action(action_file)
    
    success = validator.print_results()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
