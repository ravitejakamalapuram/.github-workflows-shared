## 2024-05-18 - GitHub Actions Command Injection via eval
**Vulnerability:** Command injection in bash scripts within composite actions when evaluating string inputs (e.g., `eval "zip ... $EXCLUDE_ARGS"`).
**Learning:** Using `eval` with string variables constructed from user inputs allows arbitrary command execution if an input contains shell metacharacters or command substitutions.
**Prevention:** Always map user inputs to environment variables and use bash arrays (`EXCLUDE_ARGS=()`) rather than string concatenation and `eval` to build command arguments.
