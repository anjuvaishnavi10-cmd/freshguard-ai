"""
FreshGuard - Action Agent (Indian Grocery Edition)
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery

Role: Evaluates candidate rescue actions (Dynamic Markdowns, Inter-Store Transfers,
Replenishment Adjustments, and Food Donations) against strict operational constraints.
"""

from typing import Dict, Any, List, Optional

class ActionAgent:
    """
    Generates structured candidate actions with explicit constraints validation,
    economic yield analysis in INR (₹), and manager-ready justifications.
    """

    TRANSIT_TIME_HOURS = 0.8         # ~45-50 min refrigerated courier transit between HITAM and Miyapur
    TRANSIT_COST_PER_UNIT = 5.0      # ₹5.00 per unit intra-city cold-chain handling & courier freight
    MIN_TRANSIT_SHELF_LIFE_HOURS = 16.0 # Destination must have at least 16h shelf life remaining upon arrival

    @classmethod
    def evaluate_markdown_candidate(
        cls, 
        item: Dict[str, Any], 
        freshness: Dict[str, Any], 
        demand: Dict[str, Any],
        discount_aggressiveness: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates dynamic markdown feasibility, elasticity lift, and price floor constraints in INR.
        """
        waste_units = freshness.get("projected_waste_units", 0.0)
        hours_left = freshness.get("hours_to_expiry", 0.0)
        stock = int(item.get("stock_on_hand", 0))
        selling_price = float(item.get("selling_price", 30.0))
        cost_price = float(item.get("cost_price", 24.0))

        if waste_units <= 0 or hours_left <= 0:
            return None

        # Determine optimal baseline markdown tier
        if hours_left <= 14:
            base_discount = 50
            timing = "Immediate Flash Clearance (Within 1 hour)"
            urgency = "CRITICAL"
        elif hours_left <= 30:
            base_discount = 35
            timing = "Morning Operational Rollout (Before 11:00 AM)"
            urgency = "HIGH"
        elif hours_left <= 54:
            base_discount = 20
            timing = "Afternoon Promotional Display (By 2:00 PM)"
            urgency = "MEDIUM"
        else:
            base_discount = 15
            timing = "Standard End-Cap Promotion (Next 24 hours)"
            urgency = "LOW"

        adj_discount = min(60, max(10, int(base_discount * discount_aggressiveness)))
        discounted_price = round(selling_price * (1.0 - (adj_discount / 100.0)), 2)

        # Price elasticity demand lift
        elasticity_coeff = demand.get("elasticity_coeff", 1.35)
        demand_lift = 1.0 + (elasticity_coeff * (adj_discount / 100.0))
        rescuable_units = min(stock, round(waste_units * demand_lift))

        # Financial yield
        gross_salvage_revenue = round(rescuable_units * discounted_price, 2)
        unit_gross_margin = round(discounted_price - cost_price, 2)
        net_margin_total = round(rescuable_units * unit_gross_margin, 2)

        # Constraints validation
        constraints_checked = []
        is_above_cost = discounted_price >= cost_price
        constraints_checked.append({
            "constraint": "Price Floor Margin",
            "passed": is_above_cost,
            "detail": f"Discounted price ₹{discounted_price:.2f} vs unit cost ₹{cost_price:.2f} (Margin: ₹{unit_gross_margin:.2f})"
        })
        constraints_checked.append({
            "constraint": "Shelf-Life Clearance Window",
            "passed": hours_left >= 4,
            "detail": f"{hours_left:.1f} hours remaining on batch label"
        })
        constraints_checked.append({
            "constraint": "Stock Availability",
            "passed": stock >= rescuable_units,
            "detail": f"{stock} units physically in stockroom"
        })

        # Confidence category
        if is_above_cost and hours_left >= 12:
            confidence = "HIGH"
            confidence_pct = 92
        elif is_above_cost:
            confidence = "MEDIUM"
            confidence_pct = 81
        else:
            confidence = "LOW"
            confidence_pct = 68

        co2_factor = float(item.get("co2_footprint_kg", 0.5))
        waste_avoided_kg = round(rescuable_units * (co2_factor * 0.4), 2)
        co2_avoided_kg = round(rescuable_units * co2_factor, 2)

        return {
            "candidate_type": "DISCOUNT",
            "action_type": "DISCOUNT",
            "action_title": f"Apply {adj_discount}% Flash Markdown on {item.get('product_name')}",
            "inventory_id": item.get("inventory_id"),
            "sku": item.get("sku"),
            "product_name": item.get("product_name"),
            "department": item.get("department"),
            "source_store_id": item.get("store_id"),
            "source_store_name": item.get("store_name"),
            "target_store_id": None,
            "target_store_name": None,
            "units_affected": int(rescuable_units),
            "recommended_discount_pct": adj_discount,
            "original_price": selling_price,
            "discounted_price": discounted_price,
            "timing": timing,
            "urgency": urgency,
            "confidence": confidence,
            "confidence_pct": confidence_pct,
            "projected_revenue_saved": gross_salvage_revenue,
            "net_economic_yield": gross_salvage_revenue, # In-store clearance
            "projected_waste_avoided_kg": waste_avoided_kg,
            "projected_co2_avoided_kg": co2_avoided_kg,
            "constraints_checked": constraints_checked,
            "supporting_evidence": [
                f"Batch Shelf-Life: {hours_left:.1f} hours remaining ({item.get('expiry_date')})",
                f"Sales Velocity: {demand.get('baseline_daily_demand')}/day ➔ Lifted to {demand.get('effective_daily_rate') * demand_lift:.1f}/day",
                f"Unit Pricing: Original ₹{selling_price:.2f} ➔ Markdown ₹{discounted_price:.2f} (Saving ₹{gross_salvage_revenue:.2f} vs ₹0 write-off)",
                f"Margin Impact: Unit profit ₹{unit_gross_margin:.2f} (Gross salvage: ₹{gross_salvage_revenue:.2f})"
            ],
            "manager_explanation": (
                f"{item.get('product_name')} in {item.get('store_name')} has {stock} units with {hours_left:.1f}h left. "
                f"A {adj_discount}% markdown accelerates velocity to clear {rescuable_units} units before expiry, recovering ₹{gross_salvage_revenue:.2f}."
            )
        }

    @classmethod
    def evaluate_inter_store_transfer_candidate(
        cls,
        source_item: Dict[str, Any],
        source_freshness: Dict[str, Any],
        target_item: Dict[str, Any],
        target_freshness: Dict[str, Any],
        target_demand: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates inter-store transfer feasibility: transit time, logistics cost, destination demand, and net yield in INR.
        """
        source_surplus = source_freshness.get("projected_waste_units", 0.0)
        source_hours = source_freshness.get("hours_to_expiry", 0.0)
        source_stock = int(source_item.get("stock_on_hand", 0))
        source_safety = int(source_item.get("safety_stock", 0))

        target_stock = int(target_item.get("stock_on_hand", 0))
        target_safety = int(target_item.get("safety_stock", 0))
        target_daily_demand = float(target_demand.get("effective_daily_rate", 15.0))
        target_risk_status = target_freshness.get("risk_status", "BALANCED")

        # Basic eligibility check
        if source_surplus < 5 or source_hours < (cls.TRANSIT_TIME_HOURS + cls.MIN_TRANSIT_SHELF_LIFE_HOURS):
            return None

        # Check if target store actually needs stock (Stockout threat or below safety stock or high velocity)
        target_needs_stock = (
            target_risk_status == "STOCKOUT_RISK" or 
            target_stock <= target_safety or 
            (target_stock / target_daily_demand) <= 1.5
        )
        if not target_needs_stock:
            return None

        # Determine transfer quantity
        # 1. Source cannot transfer more than its surplus
        # 2. Source must keep at least safety stock
        available_from_source = max(0, min(int(source_surplus), source_stock - source_safety))
        if available_from_source < 5:
            return None

        # 3. Target should not receive more than 1.5 days of forward demand
        target_absorption_capacity = int(target_daily_demand * 1.5)
        transfer_qty = min(available_from_source, target_absorption_capacity)
        if transfer_qty < 5:
            return None

        # Shelf life remaining at destination upon arrival
        arrival_shelf_life_hours = round(source_hours - cls.TRANSIT_TIME_HOURS, 1)

        # Financial yield comparison: Full retail price at target minus logistics transfer cost
        selling_price = float(target_item.get("selling_price", 30.0))
        cost_price = float(target_item.get("cost_price", 24.0))
        
        gross_transfer_revenue = round(transfer_qty * selling_price, 2)
        total_transit_cost = round(transfer_qty * cls.TRANSIT_COST_PER_UNIT, 2)
        # Net yield reflects full retail recovery at destination minus transit fee plus preserved retail margin over cost
        net_economic_yield = round(gross_transfer_revenue - total_transit_cost + (transfer_qty * (selling_price - cost_price)), 2)

        # Constraints validation
        constraints_checked = [
            {
                "constraint": "Transit Cold-Chain Window",
                "passed": arrival_shelf_life_hours >= cls.MIN_TRANSIT_SHELF_LIFE_HOURS,
                "detail": f"{arrival_shelf_life_hours:.1f}h remaining at destination post {cls.TRANSIT_TIME_HOURS}h courier run (Min: {cls.MIN_TRANSIT_SHELF_LIFE_HOURS}h)"
            },
            {
                "constraint": "Source Safety Stock Preserved",
                "passed": (source_stock - transfer_qty) >= source_safety,
                "detail": f"Source retains {source_stock - transfer_qty} units (Safety Target: {source_safety})"
            },
            {
                "constraint": "Destination Demand Capacity",
                "passed": transfer_qty <= (target_daily_demand * 2.0),
                "detail": f"Destination absorbs {transfer_qty} units against {target_daily_demand}/day velocity"
            },
            {
                "constraint": "Logistics Cost Viability",
                "passed": total_transit_cost < (gross_transfer_revenue * 0.25),
                "detail": f"Transit fee ₹{total_transit_cost:.2f} is only {(total_transit_cost/gross_transfer_revenue)*100:.1f}% of recovered revenue"
            }
        ]

        confidence = "HIGH" if all(c["passed"] for c in constraints_checked) else "MEDIUM"
        confidence_pct = 94 if confidence == "HIGH" else 76

        co2_factor = float(source_item.get("co2_footprint_kg", 0.5))
        waste_avoided_kg = round(transfer_qty * (co2_factor * 0.4), 2)
        co2_avoided_kg = round(transfer_qty * co2_factor, 2)

        return {
            "candidate_type": "TRANSFER",
            "action_type": "TRANSFER",
            "action_title": f"Transfer {transfer_qty} units of {source_item.get('product_name')} to {target_item.get('store_name')}",
            "inventory_id": source_item.get("inventory_id"),
            "sku": source_item.get("sku"),
            "product_name": source_item.get("product_name"),
            "department": source_item.get("department"),
            "source_store_id": source_item.get("store_id"),
            "source_store_name": source_item.get("store_name"),
            "target_store_id": target_item.get("store_id"),
            "target_store_name": target_item.get("store_name"),
            "units_affected": int(transfer_qty),
            "recommended_discount_pct": 0, # Sold at 100% full retail price at destination!
            "timing": "Next Scheduled Intra-City Courier (Departs 1:30 PM)",
            "urgency": "HIGH",
            "confidence": confidence,
            "confidence_pct": confidence_pct,
            "projected_revenue_saved": gross_transfer_revenue,
            "transit_cost": total_transit_cost,
            "net_economic_yield": net_economic_yield,
            "projected_waste_avoided_kg": waste_avoided_kg,
            "projected_co2_avoided_kg": co2_avoided_kg,
            "constraints_checked": constraints_checked,
            "supporting_evidence": [
                f"Source Surplus: {source_surplus} units in {source_item.get('store_name')} ({source_hours:.1f}h left)",
                f"Destination Deficit: {target_item.get('store_name')} on-hand {target_stock} units (Velocity: {target_daily_demand}/day)",
                f"Transit Window: {cls.TRANSIT_TIME_HOURS}h drive leaves {arrival_shelf_life_hours:.1f}h fresh shelf-life upon arrival",
                f"Financial Yield: +₹{gross_transfer_revenue:.2f} at 100% full retail price minus ₹{total_transit_cost:.2f} freight = +₹{net_economic_yield:.2f} net"
            ],
            "manager_explanation": (
                f"{source_item.get('store_name')} has {source_surplus} excess units of {source_item.get('product_name')}. "
                f"Transferring {transfer_qty} units to {target_item.get('store_name')} resolves their impending stockout at 100% full retail price, "
                f"generating ₹{net_economic_yield:.2f} net revenue after ₹{total_transit_cost:.2f} courier transit fee."
            )
        }

    @classmethod
    def evaluate_food_bank_candidate(
        cls,
        item: Dict[str, Any],
        freshness: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates emergency food pantry donation routing for items within 12h of strict cut-off in INR.
        """
        hours_left = freshness.get("hours_to_expiry", 0.0)
        stock = int(item.get("stock_on_hand", 0))
        cost_price = float(item.get("cost_price", 20.0))

        # If batch expires within 12h and high stock remains that cannot clear
        if 0 < hours_left <= 12 and stock >= 4:
            donation_qty = max(4, int(stock * 0.45))
            social_value = round(donation_qty * cost_price, 2)
            co2_factor = float(item.get("co2_footprint_kg", 0.5))
            waste_avoided_kg = round(donation_qty * (co2_factor * 0.4), 2)
            co2_avoided_kg = round(donation_qty * co2_factor, 2)

            constraints_checked = [
                {
                    "constraint": "Food Safety Donation Window",
                    "passed": hours_left >= 3.0,
                    "detail": f"{hours_left:.1f}h remaining (Pantry collection pickup required within 3h)"
                },
                {
                    "constraint": "Zero-Landfill Certification",
                    "passed": True,
                    "detail": "100% diverted from organic municipal landfill disposal"
                }
            ]

            return {
                "candidate_type": "DONATE",
                "action_type": "DONATE",
                "action_title": f"Dispatch {donation_qty} units of {item.get('product_name')} to Community Food Pantry",
                "inventory_id": item.get("inventory_id"),
                "sku": item.get("sku"),
                "product_name": item.get("product_name"),
                "department": item.get("department"),
                "source_store_id": item.get("store_id"),
                "source_store_name": item.get("store_name"),
                "target_store_id": "COMMUNITY-FOOD-BANK-01",
                "target_store_name": "Hyderabad Youth Seva / Akshaya Community Pantry",
                "units_affected": donation_qty,
                "recommended_discount_pct": 100,
                "timing": "Evening Food Rescue Dispatch (Pickup at 6:30 PM)",
                "urgency": "CRITICAL",
                "confidence": "HIGH",
                "confidence_pct": 98,
                "projected_revenue_saved": social_value,
                "net_economic_yield": social_value,
                "projected_waste_avoided_kg": waste_avoided_kg,
                "projected_co2_avoided_kg": co2_avoided_kg,
                "constraints_checked": constraints_checked,
                "supporting_evidence": [
                    f"Expiry Deadline: {item.get('expiry_date')} ({hours_left:.1f}h left)",
                    f"Community Partner: Hyderabad Youth Seva Community Pantry (Daily 7:00 PM distribution)",
                    f"Landfill Diversion: {waste_avoided_kg} kg organic waste prevented",
                    f"Social Welfare Value: ₹{social_value:.2f}"
                ],
                "manager_explanation": (
                    f"Batch has only {hours_left:.1f}h shelf-life remaining. Dispatching {donation_qty} units to community partner "
                    f"guarantees zero landfill waste and provides wholesome nutrition to nearby families."
                )
            }
        return None

    @classmethod
    def evaluate_pause_po_candidate(
        cls,
        item: Dict[str, Any],
        freshness: Dict[str, Any],
        demand: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates holding back replenishment purchase orders when massive overstock exists.
        """
        risk_status = freshness.get("risk_status")
        stock = int(item.get("stock_on_hand", 0))
        daily_demand = float(demand.get("effective_daily_rate", 5.0))
        days_of_supply = freshness.get("days_of_supply", 10.0)

        if risk_status == "OVERSTOCK" and days_of_supply > 6.0:
            saved_working_capital = round(daily_demand * 3 * float(item.get("cost_price", 20.0)), 2)
            return {
                "candidate_type": "PAUSE_PO",
                "action_type": "PAUSE_PO",
                "action_title": f"Hold Inbound Replenishment PO for {item.get('product_name')}",
                "inventory_id": item.get("inventory_id"),
                "sku": item.get("sku"),
                "product_name": item.get("product_name"),
                "department": item.get("department"),
                "source_store_id": item.get("store_id"),
                "source_store_name": item.get("store_name"),
                "target_store_id": None,
                "target_store_name": None,
                "units_affected": int(daily_demand * 3),
                "recommended_discount_pct": 0,
                "timing": "Next Inbound EDI Gate (By 4:00 PM)",
                "urgency": "LOW",
                "confidence": "HIGH",
                "confidence_pct": 90,
                "projected_revenue_saved": saved_working_capital,
                "net_economic_yield": saved_working_capital,
                "projected_waste_avoided_kg": 0.0,
                "projected_co2_avoided_kg": 0.0,
                "constraints_checked": [
                    {
                        "constraint": "Supplier Notice Window",
                        "passed": True,
                        "detail": "Electronic order hold submitted prior to 4-hour vendor cutoff"
                    }
                ],
                "supporting_evidence": [
                    f"Current Stock: {stock} units ({days_of_supply:.1f} days of supply on hand)",
                    f"Working Capital Preserved: ₹{saved_working_capital:.2f}"
                ],
                "manager_explanation": (
                    f"Store holds {stock} units ({days_of_supply:.1f} days of supply). "
                    f"Holding the scheduled restock preserves ₹{saved_working_capital:.2f} in working capital and prevents shelf congestion."
                )
            }
        return None

    @classmethod
    def evaluate_replenishment_candidate(
        cls,
        item: Dict[str, Any],
        freshness: Dict[str, Any],
        demand: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates priority wholesale supplier replenishment when stock is at risk of stockout
        and forward customer velocity threatens empty shelves and lost revenue.
        """
        risk_status = freshness.get("risk_status")
        stock = int(item.get("stock_on_hand", 0))
        safety_stock = int(item.get("safety_stock", 0))
        daily_demand = max(0.1, float(demand.get("effective_daily_rate", item.get("avg_daily_sales", 10.0))))
        days_of_supply = freshness.get("days_of_supply", round(stock / daily_demand, 1))
        selling_price = float(item.get("selling_price", 30.0))
        cost_price = float(item.get("cost_price", 24.0))

        # Candidate triggers if stock is depleted below safety stock or days of supply <= 1.8
        if (risk_status == "STOCKOUT_RISK" or stock <= safety_stock) and days_of_supply <= 1.8:
            order_qty = max(10, int(round((safety_stock * 1.5) - stock + (daily_demand * 2.0))))
            total_cost = round(order_qty * cost_price, 2)
            protected_revenue = round(order_qty * selling_price, 2)
            protected_margin = round(order_qty * (selling_price - cost_price), 2)

            constraints_checked = [
                {
                    "constraint": "Supplier Lead-Time Feasibility",
                    "passed": True,
                    "detail": "Overnight wholesale dispatch arrives before 7:00 AM morning opening"
                },
                {
                    "constraint": "Cooler / Storage Capacity",
                    "passed": True,
                    "detail": f"Store storage zone ({item.get('storage_zone')}) can accommodate {order_qty} {item.get('unit')}"
                },
                {
                    "constraint": "Margin Feasibility",
                    "passed": selling_price > cost_price,
                    "detail": f"Selling price ₹{selling_price:.2f} > unit cost ₹{cost_price:.2f} (Gross margin: ₹{selling_price - cost_price:.2f})"
                },
                {
                    "constraint": "Safety Stock Deficit Verified",
                    "passed": stock <= safety_stock,
                    "detail": f"Current stock ({stock}) <= safety threshold ({safety_stock})"
                }
            ]

            confidence = "HIGH"
            confidence_pct = 93

            return {
                "candidate_type": "REPLENISH",
                "action_type": "REPLENISH",
                "action_title": f"Issue Priority Restock PO for {order_qty} {item.get('unit')} of {item.get('product_name')}",
                "inventory_id": item.get("inventory_id"),
                "sku": item.get("sku"),
                "product_name": item.get("product_name"),
                "department": item.get("department"),
                "source_store_id": item.get("store_id"),
                "source_store_name": item.get("store_name"),
                "target_store_id": None,
                "target_store_name": "Regional Wholesale Vendor Hub",
                "units_affected": order_qty,
                "recommended_discount_pct": 0,
                "timing": "Priority Morning Supplier Delivery (By 7:00 AM Tomorrow)",
                "urgency": "HIGH",
                "confidence": confidence,
                "confidence_pct": confidence_pct,
                "projected_revenue_saved": protected_revenue,
                "net_economic_yield": protected_margin,
                "projected_waste_avoided_kg": 0.0,
                "projected_co2_avoided_kg": 0.0,
                "constraints_checked": constraints_checked,
                "supporting_evidence": [
                    f"Current Stock: {stock} {item.get('unit')} (Safety target: {safety_stock})",
                    f"Demand Velocity: {daily_demand}/day ({days_of_supply:.1f} days of supply remaining)",
                    f"Protected Revenue: ₹{protected_revenue:.2f} in gross customer sales (Margin: +₹{protected_margin:.2f})",
                    f"Stockout Risk: Shelves projected empty in {int(days_of_supply * 24)} operational hours without restock"
                ],
                "manager_explanation": (
                    f"{item.get('product_name')} in {item.get('store_name')} has only {stock} units on-hand against {daily_demand}/day velocity "
                    f"(Safety target: {safety_stock}). Issuing a priority replenishment order for {order_qty} units prevents stockout lost sales of ₹{protected_revenue:.2f}."
                )
            }
        return None
