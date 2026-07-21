#!/usr/bin/env python3
import subprocess
r = subprocess.run(['/usr/bin/python3.11', '/root/option-platform/self_heal.py'], capture_output=True, text=True, timeout=300)
print(r.stdout)
print(r.stderr)
