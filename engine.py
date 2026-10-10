"""
FreshGuard - Agentic AI Perishable Demand & Shelf-Life Optimization Engine
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery
"""

import datetime
import math
import json
import sqlite3
import csv
import io
import secrets
import os
import urllib.request
import re
from typing import List, Dict, Any, Optional

try:
    from freshguard_db import get_connection, hash_password, verify_password
except ImportError:
    from .freshguard_db import get_connection, hash_password, verify_password

try:
    from agents.demand_agent import DemandAgent
    from agents.freshness_agent import FreshnessAgent
    from agents.action_agent import ActionAgent
    from agents.orchestrator import Orchestrator
except ImportError:
    from .agents.demand_agent import DemandAgent
    from .agents.freshness_agent import FreshnessAgent
    from .agents.action_agent import ActionAgent
    from .agents.orchestrator import Orchestrator

class FreshGuardEngine:
    """
    Autonomous multi-tier optimization engine coordinating specialized agents.
    Provides real-time shelf-life analytics, risk scoring, and interactive manager workflows.
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
    def get_inventory_analytics(
        cls, 
        store_id: Optional[str] = None, 
        department: Optional[str] = None, 
        risk_filter: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch inventory joined with product and store details, enriched with dynamic risk calculations.
        Optionally scoped to a specific authenticated user.
        """
        conn = get_connection()
        cur = conn.cursor()

        query = """
        SELECT 
            i.id AS inventory_id,
            i.store_id,
            s.name AS store_name,
            s.location_type AS store_location,
            i.sku,
            p.name AS product_name,
            p.department,
            p.unit,
            p.cost_price,
            p.selling_price,
            p.storage_zone,
            p.co2_footprint_kg,
            p.description,
            i.batch_number,
            i.stock_on_hand,
            i.safety_stock,
            i.received_date,
            i.expiry_date,
            i.avg_daily_sales,
            i.forecast_daily_demand,
            i.current_discount_pct,
            i.status,
            i.supplier,
            i.incoming_stock,
            i.delivery_date,
            i.promotion_info,
            i.user_id
        FROM inventory i
        JOIN products p ON i.sku = p.sku
        JOIN stores s ON i.store_id = s.id
        WHERE i.status = 'ACTIVE'
        """
        params = []
        if user_id is not None:
            cur.execute("SELECT id FROM stores WHERE user_id = ?", (user_id,))
            user_stores = [r["id"] for r in cur.fetchall()]
            if not user_stores:
                conn.close()
                return []
            placeholders = ",".join("?" for _ in user_stores)
            query += f" AND i.store_id IN ({placeholders})"
            params.extend(user_stores)

        if store_id and store_id != "ALL":
            query += " AND i.store_id = ?"
            params.append(store_id)
        if department and department != "ALL":
            query += " AND p.department = ?"
            params.append(department)

        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        now = datetime.datetime.now()
        results = []

        for row in rows:
            item = dict(row)
            
            # Use DemandAgent & FreshnessAgent for standard valuation
            d_fore = DemandAgent.forecast_demand(item=item, days_ahead=3)
            f_eval = FreshnessAgent.evaluate_freshness(item=item, demand_forecast=d_fore, current_time=now)

            item.update({
                "hours_to_expiry": f_eval["hours_to_expiry"],
                "days_to_expiry": f_eval["days_to_expiry"],
                "days_of_supply": f_eval["days_of_supply"],
                "effective_price": round(item["selling_price"] * (1.0 - (item["current_discount_pct"] / 100.0)), 2),
                "projected_sales_before_expiry": f_eval["natural_sellable_units"],
                "projected_waste_units": f_eval["projected_waste_units"],
                "projected_waste_cost": f_eval["projected_cost_loss"],
                "projected_waste_retail_loss": f_eval["projected_retail_loss"],
                "projected_waste_kg": round(f_eval["projected_waste_units"] * (item["co2_footprint_kg"] * 0.4), 2),
                "projected_co2_impact_kg": f_eval["projected_co2_kg"],
                "risk_status": f_eval["risk_status"],
                "risk_label": f_eval["risk_label"],
                "risk_color": f_eval["risk_color"],
                "risk_score": f_eval["risk_score"],
                "demand_forecast": d_fore,
                "freshness_eval": f_eval
            })

            if not risk_filter or risk_filter == "ALL" or f_eval["risk_status"] == risk_filter:
                results.append(item)

        results.sort(key=lambda x: (-x["risk_score"], x["hours_to_expiry"]))
        return results

    @classmethod
    def get_overview_metrics(cls, store_id: Optional[str] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate executive morning briefing overview metrics scoped to user.
        """
        items = cls.get_inventory_analytics(store_id=store_id, user_id=user_id)
        total_skus = len(items)

        critical_items = [i for i in items if i["risk_status"] == "CRITICAL_EXPIRY_RISK"]
        moderate_items = [i for i in items if i["risk_status"] == "MODERATE_EXPIRY_RISK"]
        overstock_items = [i for i in items if i["risk_status"] == "OVERSTOCK"]
        stockout_items = [i for i in items if i["risk_status"] == "STOCKOUT_RISK"]
        healthy_items = [i for i in items if i["risk_status"] == "BALANCED"]

        total_units_at_risk = sum(i["projected_waste_units"] for i in items)
        total_cost_at_risk = sum(i["projected_waste_cost"] for i in items)
        total_retail_value_at_risk = sum(i["projected_waste_retail_loss"] for i in items)
        total_co2_at_risk_kg = sum(i["projected_co2_impact_kg"] for i in items)
        total_inventory_value = sum(i["stock_on_hand"] * i["selling_price"] for i in items)

        avg_risk = sum(i["risk_score"] for i in items) / total_skus if total_skus > 0 else 0
        store_freshness_index = round(max(0, 100 - avg_risk), 1)

        # Department risk breakdown
        dept_summary = {}
        for i in items:
            dept = i["department"]
            if dept not in dept_summary:
                dept_summary[dept] = {"total_skus": 0, "at_risk_skus": 0, "waste_units": 0, "value_at_risk": 0.0}
            dept_summary[dept]["total_skus"] += 1
            if i["risk_status"] in ("CRITICAL_EXPIRY_RISK", "MODERATE_EXPIRY_RISK"):
                dept_summary[dept]["at_risk_skus"] += 1
            dept_summary[dept]["waste_units"] += i["projected_waste_units"]
            dept_summary[dept]["value_at_risk"] += i["projected_waste_retail_loss"]

        dept_list = [
            {
                "department": k,
                "total_skus": v["total_skus"],
                "at_risk_skus": v["at_risk_skus"],
                "waste_units": round(v["waste_units"], 1),
                "value_at_risk": round(v["value_at_risk"], 2)
            }
            for k, v in dept_summary.items()
        ]
        dept_list.sort(key=lambda x: -x["value_at_risk"])

        return {
            "store_id": store_id or "ALL",
            "total_skus": total_skus,
            "critical_count": len(critical_items),
            "moderate_count": len(moderate_items),
            "overstock_count": len(overstock_items),
            "stockout_count": len(stockout_items),
            "healthy_count": len(healthy_items),
            "total_units_at_risk": round(total_units_at_risk, 1),
            "total_cost_at_risk": round(total_cost_at_risk, 2),
            "total_retail_value_at_risk": round(total_retail_value_at_risk, 2),
            "total_co2_at_risk_kg": round(total_co2_at_risk_kg, 2),
            "total_inventory_value": round(total_inventory_value, 2),
            "store_freshness_index": store_freshness_index,
            "department_breakdown": dept_list,
            "urgent_items": critical_items[:5]
        }

    @classmethod
    def run_rescue_scenario(cls, params: Optional[Dict[str, Any]] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Orchestrates specialized agents to run real-time multi-agent perishable rescue simulation scoped to user.
        """
        all_items = cls.get_inventory_analytics(store_id="ALL", user_id=user_id)
        return Orchestrator.run_pipeline(all_inventory_items=all_items, scenario_params=params)

    @classmethod
    def execute_action(
        cls, 
        action_payload: Dict[str, Any], 
        manager_notes: str = "", 
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Approve and execute an optimized rescue action, updating physical SQLite stock.
        """
        conn = get_connection()
        cur = conn.cursor()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        action_type = action_payload.get("action_type")
        inv_id = action_payload.get("inventory_id")
        sku = action_payload.get("sku")
        store_id = action_payload.get("source_store_id")
        target_store_id = action_payload.get("target_store_id")
        units = int(action_payload.get("units_affected", 0))
        discount_pct = int(action_payload.get("recommended_discount_pct", 0))
        revenue_saved = float(action_payload.get("net_economic_yield", action_payload.get("projected_revenue_saved", 0.0)))
        waste_avoided_kg = float(action_payload.get("projected_waste_avoided_kg", 0.0))
        rationale = action_payload.get("manager_explanation", action_payload.get("rationale", ""))

        if action_type == "DISCOUNT":
            cur.execute("""
            UPDATE inventory 
            SET current_discount_pct = ?
            WHERE id = ?
            """, (discount_pct, inv_id))
            message = f"Applied {discount_pct}% dynamic markdown on SKU {sku} in {store_id}."

        elif action_type == "TRANSFER":
            cur.execute("""
            UPDATE inventory
            SET stock_on_hand = MAX(0, stock_on_hand - ?)
            WHERE id = ?
            """, (units, inv_id))

            if target_store_id:
                cur.execute("""
                UPDATE inventory
                SET stock_on_hand = stock_on_hand + ?
                WHERE store_id = ? AND sku = ?
                """, (units, target_store_id, sku))
            message = f"Transferred {units} units of {sku} from {store_id} to {target_store_id or 'partner store'}."

        elif action_type == "DONATE":
            cur.execute("""
            UPDATE inventory
            SET stock_on_hand = MAX(0, stock_on_hand - ?)
            WHERE id = ?
            """, (units, inv_id))
            message = f"Dispatched {units} units of {sku} from {store_id} to food pantry."

        elif action_type == "PAUSE_PO":
            message = f"Placed 48-hour delivery hold on replenishment PO for {sku} in {store_id}."

        elif action_type == "REPLENISH":
            cur.execute("""
            UPDATE inventory
            SET stock_on_hand = stock_on_hand + ?
            WHERE id = ?
            """, (units, inv_id))
            message = f"Executed priority replenishment order for {units} units of {sku} in {store_id}."

        else:
            message = f"Executed {action_type} on {sku}."

        # Record to rescue_actions audit table with user_id
        cur.execute("""
        INSERT INTO rescue_actions (
            user_id, inventory_id, store_id, sku, action_type, action_details, 
            discount_pct, transfer_to_store, units_affected, 
            projected_waste_avoided_kg, projected_revenue_saved, 
            status, created_at, executed_at, rationale
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'EXECUTED', ?, ?, ?)
        """, (
            user_id, inv_id, store_id, sku, action_type, message + (f" Note: {manager_notes}" if manager_notes else ""),
            discount_pct, target_store_id, units,
            waste_avoided_kg, revenue_saved,
            now_str, now_str, rationale
        ))

        action_record_id = cur.lastrowid

        # System audit log
        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'INFO', 'RESCUE_ACTION_APPROVED_AND_EXECUTED', ?, ?)
        """, (
            now_str,
            message,
            json.dumps({"user_id": user_id, "action_payload": action_payload, "manager_notes": manager_notes})
        ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "action_record_id": action_record_id,
            "action_type": action_type,
            "message": message,
            "executed_at": now_str
        }

    @classmethod
    def modify_and_execute_action(
        cls, 
        action_payload: Dict[str, Any], 
        modified_params: Dict[str, Any],
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Allows store managers to adjust discount % or transfer quantity before approving and executing.
        """
        updated_payload = dict(action_payload)
        
        if "discount_pct" in modified_params and updated_payload.get("action_type") == "DISCOUNT":
            mod_disc = int(modified_params["discount_pct"])
            updated_payload["recommended_discount_pct"] = mod_disc
            orig_price = float(updated_payload.get("original_price", 40.0))
            new_price = round(orig_price * (1.0 - (mod_disc / 100.0)), 2)
            updated_payload["discounted_price"] = new_price
            updated_payload["projected_revenue_saved"] = round(int(updated_payload["units_affected"]) * new_price, 2)
            updated_payload["net_economic_yield"] = updated_payload["projected_revenue_saved"]

        if "units_affected" in modified_params:
            mod_units = int(modified_params["units_affected"])
            updated_payload["units_affected"] = mod_units
            if updated_payload.get("action_type") == "TRANSFER":
                selling_price = float(updated_payload.get("projected_revenue_saved", 50.0) / max(1, action_payload.get("units_affected", 1)))
                transit_cost = round(mod_units * 5.0, 2)
                gross_rev = round(mod_units * selling_price, 2)
                updated_payload["projected_revenue_saved"] = gross_rev
                updated_payload["transit_cost"] = transit_cost
                updated_payload["net_economic_yield"] = round(gross_rev - transit_cost, 2)
            elif updated_payload.get("action_type") == "REPLENISH":
                unit_rev = float(updated_payload.get("projected_revenue_saved", 40.0) / max(1, action_payload.get("units_affected", 1)))
                unit_yield = float(updated_payload.get("net_economic_yield", 12.0) / max(1, action_payload.get("units_affected", 1)))
                updated_payload["projected_revenue_saved"] = round(mod_units * unit_rev, 2)
                updated_payload["net_economic_yield"] = round(mod_units * unit_yield, 2)

        notes = modified_params.get("notes", "Manager adjusted action parameters before execution.")
        return cls.execute_action(updated_payload, manager_notes=notes, user_id=user_id)

    @classmethod
    def reject_action(
        cls, 
        action_payload: Dict[str, Any], 
        rejection_reason: str,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Logs a manager's explicit rejection of a recommended action.
        DOES NOT alter physical inventory stock.
        """
        conn = get_connection()
        cur = conn.cursor()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        action_type = action_payload.get("action_type")
        inv_id = action_payload.get("inventory_id")
        sku = action_payload.get("sku")
        store_id = action_payload.get("source_store_id")

        message = f"Manager REJECTED proposed {action_type} for SKU {sku} in {store_id}. Reason: {rejection_reason}"

        cur.execute("""
        INSERT INTO rescue_actions (
            user_id, inventory_id, store_id, sku, action_type, action_details, 
            discount_pct, transfer_to_store, units_affected, 
            projected_waste_avoided_kg, projected_revenue_saved, 
            status, created_at, executed_at, rationale
        ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, 0, 0.0, 0.0, 'REJECTED', ?, ?, ?)
        """, (
            user_id, inv_id, store_id, sku, action_type, message,
            now_str, now_str, rejection_reason
        ))

        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'WARNING', 'RESCUE_ACTION_REJECTED', ?, ?)
        """, (
            now_str,
            message,
            json.dumps({"user_id": user_id, "action_payload": action_payload, "rejection_reason": rejection_reason})
        ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "status": "REJECTED",
            "message": message,
            "rejected_at": now_str
        }

    @classmethod
    def get_results_history(cls, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch cumulative impact metrics and historical executed rescue actions scoped to user.
        """
        conn = get_connection()
        cur = conn.cursor()

        query = """
        SELECT 
            ra.id,
            ra.user_id,
            ra.inventory_id,
            ra.store_id,
            COALESCE(s.name, ra.store_id) AS store_name,
            ra.sku,
            COALESCE(p.name, ra.sku) AS product_name,
            COALESCE(p.department, 'Perishables') AS department,
            ra.action_type,
            ra.action_details,
            ra.discount_pct,
            ra.transfer_to_store,
            ra.units_affected,
            ra.projected_waste_avoided_kg,
            ra.projected_revenue_saved,
            ra.status,
            ra.executed_at,
            ra.rationale
        FROM rescue_actions ra
        LEFT JOIN products p ON ra.sku = p.sku
        LEFT JOIN stores s ON ra.store_id = s.id
        """
        params = []
        if user_id is not None:
            query += " WHERE (ra.user_id = ? OR ra.store_id IN (SELECT id FROM stores WHERE user_id = ?))"
            params.extend([user_id, user_id])
        query += " ORDER BY ra.id DESC"

        cur.execute(query, params)
        rows = cur.fetchall()
        actions = [dict(r) for r in rows]

        executed_only = [a for a in actions if a["status"] == "EXECUTED"]
        total_revenue_saved = sum(a["projected_revenue_saved"] for a in executed_only)
        total_waste_avoided_kg = sum(a["projected_waste_avoided_kg"] for a in executed_only)
        total_units_rescued = sum(a["units_affected"] for a in executed_only)
        total_actions_count = len(executed_only)
        total_rejections_count = sum(1 for a in actions if a["status"] == "REJECTED")

        co2_avoided_total = round(total_waste_avoided_kg * 2.5, 2)
        meals_total = int(total_waste_avoided_kg / 0.45)

        conn.close()

        return {
            "cumulative_impact": {
                "total_actions_executed": total_actions_count,
                "total_rejections": total_rejections_count,
                "total_revenue_saved": round(total_revenue_saved, 2),
                "total_waste_avoided_kg": round(total_waste_avoided_kg, 2),
                "total_units_rescued": total_units_rescued,
                "total_co2_avoided_kg": co2_avoided_total,
                "meals_equivalent_provided": meals_total
            },
            "executed_actions": actions
        }

    @classmethod
    def get_audit_log(cls, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch audit trail of executed and rejected actions scoped to user.
        """
        res = cls.get_results_history(user_id=user_id)
        return res.get("executed_actions", [])

    @classmethod
    def add_inventory_item(cls, payload: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Add a product and batch directly into the SQLite inventory ledger with validation,
        associating it with the authenticated customer's store.
        """
        name = str(payload.get("name", "")).strip()
        if not name:
            return {"success": False, "error": "Product name is required."}

        conn = get_connection()
        cur = conn.cursor()

        # Resolve store for user
        store_id = str(payload.get("store_id", "")).strip()
        if user_id is not None:
            cur.execute("SELECT id FROM stores WHERE user_id = ?", (user_id,))
            user_stores = [r["id"] for r in cur.fetchall()]
            if store_id in user_stores:
                pass
            elif user_stores:
                store_id = user_stores[0]
            else:
                # User has no stores yet; auto-create one
                store_id = f"STORE-CUST-{user_id:03d}"
                cur.execute("""
                INSERT INTO stores (id, name, location_type, address, daily_footfall, cooler_capacity_sqft, user_id, city, store_type, branch_count, categories)
                VALUES (?, ?, 'Hyderabad', 'Main Commercial Road', 1200, 450, ?, 'Hyderabad', 'Supermarket', 1, 'Vegetables & Fruits, Dairy')
                """, (store_id, f"My Store", user_id))
        else:
            if store_id not in ("STORE-101", "STORE-102"):
                store_id = "STORE-101"

        try:
            stock = int(payload.get("stock_on_hand", 0))
            if stock < 0:
                conn.close()
                return {"success": False, "error": "Stock available cannot be negative."}
        except (ValueError, TypeError):
            conn.close()
            return {"success": False, "error": "Invalid stock quantity."}

        try:
            daily_sales = float(payload.get("avg_daily_sales", 10.0))
            if daily_sales < 0:
                conn.close()
                return {"success": False, "error": "Daily sales cannot be negative."}
        except (ValueError, TypeError):
            daily_sales = 5.0

        expiry_date = str(payload.get("expiry_date", "")).strip()
        if not expiry_date:
            conn.close()
            return {"success": False, "error": "Expiry date is required."}

        if len(expiry_date) == 10:
            expiry_date += " 18:00"

        try:
            selling_price = float(payload.get("selling_price", 40.0))
            if selling_price <= 0:
                conn.close()
                return {"success": False, "error": "Selling price must be greater than zero."}
        except (ValueError, TypeError):
            conn.close()
            return {"success": False, "error": "Invalid selling price."}

        try:
            cost_price = float(payload.get("cost_price", round(selling_price * 0.7, 2)))
            if cost_price < 0:
                conn.close()
                return {"success": False, "error": "Cost price cannot be negative."}
        except (ValueError, TypeError):
            cost_price = round(selling_price * 0.7, 2)

        department = str(payload.get("department", "Vegetables & Fruits")).strip() or "Vegetables & Fruits"
        unit = str(payload.get("unit", "packet")).strip() or "packet"
        shelf_life_days = int(payload.get("shelf_life_days", 4))
        safety_stock = int(payload.get("safety_stock", max(5, int(daily_sales * 1.5))))
        supplier = str(payload.get("supplier", "Local APMC Mandi")).strip() or "Local APMC Mandi"
        incoming_stock = int(payload.get("incoming_stock", 0) or 0)
        delivery_date = str(payload.get("delivery_date", "")).strip()
        promotion_info = str(payload.get("promotion_info", "")).strip()

        # Check or create product
        custom_sku = str(payload.get("sku", "")).strip()
        if custom_sku:
            sku = custom_sku
            cur.execute("SELECT sku FROM products WHERE sku = ?", (sku,))
            if not cur.fetchone():
                cur.execute("""
                INSERT INTO products (sku, name, department, unit, cost_price, selling_price, shelf_life_days, storage_zone, co2_footprint_kg, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Chilled Cold Room', 0.8, ?)
                """, (sku, name, department, unit, cost_price, selling_price, shelf_life_days, f"Fresh {name} in {department}"))
        else:
            cur.execute("SELECT sku FROM products WHERE LOWER(name) = LOWER(?) LIMIT 1", (name,))
            existing_p = cur.fetchone()
            if existing_p:
                sku = existing_p["sku"]
            else:
                prefix = "SKU-CUS"
                if "veg" in department.lower():
                    prefix = "SKU-VEG"
                elif "fruit" in department.lower():
                    prefix = "SKU-FRU"
                elif "dairy" in department.lower():
                    prefix = "SKU-DAI"
                elif "bake" in department.lower():
                    prefix = "SKU-BAK"
                elif "staple" in department.lower() or "pantry" in department.lower():
                    prefix = "SKU-PAN"

                cur.execute("SELECT COUNT(*) AS cnt FROM products WHERE sku LIKE ?", (f"{prefix}%",))
                cnt = cur.fetchone()["cnt"] + 1
                sku = f"{prefix}-{cnt:03d}"

                cur.execute("""
                INSERT INTO products (sku, name, department, unit, cost_price, selling_price, shelf_life_days, storage_zone, co2_footprint_kg, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Chilled Cold Room', 0.8, ?)
                """, (sku, name, department, unit, cost_price, selling_price, shelf_life_days, f"Fresh {name} in {department}"))

        now = datetime.datetime.now()
        batch_number = f"BAT-{now.strftime('%m%d')}-{sku[-3:] if len(sku) >= 3 else '001'}"
        now_str = now.strftime("%Y-%m-%d %H:%M")

        cur.execute("""
        INSERT INTO inventory (
            user_id, store_id, sku, batch_number, stock_on_hand, safety_stock, 
            received_date, expiry_date, avg_daily_sales, forecast_daily_demand, 
            current_discount_pct, status, supplier, incoming_stock, delivery_date, promotion_info
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'ACTIVE', ?, ?, ?, ?)
        """, (
            user_id, store_id, sku, batch_number, stock, safety_stock, 
            now_str, expiry_date, daily_sales, daily_sales,
            supplier, incoming_stock, delivery_date, promotion_info
        ))

        inv_id = cur.lastrowid

        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'INFO', 'INVENTORY_PRODUCT_ADDED', ?, ?)
        """, (now_str, f"Added {stock} units of {name} ({sku}) to {store_id}", json.dumps({"user_id": user_id, "sku": sku, "batch": batch_number, "stock": stock})))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Successfully added {name} ({stock} {unit}) to stock.",
            "inventory_id": inv_id,
            "sku": sku,
            "batch_number": batch_number,
            "store_id": store_id
        }

    @classmethod
    def preview_csv_data(cls, csv_text: str) -> Dict[str, Any]:
        """
        Parses and validates CSV content without saving, returning row-by-row status for manager review.
        """
        if not csv_text or not csv_text.strip():
            return {"success": False, "error": "CSV file content is empty."}

        f = io.StringIO(csv_text.strip())
        reader = csv.reader(f)

        try:
            headers = next(reader)
        except StopIteration:
            return {"success": False, "error": "CSV file contains no rows."}

        header_map = {}
        for idx, h in enumerate(headers):
            clean_h = h.strip().lower().replace("_", "").replace(" ", "").replace("-", "")
            if clean_h in ("product", "productname", "name", "item", "itemname"):
                header_map["name"] = idx
            elif clean_h in ("sku", "itemcode", "barcode"):
                header_map["sku"] = idx
            elif clean_h in ("stock", "stockavailable", "stockonhand", "quantity", "qty", "currentstock"):
                header_map["stock_on_hand"] = idx
            elif clean_h in ("dailysales", "expecteddailysales", "avgdailysales", "velocity", "demand", "unitssoldperday"):
                header_map["avg_daily_sales"] = idx
            elif clean_h in ("expiry", "expirydate", "expires", "shelflife"):
                header_map["expiry_date"] = idx
            elif clean_h in ("price", "sellingprice", "mrp", "unitprice", "unitsellingprice"):
                header_map["selling_price"] = idx
            elif clean_h in ("cost", "costprice", "unitcost"):
                header_map["cost_price"] = idx
            elif clean_h in ("unit", "measure", "uom"):
                header_map["unit"] = idx
            elif clean_h in ("dept", "department", "category"):
                header_map["department"] = idx
            elif clean_h in ("supplier", "vendor", "distributor"):
                header_map["supplier"] = idx
            elif clean_h in ("incomingstock", "incomingqty", "pendingstock"):
                header_map["incoming_stock"] = idx
            elif clean_h in ("deliverydate", "incomingdate"):
                header_map["delivery_date"] = idx
            elif clean_h in ("promotion", "discount", "promo", "promotioninfo"):
                header_map["promotion_info"] = idx

        if "name" not in header_map:
            return {"success": False, "error": "Missing required header: 'Product Name' or 'Item Name'."}

        parsed_rows = []
        valid_count = 0
        invalid_count = 0
        row_idx = 1

        for row in reader:
            row_idx += 1
            if not row or all(c.strip() == "" for c in row):
                continue

            errors = []
            name = row[header_map["name"]].strip() if len(row) > header_map["name"] else ""
            if not name:
                errors.append("Product name is missing.")

            sku = row[header_map["sku"]].strip() if "sku" in header_map and len(row) > header_map["sku"] else ""

            stock = 0
            if "stock_on_hand" in header_map and len(row) > header_map["stock_on_hand"]:
                raw_stock = row[header_map["stock_on_hand"]].strip()
                try:
                    stock = int(float(raw_stock))
                    if stock < 0:
                        errors.append("Stock quantity cannot be negative.")
                except (ValueError, TypeError):
                    errors.append(f"Invalid stock quantity: '{raw_stock}'")
            else:
                errors.append("Stock quantity is missing.")

            selling_price = 0.0
            if "selling_price" in header_map and len(row) > header_map["selling_price"]:
                raw_price = row[header_map["selling_price"]].replace("₹", "").replace(",", "").strip()
                try:
                    selling_price = float(raw_price)
                    if selling_price <= 0:
                        errors.append("Selling price must be greater than zero.")
                except (ValueError, TypeError):
                    errors.append(f"Invalid selling price: '{raw_price}'")
            else:
                errors.append("Selling price is missing.")

            cost_price = 0.0
            if "cost_price" in header_map and len(row) > header_map["cost_price"]:
                raw_cost = row[header_map["cost_price"]].replace("₹", "").replace(",", "").strip()
                try:
                    cost_price = float(raw_cost)
                    if cost_price < 0:
                        errors.append("Cost price cannot be negative.")
                except (ValueError, TypeError):
                    errors.append(f"Invalid cost price: '{raw_cost}'")
            else:
                cost_price = round(selling_price * 0.7, 2) if selling_price > 0 else 0.0

            daily_sales = 0.0
            if "avg_daily_sales" in header_map and len(row) > header_map["avg_daily_sales"]:
                raw_sales = row[header_map["avg_daily_sales"]].strip()
                try:
                    daily_sales = float(raw_sales)
                    if daily_sales < 0:
                        errors.append("Daily sales cannot be negative.")
                except (ValueError, TypeError):
                    errors.append(f"Invalid daily sales: '{raw_sales}'")
            else:
                daily_sales = 5.0

            expiry_date = ""
            if "expiry_date" in header_map and len(row) > header_map["expiry_date"]:
                raw_exp = row[header_map["expiry_date"]].strip()
                parsed_dt = None
                for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        parsed_dt = datetime.datetime.strptime(raw_exp, fmt)
                        break
                    except ValueError:
                        pass
                if parsed_dt:
                    expiry_date = parsed_dt.strftime("%Y-%m-%d 18:00")
                else:
                    errors.append(f"Invalid date format: '{raw_exp}' (use YYYY-MM-DD or DD-MM-YYYY)")
            else:
                errors.append("Expiry date is missing.")

            unit = row[header_map["unit"]].strip() if "unit" in header_map and len(row) > header_map["unit"] else "packet"
            department = row[header_map["department"]].strip() if "department" in header_map and len(row) > header_map["department"] else "Vegetables & Fruits"
            supplier = row[header_map["supplier"]].strip() if "supplier" in header_map and len(row) > header_map["supplier"] else "Local APMC Mandi"
            incoming_stock = 0
            if "incoming_stock" in header_map and len(row) > header_map["incoming_stock"]:
                try:
                    incoming_stock = int(float(row[header_map["incoming_stock"]].strip() or 0))
                except (ValueError, TypeError):
                    incoming_stock = 0
            delivery_date = row[header_map["delivery_date"]].strip() if "delivery_date" in header_map and len(row) > header_map["delivery_date"] else ""
            promotion_info = row[header_map["promotion_info"]].strip() if "promotion_info" in header_map and len(row) > header_map["promotion_info"] else ""

            is_valid = len(errors) == 0
            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1

            parsed_rows.append({
                "row_number": row_idx,
                "is_valid": is_valid,
                "errors": errors,
                "data": {
                    "name": name,
                    "sku": sku,
                    "stock_on_hand": stock,
                    "selling_price": selling_price,
                    "cost_price": cost_price,
                    "avg_daily_sales": daily_sales,
                    "expiry_date": expiry_date,
                    "unit": unit or "packet",
                    "department": department or "Vegetables & Fruits",
                    "supplier": supplier or "Local APMC Mandi",
                    "incoming_stock": incoming_stock,
                    "delivery_date": delivery_date,
                    "promotion_info": promotion_info
                }
            })

        return {
            "success": True,
            "total_rows": len(parsed_rows),
            "valid_rows": valid_count,
            "invalid_rows": invalid_count,
            "rows": parsed_rows
        }

    @classmethod
    def upload_csv_inventory(
        cls, 
        csv_text: str, 
        default_store_id: Optional[str] = None, 
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Validates and commits CSV inventory into SQLite database for the authenticated user.
        """
        preview = cls.preview_csv_data(csv_text)
        if not preview.get("success"):
            return preview

        added_count = 0
        errors = []

        for row_item in preview.get("rows", []):
            if not row_item["is_valid"]:
                errors.append(f"Row {row_item['row_number']}: " + "; ".join(row_item["errors"]))
                continue

            data = row_item["data"]
            if default_store_id:
                data["store_id"] = default_store_id

            res = cls.add_inventory_item(data, user_id=user_id)
            if res.get("success"):
                added_count += 1
            else:
                errors.append(f"Row {row_item['row_number']}: {res.get('error')}")

        return {
            "success": added_count > 0,
            "added_count": added_count,
            "invalid_count": preview.get("invalid_rows", 0),
            "errors": errors,
            "message": f"Successfully imported {added_count} products from CSV."
        }

    @classmethod
    def edit_inventory_item(cls, user_id: int, inventory_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Edit an existing product and batch in the SQLite inventory ledger with ownership checks.
        """
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT i.id, i.sku, i.store_id 
        FROM inventory i
        JOIN stores s ON i.store_id = s.id
        WHERE i.id = ? AND (i.user_id = ? OR s.user_id = ?)
        """, (inventory_id, user_id, user_id))
        item = cur.fetchone()

        if not item:
            conn.close()
            return {"success": False, "error": "Inventory item not found or you do not have permission to edit it."}

        sku = item["sku"]

        updates_inv = []
        params_inv = []

        if "stock_on_hand" in payload:
            try:
                stock = int(payload["stock_on_hand"])
                if stock < 0:
                    conn.close()
                    return {"success": False, "error": "Stock quantity cannot be negative."}
                updates_inv.append("stock_on_hand = ?")
                params_inv.append(stock)
            except (ValueError, TypeError):
                conn.close()
                return {"success": False, "error": "Invalid stock quantity."}

        if "avg_daily_sales" in payload:
            try:
                sales = float(payload["avg_daily_sales"])
                if sales < 0:
                    conn.close()
                    return {"success": False, "error": "Daily sales cannot be negative."}
                updates_inv.append("avg_daily_sales = ?")
                params_inv.append(sales)
                updates_inv.append("forecast_daily_demand = ?")
                params_inv.append(sales)
            except (ValueError, TypeError):
                pass

        if "expiry_date" in payload and payload["expiry_date"]:
            exp = str(payload["expiry_date"]).strip()
            if len(exp) == 10:
                exp += " 18:00"
            updates_inv.append("expiry_date = ?")
            params_inv.append(exp)

        if "supplier" in payload:
            updates_inv.append("supplier = ?")
            params_inv.append(str(payload["supplier"]).strip())

        if "incoming_stock" in payload:
            try:
                updates_inv.append("incoming_stock = ?")
                params_inv.append(int(payload.get("incoming_stock", 0) or 0))
            except (ValueError, TypeError):
                pass

        if "delivery_date" in payload:
            updates_inv.append("delivery_date = ?")
            params_inv.append(str(payload["delivery_date"]).strip())

        if "promotion_info" in payload:
            updates_inv.append("promotion_info = ?")
            params_inv.append(str(payload["promotion_info"]).strip())

        if updates_inv:
            params_inv.append(inventory_id)
            cur.execute(f"UPDATE inventory SET {', '.join(updates_inv)} WHERE id = ?", params_inv)

        # Update product master info
        updates_prod = []
        params_prod = []
        if "selling_price" in payload:
            try:
                sp = float(payload["selling_price"])
                if sp <= 0:
                    conn.close()
                    return {"success": False, "error": "Selling price must be greater than zero."}
                updates_prod.append("selling_price = ?")
                params_prod.append(sp)
            except (ValueError, TypeError):
                pass

        if "cost_price" in payload:
            try:
                cp = float(payload["cost_price"])
                if cp < 0:
                    conn.close()
                    return {"success": False, "error": "Cost price cannot be negative."}
                updates_prod.append("cost_price = ?")
                params_prod.append(cp)
            except (ValueError, TypeError):
                pass

        if "name" in payload and payload["name"]:
            updates_prod.append("name = ?")
            params_prod.append(str(payload["name"]).strip())

        if "department" in payload and payload["department"]:
            updates_prod.append("department = ?")
            params_prod.append(str(payload["department"]).strip())

        if updates_prod:
            params_prod.append(sku)
            cur.execute(f"UPDATE products SET {', '.join(updates_prod)} WHERE sku = ?", params_prod)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'INFO', 'INVENTORY_PRODUCT_UPDATED', ?, ?)
        """, (now_str, f"User {user_id} updated inventory item {inventory_id} ({sku})", json.dumps(payload)))

        conn.commit()
        conn.close()
        return {"success": True, "message": "Product inventory record updated successfully."}

    @classmethod
    def delete_inventory_item(cls, user_id: int, inventory_id: int) -> Dict[str, Any]:
        """
        Delete an existing inventory batch with customer isolation check.
        """
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        SELECT i.id, i.sku, i.store_id 
        FROM inventory i
        JOIN stores s ON i.store_id = s.id
        WHERE i.id = ? AND (i.user_id = ? OR s.user_id = ?)
        """, (inventory_id, user_id, user_id))
        item = cur.fetchone()

        if not item:
            conn.close()
            return {"success": False, "error": "Inventory item not found or you do not have permission to delete it."}

        cur.execute("UPDATE inventory SET status = 'DELETED' WHERE id = ?", (inventory_id,))
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'WARNING', 'INVENTORY_PRODUCT_DELETED', ?, ?)
        """, (now_str, f"User {user_id} removed inventory item {inventory_id}", json.dumps({"inventory_id": inventory_id})))

        conn.commit()
        conn.close()
        return {"success": True, "message": "Product removed from inventory."}

    # ==========================================
    # CUSTOMER AUTHENTICATION & ACCESS CONTROL
    # ==========================================

    @classmethod
    def register_user(cls, username: str, email: str, password: str) -> Dict[str, Any]:
        """
        Creates new customer account using salted PBKDF2-HMAC-SHA256 password hashing.
        """
        username = (username or "").strip()
        email = (email or "").strip().lower()
        password = (password or "").strip()

        if not username or len(username) < 3:
            return {"success": False, "error": "Username must be at least 3 characters."}
        if not email or "@" not in email:
            return {"success": False, "error": "Please provide a valid email address."}
        if not password or len(password) < 6:
            return {"success": False, "error": "Password must be at least 6 characters."}

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)", (username, email))
        if cur.fetchone():
            conn.close()
            return {"success": False, "error": "An account with that username or email already exists."}

        pwd_hash, salt = hash_password(password)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
        INSERT INTO users (username, email, password_hash, salt, role, created_at, is_onboarded)
        VALUES (?, ?, ?, ?, 'store_manager', ?, 0)
        """, (username, email, pwd_hash, salt, now_str))
        user_id = cur.lastrowid

        token = secrets.token_hex(24)
        expires_at = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (token, user_id, now_str, expires_at))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "token": token,
            "user": {
                "id": user_id,
                "username": username,
                "email": email,
                "role": "store_manager",
                "is_onboarded": False,
                "stores": []
            }
        }

    @classmethod
    def login_user(cls, username_or_email: str, password: str) -> Dict[str, Any]:
        """
        Authenticates user with username/email and password against stored PBKDF2 hash.
        """
        identifier = (username_or_email or "").strip().lower()
        password = (password or "").strip()

        if not identifier or not password:
            return {"success": False, "error": "Username/email and password are required."}

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE LOWER(username) = ? OR LOWER(email) = ?", (identifier, identifier))
        user = cur.fetchone()

        if not user:
            conn.close()
            return {"success": False, "error": "Invalid username or password."}

        if not verify_password(password, user["password_hash"], user["salt"]):
            conn.close()
            return {"success": False, "error": "Invalid username or password."}

        token = secrets.token_hex(24)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (token, user["id"], now_str, expires_at))
        conn.commit()

        cur.execute("SELECT id, name, city, store_type, branch_count, categories FROM stores WHERE user_id = ?", (user["id"],))
        stores = [dict(r) for r in cur.fetchall()]
        conn.close()

        return {
            "success": True,
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "is_onboarded": bool(user["is_onboarded"]),
                "stores": stores
            }
        }

    @classmethod
    def demo_login(cls, demo_key: str = "demo_hitam") -> Dict[str, Any]:
        """
        Safe 1-click login for hackathon demo mode.
        """
        target_username = "demo_hitam"
        if "miyapur" in demo_key.lower():
            target_username = "demo_miyapur"

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (target_username,))
        user = cur.fetchone()

        if not user:
            conn.close()
            return {"success": False, "error": f"Demo user '{target_username}' not seeded."}

        token = secrets.token_hex(24)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (token, user["id"], now_str, expires_at))
        conn.commit()

        cur.execute("SELECT id, name, city, store_type, branch_count, categories FROM stores WHERE user_id = ?", (user["id"],))
        stores = [dict(r) for r in cur.fetchall()]
        conn.close()

        return {
            "success": True,
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "is_onboarded": bool(user["is_onboarded"]),
                "stores": stores
            }
        }

    @classmethod
    def get_user_by_token(cls, token: str) -> Optional[Dict[str, Any]]:
        """
        Validates session token and returns authenticated user metadata.
        """
        if not token:
            return None
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT u.id, u.username, u.email, u.role, u.is_onboarded
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
        """, (token,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        user = dict(row)
        user["is_onboarded"] = bool(user["is_onboarded"])
        cur.execute("SELECT id, name, city, store_type, branch_count, categories FROM stores WHERE user_id = ?", (user["id"],))
        user["stores"] = [dict(r) for r in cur.fetchall()]
        conn.close()
        return user

    @classmethod
    def logout_user(cls, token: str) -> bool:
        """
        Terminates the active session token.
        """
        if not token:
            return False
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return True

    @classmethod
    def complete_onboarding(
        cls, 
        user_id: int, 
        store_name: str, 
        city: str, 
        store_type: str, 
        branch_count: int, 
        categories: str
    ) -> Dict[str, Any]:
        """
        Completes the first-time setup wizard for a new grocery customer.
        """
        store_name = (store_name or "").strip()
        if not store_name:
            return {"success": False, "error": "Store or business name is required."}

        city = (city or "Hyderabad").strip()
        store_type = (store_type or "Supermarket").strip()
        try:
            branch_count = max(1, int(branch_count))
        except (ValueError, TypeError):
            branch_count = 1
        categories = (categories or "Vegetables & Fruits, Dairy, Bakery").strip()

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT id FROM stores WHERE user_id = ?", (user_id,))
        existing = cur.fetchone()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if existing:
            store_id = existing["id"]
            cur.execute("""
            UPDATE stores 
            SET name = ?, city = ?, store_type = ?, branch_count = ?, categories = ?, location_type = ?
            WHERE id = ?
            """, (store_name, city, store_type, branch_count, categories, city, store_id))
        else:
            store_id = f"STORE-CUST-{user_id:03d}"
            cur.execute("""
            INSERT INTO stores (id, name, location_type, address, daily_footfall, cooler_capacity_sqft, user_id, city, store_type, branch_count, categories)
            VALUES (?, ?, ?, 'Plot 42, Sector 1', 1500, 500, ?, ?, ?, ?, ?)
            """, (store_id, store_name, city, user_id, city, store_type, branch_count, categories))

        cur.execute("UPDATE users SET is_onboarded = 1 WHERE id = ?", (user_id,))

        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'INFO', 'CUSTOMER_ONBOARDING_COMPLETED', ?, ?)
        """, (now_str, f"User {user_id} onboarded store {store_name} ({store_id})", json.dumps({"store_id": store_id, "name": store_name, "city": city})))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "store_id": store_id,
            "store_name": store_name,
            "message": f"Store '{store_name}' registered successfully."
        }

    @classmethod
    def get_user_stores(cls, user_id: int) -> List[Dict[str, Any]]:
        """
        Fetch stores belonging to the authenticated customer.
        """
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, city, store_type, branch_count, categories FROM stores WHERE user_id = ?", (user_id,))
        stores = [dict(r) for r in cur.fetchall()]
        conn.close()
        return stores

    @classmethod
    def get_audit_log(cls, user_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch audit log of recommendations, approvals, and rejections.
        """
        conn = get_connection()
        cur = conn.cursor()

        query = """
        SELECT 
            ra.id,
            ra.user_id,
            ra.action_type,
            ra.action_details,
            ra.units_affected,
            ra.discount_pct,
            ra.transfer_to_store,
            ra.projected_waste_avoided_kg,
            ra.projected_revenue_saved,
            ra.status,
            ra.executed_at,
            ra.rationale,
            p.name AS product_name,
            s.name AS store_name
        FROM rescue_actions ra
        LEFT JOIN products p ON ra.sku = p.sku
        LEFT JOIN stores s ON ra.store_id = s.id
        """
        params = []
        if user_id is not None:
            query += " WHERE (ra.user_id = ? OR ra.store_id IN (SELECT id FROM stores WHERE user_id = ?))"
            params.extend([user_id, user_id])
        query += " ORDER BY ra.id DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    # ================================================================
    # GOOGLE OAUTH AUTHENTICATION
    # ================================================================
    @classmethod
    def get_google_oauth_config(cls) -> Dict[str, Any]:
        """
        Retrieves current Google OAuth configuration status and credentials instructions.
        """
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

        # Check SQLite settings if not in env
        if not client_id:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT value FROM app_settings WHERE key = 'google_client_id'")
            row = cur.fetchone()
            if row:
                client_id = row["value"].strip()
            cur.execute("SELECT value FROM app_settings WHERE key = 'google_client_secret'")
            row_s = cur.fetchone()
            if row_s:
                client_secret = row_s["value"].strip()
            conn.close()

        configured = bool(client_id)
        instructions = (
            "To enable Google OAuth for FreshGuard AI:\n"
            "1. Visit the Google Cloud Console (console.cloud.google.com/apis/credentials).\n"
            "2. Create an OAuth 2.0 Client ID (Application type: 'Web application').\n"
            "3. Add your app domain (e.g. http://localhost:8080) to 'Authorized JavaScript origins'.\n"
            "4. Add http://localhost:8080/api/auth/google/callback to 'Authorized redirect URIs'.\n"
            "5. Set environment variables GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or save them in settings."
        )

        return {
            "configured": configured,
            "client_id": client_id,
            "has_secret": bool(client_secret),
            "instructions": instructions
        }

    @classmethod
    def save_google_oauth_config(cls, client_id: str, client_secret: str = "") -> Dict[str, Any]:
        """
        Saves Google OAuth Client ID and Secret to persistent app settings.
        """
        client_id = (client_id or "").strip()
        client_secret = (client_secret or "").strip()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO app_settings (key, value, updated_at) VALUES ('google_client_id', ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (client_id, now_str))

        if client_secret:
            cur.execute("""
            INSERT INTO app_settings (key, value, updated_at) VALUES ('google_client_secret', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (client_secret, now_str))

        conn.commit()
        conn.close()

        os.environ["GOOGLE_CLIENT_ID"] = client_id
        if client_secret:
            os.environ["GOOGLE_CLIENT_SECRET"] = client_secret

        return {
            "success": True,
            "configured": bool(client_id),
            "config": cls.get_google_oauth_config(),
            "message": "Google OAuth configuration saved successfully."
        }

    @classmethod
    def authenticate_google_user(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Authenticates a user via Google OAuth ID Token or verified Google profile.
        Creates account if first time, creates session, and takes customer directly to their dashboard.
        """
        email = ""
        name = ""
        google_id = ""

        # Case 1: ID Token credential passed from Google Identity Services (GIS)
        credential = payload.get("credential") or payload.get("id_token") or payload.get("credential_token")
        if credential:
            try:
                # Verify token with Google's tokeninfo endpoint
                verify_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
                req = urllib.request.Request(verify_url, headers={"User-Agent": "FreshGuard-AI/2.2"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status != 200:
                        return {"success": False, "error": f"Google token verification failed (HTTP {resp.status})."}
                    info = json.loads(resp.read().decode("utf-8"))

                email = info.get("email", "").lower().strip()
                name = info.get("name") or info.get("given_name") or email.split("@")[0]
                google_id = info.get("sub", "")

                if not email:
                    return {"success": False, "error": "Google profile did not provide a valid email address."}

                # Verify audience if client_id configured
                config = cls.get_google_oauth_config()
                if config["client_id"] and info.get("aud") != config["client_id"]:
                    return {"success": False, "error": "Google token audience mismatch with configured Client ID."}

            except Exception as e:
                return {"success": False, "error": f"Failed to verify Google token: {str(e)}"}

        # Case 2: Sandbox / Test Google Authentication (for local environments without cloud connection)
        elif payload.get("test_mode") or payload.get("test_login") or payload.get("test_user_email") or payload.get("email"):
            email = str(payload.get("test_user_email") or payload.get("email", "")).lower().strip()
            name = str(payload.get("test_user_name") or payload.get("name", "")).strip() or email.split("@")[0]
            if not email or "@" not in email:
                email = "demo.google.user@gmail.com"
                name = "Google Test User"
            google_id = f"sandbox_google_{abs(hash(email)) % 10000000}"
        else:
            # Missing token or credentials
            config = cls.get_google_oauth_config()
            if not config["configured"]:
                return {
                    "success": False,
                    "error": "Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
                    "needs_config": True,
                    "instructions": config["instructions"]
                }
            return {"success": False, "error": "Missing Google authentication token."}

        # Resolve or create user in SQLite database
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email,))
        existing_user = cur.fetchone()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if existing_user:
            user_id = existing_user["id"]
            username = existing_user["username"]
            role = existing_user["role"]
            is_onboarded = bool(existing_user["is_onboarded"])
        else:
            # Create a clean username from name or email
            base_username = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower().replace(" ", "_"))[:20]
            if not base_username:
                base_username = "customer"
            
            cur.execute("SELECT id FROM users WHERE LOWER(username) = ?", (base_username,))
            if cur.fetchone():
                username = f"{base_username}_{secrets.token_hex(3)}"
            else:
                username = base_username

            dummy_hash, dummy_salt = hash_password(secrets.token_hex(16))
            cur.execute("""
            INSERT INTO users (username, email, password_hash, salt, role, created_at, is_onboarded)
            VALUES (?, ?, ?, ?, 'CUSTOMER', ?, 1)
            """, (username, email, dummy_hash, dummy_salt, now_str))
            user_id = cur.lastrowid
            role = "CUSTOMER"
            is_onboarded = True

            # Auto-provision isolated private customer store
            store_id = f"STORE-CUST-{user_id:03d}"
            cur.execute("""
            INSERT INTO stores (id, name, location_type, address, daily_footfall, cooler_capacity_sqft, user_id, city, store_type, branch_count, categories)
            VALUES (?, ?, 'Local Store', 'Customer Retail Address', 1200, 400, ?, 'Hyderabad', 'Supermarket', 1, 'Vegetables & Fruits, Dairy, Bakery, Packaged')
            """, (store_id, f"{name}'s Store", user_id))

            cur.execute("""
            INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
            VALUES (?, 'INFO', 'GOOGLE_CUSTOMER_REGISTERED', ?, ?)
            """, (now_str, f"Registered new customer via Google: {email} (ID: {user_id})", json.dumps({"email": email, "user_id": user_id})))

        # Create session token
        token = secrets.token_hex(24)
        expires_at = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (token, user_id, now_str, expires_at))
        conn.commit()

        # Fetch customer's stores
        cur.execute("SELECT id, name, city, store_type, branch_count, categories FROM stores WHERE user_id = ?", (user_id,))
        stores = [dict(r) for r in cur.fetchall()]
        conn.close()

        return {
            "success": True,
            "token": token,
            "user": {
                "id": user_id,
                "username": username,
                "email": email,
                "role": role,
                "is_onboarded": is_onboarded,
                "stores": stores
            },
            "message": f"Welcome back, {name}! Logged in via Google."
        }

    # ================================================================
    # BARCODE SCANNING & PRODUCT LOOKUP
    # ================================================================
    KNOWN_BARCODE_DATABASE = {
        "8901262010053": {
            "name": "Amul Taaza Fresh Toned Milk (500ml)",
            "brand": "Amul",
            "category": "dairy",
            "storage_instructions": "Keep refrigerated at 4°C or below",
            "notes": "Daily standardized fresh pasteurized milk pouch"
        },
        "8901262010114": {
            "name": "Amul Gold Full Cream Milk (500ml)",
            "brand": "Amul",
            "category": "dairy",
            "storage_instructions": "Keep refrigerated at 4°C or below",
            "notes": "Full cream homogenized pasteurized milk"
        },
        "8901063012487": {
            "name": "Britannia 100% Whole Wheat Bread (400g)",
            "brand": "Britannia",
            "category": "packaged food",
            "storage_instructions": "Store in a cool, dry place away from direct sunlight",
            "notes": "Zero maida high-fiber whole wheat sliced sandwich bread"
        },
        "8901725181222": {
            "name": "Mother Dairy Classic Dahi / Curd (400g)",
            "brand": "Mother Dairy",
            "category": "dairy",
            "storage_instructions": "Refrigerate between 2°C and 4°C",
            "notes": "Thick set creamy pasteurized dahi tub"
        },
        "8901491101837": {
            "name": "Tata Sampann Unpolished Toor Dal (1kg)",
            "brand": "Tata Sampann",
            "category": "packaged food",
            "storage_instructions": "Store in an airtight container in a dry pantry",
            "notes": "Natural wholesome unpolished pigeon peas rich in protein"
        },
        "8901058852892": {
            "name": "Maggi 2-Minute Masala Noodles (70g)",
            "brand": "Nestle",
            "category": "packaged food",
            "storage_instructions": "Store in a cool, dry and hygienic environment",
            "notes": "Classic Indian spiced instant noodles"
        },
        "8901030383454": {
            "name": "Kissan Fresh Tomato Ketchup (500g)",
            "brand": "Kissan",
            "category": "packaged food",
            "storage_instructions": "Store in a cool dry place. Refrigerate after opening",
            "notes": "Made with 100% real ripe fresh tomatoes"
        },
        "8906010500010": {
            "name": "Epigamia Natural Greek Yogurt (100g)",
            "brand": "Epigamia",
            "category": "dairy",
            "storage_instructions": "Keep refrigerated at 4°C",
            "notes": "High protein strained preservative-free Greek yogurt"
        },
        "8901764012204": {
            "name": "Tropicana 100% Mixed Fruit Juice (1L)",
            "brand": "Tropicana",
            "category": "beverages",
            "storage_instructions": "Refrigerate after opening and consume within 3 days",
            "notes": "100% real fruit juice with no added sugar"
        },
        "7622210817024": {
            "name": "Cadbury Dairy Milk Silk Chocolate (60g)",
            "brand": "Cadbury",
            "category": "packaged food",
            "storage_instructions": "Store in a cool, dry place (15-20°C) to prevent melting",
            "notes": "Smooth creamy milk chocolate bar"
        },
        "8901030001234": {
            "name": "Bru Instant Coffee Jar (100g)",
            "brand": "Bru",
            "category": "beverages",
            "storage_instructions": "Keep container tightly closed in a cool dry place",
            "notes": "Aromatic roasted coffee and chicory blend"
        },
        "8902080000014": {
            "name": "Fresho Farm Fresh Red Tomatoes (1kg)",
            "brand": "Fresho",
            "category": "vegetables",
            "storage_instructions": "Store at ambient room temperature or crisper drawer",
            "notes": "Juicy firm hybrid cooking tomatoes"
        },
        "8902080000021": {
            "name": "Fresho Golden Bananas (1kg)",
            "brand": "Fresho",
            "category": "fruits",
            "storage_instructions": "Store at room temperature; do not refrigerate unripe",
            "notes": "Naturally ripe sweet bananas"
        },
        "8906020000055": {
            "name": "Fresh Cut Tender Chicken Breast (500g)",
            "brand": "Licious",
            "category": "meat",
            "storage_instructions": "Keep refrigerated at 0-4°C or freeze below -18°C",
            "notes": "Clean boneless chilled chicken breast fillets"
        },
        "049000006346": {
            "name": "Coca-Cola Original Taste Can (330ml)",
            "brand": "Coca-Cola",
            "category": "beverages",
            "storage_instructions": "Store in a cool dry place, serve chilled",
            "notes": "Classic sparkling soft drink (UPC-A)"
        },
        "89010300": {
            "name": "Parle-G Glucose Biscuits (50g)",
            "brand": "Parle",
            "category": "packaged food",
            "storage_instructions": "Keep in a cool dry place",
            "notes": "Classic Indian tea-time glucose biscuits (EAN-8)"
        },
        "01234565": {
            "name": "Heinz Tomato Ketchup Squeeze (300g)",
            "brand": "Heinz",
            "category": "packaged food",
            "storage_instructions": "Shake well before use, refrigerate after opening",
            "notes": "Rich thick tomato ketchup (UPC-E)"
        }
    }

    @classmethod
    def lookup_barcode(cls, barcode: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Looks up a product barcode in local catalog and Open Food Facts database.
        Checks for duplicate barcodes in the customer's private product list.
        """
        raw_code = str(barcode or "").strip()
        clean_code = re.sub(r'[^a-zA-Z0-9]', '', raw_code)

        if not clean_code or len(clean_code) < 6:
            return {
                "success": False,
                "barcode": raw_code,
                "error": "Invalid barcode format. Expected EAN-13, EAN-8, UPC-A, or UPC-E format.",
                "found": False
            }

        # Check if customer already has this barcode in their private list
        is_duplicate = False
        existing_name = None
        if user_id is not None:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT id, name FROM customer_products 
            WHERE user_id = ? AND barcode = ? AND status = 'ACTIVE'
            LIMIT 1
            """, (user_id, clean_code))
            dup = cur.fetchone()
            conn.close()
            if dup:
                is_duplicate = True
                existing_name = dup["name"]

        # 1. Check local FMCG database
        if clean_code in cls.KNOWN_BARCODE_DATABASE:
            prod_info = dict(cls.KNOWN_BARCODE_DATABASE[clean_code])
            prod_info["barcode"] = clean_code
            return {
                "success": True,
                "barcode": clean_code,
                "found": True,
                "source": "Local FMCG Catalog",
                "is_duplicate_for_user": is_duplicate,
                "existing_product_name": existing_name,
                "product": prod_info,
                "message": "Product details successfully retrieved from catalog."
            }

        # 2. Query Open Food Facts API (Live Global Database)
        try:
            off_url = f"https://world.openfoodfacts.org/api/v2/product/{clean_code}.json"
            req = urllib.request.Request(off_url, headers={"User-Agent": "FreshGuard-Grocery-Scanner/2.2"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("status") == 1 and "product" in data:
                        off_p = data["product"]
                        name = off_p.get("product_name_en") or off_p.get("product_name") or ""
                        brand = off_p.get("brands", "")
                        if "," in brand:
                            brand = brand.split(",")[0].strip()

                        # Classify category into one of the 7 supported options
                        cat_tags = " ".join(off_p.get("categories_tags", [])).lower()
                        category = "packaged food"
                        if any(w in cat_tags for w in ["fruit", "apple", "banana", "orange", "berry"]):
                            category = "fruits"
                        elif any(w in cat_tags for w in ["vegetable", "tomato", "potato", "onion", "greens"]):
                            category = "vegetables"
                        elif any(w in cat_tags for w in ["dairy", "milk", "cheese", "yogurt", "curd", "butter", "paneer"]):
                            category = "dairy"
                        elif any(w in cat_tags for w in ["meat", "poultry", "chicken", "beef", "pork", "fish", "seafood"]):
                            category = "meat"
                        elif any(w in cat_tags for w in ["beverage", "drink", "juice", "soda", "water", "tea", "coffee"]):
                            category = "beverages"

                        storage = "Store in a cool, dry place"
                        if category in ("dairy", "meat"):
                            storage = "Keep refrigerated at 4°C"

                        if name:
                            return {
                                "success": True,
                                "barcode": clean_code,
                                "found": True,
                                "source": "Open Food Facts",
                                "is_duplicate_for_user": is_duplicate,
                                "existing_product_name": existing_name,
                                "product": {
                                    "name": name,
                                    "brand": brand,
                                    "category": category,
                                    "barcode": clean_code,
                                    "storage_instructions": storage,
                                    "notes": f"Imported via barcode {clean_code}"
                                },
                                "message": "Product identified from Open Food Facts database."
                            }
        except Exception:
            pass

        # 3. Not found fallback
        return {
            "success": True,
            "barcode": clean_code,
            "found": False,
            "is_duplicate_for_user": is_duplicate,
            "existing_product_name": existing_name,
            "product": None,
            "message": f"Barcode {clean_code} was not found in the product database. Please enter product details manually."
        }

    # ================================================================
    # CUSTOMER PRODUCTS (PRIVATE LEDGER & CRUD)
    # ================================================================
    SUPPORTED_CATEGORIES = ["fruits", "vegetables", "dairy", "meat", "packaged food", "beverages", "other"]

    @classmethod
    def get_customer_products(cls, user_id: int) -> List[Dict[str, Any]]:
        """
        Fetches all active private products belonging to the authenticated customer.
        Strictly isolated by user_id.
        """
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT id, user_id, name, brand, category, barcode, purchase_date, expiry_date, 
               storage_instructions, notes, created_at, updated_at
        FROM customer_products
        WHERE user_id = ? AND status = 'ACTIVE'
        ORDER BY id DESC
        """, (user_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    @classmethod
    def get_customer_product_by_id(cls, user_id: int, product_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches a single customer product by ID with ownership verification.
        """
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT id, user_id, name, brand, category, barcode, purchase_date, expiry_date, 
               storage_instructions, notes, created_at, updated_at
        FROM customer_products
        WHERE id = ? AND user_id = ? AND status = 'ACTIVE'
        """, (product_id, user_id))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    @classmethod
    def validate_customer_product_payload(
        cls, 
        user_id: int, 
        payload: Dict[str, Any], 
        current_id: Optional[int] = None
    ) -> tuple[bool, Dict[str, str], Dict[str, Any]]:
        """
        Validates customer product data:
        - Product name (required, non-blank)
        - Category (required, one of supported options)
        - Barcode (optional, format check + customer duplicate check)
        - Dates (optional, format check + expiry_date >= purchase_date)
        """
        errors = {}
        cleaned = {}

        # 1. Product Name
        name = str(payload.get("name", "")).strip()
        if not name:
            errors["name"] = "Product name is required and cannot be blank."
        cleaned["name"] = name

        # 2. Brand
        cleaned["brand"] = str(payload.get("brand", "")).strip() or None

        # 3. Category
        category = str(payload.get("category", "")).strip().lower()
        if not category:
            errors["category"] = "Category is required."
        elif category not in cls.SUPPORTED_CATEGORIES:
            errors["category"] = f"Category must be one of: {', '.join(cls.SUPPORTED_CATEGORIES)}."
        cleaned["category"] = category

        # 4. Barcode (optional, format & duplicate check)
        raw_barcode = str(payload.get("barcode", "")).strip()
        if raw_barcode:
            clean_code = re.sub(r'[^a-zA-Z0-9]', '', raw_barcode)
            if len(clean_code) < 4 or len(clean_code) > 20:
                errors["barcode"] = "Barcode must contain between 4 and 20 alphanumeric characters."
            else:
                # Check for duplicate barcode in this customer's active product list
                conn = get_connection()
                cur = conn.cursor()
                query = "SELECT id, name FROM customer_products WHERE user_id = ? AND barcode = ? AND status = 'ACTIVE'"
                params = [user_id, clean_code]
                if current_id is not None:
                    query += " AND id != ?"
                    params.append(current_id)
                cur.execute(query, params)
                existing = cur.fetchone()
                conn.close()

                if existing:
                    errors["barcode"] = f"A product with this barcode already exists in your list ('{existing['name']}')."
            cleaned["barcode"] = clean_code
        else:
            cleaned["barcode"] = None

        # 5. Purchase Date
        purchase_date = str(payload.get("purchase_date", "")).strip()
        cleaned["purchase_date"] = None
        if purchase_date:
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', purchase_date):
                errors["purchase_date"] = "Purchase date must be formatted as YYYY-MM-DD."
            else:
                cleaned["purchase_date"] = purchase_date

        # 6. Expiry Date
        expiry_date = str(payload.get("expiry_date", "")).strip()
        cleaned["expiry_date"] = None
        if expiry_date:
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', expiry_date):
                errors["expiry_date"] = "Expiry date must be formatted as YYYY-MM-DD."
            else:
                cleaned["expiry_date"] = expiry_date

        # 7. Date cross-validation (expiry date cannot be earlier than purchase date)
        if cleaned.get("purchase_date") and cleaned.get("expiry_date"):
            if cleaned["expiry_date"] < cleaned["purchase_date"]:
                errors["expiry_date"] = "Expiry date cannot be earlier than purchase date."

        # 8. Storage instructions & notes
        cleaned["storage_instructions"] = str(payload.get("storage_instructions", "")).strip() or None
        cleaned["notes"] = str(payload.get("notes", "")).strip() or None

        is_valid = len(errors) == 0
        return is_valid, errors, cleaned

    @classmethod
    def add_customer_product(cls, user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adds a new customer product to their private product list with full validation.
        Also registers an inventory item for the user's store so AI agents can track and optimize it.
        """
        is_valid, errors, cleaned = cls.validate_customer_product_payload(user_id, payload)
        if not is_valid:
            first_err = next(iter(errors.values())) if errors else "Validation failed."
            return {
                "success": False,
                "error": first_err,
                "errors": errors,
                "data": payload
            }

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO customer_products (
            user_id, name, brand, category, barcode, purchase_date, expiry_date, 
            storage_instructions, notes, created_at, updated_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
        """, (
            user_id, cleaned["name"], cleaned["brand"], cleaned["category"], 
            cleaned["barcode"], cleaned["purchase_date"], cleaned["expiry_date"],
            cleaned["storage_instructions"], cleaned["notes"], now_str, now_str
        ))
        product_id = cur.lastrowid

        # Also synchronize into store inventory so FreshGuard AI agents can analyze it
        cur.execute("SELECT id FROM stores WHERE user_id = ? LIMIT 1", (user_id,))
        store_row = cur.fetchone()
        if store_row:
            store_id = store_row["id"]
            sku = cleaned["barcode"] or f"SKU-CUST-{product_id:04d}"
            
            # Map category to standard department
            dept_map = {
                "fruits": "Fruits",
                "vegetables": "Vegetables",
                "dairy": "Dairy",
                "meat": "Perishables",
                "packaged food": "Bakery",
                "beverages": "Dairy",
                "other": "Perishables"
            }
            dept = dept_map.get(cleaned["category"], "Perishables")
            exp_date_str = cleaned["expiry_date"] + " 18:00" if cleaned["expiry_date"] else (datetime.datetime.now() + datetime.timedelta(days=4)).strftime("%Y-%m-%d 18:00")

            # Check or create product in products table
            cur.execute("SELECT sku FROM products WHERE sku = ?", (sku,))
            if not cur.fetchone():
                cur.execute("""
                INSERT INTO products (sku, name, department, unit, cost_price, selling_price, shelf_life_days, storage_zone, co2_footprint_kg, description)
                VALUES (?, ?, ?, 'pack', 25.0, 35.0, 5, 'Cool Produce', 0.5, ?)
                """, (sku, cleaned["name"], dept, f"Customer product: {cleaned['name']} ({cleaned['category']})"))

            batch_number = f"BAT-CUST-{product_id:04d}"
            cur.execute("""
            INSERT INTO inventory (
                store_id, sku, batch_number, stock_on_hand, safety_stock, 
                received_date, expiry_date, avg_daily_sales, forecast_daily_demand, 
                current_discount_pct, status, user_id, supplier, incoming_stock, delivery_date, promotion_info
            ) VALUES (?, ?, ?, 15, 5, ?, ?, 5.0, 5.0, 0, 'ACTIVE', ?, ?, 0, NULL, NULL)
            """, (store_id, sku, batch_number, now_str[:16], exp_date_str, user_id, cleaned["brand"] or "Customer Entry"))

        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'INFO', 'CUSTOMER_PRODUCT_CREATED', ?, ?)
        """, (now_str, f"User {user_id} added product '{cleaned['name']}' (ID: {product_id})", json.dumps({"product_id": product_id, "name": cleaned["name"]})))

        conn.commit()
        conn.close()

        # Fetch newly created product record
        new_prod = cls.get_customer_product_by_id(user_id, product_id)

        return {
            "success": True,
            "product_id": product_id,
            "product": new_prod,
            "message": f"Product '{cleaned['name']}' added to your private list successfully."
        }

    @classmethod
    def update_customer_product(cls, user_id: int, product_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates an existing customer product with authorization and full validation.
        Excludes current product from duplicate barcode check.
        """
        existing = cls.get_customer_product_by_id(user_id, product_id)
        if not existing:
            return {"success": False, "error": "Product not found or you do not have permission to edit it."}

        is_valid, errors, cleaned = cls.validate_customer_product_payload(user_id, payload, current_id=product_id)
        if not is_valid:
            first_err = next(iter(errors.values())) if errors else "Validation failed."
            return {
                "success": False,
                "error": first_err,
                "errors": errors,
                "data": payload
            }

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        UPDATE customer_products 
        SET name = ?, brand = ?, category = ?, barcode = ?, purchase_date = ?, expiry_date = ?, 
            storage_instructions = ?, notes = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """, (
            cleaned["name"], cleaned["brand"], cleaned["category"], 
            cleaned["barcode"], cleaned["purchase_date"], cleaned["expiry_date"],
            cleaned["storage_instructions"], cleaned["notes"], now_str, product_id, user_id
        ))

        # Update product name in synced products table if applicable
        old_barcode = existing.get("barcode") or f"SKU-CUST-{product_id:04d}"
        cur.execute("UPDATE products SET name = ? WHERE sku = ?", (cleaned["name"], old_barcode))

        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'INFO', 'CUSTOMER_PRODUCT_UPDATED', ?, ?)
        """, (now_str, f"User {user_id} updated product '{cleaned['name']}' (ID: {product_id})", json.dumps({"product_id": product_id, "name": cleaned["name"]})))

        conn.commit()
        conn.close()

        updated_prod = cls.get_customer_product_by_id(user_id, product_id)

        return {
            "success": True,
            "product": updated_prod,
            "message": f"Product '{cleaned['name']}' updated successfully."
        }

    @classmethod
    def delete_customer_product(cls, user_id: int, product_id: int) -> Dict[str, Any]:
        """
        Soft-deletes a customer product with ownership validation.
        """
        existing = cls.get_customer_product_by_id(user_id, product_id)
        if not existing:
            return {"success": False, "error": "Product not found or you do not have permission to delete it."}

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        UPDATE customer_products 
        SET status = 'DELETED', updated_at = ?
        WHERE id = ? AND user_id = ?
        """, (now_str, product_id, user_id))

        # Soft delete in inventory
        old_barcode = existing.get("barcode") or f"SKU-CUST-{product_id:04d}"
        cur.execute("UPDATE inventory SET status = 'DELETED' WHERE user_id = ? AND sku = ?", (user_id, old_barcode))

        cur.execute("""
        INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
        VALUES (?, 'INFO', 'CUSTOMER_PRODUCT_DELETED', ?, ?)
        """, (now_str, f"User {user_id} deleted product '{existing['name']}' (ID: {product_id})", json.dumps({"product_id": product_id, "name": existing["name"]})))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "product_id": product_id,
            "message": f"Product '{existing['name']}' was deleted successfully."
        }


