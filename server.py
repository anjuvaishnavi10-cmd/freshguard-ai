"""
FreshGuard - HTTP Server & REST API with Multi-Tenant Customer Access
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery
"""

import http.server
import socketserver
import json
import os
import sys
import urllib.parse
from pathlib import Path

from freshguard_db import init_db, seed_data, get_connection
from engine import FreshGuardEngine
from evaluation_simulator import EvaluationSimulator

PORT = 8080
BASE_DIR = Path(__file__).parent.resolve()
STATIC_DIR = BASE_DIR / "static"

class FreshGuardRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    Custom HTTP Request Handler serving static frontend and customer-isolated REST API.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _send_json(self, data, status=200):
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Auth-Token")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                raw = self.rfile.read(content_length).decode("utf-8")
                return json.loads(raw)
        except Exception as e:
            print(f"Error parsing JSON request body: {e}")
        return {}

    def _get_authenticated_user(self):
        """
        Extract and validate session token from Authorization header or X-Auth-Token.
        """
        auth_header = self.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "token=" in self.headers.get("Cookie", ""):
            for part in self.headers.get("Cookie", "").split(";"):
                if "token=" in part:
                    token = part.split("token=")[-1].strip()
        if not token:
            token = self.headers.get("X-Auth-Token", "").strip()
        if not token:
            return None
        return FreshGuardEngine.get_user_by_token(token)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Auth-Token")
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        query = {k: v[0] for k, v in query_params.items()}

        user = self._get_authenticated_user()
        user_id = user["id"] if user else None

        # Health Check
        if path == "/api/health":
            return self._send_json({
                "status": "ok", 
                "service": "FreshGuard Multi-Agent Decision & Evaluation Engine", 
                "version": "2.2.0",
                "auth_status": "authenticated" if user else "unauthenticated"
            })

        # Auth Me Check
        elif path == "/api/auth/me":
            if not user:
                return self._send_json({"authenticated": False, "user": None}, status=401)
            return self._send_json({"authenticated": True, "user": user})

        # Stores List (scoped to user if authenticated)
        elif path == "/api/stores":
            if user:
                stores = FreshGuardEngine.get_user_stores(user_id)
                # If demo account or admin, can fallback to all stores if none owned
                if not stores and user["role"] == "admin":
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM stores ORDER BY id")
                    stores = [dict(r) for r in cur.fetchall()]
                    conn.close()
                return self._send_json({"stores": stores})
            else:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT id, name, location_type, city, store_type FROM stores WHERE id IN ('STORE-101', 'STORE-102') ORDER BY id")
                stores = [dict(r) for r in cur.fetchall()]
                conn.close()
                return self._send_json({"stores": stores, "mode": "demo_preview"})

        # Overview Metrics (Customer Scoped)
        elif path == "/api/overview":
            store_id = query.get("store_id", "ALL")
            overview = FreshGuardEngine.get_overview_metrics(store_id=store_id, user_id=user_id)
            return self._send_json(overview)

        # Inventory Analytics (Customer Scoped)
        elif path == "/api/inventory":
            store_id = query.get("store_id", "ALL")
            department = query.get("department", "ALL")
            risk_filter = query.get("risk", "ALL")
            inventory = FreshGuardEngine.get_inventory_analytics(
                store_id=store_id, 
                department=department, 
                risk_filter=risk_filter,
                user_id=user_id
            )
            return self._send_json({"inventory": inventory, "count": len(inventory)})

        # Rescue Simulation (Customer Scoped)
        elif path == "/api/rescue/simulate":
            params = {
                "store_id": query.get("store_id", "ALL"),
                "foot_traffic_mult": float(query.get("foot_traffic_mult", 1.0)),
                "discount_aggressiveness": float(query.get("discount_aggressiveness", 1.0)),
                "allow_inter_store": query.get("allow_inter_store", "true").lower() == "true",
                "allow_food_bank": query.get("allow_food_bank", "true").lower() == "true"
            }
            scenario = FreshGuardEngine.run_rescue_scenario(params, user_id=user_id)
            return self._send_json(scenario)

        # Demo Scenario
        elif path == "/api/demo/milk-scenario":
            scenario = FreshGuardEngine.run_rescue_scenario({"allow_inter_store": True, "store_id": "ALL"}, user_id=user_id)
            milk_pouch_recs = [
                r for r in scenario["recommendations"] 
                if ("SKU-DAI-01" in r["sku"] or ("milk" in r["product_name"].lower() and "bread" not in r["product_name"].lower() and "paneer" not in r["product_name"].lower()))
            ]
            winning_milk = next((r for r in milk_pouch_recs if r.get("action_type") == "TRANSFER"), milk_pouch_recs[0] if milk_pouch_recs else None)
            return self._send_json({
                "scenario_name": "Fresh Milk Pouch Rebalancing Scenario",
                "source_store": "HITAM Campus Store (Surplus: 68 pouches on-hand, 2.2 days left)",
                "target_store": "Miyapur Neighbourhood Store (Deficit: 14 pouches on-hand, 42/day demand)",
                "winning_orchestrated_decision": winning_milk,
                "all_milk_recommendations": milk_pouch_recs
            })

        # Evaluation Scenarios
        elif path == "/api/evaluation/scenarios":
            return self._send_json({"scenarios": EvaluationSimulator.SCENARIOS})

        # Run 7-Day Fair Benchmark Evaluation
        elif path == "/api/evaluation/run":
            scen_key = query.get("scenario", "NORMAL")
            seed = int(query.get("seed", 42))
            eval_res = EvaluationSimulator.run_7day_simulation(scenario_key=scen_key, seed=seed)
            b = eval_res.get("baseline", {})
            fg = eval_res.get("freshguard", {})
            eval_res["baseline_results"] = {
                "total_food_waste_kg": round(b.get("units_expired", 0) * 0.45, 1),
                "total_revenue": b.get("gross_revenue", 0.0),
                "total_profit": b.get("gross_margin_dollars", 0.0),
                **b
            }
            eval_res["freshguard_results"] = {
                "total_food_waste_kg": round(fg.get("units_expired", 0) * 0.45, 1),
                "total_revenue": fg.get("gross_revenue", 0.0),
                "total_profit": fg.get("gross_margin_dollars", 0.0),
                **fg
            }
            return self._send_json(eval_res)

        # Historical Results & Audit Log (Customer Scoped)
        elif path == "/api/results":
            history = FreshGuardEngine.get_results_history(user_id=user_id)
            return self._send_json(history)

        elif path == "/api/audit-log":
            history = FreshGuardEngine.get_results_history(user_id=user_id)
            return self._send_json(history.get("executed_actions", []))

        # Realistic Sample CSV with Indian Grocery SKUs & Full Fields
        elif path == "/api/inventory/sample-csv":
            sample_content = (
                "Product Name,SKU,Category,Current Stock,Daily Sales,Unit Selling Price,Unit Cost,Expiry Date,Supplier,Incoming Stock,Delivery Date,Promotion Info\n"
                "Amul Taaza Toned Milk (500ml),SKU-DAI-001,Dairy & Eggs,45,28,27.0,22.0,2026-10-12 18:00,Amul Hyderabad Depot,20,2026-10-11,None\n"
                "Desi Hybrid Tomatoes (1kg),SKU-VEG-002,Vegetables & Fruits,35,14,40.0,26.0,2026-10-14 18:00,Bowenpally APMC,15,2026-10-12,Buy 2kg Get 5% Off\n"
                "Fresh Palak Spinach Bunch,SKU-VEG-003,Vegetables & Fruits,25,10,18.0,11.0,2026-10-11 18:00,Medchal Organic Farms,0,,Fresh Arrival\n"
                "Modern Special Milk Bread (400g),SKU-BAK-004,Bakery & Sweets,20,8,45.0,32.0,2026-10-13 18:00,Modern Food Enterprises,10,2026-10-12,None\n"
                "Milky Mist Malai Paneer (200g),SKU-DAI-005,Dairy & Eggs,18,6,95.0,72.0,2026-10-13 18:00,Milky Mist Cold Chain,0,,Weekend Offer\n"
                "Robusta Golden Bananas (1 Dozen),SKU-FRU-006,Vegetables & Fruits,30,12,60.0,42.0,2026-10-13 18:00,Kothapet Fruit Mandi,25,2026-10-12,None\n"
                "Fresh Coriander Bunch (Kothimeera),SKU-VEG-008,Vegetables & Fruits,40,15,15.0,8.0,2026-10-11 18:00,Gudimalkapur Mandi,0,,Clearance Item\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=\"sample_grocery_stock.csv\"")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(sample_content.encode("utf-8"))
            return

        # Google OAuth Config
        elif path == "/api/auth/google/config":
            return self._send_json(FreshGuardEngine.get_google_oauth_config())

        # Barcode Scanner & Lookup
        elif path == "/api/barcode/lookup":
            code = query.get("code") or query.get("barcode") or ""
            res = FreshGuardEngine.lookup_barcode(code, user_id=user_id)
            return self._send_json(res)

        # Customer Products (Private Ledger)
        elif path == "/api/customer/products":
            if not user:
                return self._send_json({"success": False, "error": "Authentication required to view your products."}, status=401)
            prods = FreshGuardEngine.get_customer_products(user["id"])
            return self._send_json({"success": True, "products": prods, "count": len(prods)})

        elif path in ("/api/customer/products/view", "/api/customer/products/get"):
            if not user:
                return self._send_json({"success": False, "error": "Authentication required."}, status=401)
            try:
                pid = int(query.get("id", 0))
            except (ValueError, TypeError):
                pid = 0
            prod = FreshGuardEngine.get_customer_product_by_id(user["id"], pid)
            if not prod:
                return self._send_json({"success": False, "error": "Product not found or access denied."}, status=404)
            return self._send_json({"success": True, "product": prod})

        # Static assets fallback
        if path == "/" or not path:
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        body = self._read_json_body()

        user = self._get_authenticated_user()
        user_id = user["id"] if user else None

        # ==========================================
        # AUTHENTICATION ROUTES
        # ==========================================
        if path in ("/api/auth/register", "/api/auth/signup"):
            username = body.get("username", "")
            email = body.get("email", "")
            password = body.get("password", "")
            result = FreshGuardEngine.register_user(username, email, password)
            return self._send_json(result, status=200 if result.get("success") else 400)

        elif path == "/api/auth/login":
            identifier = body.get("username") or body.get("email") or ""
            password = body.get("password", "")
            result = FreshGuardEngine.login_user(identifier, password)
            return self._send_json(result, status=200 if result.get("success") else 401)

        elif path == "/api/auth/demo-login":
            demo_key = body.get("demo_key", "demo_hitam")
            result = FreshGuardEngine.demo_login(demo_key)
            return self._send_json(result, status=200 if result.get("success") else 400)

        elif path in ("/api/auth/google", "/api/auth/google/login"):
            result = FreshGuardEngine.authenticate_google_user(body)
            return self._send_json(result, status=200 if result.get("success") else 400)

        elif path == "/api/auth/google/config":
            client_id = body.get("client_id", "")
            client_secret = body.get("client_secret", "")
            result = FreshGuardEngine.save_google_oauth_config(client_id, client_secret)
            return self._send_json(result)

        elif path == "/api/auth/logout":
            token = ""
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            if not token:
                token = body.get("token", "")
            success = FreshGuardEngine.logout_user(token)
            return self._send_json({"success": success, "message": "Logged out successfully."})

        # ==========================================
        # FIRST-TIME CUSTOMER ONBOARDING
        # ==========================================
        elif path == "/api/onboarding/complete":
            if not user:
                return self._send_json({"success": False, "error": "Authentication required for store onboarding."}, status=401)

            store_name = body.get("store_name", "")
            city = body.get("city", "Hyderabad")
            store_type = body.get("store_type", "Supermarket")
            branch_count = body.get("branch_count", 1)
            categories = body.get("categories", "Vegetables & Fruits, Dairy & Eggs, Bakery & Sweets")

            result = FreshGuardEngine.complete_onboarding(
                user_id=user["id"],
                store_name=store_name,
                city=city,
                store_type=store_type,
                branch_count=branch_count,
                categories=categories
            )
            return self._send_json(result, status=200 if result.get("success") else 400)

        # ==========================================
        # INVENTORY DATA MANAGEMENT
        # ==========================================
        elif path == "/api/inventory/preview-csv":
            csv_text = body.get("csv_text", "")
            preview = FreshGuardEngine.preview_csv_data(csv_text)
            return self._send_json(preview, status=200 if preview.get("success") else 400)

        elif path == "/api/inventory/upload-csv":
            csv_text = body.get("csv_text", "")
            store_id = body.get("store_id")
            result = FreshGuardEngine.upload_csv_inventory(
                csv_text=csv_text, 
                default_store_id=store_id, 
                user_id=user_id
            )
            return self._send_json(result, status=200 if result.get("success") else 400)

        elif path == "/api/inventory/add":
            result = FreshGuardEngine.add_inventory_item(body, user_id=user_id)
            return self._send_json(result, status=200 if result.get("success") else 400)

        elif path in ("/api/inventory/edit", "/api/inventory/update"):
            if not user:
                return self._send_json({"success": False, "error": "Authentication required to edit products."}, status=401)
            inv_id = body.get("inventory_id") or body.get("id")
            if not inv_id:
                return self._send_json({"success": False, "error": "Missing inventory_id"}, status=400)
            result = FreshGuardEngine.edit_inventory_item(user["id"], int(inv_id), body)
            return self._send_json(result, status=200 if result.get("success") else 400)

        elif path == "/api/inventory/delete":
            if not user:
                return self._send_json({"success": False, "error": "Authentication required to delete products."}, status=401)
            inv_id = body.get("inventory_id") or body.get("id")
            if not inv_id:
                return self._send_json({"success": False, "error": "Missing inventory_id"}, status=400)
            result = FreshGuardEngine.delete_inventory_item(user["id"], int(inv_id))
            return self._send_json(result, status=200 if result.get("success") else 400)

        # ==========================================
        # CUSTOMER PRODUCTS (PRIVATE LEDGER & CRUD)
        # ==========================================
        elif path in ("/api/customer/products/add", "/api/customer/products"):
            if not user:
                return self._send_json({"success": False, "error": "Authentication required to add products."}, status=401)
            result = FreshGuardEngine.add_customer_product(user["id"], body)
            return self._send_json(result, status=200 if result.get("success") else 400)

        elif path in ("/api/customer/products/update", "/api/customer/products/edit"):
            if not user:
                return self._send_json({"success": False, "error": "Authentication required to edit products."}, status=401)
            pid = body.get("id") or body.get("product_id")
            if not pid:
                return self._send_json({"success": False, "error": "Missing product ID."}, status=400)
            try:
                pid_int = int(pid)
            except (ValueError, TypeError):
                return self._send_json({"success": False, "error": "Invalid product ID."}, status=400)
            result = FreshGuardEngine.update_customer_product(user["id"], pid_int, body)
            return self._send_json(result, status=200 if result.get("success") else 400)

        elif path == "/api/customer/products/delete":
            if not user:
                return self._send_json({"success": False, "error": "Authentication required to delete products."}, status=401)
            pid = body.get("id") or body.get("product_id")
            if not pid:
                return self._send_json({"success": False, "error": "Missing product ID."}, status=400)
            try:
                pid_int = int(pid)
            except (ValueError, TypeError):
                return self._send_json({"success": False, "error": "Invalid product ID."}, status=400)
            result = FreshGuardEngine.delete_customer_product(user["id"], pid_int)
            return self._send_json(result, status=200 if result.get("success") else 400)

        # ==========================================
        # RESCUE SCENARIOS & DECISION PIPELINE
        # ==========================================
        elif path == "/api/rescue/simulate":
            scenario = FreshGuardEngine.run_rescue_scenario(body, user_id=user_id)
            return self._send_json(scenario)

        elif path in ("/api/rescue/approve", "/api/rescue/execute"):
            result = FreshGuardEngine.execute_action(body, user_id=user_id)
            return self._send_json(result)

        elif path == "/api/rescue/modify-approve":
            action_payload = body.get("action_payload", {})
            modified_params = body.get("modified_params", {})
            result = FreshGuardEngine.modify_and_execute_action(action_payload, modified_params, user_id=user_id)
            return self._send_json(result)

        elif path == "/api/rescue/reject":
            action_payload = body.get("action_payload", {})
            rejection_reason = body.get("rejection_reason", "Manager override")
            result = FreshGuardEngine.reject_action(action_payload, rejection_reason, user_id=user_id)
            return self._send_json(result)

        elif path == "/api/rescue/execute-batch":
            actions = body.get("actions", [])
            results = []
            for act in actions:
                res = FreshGuardEngine.execute_action(act, user_id=user_id)
                results.append(res)
            return self._send_json({
                "success": True, 
                "executed_count": len(results), 
                "results": results
            })

        # ==========================================
        # EVALUATION SIMULATOR
        # ==========================================
        elif path == "/api/evaluation/run":
            scen_key = body.get("scenario_key", "NORMAL")
            seed = int(body.get("seed", 42))
            eval_res = EvaluationSimulator.run_7day_simulation(scenario_key=scen_key, seed=seed)
            b = eval_res.get("baseline", {})
            fg = eval_res.get("freshguard", {})
            eval_res["baseline_results"] = {
                "total_food_waste_kg": round(b.get("units_expired", 0) * 0.45, 1),
                "total_revenue": b.get("gross_revenue", 0.0),
                "total_profit": b.get("gross_margin_dollars", 0.0),
                **b
            }
            eval_res["freshguard_results"] = {
                "total_food_waste_kg": round(fg.get("units_expired", 0) * 0.45, 1),
                "total_revenue": fg.get("gross_revenue", 0.0),
                "total_profit": fg.get("gross_margin_dollars", 0.0),
                **fg
            }
            return self._send_json(eval_res)

        elif path == "/api/reset-data":
            seed_data(force=True)
            return self._send_json({"success": True, "message": "Database reset to initial demo state."})

        self.send_error(404, "Endpoint not found")

class RobustThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass

def run_server(port=PORT):
    init_db()
    seed_data(force=False)

    handler = FreshGuardRequestHandler
    with RobustThreadingServer(("", port), handler) as httpd:
        print(f"=====================================================")
        print(f" FreshGuard Customer Access & Optimization Engine running!")
        print(f" URL: http://localhost:{port}")
        print(f"=====================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down FreshGuard server.")
            httpd.server_close()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_server(port)
