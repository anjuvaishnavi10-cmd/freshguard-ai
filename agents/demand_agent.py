"""
FreshGuard - Demand Agent
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery

Role: Estimates perishable demand for next 1–3 days using historical sales velocity,
store footfall coefficients, and price elasticity with fully transparent math and limitation detection.
"""

from typing import Dict, Any, List

class DemandAgent:
    """
    Transparent forecasting agent for perishable grocery SKUs.
    Estimates 1-day, 2-day, and 3-day forward demand with clear mathematical reasoning and confidence scoring.
    """

    # Price elasticity coefficients by department (per 10% markdown)
    PRICE_ELASTICITY = {
        "Bakery": 1.55,     # Highly elastic (fresh bread/pastry sells rapidly with discount)
        "Fruits": 1.45,     # Highly elastic (impulse fresh purchase)
        "Vegetables": 1.35, # Moderately elastic
        "Dairy": 1.25       # Staple commodity elasticity
    }

    @classmethod
    def forecast_demand(
        cls, 
        item: Dict[str, Any], 
        days_ahead: int = 3, 
        traffic_multiplier: float = 1.0,
        hypothetical_discount_pct: int = 0
    ) -> Dict[str, Any]:
        """
        Calculates forward demand projection for a given SKU in a given store.
        """
        sku = item.get("sku", "")
        product_name = item.get("product_name", "")
        department = item.get("department", "Dairy")
        store_id = item.get("store_id", "")
        store_name = item.get("store_name", "")
        
        CATEGORY_BENCHMARKS = {
            "Dairy": 12.0,
            "Bakery": 14.0,
            "Vegetables": 15.0,
            "Fruits": 10.0,
            "Vegetables & Fruits": 12.0,
            "Pantry": 6.0,
            "Staples": 5.0
        }

        raw_sales = item.get("avg_daily_sales")
        insufficient_history = False
        try:
            avg_daily_sales = float(raw_sales) if raw_sales is not None else 0.0
        except (ValueError, TypeError):
            avg_daily_sales = 0.0

        if avg_daily_sales <= 0:
            insufficient_history = True
            dept_key = next((k for k in CATEGORY_BENCHMARKS if k.lower() in department.lower()), "Dairy")
            baseline_forecast = CATEGORY_BENCHMARKS.get(dept_key, 8.0)
        else:
            raw_forecast = item.get("forecast_daily_demand")
            try:
                baseline_forecast = float(raw_forecast) if raw_forecast is not None else avg_daily_sales
            except (ValueError, TypeError):
                baseline_forecast = avg_daily_sales

        # Store footfall weight factor (Urban vs Suburban velocity profile)
        is_urban = "101" in store_id
        store_profile_weight = 1.05 if is_urban else 0.98

        # Calculate Price Elasticity Lift
        elasticity_coeff = cls.PRICE_ELASTICITY.get(department, 1.35)
        discount_fraction = (hypothetical_discount_pct or item.get("current_discount_pct", 0)) / 100.0
        elasticity_lift = 1.0 + (elasticity_coeff * discount_fraction)

        # Adjusted Daily Demand Rate
        effective_daily_rate = round(baseline_forecast * store_profile_weight * traffic_multiplier * elasticity_lift, 2)

        # Day-by-day projected units
        daily_breakdown = []
        cumulative_demand = 0.0
        for day in range(1, days_ahead + 1):
            # Day-of-week decay/variation factor (Day 1 standard, Day 2 +5%, Day 3 +8%)
            day_decay = 1.0 + (0.04 * (day - 1))
            day_expected = round(effective_daily_rate * day_decay, 1)
            cumulative_demand += day_expected
            daily_breakdown.append({
                "day": day,
                "projected_units": day_expected,
                "cumulative_units": round(cumulative_demand, 1)
            })

        # Confidence & Limitation Assessment
        limitations = []
        if insufficient_history:
            confidence = "MEDIUM_ESTIMATE"
            confidence_pct = 68
            limitations.append(
                f"Insufficient historical sales records detected for this SKU. "
                f"Applied transparent category-benchmark fallback ({baseline_forecast} units/day based on {department}) "
                f"with conservative buffer."
            )
        else:
            # If variance between avg_daily_sales and baseline_forecast is high, confidence drops
            velocity_diff = abs(avg_daily_sales - baseline_forecast) / max(0.1, avg_daily_sales)
            if velocity_diff > 0.25:
                confidence = "MEDIUM"
                confidence_pct = 78
                limitations.append(f"High variance ({velocity_diff*100:.0f}%) between historical 7-day velocity and current forecast.")
            elif item.get("stock_on_hand", 0) <= item.get("safety_stock", 0):
                confidence = "HIGH"
                confidence_pct = 91
                limitations.append("Impending stockout may artificially constrain observed sales velocity.")
            else:
                confidence = "HIGH"
                confidence_pct = 95

        if insufficient_history:
            explanation = (
                f"Fallback Forecast for {product_name} in {store_name}: Insufficient historical POS sales. "
                f"Derived benchmark of {baseline_forecast} units/day from {department} category norms, "
                f"adjusted by store profile ({store_profile_weight}x)."
            )
        else:
            explanation = (
                f"Forecast for {product_name} in {store_name}: Baseline velocity of {baseline_forecast} units/day adjusted "
                f"by store footfall factor ({store_profile_weight}x), traffic scenario ({traffic_multiplier:.1f}x)"
            )
        if discount_fraction > 0:
            explanation += f", and {hypothetical_discount_pct}% markdown elasticity lift (+{(elasticity_lift-1.0)*100:.0f}% demand)."
        else:
            explanation += ". Expected 3-day total demand: " + f"{cumulative_demand:.1f} units."

        return {
            "sku": sku,
            "product_name": product_name,
            "department": department,
            "store_id": store_id,
            "baseline_daily_demand": baseline_forecast,
            "effective_daily_rate": effective_daily_rate,
            "elasticity_coeff": elasticity_coeff,
            "elasticity_lift": round(elasticity_lift, 2),
            "days_ahead": days_ahead,
            "cumulative_demand_3d": round(cumulative_demand, 1),
            "daily_breakdown": daily_breakdown,
            "confidence": confidence,
            "confidence_pct": confidence_pct,
            "limitations": limitations,
            "explanation": explanation
        }
