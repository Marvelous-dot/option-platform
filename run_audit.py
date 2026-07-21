#!/usr/bin/env python3
import subprocess
import sys
import os

result = subprocess.run(
    ["python3.11", "/root/option-platform/accuracy_audit.py"],
    capture_output=True,
    text=True,
    timeout=180,
    cwd="/root/option-platform"
)
print(result.stdout)
print(result.stderr, file=sys.stderr)
sys.exit(result.returncode)