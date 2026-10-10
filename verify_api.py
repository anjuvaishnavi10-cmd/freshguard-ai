import urllib.request
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

print("1. Health Check:", get("http://localhost:8080/api/health"))

# Test Milk Scenario Endpoint
milk_demo = get("http://localhost:8080/api/demo/milk-scenario")
print("2. Milk Scenario Winning Decision:", milk_demo["winning_orchestrated_decision"]["action_title"])
print("   Decision Type:", milk_demo["winning_orchestrated_decision"]["action_type"])
print("   Net Economic Yield: ₹", milk_demo["winning_orchestrated_decision"]["net_economic_yield"])

# Test Simulation
sim = post("http://localhost:8080/api/rescue/simulate", {"foot_traffic_mult": 1.1, "discount_aggressiveness": 1.0})
print("3. Orchestrated Recommendations Count:", len(sim["recommendations"]))
top_rec = sim["recommendations"][0]
print("   Top Rec:", top_rec["action_title"], f"({top_rec['confidence']} Confidence)")
print("   Constraints Checked Count:", len(top_rec["constraints_checked"]))

# Test Approve Workflow
app_res = post("http://localhost:8080/api/rescue/approve", top_rec)
print("4. Approve Workflow:", app_res)

# Test Reject Workflow
rej_rec = sim["recommendations"][1]
rej_res = post("http://localhost:8080/api/rescue/reject", {
    "action_payload": rej_rec,
    "rejection_reason": "Supplier credit return agreed"
})
print("5. Reject Workflow:", rej_res)

# Test Results Ledger
res_history = get("http://localhost:8080/api/results")
print("6. Results Total Actions Executed:", res_history["cumulative_impact"]["total_actions_executed"])
print("   Results Total Rejections:", res_history["cumulative_impact"]["total_rejections"])
print("   Results Total Revenue Saved: ₹", res_history["cumulative_impact"]["total_revenue_saved"])

print("\nALL MULTI-AGENT ORCHESTRATOR TESTS PASSED!")
