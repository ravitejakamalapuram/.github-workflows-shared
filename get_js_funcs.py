import re

with open("scripts/onboard-wizard.py", "r") as f:
    content = f.read()

funcs = re.findall(r'function\s+(\w+)\s*\(', content)
print("\n".join(funcs))
