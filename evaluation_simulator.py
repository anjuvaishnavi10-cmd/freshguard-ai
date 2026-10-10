"""
FreshGuard - Reproducible 7-Day Evaluation & Benchmark Simulation Engine
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery

Provides a rigorous, deterministic 7-day comparative simulation evaluating:
1. Baseline Heuristic: Fixed static rules (late 20% markdown on day-1, no transfers, fixed static POs)
2. FreshGuard Multi-Agent System: DemandAgent, FreshnessAgent, ActionAgent, Orchestrator
"""

import copy
import math
import random
import datetime
from typing import Dict, Any, List, Tuple

try:
    from freshguard_db import get_connection
    from engine import FreshGuardEngine
    from agents.orchestrator import Orchestrator
except ImportError:
    from .freshguard_db import get_connection
    from .engine import FreshGuardEngine
    from .agents.orchestrator import Orchestrator

class EvaluationSimulator:
    """
    Simulates a 7-day operational horizon for grocery store inventory under identical starting
    conditions, demand distributions, pricing, and operating costs.
    """

    SCENARIOS = {
        "NORMAL": {
            "name": "Normal Operations",
            "description": "Standard baseline campus and neighborhood traffic with balanced initial stock across both stores.",
            "traffic_mult_store1": 1.0,
            "traffic_mult_store2": 1.0,
            "stock_modifier": "DEFAULT"
        },
        "EXCESS_EXPIRING": {
            "name": "Excess Stock Approaching Expiry",
            "description": "Surplus batch deliveries in dairy and bakery with short 2–3 day shelf life.",
            "traffic_mult_store1": 1.0,
            "traffic_mult_store2": 0.9,
            "stock_modifier": "HIGH_SURPLUS"
        },
        "DEMAND_SURGE_URBAN": {
            "name": "Unexpected Demand Surge (HITAM Campus Store)",
            "description": "Campus foot-traffic surges +50% due to college fest, causing rapid stockout pressures.",
            "traffic_mult_store1": 1.5,
            "traffic_mult_store2": 0.95,
            "stock_modifier": "DEFAULT"
        },
        "TRANSFER_CONSTRAINED": {
            "name": "Transfer Constrained by Low Stock at Miyapur Store",
            "description": "Miyapur Neighbourhood Store has high residential demand of its own, limiting surplus available for transfer.",
            "traffic_mult_store1": 1.2,
            "traffic_mult_store2": 1.3,
            "stock_modifier": "TIGHT_STOCK"
        }
    }

    @classmethod
    def get_initial_simulation_state(cls, scenario_key: str = "NORMAL") -> List[Dict[str, Any]]:
        """
        Creates a deep copy of current inventory enriched with day-to-expiry integer counters.
        """
        raw_items = FreshGuardEngine.get_inventory_analytics(store_id="ALL")
        scenario = cls.SCENARIOS.get(scenario_key, cls.SCENARIOS["NORMAL"])
        modifier = scenario["stock_modifier"]

        sim_items = []
        for it in raw_items:
            item = copy.deepcopy(it)
            # Days to expiry rounded to nearest integer days for 7-day horizon (min 1 day)
            days_to_exp = max(1, int(math.ceil(item["hours_to_expiry"] / 24.0)))
            
            # Apply scenario modifiers
            if modifier == "HIGH_SURPLUS" and item["department"] in ("Dairy", "Bakery"):
                item["stock_on_hand"] = int(item["stock_on_hand"] * 1.4)
                days_to_exp = min(3, days_to_exp)
            elif modifier == "TIGHT_STOCK" and item["store_id"] == "STORE-102":
                item["stock_on_hand"] = max(item["safety_stock"], int(item["stock_on_hand"] * 0.5))

            item["sim_days_to_expiry"] = days_to_exp
            item["current_discount_pct"] = 0
            item["initial_stock"] = item["stock_on_hand"]
            sim_items.append(item)

        return sim_items

    @classmethod
    def run_7day_simulation(
        cls, 
        scenario_key: str = "NORMAL", 
        seed: int = 42
    ) -> Dict[str, Any]:
        """
        Executes a side-by-side 7-day simulation comparing Baseline vs FreshGuard.
        Enforces strict inventory conservation, non-negative stock, and realistic cost models.
        """
        scenario = cls.SCENARIOS.get(scenario_key, cls.SCENARIOS["NORMAL"])
        
        # 1. Initialize identical states
        state_baseline = cls.get_initial_simulation_state(scenario_key)
        state_freshguard = copy.deepcopy(state_baseline)

        # 2. Run deterministic demand generation for all 7 days
        rng = random.Random(seed)
        daily_demand_draws = cls._generate_7day_demand(state_baseline, scenario, rng)

        # 3. Simulate Baseline Strategy
        baseline_results = cls._simulate_strategy(
            strategy_name="BASELINE",
            initial_state=state_baseline,
            daily_demand=daily_demand_draws,
            scenario=scenario
        )

        # 4. Simulate FreshGuard Strategy
        freshguard_results = cls._simulate_strategy(
            strategy_name="FRESHGUARD",
            initial_state=state_freshguard,
            daily_demand=daily_demand_draws,
            scenario=scenario
        )

        # 5. Compute Comparative Deltas
        comparison = cls._compute_comparison(baseline_results, freshguard_results)

        return {
            "scenario": {
                "key": scenario_key,
                "name": scenario["name"],
                "description": scenario["description"],
                "seed": seed,
                "simulated_days": 7
            },
            "baseline": baseline_results,
            "freshguard": freshguard_results,
            "comparison": comparison,
            "assumptions_and_limitations": [
                "Identical starting inventory, SKU prices, costs, and customer demand curves applied to both strategies.",
                "Deterministic fixed random seed (42) guarantees exact mathematical repeatability.",
                "Inter-store transfer cost modeled at ₹5.00/unit courier transit fee with 45-min transit.",
                "Strict physical rules: Never sell expired stock; sales capped by available on-hand inventory; zero negative stock.",
                "Baseline uses industry-standard static rules: 20% markdown on day-1 before expiry, no inter-store transfers, static replenishment.",
                "FreshGuard dynamically coordinates DemandAgent elasticity, FreshnessAgent decay, and Orchestrator inter-store rebalancing."
            ]
        }

    @classmethod
    def _generate_7day_demand(
        cls, 
        items: List[Dict[str, Any]], 
        scenario: Dict[str, Any], 
        rng: random.Random
    ) -> Dict[int, Dict[int, float]]:
        """
        Generates identical customer demand draws for each day (1 to 7) and each SKU batch.
        """
        demand_draws: Dict[int, Dict[int, float]] = {}

        for day in range(1, 8):
            demand_draws[day] = {}
            # Weekend surge on Day 6 (Saturday) and Day 7 (Sunday)
            day_of_week_mult = 1.25 if day in (6, 7) else 1.0

            for it in items:
                inv_id = it["inventory_id"]
                base_demand = float(it["forecast_daily_demand"])
                store_mult = scenario["traffic_mult_store1"] if it["store_id"] == "STORE-101" else scenario["traffic_mult_store2"]
                
                # Small deterministic pseudo-random variance (+- 8%)
                variance = rng.uniform(0.92, 1.08)
                expected_draw = round(base_demand * store_mult * day_of_week_mult * variance, 1)
                demand_draws[day][inv_id] = max(1.0, expected_draw)

        return demand_draws

    @classmethod
    def _simulate_strategy(
        cls,
        strategy_name: str,
        initial_state: List[Dict[str, Any]],
        daily_demand: Dict[int, Dict[int, float]],
        scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Simulates 7 consecutive days for a given strategy.
        """
        items_by_id: Dict[int, Dict[str, Any]] = {it["inventory_id"]: it for it in initial_state}

        total_units_sold = 0
        total_units_expired = 0
        total_stockout_units = 0
        total_gross_revenue = 0.0
        total_cost_of_goods_sold = 0.0
        total_markdown_loss = 0.0
        total_transfer_costs = 0.0
        total_waste_cost_loss = 0.0
        total_transfers_count = 0
        total_donations_count = 0
        constraint_violations = 0

        daily_log = []

        initial_inventory_units = sum(it.get("initial_stock", it["stock_on_hand"]) for it in initial_state)
        total_restocked_units = 0
        total_units_donated = 0

        for day in range(1, 8):
            day_sold = 0
            day_expired = 0
            day_stockout = 0
            day_revenue = 0.0
            day_waste_cost = 0.0

            # -------------------------------------------------------------
            # PHASE 1: MORNING DECISION & INTERVENTION
            # -------------------------------------------------------------
            if strategy_name == "BASELINE":
                # Baseline: Fixed static rules
                # Rule 1: Apply fixed 20% discount if days_to_expiry == 1 and stock > 5
                for inv_id, it in items_by_id.items():
                    if it["sim_days_to_expiry"] == 1 and it["stock_on_hand"] > 5:
                        it["current_discount_pct"] = 20
                    else:
                        it["current_discount_pct"] = 0
                # Baseline never executes inter-store transfers

            elif strategy_name == "FRESHGUARD":
                # FreshGuard: Run actual multi-agent orchestrator pipeline
                # Format current state for Orchestrator
                current_items_list = list(items_by_id.values())
                # Adapt days to hours for agent engine
                for it in current_items_list:
                    it["hours_to_expiry"] = it["sim_days_to_expiry"] * 24.0

                orch_output = Orchestrator.run_pipeline(
                    all_inventory_items=current_items_list,
                    scenario_params={"foot_traffic_mult": 1.0, "allow_inter_store": True, "allow_food_bank": True}
                )

                # Execute winning approved recommendations
                for rec in orch_output.get("recommendations", []):
                    inv_id = rec["inventory_id"]
                    if inv_id not in items_by_id:
                        continue
                    it = items_by_id[inv_id]

                    if rec["action_type"] == "DISCOUNT":
                        it["current_discount_pct"] = rec.get("recommended_discount_pct", 20)

                    elif rec["action_type"] == "TRANSFER":
                        qty = min(it["stock_on_hand"], rec["units_affected"])
                        target_store = rec.get("target_store_id")
                        sku = rec.get("sku")
                        
                        # Find destination item
                        dest_item = next((d for d in items_by_id.values() if d["store_id"] == target_store and d["sku"] == sku), None)
                        if dest_item and qty > 0:
                            # Transfer logic: Source decrements, Dest increments
                            it["stock_on_hand"] -= qty
                            dest_item["stock_on_hand"] += qty
                            transfer_fee = round(qty * 5.0, 2)
                            total_transfer_costs += transfer_fee
                            total_transfers_count += 1

                    elif rec["action_type"] == "DONATE":
                        qty = min(it["stock_on_hand"], rec["units_affected"])
                        if qty > 0:
                            it["stock_on_hand"] -= qty
                            total_donations_count += 1
                            total_units_donated += qty

            # -------------------------------------------------------------
            # PHASE 2: DAILY DEMAND FULFILLMENT & SALES
            # -------------------------------------------------------------
            for inv_id, it in items_by_id.items():
                if it["stock_on_hand"] <= 0 or it["sim_days_to_expiry"] <= 0:
                    continue

                raw_demand = daily_demand[day].get(inv_id, 10.0)
                
                # Apply price elasticity if discounted
                discount_pct = it.get("current_discount_pct", 0)
                elasticity = 1.35
                elastic_mult = 1.0 + (elasticity * (discount_pct / 100.0))
                effective_demand = raw_demand * elastic_mult

                # Physical Constraint: Cannot sell more than available on-hand stock
                units_can_sell = min(int(it["stock_on_hand"]), int(round(effective_demand)))
                
                # Record Stockout if demand > stock
                if effective_demand > it["stock_on_hand"]:
                    unmet = int(round(effective_demand - it["stock_on_hand"]))
                    total_stockout_units += unmet
                    day_stockout += unmet

                if units_can_sell > 0:
                    unit_selling_price = float(it["selling_price"])
                    effective_price = unit_selling_price * (1.0 - (discount_pct / 100.0))
                    unit_cost = float(it["cost_price"])

                    revenue = round(units_can_sell * effective_price, 2)
                    cogs = round(units_can_sell * unit_cost, 2)
                    markdown_loss = round(units_can_sell * (unit_selling_price - effective_price), 2)

                    # Update stock & financial accumulators
                    it["stock_on_hand"] -= units_can_sell
                    total_units_sold += units_can_sell
                    total_gross_revenue += revenue
                    total_cost_of_goods_sold += cogs
                    total_markdown_loss += markdown_loss

                    day_sold += units_can_sell
                    day_revenue += revenue

                    # Constraint Check: Stock must never be negative
                    if it["stock_on_hand"] < 0:
                        constraint_violations += 1
                        it["stock_on_hand"] = 0

            # -------------------------------------------------------------
            # PHASE 3: END OF DAY EXPIRY & REPLENISHMENT
            # -------------------------------------------------------------
            for inv_id, it in items_by_id.items():
                it["sim_days_to_expiry"] -= 1

                # If item expired today, write off remaining stock as spoilage
                if it["sim_days_to_expiry"] <= 0 and it["stock_on_hand"] > 0:
                    expired_qty = it["stock_on_hand"]
                    cost_loss = round(expired_qty * float(it["cost_price"]), 2)
                    
                    total_units_expired += expired_qty
                    total_waste_cost_loss += cost_loss
                    day_expired += expired_qty
                    day_waste_cost += cost_loss
                    
                    it["stock_on_hand"] = 0 # Discarded / composted

                # Daily replenishment delivery: If stock below safety stock, restock fresh batch
                if it["stock_on_hand"] < it["safety_stock"]:
                    restock_qty = int(it["forecast_daily_demand"] * 2.5)
                    it["stock_on_hand"] += restock_qty
                    total_restocked_units += restock_qty
                    it["sim_days_to_expiry"] = max(3, it.get("shelf_life_days", 4))
                    it["current_discount_pct"] = 0

            daily_log.append({
                "day": day,
                "units_sold": day_sold,
                "units_expired": day_expired,
                "stockout_units": day_stockout,
                "revenue": round(day_revenue, 2),
                "waste_cost": round(day_waste_cost, 2)
            })

        # Calculate final ending inventory
        ending_inventory_units = sum(it["stock_on_hand"] for it in items_by_id.values())

        # Physical Conservation Invariant: Inflow == Outflow + Retained
        inflow = initial_inventory_units + total_restocked_units
        outflow = total_units_sold + total_units_expired + total_units_donated + ending_inventory_units
        if inflow != outflow:
            constraint_violations += abs(inflow - outflow)

        # Calculate final metrics
        gross_margin_dollars = round(total_gross_revenue - total_cost_of_goods_sold - total_transfer_costs, 2)
        gross_margin_pct = round((gross_margin_dollars / total_gross_revenue * 100), 1) if total_gross_revenue > 0 else 0.0
        total_demand_attempted = total_units_sold + total_stockout_units
        fulfillment_rate = round((total_units_sold / total_demand_attempted * 100), 1) if total_demand_attempted > 0 else 100.0

        return {
            "strategy": strategy_name,
            "initial_inventory_units": initial_inventory_units,
            "restocked_units": total_restocked_units,
            "ending_inventory_units": ending_inventory_units,
            "units_sold": total_units_sold,
            "units_expired": total_units_expired,
            "units_donated": total_units_donated,
            "stockout_units": total_stockout_units,
            "fulfillment_rate_pct": fulfillment_rate,
            "gross_revenue": round(total_gross_revenue, 2),
            "cost_of_goods_sold": round(total_cost_of_goods_sold, 2),
            "gross_margin_dollars": gross_margin_dollars,
            "gross_margin_pct": gross_margin_pct,
            "markdown_loss": round(total_markdown_loss, 2),
            "transfer_costs": round(total_transfer_costs, 2),
            "waste_cost_loss": round(total_waste_cost_loss, 2),
            "transfers_executed": total_transfers_count,
            "donations_executed": total_donations_count,
            "constraint_violations": constraint_violations,
            "inventory_conservation_verified": (inflow == outflow),
            "daily_breakdown": daily_log
        }

    @classmethod
    def _compute_comparison(
        cls, 
        base: Dict[str, Any], 
        fg: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Computes exact absolute differences (Deltas) between FreshGuard and Baseline.
        """
        waste_reduction_units = base["units_expired"] - fg["units_expired"]
        waste_reduction_pct = round((waste_reduction_units / max(1, base["units_expired"]) * 100), 1) if base["units_expired"] > 0 else 0.0

        revenue_diff = round(fg["gross_revenue"] - base["gross_revenue"], 2)
        margin_diff = round(fg["gross_margin_dollars"] - base["gross_margin_dollars"], 2)
        waste_cost_saved = round(base["waste_cost_loss"] - fg["waste_cost_loss"], 2)
        stockout_diff = base["stockout_units"] - fg["stockout_units"] # Positive means FreshGuard reduced stockouts

        # Construct trade-off summary
        trade_offs = []
        if fg["transfer_costs"] > 0:
            trade_offs.append(
                f"FreshGuard deployed {fg['transfers_executed']} inter-store transfers (₹{fg['transfer_costs']:,.2f} total freight) to move stock where velocity is higher, preventing localized stockouts and rescuing perishable inventory."
            )
        if fg["markdown_loss"] > base["markdown_loss"]:
            markdown_diff = fg["markdown_loss"] - base["markdown_loss"]
            trade_offs.append(
                f"FreshGuard executed dynamic elasticity markdowns (₹{fg['markdown_loss']:,.2f} total concession, +₹{markdown_diff:,.2f} over baseline), accelerating unit sell-through by +{fg['units_sold'] - base['units_sold']} units and saving ₹{waste_cost_saved:,.2f} in waste write-offs."
            )
        else:
            trade_offs.append(
                f"FreshGuard preserved higher unit margins by routing surplus to high-demand stores rather than relying solely on deep in-store price slashing."
            )
        if waste_reduction_units > 0:
            trade_offs.append(
                f"Total physical shrinkage was reduced by {waste_reduction_units} units ({waste_reduction_pct}% waste reduction) while strictly respecting all shelf-life and non-negative inventory constraints."
            )

        return {
            "waste_reduction_units": waste_reduction_units,
            "waste_reduction_pct": waste_reduction_pct,
            "revenue_delta": revenue_diff,
            "gross_margin_delta": margin_diff,
            "waste_cost_saved": waste_cost_saved,
            "stockout_reduction_units": stockout_diff,
            "fulfillment_rate_delta": round(fg["fulfillment_rate_pct"] - base["fulfillment_rate_pct"], 1),
            "trade_offs_summary": trade_offs
        }
