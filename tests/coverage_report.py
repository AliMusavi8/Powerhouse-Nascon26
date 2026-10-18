"""Run the unit tests with line coverage and write COVERAGE.json (per backend area)."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join("backend", "app")

AREAS = {
    "fixtures": ["domain/fixtures/__init__.py", "domain/fixtures/round_robin.py", "domain/fixtures/swiss.py",
                 "domain/fixtures/elimination.py"],
    "scoring": ["domain/scoring.py", "domain/sports.py", "crypto.py"],
    "standings": ["domain/standings.py"],
    "store": ["domain/store.py", "services/pdf.py"],
    "roster": ["domain/roster.py"],
    "rbac": ["domain/rbac.py"],
}

# Part II modules (spec 7.2) -> COVERAGE_DAY2.json
AREAS_DAY2 = {
    "streaming": ["domain/streaming.py"],
    "costream": ["domain/costream.py"],
    "qr_guest": ["domain/qr.py", "domain/guest.py"],
    "moderation_dlq": ["domain/moderation.py", "domain/dlq.py"],
    "observability": ["domain/metrics.py"],
}


def main() -> int:
    os.chdir(ROOT)
    cmd = [sys.executable, "-m", "pytest", "tests/unit", "-q", f"--cov={APP}", "--cov-report=json:.coverage-raw.json",
           "--cov-report=term"]
    rc = subprocess.call(cmd)
    with open(".coverage-raw.json", encoding="utf-8") as f:
        files = {os.path.normpath(k): v["summary"] for k, v in json.load(f)["files"].items()}
    for target, areas in (("COVERAGE.json", AREAS), ("COVERAGE_DAY2.json", AREAS_DAY2)):
        out = {}
        for area, rels in areas.items():
            covered = total = 0
            for rel in rels:
                s = files.get(os.path.normpath(os.path.join(APP, rel)))
                if s:
                    covered += s["covered_lines"]
                    total += s["num_statements"]
            out[area] = round(100.0 * covered / total, 1) if total else 0.0
        with open(target, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
            f.write("\n")
        print(target + ":", json.dumps(out))
    return rc


if __name__ == "__main__":
    sys.exit(main())
