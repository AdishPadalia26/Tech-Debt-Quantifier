"""Prints the /debug/results/{job_id} JSON nicely so I can see raw_analysis and priority_actions.
Run: python debug_print_results.py <job_id>
"""
import sys
import json
import httpx

BASE_URL = "http://localhost:8000"

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_print_results.py <job_id>")
        sys.exit(1)

    job_id = sys.argv[1]
    url = f"{BASE_URL}/debug/results/{job_id}"
    r = httpx.get(url, timeout=30)

    print(f"GET {url} -> {r.status_code}")
    if r.status_code != 200:
        print(r.text)
        return

    data = r.json()

    # Show top-level keys
    print("\nTop-level keys:")
    print(list(data.keys()))

    # Show raw_analysis core fields
    ra = data.get("raw_analysis", {})
    print("\nraw_analysis keys:")
    print(list(ra.keys()))
    print("\nSample raw_analysis values:")
    snippet = {
        "debt_score": ra.get("debt_score"),
        "total_cost_usd": ra.get("total_cost_usd"),
        "total_remediation_hours": ra.get("total_remediation_hours"),
        "cost_by_category": ra.get("cost_by_category"),
    }
    print(json.dumps(snippet, indent=2))

    # Show priority_actions
    pa = data.get("priority_actions") or []
    if pa:
        print("\nFirst priority_action:")
        print(json.dumps(pa[0] if isinstance(pa, list) and pa else pa, indent=2))
    else:
        print("\nNo priority_actions found.")

if __name__ == "__main__":
    main()
