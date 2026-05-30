## 2026-05-29 - [Replace python3 JSON parsing with jq in shell scripts]
**Learning:** Using `python3 -c` for parsing JSON in bash scripts adds high interpreter startup overhead (~50-100ms) compared to using `jq` (~2-5ms). This overhead is multiplied in GitHub Actions when parsing multiple keys sequentially.
**Action:** Always prefer `jq` for JSON parsing/validation in bash over firing up a Python interpreter.
