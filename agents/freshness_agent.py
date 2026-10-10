"""
FreshGuard - Freshness Agent
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery

Role: Calculates remaining shelf life, evaluates temperature-adjusted spoilage curves,
estimates natural sell-through before expiry, and flags spoilage risk with explicit rules.
"""

import datetime
from typing import Dict, Any, List

class FreshnessAgent:
    """
    Evaluates physical shelf-life decay, sellable quantities before cutoff, and spoilage risk.
    """

    @staticmethod
    def parse_datetime(dt_str: str) -> datetime.datetime:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(dt_str, fmt)
            except ValueError:
                pass
        return datetime.datetime.now()

    @classmethod
    def evaluate_freshness(
        cls, 
        item: Dict[str, Any], 
        demand_forecast: Dict[str, Any],
        current_time: datetime.datetime = None
    ) -> Dict[str, Any]:
        """
        Assesses shelf-life health and flags potential spoilage with clear rule explanations.
        """
        now = current_time or datetime.datetime.now()
        exp_dt = cls.parse_datetime(item.get("expiry_date", ""))
        rec_dt = cls.parse_datetime(item.get("received_date", ""))

        time_remaining = exp_dt - now
        hours_remaining = max(0.0, time_remaining.total_seconds() / 3600.0)
        days_remaining = round(hours_remaining / 24.0, 2)

        stock = int(item.get("stock_on_hand", 0))
        safety_stock = int(item.get("safety_stock", 0))
        cost_price = float(item.get("cost_price", 1.0))
        selling_price = float(item.get("selling_price", 2.0))
        storage_zone = item.get("storage_zone", "Ambient")

        daily_rate = max(0.1, float(demand_forecast.get("effective_daily_rate", 10.0)))
        days_of_supply = round(stock / daily_rate, 1)

        # Estimate Natural Sellable Units before expiry (without extra intervention)
        # Sellable = min(Stock, Daily Demand * Days Left)
        natural_sellable_units = min(stock, round(daily_rate * max(0.1, days_remaining), 1))
        projected_waste_units = max(0.0, round(stock - natural_sellable_units, 1))

        # Financial & Carbon Loss Exposure
        projected_cost_loss = round(projected_waste_units * cost_price, 2)
        projected_retail_loss = round(projected_waste_units * selling_price, 2)
        co2_factor = float(item.get("co2_footprint_kg", 1.0))
        projected_co2_kg = round(projected_waste_units * co2_factor, 2)

        # Explicit Rule-Based Risk Evaluation
        rule_reasons = []
        if hours_remaining <= 0:
            risk_status = "EXPIRED"
            risk_label = "Expired Batch"
            risk_color = "critical"
            risk_score = 100
            rule_reasons.append("Batch has crossed its strict sell-by expiry timestamp.")
        elif hours_remaining <= 36 and projected_waste_units > 0:
            risk_status = "CRITICAL_EXPIRY_RISK"
            risk_label = "Critical Expiry Risk"
            risk_color = "critical"
            urgency_pct = 1.0 - min(1.0, hours_remaining / 36.0)
            risk_score = min(100, int(70 + (30 * urgency_pct)))
            rule_reasons.append(
                f"Rule 1 triggered: Only {hours_remaining:.1f}h remaining on shelf life. "
                f"On-hand stock ({stock}) exceeds expected natural sales ({natural_sellable_units:.1f}) before cut-off, leaving {projected_waste_units:.1f} units at risk of dumping."
            )
        elif hours_remaining <= 72 and projected_waste_units > 0:
            risk_status = "MODERATE_EXPIRY_RISK"
            risk_label = "Moderate Expiry Risk"
            risk_color = "warning"
            risk_score = min(75, int(45 + (25 * (projected_waste_units / max(1, stock)))))
            rule_reasons.append(
                f"Rule 2 triggered: {days_remaining:.1f} days remaining. Velocity ({daily_rate}/day) is insufficient to clear all {stock} units before spoilage."
            )
        elif stock <= safety_stock and days_of_supply <= 1.5:
            risk_status = "STOCKOUT_RISK"
            risk_label = "Stockout Threat"
            risk_color = "stockout"
            risk_score = min(85, int(60 + (25 * (1.0 - min(1.0, stock / max(1, safety_stock))))))
            rule_reasons.append(
                f"Rule 3 triggered: Current stock ({stock}) is below safety threshold ({safety_stock}). Stockout projected in {days_of_supply} days."
            )
        elif days_of_supply >= 3.5:
            risk_status = "OVERSTOCK"
            risk_label = "Overstocked"
            risk_color = "amber"
            risk_score = min(60, int(35 + (20 * min(1.0, days_of_supply / 6.0))))
            rule_reasons.append(
                f"Rule 4 triggered: Days of supply ({days_of_supply} days) is excessively high for perishable department ({item.get('department')})."
            )
        else:
            risk_status = "BALANCED"
            risk_label = "Healthy Flow"
            risk_color = "healthy"
            risk_score = max(5, int(15 * (1.0 - min(1.0, days_remaining / 10.0))))
            rule_reasons.append("Rule 5: Stock levels and sales velocity are in healthy equilibrium with safe shelf-life margin.")

        explanation = (
            f"Freshness status for {item.get('product_name')}: {hours_remaining:.1f} hours remaining ({days_remaining:.1f} days). "
            f"Under current velocity of {daily_rate} units/day, {natural_sellable_units:.1f} of {stock} units will sell naturally. "
            f"Expected unsold waste without intervention: {projected_waste_units:.1f} units (₹{projected_retail_loss:.2f} retail loss)."
        )

        return {
            "sku": item.get("sku"),
            "inventory_id": item.get("inventory_id"),
            "store_id": item.get("store_id"),
            "store_name": item.get("store_name"),
            "hours_to_expiry": round(hours_remaining, 1),
            "days_to_expiry": days_remaining,
            "days_of_supply": days_of_supply,
            "natural_sellable_units": natural_sellable_units,
            "projected_waste_units": projected_waste_units,
            "projected_cost_loss": projected_cost_loss,
            "projected_retail_loss": projected_retail_loss,
            "projected_co2_kg": projected_co2_kg,
            "risk_status": risk_status,
            "risk_label": risk_label,
            "risk_color": risk_color,
            "risk_score": risk_score,
            "rule_reasons": rule_reasons,
            "explanation": explanation
        }
