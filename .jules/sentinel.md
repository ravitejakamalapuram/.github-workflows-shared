## 2024-05-15 - Command Injection in GitHub Actions Shell Scripts
**Vulnerability:** Shell scripts inside GitHub Actions use `eval` with unvalidated user inputs (e.g. `${{ inputs.exclude-patterns }}`). This allows arbitrary command execution by users supplying malicious inputs.
**Learning:** GitHub Action inputs are inserted as strings before shell evaluation. Using `eval` with unescaped inputs leads to command injection vulnerabilities.
**Prevention:** Avoid `eval` entirely. Use bash arrays and environment variables instead of direct string substitution or `eval` when executing commands with user inputs. Map action inputs to environment variables and consume them in scripts securely.

## 2024-05-18 - [Command Injection via GitHub Actions Inputs]
**Vulnerability:** Inline interpolation of `inputs` (e.g. `${{ inputs.test-script }}`) in shell scripts (`run: |`) creates a command injection risk.
**Learning:** Directly interpolating user inputs into a shell script within a GitHub action evaluates it at template time, before the shell executes it, leading to arbitrary code execution if the input is malicious.
**Prevention:** Always map `inputs` to environment variables in the `env:` block, and reference the environment variables in the shell scripts.
