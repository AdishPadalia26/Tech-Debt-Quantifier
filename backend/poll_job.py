import httpx, time, json, sys

job_id = "cad9f67e-5d06-4cf1-a178-4783348d52e1"
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.eceUiIUsyA1SqgNG3UE9f7H_KxLiZs_07nzhe7cQtOU"

status = "queued"
start = time.time()

print(f"Polling job: {job_id}")

while status not in ["complete", "failed"]:
    time.sleep(10)
    r = httpx.get(f"http://localhost:8000/results/{job_id}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    data = r.json()
    status = data.get("status", "unknown")
    elapsed = int(time.time() - start)
    print(f"[{elapsed}s] Status: {status}")
    sys.stdout.flush()
    
    if elapsed > 600:
        print("Timeout after 10 minutes")
        break
    
    if status == "complete":
        raw = data.get("raw", {})
        analysis = raw.get("raw_analysis") or raw
        print(f"Cost: ${analysis.get('total_cost_usd', 0):,.2f}")
        print(f"Score: {analysis.get('debt_score', 0)}/10")
        print(f"Hours: {analysis.get('total_remediation_hours', 0)}")
        break
    
    if status == "failed":
        print(f"Error: {data.get('error')}")
        break