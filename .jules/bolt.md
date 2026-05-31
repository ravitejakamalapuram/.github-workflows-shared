## 2025-01-28 - Fast JSON Parsing in Shell Scripts
**Learning:** In bash scripts running in GitHub Actions, `python3 -c` has significant startup overhead for simple JSON tasks. `jq` is pre-installed on runners and dramatically faster for validation and value extraction.
**Action:** Always prefer `jq -r` for extracting values and `jq empty` for validation over spinning up the Python interpreter when writing shell scripts in composite actions.
