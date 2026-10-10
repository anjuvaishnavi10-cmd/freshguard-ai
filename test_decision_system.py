"""
FreshGuard - Automated Test Suite for Specialized Multi-Agent Decision System
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery
"""

import unittest
import os
import sys
import datetime
import json

from freshguard_db import init_db, seed_data, get_connection
from agents.demand_agent import DemandAgent
from agents.freshness_agent import FreshnessAgent
from agents.action_agent import ActionAgent
from agents.orchestrator import Orchestrator
from engine import FreshGuardEngine

class TestDecisionSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        seed_data(force=True)

    def setUp(self):
        # Fresh seed for predictable state
        seed_data(force=True)

    # -------------------------------------------------------------
    # 1. EXPIRY RISK & SHELF-LIFE DECAY TESTS
    # -------------------------------------------------------------
    def test_01_expiry_risk_decay_calculation(self):
        now = datetime.datetime.now()
        
        # Test item 1: Critical (expires in 12 hours)
        mock_item_critical = {
            "inventory_id": 991,
            "sku": "SKU-BAK-01",
            "product_name": "Classic White Bread Loaf",
            "department": "Bakery",
            "stock_on_hand": 30,
            "safety_stock": 10,
            "cost_price": 28.00,
            "selling_price": 40.00,
            "co2_footprint_kg": 0.5,
            "received_date": (now - datetime.timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
            "expiry_date": (now + datetime.timedelta(hours=12)).strftime("%Y-%m-%d %H:%M"),
            "storage_zone": "Ambient (Dry)"
        }
        mock_demand = {"effective_daily_rate": 10.0, "baseline_daily_demand": 10.0}

        freshness_eval = FreshnessAgent.evaluate_freshness(mock_item_critical, mock_demand, current_time=now)
        
        self.assertAlmostEqual(freshness_eval["hours_to_expiry"], 12.0, delta=0.5)
        self.assertEqual(freshness_eval["risk_status"], "CRITICAL_EXPIRY_RISK")
        self.assertGreater(freshness_eval["projected_waste_units"], 0)
        self.assertGreater(freshness_eval["risk_score"], 70)
        self.assertTrue(len(freshness_eval["rule_reasons"]) > 0)

    # -------------------------------------------------------------
    # 2. LOW STOCK & STOCKOUT THREAT DETECTION
    # -------------------------------------------------------------
    def test_02_stockout_threat_detection(self):
        now = datetime.datetime.now()
        mock_item_depleted = {
            "inventory_id": 992,
            "sku": "SKU-DAI-01",
            "product_name": "Fresh Milk Pouch (500 ml)",
            "department": "Dairy",
            "stock_on_hand": 5,      # Low stock
            "safety_stock": 20,     # High safety threshold
            "cost_price": 24.00,
            "selling_price": 30.00,
            "co2_footprint_kg": 0.9,
            "received_date": (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
            "expiry_date": (now + datetime.timedelta(days=5)).strftime("%Y-%m-%d %H:%M"),
            "storage_zone": "Chilled (2-4°C)"
        }
        mock_demand = {"effective_daily_rate": 25.0, "baseline_daily_demand": 25.0}

        freshness_eval = FreshnessAgent.evaluate_freshness(mock_item_depleted, mock_demand, current_time=now)
        self.assertEqual(freshness_eval["risk_status"], "STOCKOUT_RISK")
        self.assertLessEqual(freshness_eval["days_of_supply"], 0.5)

    # -------------------------------------------------------------
    # 3. VALID & INVALID INTER-STORE TRANSFERS
    # -------------------------------------------------------------
    def test_03_valid_and_invalid_transfers(self):
        now = datetime.datetime.now()

        # Case A: VALID Transfer (Source has surplus, target has deficit, safe transit shelf life)
        source_item = {
            "inventory_id": 993,
            "sku": "SKU-DAI-01",
            "product_name": "Fresh Milk Pouch (500 ml)",
            "department": "Dairy",
            "store_id": "STORE-101",
            "store_name": "HITAM Campus Store",
            "stock_on_hand": 68,
            "safety_stock": 20,
            "cost_price": 24.00,
            "selling_price": 30.00,
            "co2_footprint_kg": 0.9,
            "expiry_date": (now + datetime.timedelta(hours=48)).strftime("%Y-%m-%d %H:%M")
        }
        source_freshness = {"projected_waste_units": 25.0, "hours_to_expiry": 48.0, "risk_status": "MODERATE_EXPIRY_RISK"}
        
        target_item = {
            "inventory_id": 994,
            "sku": "SKU-DAI-01",
            "product_name": "Fresh Milk Pouch (500 ml)",
            "department": "Dairy",
            "store_id": "STORE-102",
            "store_name": "Miyapur Neighbourhood Store",
            "stock_on_hand": 14,
            "safety_stock": 35,
            "cost_price": 24.00,
            "selling_price": 30.00,
            "co2_footprint_kg": 0.9
        }
        target_freshness = {"risk_status": "STOCKOUT_RISK"}
        target_demand = {"effective_daily_rate": 42.0}

        transfer_valid = ActionAgent.evaluate_inter_store_transfer_candidate(
            source_item, source_freshness, target_item, target_freshness, target_demand
        )
        self.assertIsNotNone(transfer_valid, "Valid transfer must be generated")
        self.assertGreater(transfer_valid["units_affected"], 0)
        self.assertGreater(transfer_valid["net_economic_yield"], 0)
        self.assertTrue(all(c["passed"] for c in transfer_valid["constraints_checked"]))

        # Case B: INVALID Transfer (Expiry window too short for transit: only 0.2h remaining)
        source_short_freshness = {"projected_waste_units": 25.0, "hours_to_expiry": 0.2, "risk_status": "CRITICAL_EXPIRY_RISK"}
        transfer_invalid_transit = ActionAgent.evaluate_inter_store_transfer_candidate(
            source_item, source_short_freshness, target_item, target_freshness, target_demand
        )
        self.assertIsNone(transfer_invalid_transit, "Transfer must be rejected when shelf life is insufficient for transit")

    # -------------------------------------------------------------
    # 4. MINIMUM PRICE CONSTRAINTS & DYNAMIC MARKDOWN ELASTICITY
    # -------------------------------------------------------------
    def test_04_minimum_price_and_elasticity_markdown(self):
        now = datetime.datetime.now()
        item = {
            "inventory_id": 995,
            "sku": "SKU-BAK-02",
            "product_name": "Fresh Ladi Pav (6 Pieces)",
            "department": "Bakery",
            "store_id": "STORE-101",
            "store_name": "HITAM Campus Store",
            "stock_on_hand": 25,
            "cost_price": 18.00,
            "selling_price": 30.00,
            "co2_footprint_kg": 0.4,
            "expiry_date": (now + datetime.timedelta(hours=22)).strftime("%Y-%m-%d %H:%M")
        }
        freshness = {"projected_waste_units": 15.0, "hours_to_expiry": 22.0}
        demand = {"baseline_daily_demand": 12.0, "effective_daily_rate": 12.0, "elasticity_coeff": 1.55}

        markdown_cand = ActionAgent.evaluate_markdown_candidate(item, freshness, demand, discount_aggressiveness=1.0)
        self.assertIsNotNone(markdown_cand)
        self.assertGreaterEqual(markdown_cand["discounted_price"], item["cost_price"], "Price floor check: markdown price must be above cost")
        self.assertEqual(markdown_cand["confidence"], "HIGH")

    # -------------------------------------------------------------
    # 5. CONFLICT RESOLUTION & DOUBLE-COUNTING PREVENTION
    # -------------------------------------------------------------
    def test_05_orchestrator_conflict_resolution_and_no_double_counting(self):
        all_items = FreshGuardEngine.get_inventory_analytics(store_id="ALL")
        scenario = Orchestrator.run_pipeline(all_items, {"allow_inter_store": True, "allow_food_bank": True})
        
        recs = scenario["recommendations"]
        self.assertGreater(len(recs), 0)

        # Verify that each inventory_id has EXACTLY ONE winning primary recommendation
        seen_inventory_ids = set()
        for r in recs:
            inv_id = r["inventory_id"]
            self.assertNotIn(inv_id, seen_inventory_ids, f"Inventory batch {inv_id} was double-allocated in recommendations!")
            seen_inventory_ids.add(inv_id)

    # -------------------------------------------------------------
    # 6. HUMAN MANAGER REVIEW: APPROVE, MODIFY, REJECT & AUDIT LOG
    # -------------------------------------------------------------
    def test_06_human_manager_review_lifecycle(self):
        scenario = FreshGuardEngine.run_rescue_scenario({"store_id": "STORE-101"})
        self.assertGreater(len(scenario["recommendations"]), 0)
        rec = scenario["recommendations"][0]

        # 6A. Test Rejection (Must NOT change inventory stock, must log to DB)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT stock_on_hand FROM inventory WHERE id = ?", (rec["inventory_id"],))
        stock_before_reject = cur.fetchone()[0]
        conn.close()

        rej_res = FreshGuardEngine.reject_action(rec, "Vendor return planned by manager")
        self.assertTrue(rej_res["success"])
        self.assertEqual(rej_res["status"], "REJECTED")

        # Verify stock was untouched
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT stock_on_hand FROM inventory WHERE id = ?", (rec["inventory_id"],))
        stock_after_reject = cur.fetchone()[0]
        conn.close()
        self.assertEqual(stock_before_reject, stock_after_reject, "Rejecting an action must never alter physical stock!")

        # 6B. Test Modified Approval (Manager adjusts discount %)
        mod_res = FreshGuardEngine.modify_and_execute_action(rec, {
            "discount_pct": 25,
            "notes": "Manager adjusted discount to 25% for gentle clearance"
        })
        self.assertTrue(mod_res["success"])

        # 6C. Check Cumulative Audit History
        history = FreshGuardEngine.get_results_history()
        self.assertGreaterEqual(history["cumulative_impact"]["total_actions_executed"], 1)
        self.assertGreaterEqual(history["cumulative_impact"]["total_rejections"], 1)

    # -------------------------------------------------------------
    # 7. REPRODUCIBLE MILK SCENARIO BENCHMARK
    # -------------------------------------------------------------
    def test_07_milk_scenario_benchmark(self):
        scenario = FreshGuardEngine.run_rescue_scenario({"allow_inter_store": True, "store_id": "ALL"})
        recs = scenario["recommendations"]

        # Find the recommendation for Fresh Milk Pouch (SKU-DAI-01)
        milk_rec = next((r for r in recs if r["sku"] == "SKU-DAI-01"), None)
        self.assertIsNotNone(milk_rec, "Orchestrator must produce a recommendation for Fresh Milk Pouch")
        self.assertEqual(milk_rec["action_type"], "TRANSFER", "Fresh Milk Pouch should resolve to Transfer due to higher net yield vs markdown")
        self.assertEqual(milk_rec["source_store_id"], "STORE-101", "Source store must be HITAM Campus Store (Store 101)")
        self.assertEqual(milk_rec["target_store_id"], "STORE-102", "Destination store must be Miyapur Neighbourhood Store (Store 102)")
        self.assertGreater(milk_rec["net_economic_yield"], 0)

    # -------------------------------------------------------------
    # 8. REPLENISHMENT CANDIDATE EVALUATION & EXECUTION
    # -------------------------------------------------------------
    def test_08_replenishment_candidate_evaluation_and_execution(self):
        now = datetime.datetime.now()
        low_stock_item = {
            "inventory_id": 996,
            "sku": "SKU-DAI-07",
            "product_name": "Spiced Buttermilk / Chaas (200 ml)",
            "department": "Dairy",
            "store_id": "STORE-101",
            "store_name": "HITAM Campus Store",
            "stock_on_hand": 5,
            "safety_stock": 15,
            "cost_price": 10.00,
            "selling_price": 15.00,
            "storage_zone": "Chilled (2-4°C)",
            "co2_footprint_kg": 0.3,
            "expiry_date": (now + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
        }
        freshness = {"risk_status": "STOCKOUT_RISK", "days_of_supply": 0.5}
        demand = {"effective_daily_rate": 10.0, "baseline_daily_demand": 10.0}

        rep_cand = ActionAgent.evaluate_replenishment_candidate(low_stock_item, freshness, demand)
        self.assertIsNotNone(rep_cand, "Depleted stock must trigger a replenishment candidate")
        self.assertEqual(rep_cand["action_type"], "REPLENISH")
        self.assertGreaterEqual(rep_cand["units_affected"], 10)
        self.assertGreater(rep_cand["net_economic_yield"], 0)
        self.assertTrue(all(c["passed"] for c in rep_cand["constraints_checked"]))

        # Test execution in database
        conn = get_connection()
        cur = conn.cursor()
        # Insert a temporary row for inventory_id 996
        cur.execute("""
        INSERT INTO inventory (id, store_id, sku, batch_number, stock_on_hand, safety_stock, received_date, expiry_date, avg_daily_sales, forecast_daily_demand)
        VALUES (996, 'STORE-101', 'SKU-DAI-07', 'B-TEST-996', 5, 15, '2026-10-08', '2026-10-14', 10.0, 10.0)
        """)
        conn.commit()
        conn.close()

        exec_res = FreshGuardEngine.execute_action(rep_cand)
        self.assertTrue(exec_res["success"])

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT stock_on_hand FROM inventory WHERE id = 996")
        updated_stock = cur.fetchone()[0]
        conn.close()
        self.assertEqual(updated_stock, 5 + rep_cand["units_affected"], "Executing replenishment must increment physical stock in inventory")

    # -------------------------------------------------------------
    # 9. DEMAND AGENT TRANSPARENT FORECAST & LIMITATION DETECTION
    # -------------------------------------------------------------
    def test_09_demand_agent_transparency_and_limitations(self):
        # Case A: High variance between historical sales and baseline forecast
        item_high_var = {
            "sku": "SKU-FRU-04",
            "product_name": "Fresh-Cut Fruit Bowl",
            "department": "Fruits",
            "store_id": "STORE-101",
            "store_name": "HITAM Campus Store",
            "avg_daily_sales": 10.0,
            "forecast_daily_demand": 18.0,  # 80% higher than historical avg
            "stock_on_hand": 20,
            "safety_stock": 10
        }
        forecast_high_var = DemandAgent.forecast_demand(item_high_var, days_ahead=3)
        self.assertEqual(forecast_high_var["confidence"], "MEDIUM")
        self.assertTrue(any("High variance" in lim for lim in forecast_high_var["limitations"]))
        self.assertEqual(len(forecast_high_var["daily_breakdown"]), 3)

        # Case B: Constrained by impending stockout
        item_stockout = {
            "sku": "SKU-DAI-01",
            "product_name": "Fresh Milk Pouch (500 ml)",
            "department": "Dairy",
            "store_id": "STORE-102",
            "store_name": "Miyapur Neighbourhood Store",
            "avg_daily_sales": 40.0,
            "forecast_daily_demand": 42.0,
            "stock_on_hand": 10,
            "safety_stock": 35
        }
        forecast_stockout = DemandAgent.forecast_demand(item_stockout, days_ahead=3)
        self.assertTrue(any("stockout" in lim.lower() for lim in forecast_stockout["limitations"]))

if __name__ == "__main__":
    unittest.main()
