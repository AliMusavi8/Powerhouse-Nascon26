#!/usr/bin/env sh
# Runs the unit tests with coverage and regenerates COVERAGE.json.
# Integration tests (tests/integration) run against a live stack on http://localhost:8080:
#   RUN_INTEGRATION=1 ./run_tests.sh
set -e
cd "$(dirname "$0")"

DEPS="segno==1.6.1 fastapi==0.115.0 psycopg[binary]==3.2.3 psycopg-pool==3.2.3 redis==5.0.8 PyJWT==2.9.0 fpdf2==2.8.1 pytest pytest-cov pypdf requests"

if python3 -c "import pytest, pytest_cov, fastapi, psycopg, jwt, fpdf, redis" >/dev/null 2>&1; then
  PY=python3
else
  echo "Python test dependencies not found locally; running tests in a python:3.12-slim container."
  exec docker run --rm --network host -e RUN_INTEGRATION="${RUN_INTEGRATION:-}" -v "$PWD":/w -w /w python:3.12-slim \
    sh -c "pip install -q $DEPS && python tests/coverage_report.py && if [ -n \"\$RUN_INTEGRATION\" ]; then python -m pytest tests/integration -q; fi"
fi

$PY tests/coverage_report.py
if [ -n "${RUN_INTEGRATION:-}" ]; then
  $PY -m pytest tests/integration -q
fi
