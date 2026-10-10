"""
Test Customer Products & Google OAuth via HTTP REST API
"""

import urllib.request
import urllib.parse
import json
import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8080"

def request_json(path, method="GET", payload=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))

def run():
    print("Testing HTTP Endpoints...")
    # 1. Google config
    status, g_cfg = request_json("/api/auth/google/config")
    assert status == 200, f"Google config failed: {g_cfg}"
    print("✓ Google OAuth config endpoint OK:", g_cfg["configured"])

    # 2. Google Login via test mode
    ts = int(time.time())
    status, g_login = request_json("/api/auth/google", method="POST", payload={
        "test_mode": True,
        "email": f"customer_{ts}@googlemail.com",
        "name": f"Anjali Google {ts}"
    })
    assert status == 200 and g_login["success"], f"Google login failed: {g_login}"
    token_g = g_login["token"]
    user_g = g_login["user"]
    print(f"✓ Google authentication succeeded for {user_g['email']} (User ID: {user_g['id']})")

    # 3. Barcode Lookup via HTTP
    status, b_res = request_json("/api/barcode/lookup?code=8901262010053", token=token_g)
    assert status == 200 and b_res["found"], f"Barcode lookup failed: {b_res}"
    assert b_res["product"]["brand"] == "Amul", "Brand mismatch"
    print(f"✓ Barcode 8901262010053 looked up successfully: {b_res['product']['name']}")

    # 4. Add Customer Product via Form
    status, add_res = request_json("/api/customer/products/add", method="POST", payload={
        "name": "Organic Alphonso Mangoes",
        "brand": "Devgad Naturals",
        "category": "fruits",
        "barcode": f"890999{ts % 1000000:06d}",
        "purchase_date": "2026-10-10",
        "expiry_date": "2026-10-16",
        "storage_instructions": "Store in fruit basket",
        "notes": "Handpicked fresh harvest"
    }, token=token_g)
    assert status == 200 and add_res["success"], f"Product add failed: {add_res}"
    prod_id = add_res["product"]["id"]
    print(f"✓ Customer added new product #{prod_id}: {add_res['product']['name']}")

    # 5. List Customer Products
    status, list_res = request_json("/api/customer/products", token=token_g)
    assert status == 200 and list_res["success"], f"Product list failed: {list_res}"
    assert any(p["id"] == prod_id for p in list_res["products"]), "Created product not in list"
    print(f"✓ Customer product list retrieved ({list_res['count']} products)")

    # 6. View Single Product
    status, view_res = request_json(f"/api/customer/products/view?id={prod_id}", token=token_g)
    assert status == 200 and view_res["success"], f"View product failed: {view_res}"
    assert view_res["product"]["name"] == "Organic Alphonso Mangoes"
    print(f"✓ View single product OK: {view_res['product']['name']}")

    # 7. Update Product
    status, upd_res = request_json("/api/customer/products/update", method="POST", payload={
        "id": prod_id,
        "name": "Organic Alphonso Mangoes (Export Grade)",
        "brand": "Devgad Naturals",
        "category": "fruits",
        "barcode": add_res["product"]["barcode"],
        "purchase_date": "2026-10-10",
        "expiry_date": "2026-10-18"
    }, token=token_g)
    assert status == 200 and upd_res["success"], f"Product update failed: {upd_res}"
    print(f"✓ Updated product #{prod_id} successfully: {upd_res['product']['name']}")

    # 8. Delete Product
    status, del_res = request_json("/api/customer/products/delete", method="POST", payload={
        "id": prod_id
    }, token=token_g)
    assert status == 200 and del_res["success"], f"Product delete failed: {del_res}"
    print(f"✓ Deleted product #{prod_id} successfully")

    # Verify no longer active
    status, list_after = request_json("/api/customer/products", token=token_g)
    assert not any(p["id"] == prod_id for p in list_after["products"]), "Deleted product still in list"
    print("✓ Product deletion confirmed from active ledger")

    print("\nALL HTTP API TESTS PASSED!")

if __name__ == "__main__":
    run()
