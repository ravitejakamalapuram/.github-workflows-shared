## 2024-05-15 - Prefer jq over python3 in bash scripts
**Learning:** In GitHub Actions bash scripts, using `jq` for JSON parsing and validation is significantly faster than using `python3` one-liners. `python3` suffers from high interpreter startup overhead (~300ms per call vs ~5ms for jq).
**Action:** Always prefer `jq` (e.g., `jq -r`, `jq empty`) over `python3 -c` or `python3 -m json.tool` for JSON processing in CI/CD bash scripts to reduce execution time.
