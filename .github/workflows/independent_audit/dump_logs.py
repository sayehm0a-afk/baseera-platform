"""One-off: dump recent backend logs verbatim so a human/AI reviewer
can read the full traceback behind the /quote 503s found by the main
audit, without truncation. Throwaway diagnostic tooling."""

import subprocess

proc = subprocess.run(
    ["timeout", "25", "railway", "logs", "--service", "backend"],
    capture_output=True, text=True, timeout=30,
)
print(proc.stdout)
print(proc.stderr)
