
## 2026-06-02 - Command Injection in GitHub Actions Shell Scripts
**Vulnerability:** Shell scripts inside GitHub Actions workflows (`run: |`) were vulnerable to command injection because user inputs (`${{ inputs.* }}`) were interpolated inline as strings and passed to unsafe functions like `eval`. An attacker could pass a malicious string to execute arbitrary commands on the runner.
**Learning:** Even internal composite actions should treat user inputs as untrusted. Injecting them inline into Bash can break quotes and syntax, leading to RCE or failed builds. Furthermore, using `eval` for command argument expansion is extremely unsafe.
**Prevention:** Always map user inputs to environment variables inside the `env:` block. Inside the `run` script, reference the variables securely (e.g., `"$ENV_VAR"`). If dynamic arguments are required, use bash array syntax (e.g., `read -ra` and `"${ARGS[@]}"`) instead of building a string for `eval`.
