## 2024-05-24 - Python interpreter overhead in bash scripts
**Learning:** `python3 -c` and `python3 -m json.tool` introduce significant interpreter startup latency (often ~1s+) compared to `jq` (~0.02s) for simple JSON parsing in bash scripts within GitHub Actions.
**Action:** Prefer using `jq` (e.g., `jq empty`, `jq -r '.key // "default"'`) over `python3` for JSON parsing and validation to avoid high Python interpreter startup overhead. Use the `//` operator to cleanly handle defaults similarly to Python's `.get('key', 'default')`.
