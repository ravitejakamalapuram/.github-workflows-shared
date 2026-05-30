
## 2024-05-18 - Replacing python3 json parsing with jq in bash scripts
**Learning:** Using `python3 -c "import json; ..."` inside bash scripts for simple JSON parsing operations like extracting single values or validating JSON structure introduces significant latency (~0.8s vs ~0.005s) due to the Python interpreter's startup overhead. This becomes a major bottleneck when invoked multiple times in CI/CD pipelines (like GitHub Actions workflows).
**Action:** Always prefer `jq` (e.g., `jq -r`, `jq empty`) over `python3` for JSON parsing and validation inside bash scripts for GitHub Actions and build scripts to significantly speed up execution time.
