"""CLI script to fetch and display raw JSON from /debug/results/{job_id}."""

import json
import sys
import httpx

BASE_URL = "http://localhost:8000"


def fetch_debug(job_id: str) -> None:
    """Fetch raw result for a job_id and pretty-print it."""
    url = f"{BASE_URL}/debug/results/{job_id}"
    resp = httpx.get(url, timeout=30)

    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text}")
        sys.exit(1)

    data = resp.json()
    print(json.dumps(data, indent=2, default=str))


def list_jobs() -> None:
    """List all in-memory jobs."""
    resp = httpx.get(f"{BASE_URL}/jobs", timeout=10)
    print(json.dumps(resp.json(), indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_fetch.py <job_id>    # fetch raw result")
        print("  python debug_fetch.py --list      # list all jobs")
        sys.exit(0)

    if sys.argv[1] == "--list":
        list_jobs()
    else:
        fetch_debug(sys.argv[1])
