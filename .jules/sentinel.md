## 2026-05-27 - [Critical] Shell Injection via Unsafe GitHub Actions Inputs
**Vulnerability:** Shell injection via unsanitized `inputs` directly interpolated into bash `run` blocks in GitHub Composite Actions (`${{ inputs.variable }}`). Compounded by use of `eval` to construct dynamic zip arguments.
**Learning:** GitHub Actions composite scripts are highly susceptible to shell injection if inputs from triggering workflows are injected directly into scripts without environment mapping. Use of `eval` expands the attack surface further.
**Prevention:** Always map action `inputs` to environment variables (`env:`) within steps and reference them securely as `$ENV_VAR` in bash scripts. Avoid `eval` entirely by constructing complex shell arguments using bash arrays (e.g., `ARGS=()`).
