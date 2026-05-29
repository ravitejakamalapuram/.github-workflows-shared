## 2024-10-24 - Avoid Python overhead for simple JSON operations in bash
**Learning:** Using `python3 -c "import json..."` or `python3 -m json.tool` inline within bash scripts inside GitHub Actions introduces significant interpreter startup overhead compared to lightweight command-line utilities.
**Action:** Always prefer using `jq` (e.g., `jq -r`, `jq empty`) over `python3` for parsing, validating, and extracting values from JSON files in shell scripts and CI/CD workflows to improve execution speed.
