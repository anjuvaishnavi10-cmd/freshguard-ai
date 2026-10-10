"""
FreshGuard - Automated Test Suite for 7-Day Reproducible Evaluation Simulator
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery
"""

import unittest
import os
import sys
import copy

from freshguard_db import init_db, seed_data
from evaluation_simulator import EvaluationSimulator

class TestEvaluationSimulator(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        seed_data(force=True)

    # 1. CONSISTENT STARTING CONDITIONS
    def test_01_identical_initial_conditions(self):
        state_base = EvaluationSimulator.get_initial_simulation_state("NORMAL")
        state_fg = copy.deepcopy(state_base)

        self.assertEqual(len(state_base), len(state_fg))
        for b, f in zip(state_base, state_fg):
            self.assertEqual(b["sku"], f["sku"])
            self.assertEqual(b["store_id"], f["store_id"])
            self.assertEqual(b["stock_on_hand"], f["stock_on_hand"])
            self.assertEqual(b["cost_price"], f["cost_price"])
            self.assertEqual(b["selling_price"], f["selling_price"])
            self.assertEqual(b["sim_days_to_expiry"], f["sim_days_to_expiry"])

    # 2. DETERMINISTIC REPEATABILITY
    def test_02_deterministic_repeatability(self):
        sim1 = EvaluationSimulator.run_7day_simulation(scenario_key="NORMAL", seed=42)
        sim2 = EvaluationSimulator.run_7day_simulation(scenario_key="NORMAL", seed=42)

        # Baseline repeatability
        self.assertEqual(sim1["baseline"]["units_sold"], sim2["baseline"]["units_sold"])
        self.assertEqual(sim1["baseline"]["units_expired"], sim2["baseline"]["units_expired"])
        self.assertEqual(sim1["baseline"]["gross_revenue"], sim2["baseline"]["gross_revenue"])

        # FreshGuard repeatability
        self.assertEqual(sim1["freshguard"]["units_sold"], sim2["freshguard"]["units_sold"])
        self.assertEqual(sim1["freshguard"]["units_expired"], sim2["freshguard"]["units_expired"])
        self.assertEqual(sim1["freshguard"]["gross_revenue"], sim2["freshguard"]["gross_revenue"])

    # 3. EXPIRY HANDLING & ZERO CONSTRAINT VIOLATIONS
    def test_03_expiry_handling_and_no_negative_stock(self):
        sim = EvaluationSimulator.run_7day_simulation(scenario_key="EXCESS_EXPIRING", seed=42)

        # Constraint violations must strictly be 0
        self.assertEqual(sim["baseline"]["constraint_violations"], 0)
        self.assertEqual(sim["freshguard"]["constraint_violations"], 0)

        # FreshGuard should divert and rescue waste compared to baseline
        self.assertLessEqual(sim["freshguard"]["units_expired"], sim["baseline"]["units_expired"])

    # 4. METRIC CALCULATION INTEGRITY
    def test_04_metric_calculation_formulas(self):
        sim = EvaluationSimulator.run_7day_simulation(scenario_key="NORMAL", seed=42)
        fg = sim["freshguard"]

        # Gross margin dollars = Revenue - COGS - Transfer Costs
        expected_margin = round(fg["gross_revenue"] - fg["cost_of_goods_sold"] - fg["transfer_costs"], 2)
        self.assertAlmostEqual(fg["gross_margin_dollars"], expected_margin, delta=0.01)

        # Fulfillment rate formula check
        attempted = fg["units_sold"] + fg["stockout_units"]
        expected_rate = round((fg["units_sold"] / attempted * 100), 1) if attempted > 0 else 100.0
        self.assertEqual(fg["fulfillment_rate_pct"], expected_rate)

    # 5. ALL 4 SCENARIOS EXECUTION
    def test_05_all_scenario_modes(self):
        for scen_key in ["NORMAL", "EXCESS_EXPIRING", "DEMAND_SURGE_URBAN", "TRANSFER_CONSTRAINED"]:
            result = EvaluationSimulator.run_7day_simulation(scenario_key=scen_key, seed=42)
            self.assertIn("baseline", result)
            self.assertIn("freshguard", result)
            self.assertIn("comparison", result)
            self.assertEqual(result["baseline"]["constraint_violations"], 0)
            self.assertEqual(result["freshguard"]["constraint_violations"], 0)
            self.assertTrue(len(result["comparison"]["trade_offs_summary"]) > 0)

    # 6. INVENTORY CONSERVATION INVARIANT (INFLOW == OUTFLOW)
    def test_06_inventory_conservation_strict_inflow_outflow(self):
        for scen_key in ["NORMAL", "EXCESS_EXPIRING", "DEMAND_SURGE_URBAN", "TRANSFER_CONSTRAINED"]:
            result = EvaluationSimulator.run_7day_simulation(scenario_key=scen_key, seed=42)
            
            # Baseline conservation check
            b = result["baseline"]
            b_inflow = b["initial_inventory_units"] + b["restocked_units"]
            b_outflow = b["units_sold"] + b["units_expired"] + b["units_donated"] + b["ending_inventory_units"]
            self.assertEqual(b_inflow, b_outflow, f"Baseline inventory leak in {scen_key}: {b_inflow} != {b_outflow}")
            self.assertTrue(b["inventory_conservation_verified"])

            # FreshGuard conservation check
            fg = result["freshguard"]
            fg_inflow = fg["initial_inventory_units"] + fg["restocked_units"]
            fg_outflow = fg["units_sold"] + fg["units_expired"] + fg["units_donated"] + fg["ending_inventory_units"]
            self.assertEqual(fg_inflow, fg_outflow, f"FreshGuard inventory leak in {scen_key}: {fg_inflow} != {fg_outflow}")
            self.assertTrue(fg["inventory_conservation_verified"])

if __name__ == "__main__":
    unittest.main()
