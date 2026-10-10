"""
Unit and Integration Test Suite for FreshGuard
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery
"""

import unittest
import os
import sys
import datetime

from freshguard_db import init_db, seed_data, get_connection
from engine import FreshGuardEngine

class TestFreshGuard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        seed_data(force=True)

    def test_01_database_seed_integrity(self):
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM stores")
        store_count = cur.fetchone()[0]
        self.assertEqual(store_count, 2, "Must have exactly 2 simulated grocery stores")

        cur.execute("SELECT COUNT(*) FROM products")
        product_count = cur.fetchone()[0]
        self.assertEqual(product_count, 28, "Must have 28 perishable SKUs across 4 departments")

        cur.execute("SELECT COUNT(*) FROM inventory")
        inv_count = cur.fetchone()[0]
        self.assertEqual(inv_count, 56, "Must have 56 perishable batches across both stores")
        conn.close()

    def test_02_overview_metrics_calculation(self):
        overview = FreshGuardEngine.get_overview_metrics(store_id="ALL")
        self.assertIn("total_skus", overview)
        self.assertGreater(overview["critical_count"], 0, "Should detect critical expiry items")
        self.assertGreater(overview["total_retail_value_at_risk"], 0, "Should calculate positive at-risk value")
        self.assertIsInstance(overview["department_breakdown"], list)
        self.assertEqual(len(overview["department_breakdown"]), 4, "Should have all 4 departments")

    def test_03_scenario_simulation_reasoning(self):
        scenario = FreshGuardEngine.run_rescue_scenario({
            "foot_traffic_mult": 1.0,
            "discount_aggressiveness": 1.0,
            "allow_inter_store": True,
            "allow_food_bank": True
        })
        self.assertIn("recommendations", scenario)
        recs = scenario["recommendations"]
        self.assertGreater(len(recs), 0, "Scenario should yield rescue recommendations")
        
        # Verify recommendation structure
        first_rec = recs[0]
        self.assertIn("action_id", first_rec)
        self.assertIn("action_type", first_rec)
        self.assertIn("projected_revenue_saved", first_rec)
        self.assertIn("rationale", first_rec)
        self.assertIn("evidence", first_rec)
        self.assertTrue(len(first_rec["evidence"]) >= 2, "Should provide supporting evidence data points")

    def test_04_action_execution_workflow(self):
        # Pick one recommendation and execute
        scenario = FreshGuardEngine.run_rescue_scenario({"store_id": "STORE-101"})
        self.assertTrue(len(scenario["recommendations"]) > 0)
        target_rec = scenario["recommendations"][0]

        result = FreshGuardEngine.execute_action(target_rec)
        self.assertTrue(result["success"], "Action execution should succeed")
        self.assertIn("action_record_id", result)

        # Check results ledger
        history = FreshGuardEngine.get_results_history()
        self.assertGreaterEqual(history["cumulative_impact"]["total_actions_executed"], 1)
        self.assertGreater(history["cumulative_impact"]["total_revenue_saved"], 0)

if __name__ == "__main__":
    unittest.main()
