"""
FreshGuard - Streamlit Multi-Agent Dashboard Edition with Customer Access
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery
"""

import streamlit as st
import datetime
import pandas as pd
from engine import FreshGuardEngine
from freshguard_db import init_db, seed_data, get_connection

# Page Configuration
st.set_page_config(
    page_title="FreshGuard AI — Zero-Waste Grocery Intelligence",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Design Styles matching FreshGuard Visual Identity
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,500;0,600;1,400&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
  
  html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: #143023;
  }
  
  .stApp {
    background-color: #F8F6F0;
  }
  
  h1, h2, h3 {
    font-family: 'Newsreader', Georgia, serif;
    color: #143023;
    font-weight: 600;
  }
  
  .metric-box {
    background: #FFFFFF;
    border: 1px solid #E2DCD1;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
  }
  
  .badge-critical {
    background: #FBECE8;
    color: #BD4728;
    padding: 3px 8px;
    border-radius: 9999px;
    font-weight: 600;
    font-size: 11px;
    border: 1px solid #F3C9BF;
  }
  
  .badge-healthy {
    background: #EDF6F1;
    color: #3E795B;
    padding: 3px 8px;
    border-radius: 9999px;
    font-weight: 600;
    font-size: 11px;
    border: 1px solid #C8E4D5;
  }
</style>
""", unsafe_allow_html=True)

# Initialize DB
init_db()
seed_data(force=False)

# Session State for User Authentication
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None

# Streamlit Supported Google Auth Check
has_google_auth = False
try:
    if hasattr(st, "login") and callable(st.login):
        has_google_auth = True
except Exception:
    has_google_auth = False

# Sidebar: Authentication & Customer Mode
st.sidebar.markdown("### 🌿 **FreshGuard AI**")
st.sidebar.caption("Zero-Waste Grocery Demand & Shelf-Life System")
st.sidebar.markdown("---")

# Authentication Handling
if not st.session_state.auth_user:
    st.sidebar.subheader("Account Access")
    auth_mode = st.sidebar.radio("Sign In Method", ["Demo Account (1-Click)", "Store Log In", "New Store Registration"])

    if auth_mode == "Demo Account (1-Click)":
        demo_choice = st.sidebar.selectbox("Select Hackathon Demo Store", ["HITAM Campus Store (demo_hitam)", "Miyapur Store (demo_miyapur)"])
        if st.sidebar.button("Log In as Demo Store", type="primary"):
            key = "demo_hitam" if "hitam" in demo_choice.lower() else "demo_miyapur"
            res = FreshGuardEngine.demo_login(key)
            if res.get("success"):
                st.session_state.auth_user = res["user"]
                st.session_state.auth_token = res["token"]
                st.rerun()

    elif auth_mode == "Store Log In":
        uname = st.sidebar.text_input("Username or Email")
        pword = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Log In"):
            res = FreshGuardEngine.login_user(uname, pword)
            if res.get("success"):
                st.session_state.auth_user = res["user"]
                st.session_state.auth_token = res["token"]
                st.rerun()
            else:
                st.sidebar.error(res.get("error", "Invalid credentials"))

    elif auth_mode == "New Store Registration":
        new_uname = st.sidebar.text_input("Store Manager Username")
        new_email = st.sidebar.text_input("Business Email")
        new_pword = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Register Store"):
            res = FreshGuardEngine.register_user(new_uname, new_email, new_pword)
            if res.get("success"):
                st.session_state.auth_user = res["user"]
                st.session_state.auth_token = res["token"]
                st.rerun()
            else:
                st.sidebar.error(res.get("error", "Registration failed"))

    st.info("👋 Welcome to FreshGuard AI. Please sign in or choose a 1-click demo account in the sidebar to begin.")
    st.stop()

# If authenticated
user = st.session_state.auth_user
user_id = user["id"]
st.sidebar.success(f"Signed in: **{user['username']}**")
if st.sidebar.button("Sign Out"):
    st.session_state.auth_user = None
    st.session_state.auth_token = None
    st.rerun()

st.sidebar.markdown("---")

# Store Onboarding Wizard Check
if not user.get("is_onboarded"):
    st.header("🏪 Welcome to FreshGuard! Store Setup Wizard")
    st.write("Complete this quick setup to configure your grocery store with the AI decision engine.")
    with st.form("onboard_form"):
        s_name = st.text_input("Store / Business Name", value="My Fresh Store")
        s_city = st.text_input("Store Location / City", value="Hyderabad")
        s_type = st.selectbox("Store Type", ["Supermarket", "Kirana Store", "Hypermarket", "Organic Specialty"])
        s_branches = st.number_input("Number of Branches", min_value=1, max_value=50, value=1)
        s_cats = st.multiselect("Main Categories", ["Vegetables & Fruits", "Dairy & Eggs", "Bakery & Sweets", "Staples & Pantry"], default=["Vegetables & Fruits", "Dairy & Eggs"])
        submit_onboard = st.form_submit_button("Complete Setup & Open FreshGuard")
        if submit_onboard:
            onboard_res = FreshGuardEngine.complete_onboarding(user_id, s_name, s_city, s_type, s_branches, ", ".join(s_cats))
            if onboard_res.get("success"):
                user["is_onboarded"] = True
                st.success("Store setup complete!")
                st.rerun()
    st.stop()

# Active store options for user
stores = FreshGuardEngine.get_user_stores(user_id)
store_options = ["ALL"] + [s["id"] for s in stores]
store_names = {"ALL": "All My Stores"}
for s in stores:
    store_names[s["id"]] = s["name"]

selected_store = st.sidebar.selectbox(
    "Active Store",
    options=store_options,
    format_func=lambda x: store_names.get(x, x)
)

nav_tab = st.sidebar.radio(
    "Navigation",
    ["Overview", "Stock Data Entry", "AI Action Plan", "Results & Audit Log"]
)

if st.sidebar.button("↺ Reset Demo Data"):
    seed_data(force=True)
    st.sidebar.success("Database reset to fresh demo state!")
    st.rerun()

# 1. OVERVIEW
if nav_tab == "Overview":
    st.title("Executive Waste & Demand Overview")
    st.caption(f"Real-time perishable health for {user['username']} ({store_names.get(selected_store, 'All Stores')})")

    overview = FreshGuardEngine.get_overview_metrics(store_id=selected_store, user_id=user_id)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Critical Expiry Items", f"{overview['critical_count']}", delta="Expires Soon", delta_color="inverse")
    with c2:
        st.metric("Moderate Expiry Items", f"{overview['moderate_count']}")
    with c3:
        st.metric("Units Exposed to Spoilage", f"{overview['total_units_at_risk']} units")
    with c4:
        st.metric("Value at Risk", f"₹{overview['total_retail_value_at_risk']:,.2f}")

    st.markdown("---")
    st.subheader("Urgent Products Needing Attention Today")
    urgent_items = overview.get("urgent_items", [])
    if urgent_items:
        for item in urgent_items:
            with st.container():
                st.markdown(f"""
                <div class="metric-box">
                  <div style="display: flex; justify-content: space-between;">
                    <strong>{item['product_name']} ({item['sku']})</strong>
                    <span class="badge-critical">{item['hours_to_expiry']}h remaining</span>
                  </div>
                  <div style="font-size: 13px; color: #555; margin-top: 4px;">
                    Store: {item['store_name']} | On-Hand: {item['stock_on_hand']} {item['unit']} | Daily Sales: {item['avg_daily_sales']}/day
                  </div>
                  <div style="font-size: 13px; color: #BD4728; margin-top: 4px; font-weight: 600;">
                    At-Risk Loss: ₹{item['projected_waste_retail_loss']:,.2f} ({item['projected_waste_units']} units)
                  </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("All fresh products in your inventory are safe and healthy today.")

# 2. STOCK DATA ENTRY
elif nav_tab == "Stock Data Entry":
    st.title("Stock Data Management")
    st.caption("Manage grocery batches manually or via CSV file upload with validation")

    tab_view, tab_add, tab_upload = st.tabs(["Current Stock", "Add Product Manually", "Upload CSV File"])

    with tab_view:
        items = FreshGuardEngine.get_inventory_analytics(store_id=selected_store, user_id=user_id)
        if items:
            df = pd.DataFrame(items)[[
                "sku", "product_name", "store_name", "department", 
                "stock_on_hand", "avg_daily_sales", "selling_price", 
                "cost_price", "expiry_date", "risk_label", "supplier"
            ]]
            df.columns = [
                "SKU", "Product", "Store", "Category", 
                "Stock", "Daily Sales", "Price (₹)", 
                "Cost (₹)", "Expiry Date", "Risk Status", "Supplier"
            ]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No products found. Add products using the tabs above.")

    with tab_add:
        st.subheader("Add Product Directly to Inventory")
        with st.form("manual_add_form"):
            c_name = st.text_input("Product Name", placeholder="e.g. Desi Hybrid Tomatoes (1kg)")
            c_sku = st.text_input("SKU (Optional)", placeholder="e.g. SKU-VEG-055")
            c_dept = st.selectbox("Category", ["Vegetables & Fruits", "Dairy & Eggs", "Bakery & Sweets", "Staples & Pantry"])
            c_stock = st.number_input("Current Stock Available", min_value=0, value=30)
            c_sales = st.number_input("Expected Daily Sales (Units)", min_value=0.0, value=8.0, step=0.5)
            c_price = st.number_input("Unit Selling Price (₹)", min_value=1.0, value=40.0, step=1.0)
            c_cost = st.number_input("Unit Cost Price (₹)", min_value=0.0, value=28.0, step=1.0)
            c_exp = st.date_input("Expiry Date", value=datetime.date.today() + datetime.timedelta(days=3))
            c_supp = st.text_input("Supplier / Mandi", value="Local APMC Mandi")
            c_incoming = st.number_input("Incoming Stock (Units)", min_value=0, value=0)
            c_promo = st.text_input("Promotion Info", placeholder="e.g. 5% Off on 2kg")

            submit_product = st.form_submit_button("Save Product to Stock")
            if submit_product:
                payload = {
                    "name": c_name,
                    "sku": c_sku,
                    "department": c_dept,
                    "stock_on_hand": int(c_stock),
                    "avg_daily_sales": float(c_sales),
                    "selling_price": float(c_price),
                    "cost_price": float(c_cost),
                    "expiry_date": str(c_exp) + " 18:00",
                    "supplier": c_supp,
                    "incoming_stock": int(c_incoming),
                    "promotion_info": c_promo
                }
                res = FreshGuardEngine.add_inventory_item(payload, user_id=user_id)
                if res.get("success"):
                    st.success(f"✓ Added {c_name} to inventory successfully!")
                    st.rerun()
                else:
                    st.error(res.get("error", "Failed to add product"))

    with tab_upload:
        st.subheader("Upload CSV Stock File")
        st.write("Upload a spreadsheet of your stock. FreshGuard checks every row for errors before importing.")

        uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
        if uploaded_file is not None:
            csv_str = uploaded_file.getvalue().decode("utf-8")
            preview = FreshGuardEngine.preview_csv_data(csv_str)

            st.write(f"**Preview Summary:** {preview['total_rows']} Total Rows | "
                     f":green[{preview['valid_rows']} Valid Rows] | "
                     f":red[{preview['invalid_rows']} Rows with Issues]")

            if preview.get("rows"):
                preview_records = []
                for r in preview["rows"]:
                    preview_records.append({
                        "Row": r["row_number"],
                        "Product": r["data"]["name"],
                        "Category": r["data"]["department"],
                        "Stock": r["data"]["stock_on_hand"],
                        "Daily Sales": r["data"]["avg_daily_sales"],
                        "Price (₹)": r["data"]["selling_price"],
                        "Expiry": r["data"]["expiry_date"],
                        "Status": "Valid" if r["is_valid"] else f"Error: {r['errors'][0]}"
                    })
                st.dataframe(pd.DataFrame(preview_records), use_container_width=True, hide_index=True)

                if preview["valid_rows"] > 0:
                    if st.button("Confirm & Save Valid Products"):
                        res = FreshGuardEngine.upload_csv_inventory(csv_str, user_id=user_id)
                        if res.get("success"):
                            st.success(f"✓ Successfully imported {res['added_count']} products!")
                            st.rerun()
                        else:
                            st.error(res.get("error", "Upload failed"))

# 3. AI ACTION PLAN
elif nav_tab == "AI Action Plan":
    st.title("Agentic AI Perishable Rescue Plan")
    st.caption("Coordinating Demand, Freshness, and Action Agents on your store data")

    scenario = FreshGuardEngine.run_rescue_scenario(user_id=user_id)
    recs = scenario.get("recommendations", [])

    if recs:
        st.write(f"Found **{len(recs)}** optimized suggestions to reduce waste and protect profits.")
        for r in recs:
            with st.container():
                st.markdown(f"""
                <div class="metric-box">
                  <h4>{r['product_name']} — {r['action_type']}</h4>
                  <p><strong>Action:</strong> {r['action_details']}</p>
                  <p><strong>Rationale:</strong> {r['manager_explanation']}</p>
                  <p><strong>Projected Benefit:</strong> Avoids {r['projected_waste_avoided_kg']:.1f} kg food waste | Saves ₹{r['net_economic_yield']:,.2f} net yield</p>
                </div>
                """, unsafe_allow_html=True)
                col_app, col_rej = st.columns([1, 1])
                with col_app:
                    if st.button(f"Approve Action #{r['action_id']}", key=f"app_{r['action_id']}"):
                        FreshGuardEngine.execute_action(r, user_id=user_id)
                        st.success("Action approved & inventory updated!")
                        st.rerun()
                with col_rej:
                    if st.button(f"Reject Action #{r['action_id']}", key=f"rej_{r['action_id']}"):
                        FreshGuardEngine.reject_action(r, "Manager override", user_id=user_id)
                        st.info("Action rejected and logged.")
                        st.rerun()
    else:
        st.info("All products are currently balanced. No urgent markdowns or transfers required.")

# 4. RESULTS & AUDIT LOG
elif nav_tab == "Results & Audit Log":
    st.title("Execution Audit Trail")
    st.caption("Immutable record of all approved and rejected recommendations for your account")

    audit = FreshGuardEngine.get_audit_log(user_id=user_id)
    if audit:
        df_audit = pd.DataFrame(audit)[[
            "executed_at", "store_name", "product_name", "action_type", 
            "action_details", "projected_revenue_saved", "projected_waste_avoided_kg", "status"
        ]]
        df_audit.columns = [
            "Timestamp", "Store", "Product", "Action Type", 
            "Details", "Revenue Saved (₹)", "Waste Diverted (kg)", "Status"
        ]
        st.dataframe(df_audit, use_container_width=True, hide_index=True)
    else:
        st.info("No actions recorded in audit log yet.")
