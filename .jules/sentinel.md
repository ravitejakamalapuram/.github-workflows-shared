## 2026-06-07 - Command Injection via Action Inputs
**Vulnerability:** Command injection vulnerability identified in composite actions. Directly interpolating GitHub Action user inputs (`${{ inputs.* }}`) into bash `run` scripts allows attackers to execute arbitrary shell commands if the input contains malicious payloads (e.g., `; rm -rf /`).
**Learning:** This repo has numerous reusable composite actions taking user inputs and dynamically constructing commands. Direct substitution evaluates input strings as raw bash logic instead of isolated string values.
**Prevention:** Always map user inputs (`${{ inputs.* }}`) to environment variables within the `env:` block. Never use them directly via inline string interpolation in bash scripts or `eval` statements. This ensures inputs are safely evaluated as variables.
## 2024-05-24 - Command Injection via inputs in Action scripts

**Vulnerability:** User inputs (`${{ inputs.* }}`) were directly interpolated into bash scripts within `composite-actions/flutter/test/action.yml`, which could allow command injection.
**Learning:** Inline string interpolation of user-controlled variables in shell scripts exposes the system to command execution via crafted payloads.
**Prevention:** Always map user inputs (`${{ inputs.* }}`) to environment variables within the `env:` block. Never use them directly via inline string interpolation in bash scripts or `eval` statements. This ensures inputs are safely evaluated as variables.

## 2026-06-07 - Command Injection via subprocess.Popen shell=True

**Vulnerability:** Command injection vulnerability in `scripts/onboard-wizard.py`. Passing user-provided strings like `build_script` to `subprocess.Popen(..., shell=True)` allows attackers to execute arbitrary commands by appending shell metacharacters (e.g., `; rm -rf /`).
**Learning:** Local Python servers accepting build commands must treat inputs as untrusted and properly tokenize them rather than evaluating them in a shell context.
**Prevention:** Always use `shlex.split()` to tokenize command strings into an array of arguments, and pass `shell=False` to `subprocess.Popen` or `subprocess.run`.
## 2024-10-24 - Command Injection via Inline Ternary Expressions in GitHub Actions
**Vulnerability:** Found a command injection risk where inline GitHub Actions ternary expressions (e.g., `${{ env.VAR == 'true' && 'val' || '' }}`) and indirect interpolations (`${{ steps.x.outputs.y }}`) were directly evaluated inside bash run: scripts.
**Learning:** The GitHub Actions expression engine evaluates these statements before bash executes. While seemingly harmless, they can break out of the string context and execute arbitrary shell commands if untrusted input controls the logic or outputs.
**Prevention:** Replace inline string expressions in run: scripts with native bash conditional blocks (if/else), and map all step outputs explicitly to the env: block rather than using indirect interpolation.
