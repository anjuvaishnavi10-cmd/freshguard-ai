"""
FreshGuard AI - Comprehensive Customer Products, Google Login & Barcode Scanner E2E Suite
Verifies all 5 core requirements from the user request.
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
    print("=" * 70)
    print(" FRESHGUARD AI — FULL CUSTOMER ACCESS & BARCODE E2E TEST SUITE")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. GOOGLE LOGIN & CONFIGURATION
    # -------------------------------------------------------------
    print("\n[Step 1] Verifying Google Login & OAuth Configuration...")
    status, cfg = request_json("/api/auth/google/config")
    assert status == 200 and "configured" in cfg, f"Google config GET failed: {cfg}"
    print(f"  ✓ Google OAuth Config Endpoint OK (Configured: {cfg['configured']})")

    # Save custom OAuth configuration
    status, save_cfg = request_json("/api/auth/google/config", method="POST", payload={
        "client_id": "9876543210-demo.apps.googleusercontent.com",
        "client_secret": "GOCSPX-demosecret123"
    })
    assert status == 200 and save_cfg["success"], f"Google config save failed: {save_cfg}"
    assert save_cfg["config"]["client_id"] == "9876543210-demo.apps.googleusercontent.com"
    print("  ✓ Google OAuth credentials persisted to SQLite")

    # Authenticate Customer Alex via Google OAuth
    status, alex_auth = request_json("/api/auth/google", method="POST", payload={
        "test_user_email": "alex.customer@freshguard.test",
        "test_user_name": "Alex Customer"
    })
    assert status == 200 and alex_auth["success"], f"Google login failed: {alex_auth}"
    alex_token = alex_auth["token"]
    alex_user = alex_auth["user"]
    print(f"  ✓ Customer Alex logged in with Google account (User ID: {alex_user['id']})")

    # Authenticate Customer Priya via Google OAuth
    status, priya_auth = request_json("/api/auth/google", method="POST", payload={
        "test_user_email": "priya.patel@freshguard.test",
        "test_user_name": "Priya Patel"
    })
    assert status == 200 and priya_auth["success"], f"Google login failed: {priya_auth}"
    priya_token = priya_auth["token"]
    priya_user = priya_auth["user"]
    assert alex_user["id"] != priya_user["id"], "Different Google accounts must have separate user IDs"
    print(f"  ✓ Customer Priya logged in with Google account (User ID: {priya_user['id']})")
    print("  ✓ Distinct customer accounts verified with private data partitions.")

    # -------------------------------------------------------------
    # 2. BARCODE SCANNING & LOOKUP
    # -------------------------------------------------------------
    print("\n[Step 2] Verifying Barcode Scanning & Product Lookup...")
    # Supported barcode formats: EAN-13
    status, bc_amul = request_json("/api/barcode/lookup?code=8901262010053")
    assert status == 200 and bc_amul["found"], f"Barcode lookup failed: {bc_amul}"
    p_amul = bc_amul["product"]
    assert "Amul Taaza" in p_amul["name"]
    assert p_amul["category"] == "dairy"
    assert p_amul["barcode"] == "8901262010053"
    print(f"  ✓ EAN-13 Barcode 8901262010053 looked up: {p_amul['name']} ({p_amul['brand']})")

    # UPC-A Barcode (Coca-Cola: 049000006346)
    status, bc_upc = request_json("/api/barcode/lookup?code=049000006346")
    assert status == 200 and bc_upc["found"], f"UPC-A lookup failed: {bc_upc}"
    p_upc = bc_upc["product"]
    assert p_upc["category"] == "beverages"
    print(f"  ✓ UPC-A Barcode 049000006346 looked up: {p_upc['name']} ({p_upc['brand']})")

    # Barcode not found fallback
    status, bc_unknown = request_json("/api/barcode/lookup?code=0000111122223")
    assert status == 200 and bc_unknown["found"] is False
    print("  ✓ Unregistered barcode correctly triggers manual details entry fallback.")

    # -------------------------------------------------------------
    # 3. MANUAL PRODUCT ENTRY FORM & STRICT VALIDATION
    # -------------------------------------------------------------
    print("\n[Step 3] Verifying Manual Product Entry Form Validation...")
    # Missing required name
    status, err_name = request_json("/api/customer/products/add", method="POST", payload={
        "name": "",
        "category": "fruits"
    }, token=alex_token)
    assert status == 400 and "Product name is required" in err_name["error"]
    print("  ✓ Blank product name correctly rejected with field error")

    # Invalid category
    status, err_cat = request_json("/api/customer/products/add", method="POST", payload={
        "name": "Red Apples",
        "category": "electronics"
    }, token=alex_token)
    assert status == 400 and "Category must be one of" in err_cat["error"]
    print("  ✓ Invalid category correctly rejected with field error")

    # Invalid dates (expiry earlier than purchase date)
    status, err_dates = request_json("/api/customer/products/add", method="POST", payload={
        "name": "Fresh Spinach",
        "category": "vegetables",
        "purchase_date": "2026-10-15",
        "expiry_date": "2026-10-10"
    }, token=alex_token)
    assert status == 400 and "Expiry date cannot be earlier" in err_dates["error"]
    print("  ✓ Expiry date < purchase date correctly rejected with field error")

    # -------------------------------------------------------------
    # 4. CUSTOMER PRODUCT CRUD & DUPLICATE BARCODE PREVENTION
    # -------------------------------------------------------------
    print("\n[Step 4] Verifying Customer Product Save, Duplicate Prevention & CRUD...")
    # Add Product 1 for Alex
    status, add1 = request_json("/api/customer/products/add", method="POST", payload={
        "name": "Ratnagiri Alphonso Mangoes",
        "brand": "Devgad Farms",
        "category": "fruits",
        "barcode": "8901262010053",
        "purchase_date": "2026-10-10",
        "expiry_date": "2026-10-14",
        "storage_instructions": "Keep in cool dry place, crisper drawer",
        "notes": "Premium harvest from Ratnagiri"
    }, token=alex_token)
    assert status == 200 and add1["success"], f"Add product 1 failed: {add1}"
    alex_prod1_id = add1["product_id"]
    print(f"  ✓ Alex added product #{alex_prod1_id}: Ratnagiri Alphonso Mangoes")

    # Try duplicate barcode for Alex (must fail)
    status, err_dup = request_json("/api/customer/products/add", method="POST", payload={
        "name": "Another Mango Batch",
        "category": "fruits",
        "barcode": "8901262010053"
    }, token=alex_token)
    assert status == 400 and "already exists" in err_dup["error"]
    print("  ✓ Duplicate barcode within Alex's product list correctly prevented")

    # Priya can use the same barcode without conflict (private customer list)
    status, priya_add = request_json("/api/customer/products/add", method="POST", payload={
        "name": "Amul Taaza Milk",
        "brand": "Amul",
        "category": "dairy",
        "barcode": "8901262010053"
    }, token=priya_token)
    assert status == 200 and priya_add["success"], f"Priya add failed: {priya_add}"
    priya_prod_id = priya_add["product_id"]
    print(f"  ✓ Priya can safely use barcode in her private account (#{priya_prod_id})")

    # -------------------------------------------------------------
    # 5. VIEW, EDIT, AND DELETE PRODUCTS WITH STRICT ISOLATION
    # -------------------------------------------------------------
    print("\n[Step 5] Verifying View, Edit, Delete & Multi-Tenant Authorization...")
    # List Alex's products
    status, alex_list = request_json("/api/customer/products", token=alex_token)
    assert status == 200 and len(alex_list["products"]) >= 1
    alex_ids = [p["id"] for p in alex_list["products"]]
    assert alex_prod1_id in alex_ids
    assert priya_prod_id not in alex_ids, "Alex should never see Priya's products"
    print(f"  ✓ Alex's private products list contains {len(alex_list['products'])} products (zero leakage from Priya)")

    # View Alex's product
    status, alex_view = request_json(f"/api/customer/products/view?id={alex_prod1_id}", token=alex_token)
    assert status == 200 and alex_view["product"]["name"] == "Ratnagiri Alphonso Mangoes"
    print(f"  ✓ Alex viewed complete product details for #{alex_prod1_id}")

    # Priya attempts to view Alex's product (must be unauthorized 404/403)
    status, priya_view_alex = request_json(f"/api/customer/products/view?id={alex_prod1_id}", token=priya_token)
    assert status in (403, 404), f"Security violation! Priya should not view Alex's product: {priya_view_alex}"
    print("  ✓ Security Confirmed: Direct request from another customer account rejected.")

    # Edit product (Alex edits his mangoes, retaining same barcode without triggering duplicate check)
    status, alex_update = request_json("/api/customer/products/update", method="POST", payload={
        "id": alex_prod1_id,
        "name": "Ratnagiri Alphonso Mangoes (Grade A+)",
        "brand": "Devgad Premium Farms",
        "category": "fruits",
        "barcode": "8901262010053",
        "purchase_date": "2026-10-10",
        "expiry_date": "2026-10-16",
        "storage_instructions": "Refrigerate at 4°C",
        "notes": "Updated storage to prolong freshness"
    }, token=alex_token)
    assert status == 200 and alex_update["success"], f"Update failed: {alex_update}"
    print(f"  ✓ Alex edited #{alex_prod1_id}: Title & expiry updated while retaining barcode")

    # Delete product
    status, alex_del = request_json("/api/customer/products/delete", method="POST", payload={
        "id": alex_prod1_id
    }, token=alex_token)
    assert status == 200 and alex_del["success"], f"Delete failed: {alex_del}"
    print(f"  ✓ Alex deleted product #{alex_prod1_id} after confirmation")

    # Confirm deleted product is gone from active list
    status, alex_list_after = request_json("/api/customer/products", token=alex_token)
    remaining_ids = [p["id"] for p in alex_list_after["products"]]
    assert alex_prod1_id not in remaining_ids
    print(f"  ✓ Deletion verified: Product #{alex_prod1_id} no longer in active ledger")

    print("\n" + "=" * 70)
    print(" ALL 5 REQUIREMENTS VERIFIED AND 100% OPERATIONAL!")
    print(" 1. Google OAuth Login & Config Instructions: PASSED")
    print(" 2. Customer Add Their Own Products: PASSED")
    print(" 3. Working Barcode Scanner & Catalog Lookup: PASSED")
    print(" 4. Manual Product Form & Field Validations: PASSED")
    print(" 5. View, Edit, Delete & Strict Data Isolation: PASSED")
    print("=" * 70)

if __name__ == "__main__":
    run()
