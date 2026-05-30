
## 2024-05-18 - GitHub Actions JSON Parsing Overhead
**Learning:** Using inline Python scripts (`python3 -c "import json..."`) for simple JSON parsing inside GitHub Actions bash steps adds significant overhead due to Python interpreter startup time.
**Action:** Always prefer `jq` (e.g., `jq -r`, `jq empty`) over `python3` for simple JSON parsing in bash scripts within GitHub Actions to improve execution speed.
