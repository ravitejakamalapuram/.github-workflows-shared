## 2026-06-01 - Faster JSON Parsing in GitHub Actions
**Learning:** Using `python3 -c "import json..."` or `python3 -m json.tool` for JSON parsing and validation inside GitHub Actions Bash scripts introduces significant interpreter startup overhead.
**Action:** Replace `python3` invocations with `jq` (e.g., `jq -r`, `jq empty`), which is significantly faster and well-suited for these tasks in GitHub Actions runners.
