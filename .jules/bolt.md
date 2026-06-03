## 2026-06-03 - [Optimize JSON parsing in CI scripts]
**Learning:** Python interpreter startup overhead is a measurable bottleneck in CI bash scripts for simple JSON tasks like extraction and validation. Using 'jq' is significantly faster for these operations.
**Action:** Prefer 'jq' over 'python3 -c' or 'python3 -m json.tool' in shell scripts/GitHub Actions steps when dealing with simple JSON parsing to improve script execution performance.
