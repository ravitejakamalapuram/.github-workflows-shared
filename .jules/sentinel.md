
## 2026-05-29 - Command Injection in GitHub Actions via eval
**Vulnerability:** Command injection and unauthorized execution. GitHub Actions `inputs` directly interpolated within a `run` script via `${{ inputs.foo }}` alongside `eval` allows user-controlled payloads (like `foo; rm -rf /`) to execute arbitrarily. Python inline scripts fetching properties using `${{ inputs.* }}` are also susceptible to breaking script boundaries.
**Learning:** Using `eval` together with unescaped GitHub actions inputs opens up severe command injection in composite actions. Interpolation drops input directly into the script before bash executes it, bypassing bash quoting rules.
**Prevention:**
1. **Never use inline interpolation (`${{ inputs.foo }}`) inside `run` blocks** for variables that can contain untrusted input. Instead, assign them to environment variables using the `env:` block.
2. **Avoid `eval` in Bash scripts.** Instead, use bash arrays like `ARGS=()` and construct commands using `"${ARGS[@]}"`.
3. Prefer tools like `jq` to fetch properties safely rather than using dynamic strings in Python `-c` commands.
