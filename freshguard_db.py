"""
FreshGuard - Database Schema & Realistic Indian Grocery Seed Data
GDGoC HITAM Agentic AI Hackathon - Problem Statement 2: Zero-Waste Grocery
"""

import sqlite3
import datetime
import os
import json

DB_FILE = os.path.join(os.path.dirname(__file__), "freshguard.db")

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

import hashlib
import secrets

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Securely hash a password using PBKDF2-HMAC-SHA256 with salt."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return hashed, salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verify a password against stored salt and hash."""
    new_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(new_hash, password_hash)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # 1. Users Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT DEFAULT 'CUSTOMER', -- 'CUSTOMER', 'DEMO_HITAM', 'DEMO_MIYAPUR', 'ADMIN'
        created_at TEXT NOT NULL,
        is_onboarded INTEGER DEFAULT 0
    );
    """)

    # 2. Sessions Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    # 3. Stores Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stores (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        location_type TEXT NOT NULL,
        address TEXT NOT NULL,
        daily_footfall INTEGER NOT NULL,
        cooler_capacity_sqft INTEGER NOT NULL,
        user_id INTEGER,
        city TEXT DEFAULT 'Hyderabad',
        store_type TEXT DEFAULT 'Supermarket',
        branch_count INTEGER DEFAULT 1,
        categories TEXT DEFAULT 'Vegetables & Fruits, Dairy & Eggs',
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    # 4. Products Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        sku TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        department TEXT NOT NULL,
        unit TEXT NOT NULL,
        cost_price REAL NOT NULL,
        selling_price REAL NOT NULL,
        shelf_life_days INTEGER NOT NULL,
        storage_zone TEXT NOT NULL,
        co2_footprint_kg REAL NOT NULL,
        description TEXT NOT NULL
    );
    """)

    # 5. Inventory Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store_id TEXT NOT NULL,
        sku TEXT NOT NULL,
        batch_number TEXT NOT NULL,
        stock_on_hand INTEGER NOT NULL,
        safety_stock INTEGER NOT NULL,
        received_date TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        avg_daily_sales REAL NOT NULL,
        forecast_daily_demand REAL NOT NULL,
        current_discount_pct INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ACTIVE',
        user_id INTEGER,
        supplier TEXT DEFAULT 'Local Mandi / Dairy Federation',
        incoming_stock INTEGER DEFAULT 0,
        delivery_date TEXT,
        promotion_info TEXT,
        FOREIGN KEY (store_id) REFERENCES stores(id),
        FOREIGN KEY (sku) REFERENCES products(sku),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    # 6. Rescue Actions Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rescue_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inventory_id INTEGER NOT NULL,
        store_id TEXT NOT NULL,
        sku TEXT NOT NULL,
        action_type TEXT NOT NULL, -- 'DISCOUNT', 'TRANSFER', 'DONATE', 'PAUSE_PO'
        action_details TEXT NOT NULL,
        discount_pct INTEGER DEFAULT 0,
        transfer_to_store TEXT,
        units_affected INTEGER NOT NULL,
        projected_waste_avoided_kg REAL NOT NULL,
        projected_revenue_saved REAL NOT NULL,
        status TEXT DEFAULT 'PENDING', -- 'PENDING', 'EXECUTED', 'CANCELLED'
        created_at TEXT NOT NULL,
        executed_at TEXT,
        rationale TEXT NOT NULL,
        user_id INTEGER,
        FOREIGN KEY (inventory_id) REFERENCES inventory(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    # 7. System Logs Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        level TEXT NOT NULL,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        metadata_json TEXT
    );
    """)

    # 8. Customer Products Table (Customer-Owned Private Products)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customer_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        brand TEXT,
        category TEXT NOT NULL, -- 'fruits', 'vegetables', 'dairy', 'meat', 'packaged food', 'beverages', 'other'
        barcode TEXT,
        purchase_date TEXT, -- YYYY-MM-DD
        expiry_date TEXT,   -- YYYY-MM-DD
        storage_instructions TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        status TEXT DEFAULT 'ACTIVE', -- 'ACTIVE', 'DELETED'
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_customer_products_user ON customer_products(user_id, status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_customer_products_barcode ON customer_products(user_id, barcode, status);")

    # 9. App & OAuth Settings Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Migration: add any missing columns to existing tables
    def ensure_column(table, column, col_def):
        cur.execute(f"PRAGMA table_info({table});")
        cols = [c[1] for c in cur.fetchall()]
        if column not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def};")

    ensure_column("stores", "user_id", "INTEGER")
    ensure_column("stores", "city", "TEXT DEFAULT 'Hyderabad'")
    ensure_column("stores", "store_type", "TEXT DEFAULT 'Supermarket'")
    ensure_column("stores", "branch_count", "INTEGER DEFAULT 1")
    ensure_column("stores", "categories", "TEXT DEFAULT 'Vegetables & Fruits, Dairy & Eggs'")

    ensure_column("inventory", "user_id", "INTEGER")
    ensure_column("inventory", "supplier", "TEXT DEFAULT 'Local Mandi / Dairy Federation'")
    ensure_column("inventory", "incoming_stock", "INTEGER DEFAULT 0")
    ensure_column("inventory", "delivery_date", "TEXT")
    ensure_column("inventory", "promotion_info", "TEXT")

    ensure_column("rescue_actions", "user_id", "INTEGER")

    conn.commit()
    conn.close()

def seed_data(force=False):
    conn = get_connection()
    cur = conn.cursor()

    # Check if data already exists
    cur.execute("SELECT COUNT(*) FROM stores")
    if cur.fetchone()[0] > 0 and not force:
        conn.close()
        return

    # Clear existing tables
    cur.execute("DELETE FROM sessions")
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM rescue_actions")
    cur.execute("DELETE FROM inventory")
    cur.execute("DELETE FROM products")
    cur.execute("DELETE FROM stores")
    cur.execute("DELETE FROM system_logs")
    cur.execute("DELETE FROM customer_products")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Seed Demo Accounts for Hackathon Judges
    h1, s1 = hash_password("freshguard2026!")
    h2, s2 = hash_password("freshguard2026!")

    cur.execute("""
    INSERT INTO users (id, username, email, password_hash, salt, role, created_at, is_onboarded)
    VALUES (1, 'demo_hitam', 'manager.hitam@freshguard.ai', ?, ?, 'DEMO_HITAM', ?, 1)
    """, (h1, s1, now_str))

    cur.execute("""
    INSERT INTO users (id, username, email, password_hash, salt, role, created_at, is_onboarded)
    VALUES (2, 'demo_miyapur', 'manager.miyapur@freshguard.ai', ?, ?, 'DEMO_MIYAPUR', ?, 1)
    """, (h2, s2, now_str))

    # 1. Localized Indian Stores linked to demo user accounts
    stores = [
        ("STORE-101", "HITAM Campus Store", "Campus Institutional Mart", "HITAM Engineering College, Medchal Highway, Hyderabad", 3200, 1400, 1, "Hyderabad", "Supermarket", 1, "Vegetables & Fruits, Dairy & Eggs, Bakery & Sweets"),
        ("STORE-102", "Miyapur Neighbourhood Store", "Suburban Family Depot", "Main Road, Allwyn X Roads, Miyapur, Hyderabad", 2450, 2600, 2, "Hyderabad", "Supermarket", 1, "Vegetables & Fruits, Dairy & Eggs, Bakery & Sweets"),
    ]
    cur.executemany("INSERT INTO stores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", stores)

    # 2. Perishable SKUs (28 realistic Indian grocery products across 4 core departments in INR)
    products = [
        # Dairy (7 items)
        ("SKU-DAI-01", "Fresh Milk Pouch (500 ml)", "Dairy", "500 ml Pouch", 24.00, 30.00, 3, "Chilled (2-4°C)", 0.9, "Pasteurized standardized fresh milk pouch for daily household chai and cooking."),
        ("SKU-DAI-02", "Fresh Dahi / Curd (400 g)", "Dairy", "400 g Tub", 30.00, 40.00, 5, "Chilled (2-4°C)", 0.8, "Thick set creamy dahi made from pasteurized toned milk."),
        ("SKU-DAI-03", "Fresh Malai Paneer (200 g)", "Dairy", "200 g Pack", 68.00, 90.00, 8, "Chilled (2-4°C)", 1.5, "Soft tender cottage cheese cubes vacuum-sealed for curries and tikkas."),
        ("SKU-DAI-04", "Pasteurized Salted Butter (100 g)", "Dairy", "100 g Pack", 46.00, 60.00, 45, "Chilled (2-4°C)", 1.8, "Rich cream table butter with balanced salt for breakfast toast and pav."),
        ("SKU-DAI-05", "Pure Cow Ghee (200 ml)", "Dairy", "200 ml Jar", 145.00, 190.00, 90, "Ambient (Cool)", 2.2, "Traditional granular aromatic clarified butter made from pure cow milk."),
        ("SKU-DAI-06", "Fresh Cow Milk (1 L)", "Dairy", "1 L Pouch", 48.00, 60.00, 3, "Chilled (2-4°C)", 1.6, "Pure wholesome fresh cow milk pouch rich in natural nutrients."),
        ("SKU-DAI-07", "Spiced Buttermilk / Chaas (200 ml)", "Dairy", "200 ml Pouch", 10.00, 15.00, 4, "Chilled (2-4°C)", 0.3, "Refreshing spiced buttermilk infused with ginger, green chillies, and curry leaves."),

        # Bakery (7 items)
        ("SKU-BAK-01", "Classic White Bread Loaf", "Bakery", "400 g Loaf", 28.00, 40.00, 4, "Ambient (Dry)", 0.5, "Soft freshly sliced white sandwich bread baked daily."),
        ("SKU-BAK-02", "Fresh Ladi Pav (6 Pieces)", "Bakery", "6 Pieces Pack", 20.00, 30.00, 3, "Ambient (Dry)", 0.4, "Soft pillowy bakery pav perfect for pav bhaji, maska, and vada pav."),
        ("SKU-BAK-03", "Burger & Sandwich Buns", "Bakery", "4 Pieces Pack", 24.00, 35.00, 4, "Ambient (Dry)", 0.4, "Golden toasted sesame-topped soft burger buns."),
        ("SKU-BAK-04", "100% Whole Wheat Atta Bread", "Bakery", "400 g Loaf", 34.00, 50.00, 4, "Ambient (Dry)", 0.4, "Nutritious high-fiber whole grain atta sliced bread."),
        ("SKU-BAK-05", "Crispy Elaichi Rusk Toast", "Bakery", "200 g Pack", 28.00, 40.00, 30, "Ambient (Dry)", 0.3, "Twice-baked cardamom-infused crunchy tea toasts."),
        ("SKU-BAK-06", "Sweet Fruit Milk Bread", "Bakery", "350 g Loaf", 26.00, 38.00, 4, "Ambient (Dry)", 0.4, "Tutti-frutti studded sweetened tea bread popular with students."),
        ("SKU-BAK-07", "Irani Bun Maska Duo", "Bakery", "2 Pieces Pack", 22.00, 35.00, 2, "Ambient (Dry)", 0.5, "Traditional Hyderabad cafe-style sweet buns pre-portioned for chai time."),

        # Fruits (7 items)
        ("SKU-FRU-01", "Fresh Bananas (Robusta)", "Fruits", "1 Dozen (12 Pcs)", 45.00, 60.00, 4, "Ambient (18-20°C)", 0.4, "Naturally sweet yellow bananas harvested at optimal daily ripeness."),
        ("SKU-FRU-02", "Kashmir Royal Apples", "Fruits", "1 kg Pack", 135.00, 180.00, 10, "Cool Produce (6-10°C)", 0.7, "Crisp juicy sweet Himalayan orchard apples."),
        ("SKU-FRU-03", "Hybrid Red Tomatoes", "Fruits", "1 kg Pack", 28.00, 40.00, 5, "Ambient (16-18°C)", 0.5, "Firm ripe red tomatoes essential for daily rasam, sambar, and curries."),
        ("SKU-FRU-04", "Fresh-Cut Fruit Bowl", "Fruits", "200 g Bowl", 30.00, 45.00, 2, "Chilled (2-4°C)", 0.3, "Hygienically sliced papaya, pineapple, and watermelon chunks ready to eat."),
        ("SKU-FRU-05", "Sweet Honey Papaya", "Fruits", "1 Piece (~1 kg)", 35.00, 50.00, 4, "Ambient (18-20°C)", 0.4, "Sweet golden-orange ripe papaya with rich dietary fiber."),
        ("SKU-FRU-06", "Ruby Red Pomegranate", "Fruits", "500 g Pack", 75.00, 105.00, 8, "Cool Produce (8-12°C)", 0.6, "Juicy antioxidant-rich pomegranate with sweet ruby arils."),
        ("SKU-FRU-07", "Seedless Green Grapes", "Fruits", "500 g Punnet", 52.00, 75.00, 6, "Chilled (2-4°C)", 0.5, "Crisp elongated sweet green table grapes from regional vineyards."),

        # Vegetables & Perishables (7 items)
        ("SKU-VEG-01", "Fresh Green Spinach (Palak)", "Vegetables", "1 Bunch (~250g)", 16.00, 25.00, 3, "Chilled (2-4°C)", 0.3, "Crisp farm-fresh green palak leaves tied in bundles for dal and palak paneer."),
        ("SKU-VEG-02", "Spicy Guntur Green Chillies", "Vegetables", "100 g Pouch", 9.00, 15.00, 5, "Cool Produce (8-10°C)", 0.2, "Pungent fresh green chillies essential for daily tadka and tempering."),
        ("SKU-VEG-03", "Fresh Coriander Leaves (Kothmir)", "Vegetables", "1 Bunch (~150g)", 8.00, 15.00, 3, "Chilled (2-4°C)", 0.2, "Aromatic fresh green coriander with roots intact for daily garnish."),
        ("SKU-VEG-04", "Fresh Tender Okra (Bhindi)", "Vegetables", "500 g Pack", 25.00, 38.00, 4, "Cool Produce (8-10°C)", 0.3, "Crisp tender lady fingers for quick dry fry and sambar."),
        ("SKU-VEG-05", "Fresh White Button Mushrooms", "Vegetables", "200 g Punnet", 36.00, 50.00, 4, "Chilled (2-4°C)", 0.4, "Hygienically packed button mushrooms for biryanis and stir-fries."),
        ("SKU-VEG-06", "Fresh Whole Grating Coconut", "Vegetables", "1 Piece", 24.00, 35.00, 7, "Ambient (Dry)", 0.4, "Mature fresh coconut with sweet kernel for chutneys and South Indian dishes."),
        ("SKU-VEG-07", "Fresh Aromatic Ginger (Adrak)", "Vegetables", "250 g Pack", 20.00, 30.00, 12, "Cool Produce (8-12°C)", 0.3, "Spicy washed ginger rhizomes for daily chai, paste, and curries.")
    ]
    cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", products)

    # 3. Inventory Batches for both stores
    now = datetime.datetime.now()

    def make_date(offset_days, offset_hours=0):
        d = now + datetime.timedelta(days=offset_days, hours=offset_hours)
        return d.strftime("%Y-%m-%d %H:%M")

    inventory_records = [
        # --- STORE 101: HITAM CAMPUS STORE (Campus Student & Staff Hub) ---
        # Dairy
        ("STORE-101", "SKU-DAI-01", "B-101-D01", 68, 20, make_date(-4), make_date(2, 6), 18.0, 19.0, 0, "ACTIVE"), # Surplus approaching expiry (68 units, 19/day velocity, 2.2 days left -> 25 surplus units for transfer to Miyapur!)
        ("STORE-101", "SKU-DAI-02", "B-101-D02", 36, 15, make_date(-8), make_date(2, 0), 12.0, 11.5, 0, "ACTIVE"), # Expiry Risk (36 units, 11.5/day, 2 days left -> 13 units at risk)
        ("STORE-101", "SKU-DAI-03", "B-101-D03", 22, 10, make_date(-12), make_date(8, 0), 4.5, 5.0, 0, "ACTIVE"), # Balanced
        ("STORE-101", "SKU-DAI-04", "B-101-D04", 45, 12, make_date(-10), make_date(18, 0), 3.0, 3.2, 0, "ACTIVE"), # Overstock (45 on hand vs 3.2/day sales)
        ("STORE-101", "SKU-DAI-05", "B-101-D05", 28, 15, make_date(-6), make_date(6, 0), 9.0, 10.0, 0, "ACTIVE"), # Healthy
        ("STORE-101", "SKU-DAI-06", "B-101-D06", 19, 8, make_date(-6), make_date(1, 10), 6.5, 7.0, 0, "ACTIVE"), # Expiry Risk (19 units, 1.4 days left)
        ("STORE-101", "SKU-DAI-07", "B-101-D07", 8, 12, make_date(-4), make_date(2, 0), 9.5, 10.0, 0, "ACTIVE"), # Stockout Risk

        # Bakery
        ("STORE-101", "SKU-BAK-01", "B-101-B01", 42, 15, make_date(-2), make_date(0, 14), 22.0, 20.0, 0, "ACTIVE"), # Critical Expiry Risk (Expires in 14h, 42 units)
        ("STORE-101", "SKU-BAK-02", "B-101-B02", 28, 12, make_date(-1), make_date(1, 2), 16.0, 18.0, 0, "ACTIVE"), # Moderate Expiry Risk (Pav)
        ("STORE-101", "SKU-BAK-03", "B-101-B03", 15, 10, make_date(-2), make_date(2, 0), 7.0, 7.5, 0, "ACTIVE"), # Healthy
        ("STORE-101", "SKU-BAK-04", "B-101-B04", 31, 8, make_date(-1), make_date(0, 18), 11.0, 10.0, 0, "ACTIVE"), # Critical Expiry Risk (Atta Bread)
        ("STORE-101", "SKU-BAK-05", "B-101-B05", 18, 10, make_date(-2), make_date(2, 0), 8.5, 9.0, 0, "ACTIVE"), # Healthy
        ("STORE-101", "SKU-BAK-06", "B-101-B06", 35, 12, make_date(-1), make_date(1, 4), 10.0, 11.0, 0, "ACTIVE"), # Expiry Risk (Sweet Fruit Bread)
        ("STORE-101", "SKU-BAK-07", "B-101-B07", 24, 10, make_date(-1), make_date(1, 16), 11.0, 12.0, 0, "ACTIVE"), # Moderate Expiry Risk (Bun Maska)

        # Fruits
        ("STORE-101", "SKU-FRU-01", "B-101-F01", 38, 15, make_date(-3), make_date(1, 6), 14.0, 15.0, 0, "ACTIVE"), # Expiry Risk (Bananas ripe)
        ("STORE-101", "SKU-FRU-02", "B-101-F02", 45, 12, make_date(-2), make_date(1, 0), 16.0, 17.0, 0, "ACTIVE"), # Critical Expiry Risk (Apples)
        ("STORE-101", "SKU-FRU-03", "B-101-F03", 70, 30, make_date(-3), make_date(2, 0), 30.0, 32.0, 0, "ACTIVE"), # Healthy
        ("STORE-101", "SKU-FRU-04", "B-101-F04", 55, 20, make_date(-4), make_date(1, 2), 18.0, 19.0, 0, "ACTIVE"), # Critical Expiry Risk (Fruit Bowl)
        ("STORE-101", "SKU-FRU-05", "B-101-F05", 29, 10, make_date(-3), make_date(1, 12), 11.0, 12.0, 0, "ACTIVE"), # Expiry Risk (Papaya)
        ("STORE-101", "SKU-FRU-06", "B-101-F06", 18, 10, make_date(-2), make_date(2, 0), 9.0, 9.5, 0, "ACTIVE"), # Healthy
        ("STORE-101", "SKU-FRU-07", "B-101-F07", 32, 12, make_date(-3), make_date(3, 0), 10.0, 10.5, 0, "ACTIVE"), # Healthy

        # Vegetables & Perishables
        ("STORE-101", "SKU-VEG-01", "B-101-V01", 40, 15, make_date(-2), make_date(1, 8), 15.0, 16.0, 0, "ACTIVE"), # Expiry Risk (Palak)
        ("STORE-101", "SKU-VEG-02", "B-101-V02", 26, 12, make_date(-2), make_date(2, 0), 12.0, 12.5, 0, "ACTIVE"), # Healthy
        ("STORE-101", "SKU-VEG-03", "B-101-V03", 48, 12, make_date(-2), make_date(0, 18), 14.0, 15.0, 0, "ACTIVE"), # Critical Expiry Risk (Coriander)
        ("STORE-101", "SKU-VEG-04", "B-101-V04", 35, 12, make_date(-4), make_date(3, 0), 7.0, 7.5, 0, "ACTIVE"), # Overstock (Bhindi)
        ("STORE-101", "SKU-VEG-05", "B-101-V05", 34, 10, make_date(-2), make_date(1, 14), 12.0, 13.0, 0, "ACTIVE"), # Expiry Risk (Mushrooms)
        ("STORE-101", "SKU-VEG-06", "B-101-V06", 30, 10, make_date(-2), make_date(3, 0), 8.0, 8.5, 0, "ACTIVE"), # Healthy (Coconut)
        ("STORE-101", "SKU-VEG-07", "B-101-V07", 19, 10, make_date(-2), make_date(3, 0), 8.0, 8.5, 0, "ACTIVE"), # Healthy (Ginger)

        # --- STORE 102: MIYAPUR NEIGHBOURHOOD STORE (Suburban Residential Family Hub) ---
        # Dairy
        ("STORE-102", "SKU-DAI-01", "B-102-D01", 14, 40, make_date(-5), make_date(1, 4), 38.0, 42.0, 0, "ACTIVE"), # IMPENDING STOCKOUT: High family demand (42/day), only 14 on hand! Needs transfer from HITAM!
        ("STORE-102", "SKU-DAI-02", "B-102-D02", 20, 12, make_date(-6), make_date(5, 0), 7.0, 7.5, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-DAI-03", "B-102-D03", 42, 10, make_date(-10), make_date(10, 0), 3.5, 3.5, 0, "ACTIVE"), # Overstock
        ("STORE-102", "SKU-DAI-04", "B-102-D04", 30, 10, make_date(-8), make_date(20, 0), 2.5, 2.8, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-DAI-05", "B-102-D05", 14, 10, make_date(-5), make_date(7, 0), 4.5, 5.0, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-DAI-06", "B-102-D06", 24, 8, make_date(-5), make_date(2, 4), 4.0, 4.2, 0, "ACTIVE"), # Expiry Risk (Cow Milk 1L)
        ("STORE-102", "SKU-DAI-07", "B-102-D07", 32, 12, make_date(-3), make_date(3, 0), 6.0, 6.5, 0, "ACTIVE"), # Healthy

        # Bakery
        ("STORE-102", "SKU-BAK-01", "B-102-B01", 16, 10, make_date(-1), make_date(2, 0), 9.0, 9.5, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-BAK-02", "B-102-B02", 34, 10, make_date(-1), make_date(1, 4), 9.0, 10.0, 0, "ACTIVE"), # Expiry Risk (Pav)
        ("STORE-102", "SKU-BAK-03", "B-102-B03", 28, 8, make_date(-1), make_date(3, 0), 5.0, 5.0, 0, "ACTIVE"), # Overstock
        ("STORE-102", "SKU-BAK-04", "B-102-B04", 12, 6, make_date(-1), make_date(1, 0), 6.0, 6.5, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-BAK-05", "B-102-B05", 22, 8, make_date(-1), make_date(3, 0), 5.5, 6.0, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-BAK-06", "B-102-B06", 45, 15, make_date(-1), make_date(0, 16), 18.0, 19.0, 0, "ACTIVE"), # Critical Expiry (Fruit Bread)
        ("STORE-102", "SKU-BAK-07", "B-102-B07", 15, 8, make_date(-1), make_date(2, 0), 7.0, 7.5, 0, "ACTIVE"), # Healthy

        # Fruits
        ("STORE-102", "SKU-FRU-01", "B-102-F01", 24, 12, make_date(-2), make_date(2, 0), 10.0, 10.5, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-FRU-02", "B-102-F02", 36, 10, make_date(-1), make_date(1, 8), 11.0, 12.0, 0, "ACTIVE"), # Expiry Risk (Apples)
        ("STORE-102", "SKU-FRU-03", "B-102-F03", 85, 25, make_date(-2), make_date(3, 0), 22.0, 24.0, 0, "ACTIVE"), # Healthy (Tomatoes)
        ("STORE-102", "SKU-FRU-04", "B-102-F04", 62, 18, make_date(-3), make_date(7, 0), 8.0, 8.5, 0, "ACTIVE"), # Overstock (Fruit Bowl)
        ("STORE-102", "SKU-FRU-05", "B-102-F05", 18, 8, make_date(-2), make_date(2, 12), 7.0, 7.5, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-FRU-06", "B-102-F06", 38, 10, make_date(-2), make_date(1, 18), 8.0, 9.0, 0, "ACTIVE"), # Expiry Risk (Pomegranate)
        ("STORE-102", "SKU-FRU-07", "B-102-F07", 25, 10, make_date(-2), make_date(4, 0), 7.0, 7.5, 0, "ACTIVE"), # Healthy

        # Vegetables & Perishables
        ("STORE-102", "SKU-VEG-01", "B-102-V01", 28, 12, make_date(-2), make_date(1, 12), 10.0, 10.5, 0, "ACTIVE"), # Expiry Risk (Spinach)
        ("STORE-102", "SKU-VEG-02", "B-102-V02", 30, 10, make_date(-2), make_date(2, 0), 9.0, 9.5, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-VEG-03", "B-102-V03", 35, 10, make_date(-2), make_date(4, 0), 6.5, 7.0, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-VEG-04", "B-102-V04", 40, 12, make_date(-3), make_date(4, 0), 5.5, 6.0, 0, "ACTIVE"), # Overstock
        ("STORE-102", "SKU-VEG-05", "B-102-V05", 22, 8, make_date(-2), make_date(2, 0), 8.0, 8.5, 0, "ACTIVE"), # Healthy
        ("STORE-102", "SKU-VEG-06", "B-102-V06", 26, 8, make_date(-1), make_date(1, 6), 7.5, 8.0, 0, "ACTIVE"), # Expiry Risk (Coconut)
        ("STORE-102", "SKU-VEG-07", "B-102-V07", 32, 10, make_date(-2), make_date(3, 0), 6.0, 6.5, 0, "ACTIVE"), # Healthy
    ]

    inventory_records_with_user = [
        (*r, 1 if r[0] == "STORE-101" else 2, "Local Mandi / Dairy Federation", 0, None, None)
        for r in inventory_records
    ]

    cur.executemany("""
    INSERT INTO inventory (
        store_id, sku, batch_number, stock_on_hand, safety_stock, 
        received_date, expiry_date, avg_daily_sales, forecast_daily_demand, 
        current_discount_pct, status, user_id, supplier, incoming_stock, delivery_date, promotion_info
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, inventory_records_with_user)

    # Initial log event
    cur.execute("""
    INSERT INTO system_logs (timestamp, level, event_type, message, metadata_json)
    VALUES (?, ?, ?, ?, ?)
    """, (
        now.strftime("%Y-%m-%d %H:%M:%S"),
        "INFO",
        "DATABASE_INITIALIZED",
        "FreshGuard Indian grocery inventory database initialized with 2 Hyderabad stores and 28 perishable SKUs.",
        json.dumps({"stores_count": 2, "products_count": 28, "batches_count": len(inventory_records)})
    ))

    # Seed sample customer products for Demo accounts
    sample_cust_prods = [
        (1, "Amul Taaza Toned Milk (500ml)", "Amul", "dairy", "8901262010053", "2026-10-09", "2026-10-12", "Keep refrigerated at 4°C", "Daily household chai milk pouch", now_str, now_str, "ACTIVE"),
        (1, "Britannia 100% Whole Wheat Bread", "Britannia", "packaged food", "8901063012487", "2026-10-09", "2026-10-13", "Store in a cool dry place", "Nutritious whole wheat toast", now_str, now_str, "ACTIVE"),
        (1, "Organic Palak Spinach Bunch", "Farm Fresh", "vegetables", "8901990001014", "2026-10-10", "2026-10-12", "Keep chilled in crisper drawer", "Fresh leafy green for cooking", now_str, now_str, "ACTIVE"),
        (2, "Mother Dairy Classic Dahi (400g)", "Mother Dairy", "dairy", "8901725181222", "2026-10-08", "2026-10-13", "Refrigerate between 2-4°C", "Set creamy curd tub", now_str, now_str, "ACTIVE"),
        (2, "Kissan Fresh Tomato Ketchup (500g)", "Kissan", "packaged food", "8901030383454", "2026-10-05", "2026-11-20", "Store in a cool dry place. Refrigerate after opening", "Pantry staple condiment", now_str, now_str, "ACTIVE"),
    ]
    cur.executemany("""
    INSERT INTO customer_products (
        user_id, name, brand, category, barcode, purchase_date, expiry_date, storage_instructions, notes, created_at, updated_at, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, sample_cust_prods)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    seed_data(force=True)
    print(f"FreshGuard database successfully created & seeded at: {DB_FILE}")
