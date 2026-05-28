## 2024-05-15 - Replace python3 JSON parsing with jq in shell scripts
**Learning:** Invoking Python just to parse JSON inside bash scripts (e.g., `python3 -c "import json..."`) is significantly slower than using lightweight tools like `jq`. A simple benchmark of parsing 3 properties 100 times showed Python taking ~81s vs `jq` taking ~1.5s (over 50x faster). Validating JSON with `python3 -m json.tool` is also ~60x slower than `jq empty`.
**Action:** Replace `python3 -c "import json..."` and `python3 -m json.tool` with `jq` in bash scripts when extracting simple properties from JSON files.
