"""
FreshGuard AI - Verification Suite for Google Login, Barcode Scanner & Customer Products CRUD
"""

import sys
import unittest
import os
import json

from freshguard_db import init_db, seed_data, get_connection
from engine import FreshGuardEngine

class TestCustomerProductsAndGoogleAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_data(force=True)
        cls.user_a_res = FreshGuardEngine.register_user("shopkeeper_anu", "anu@grocery.in", "pass_anu_123")
        cls.user_a_id = cls.user_a_res["user"]["id"]

        cls.user_b_res = FreshGuardEngine.register_user("storeowner_vijay", "vijay@freshbazaar.in", "pass_vijay_123")
        cls.user_b_id = cls.user_b_res["user"]["id"]

    def test_01_google_oauth_config_and_test_login(self):
        # 1. Config check
        config = FreshGuardEngine.get_google_oauth_config()
        self.assertIn("configured", config)
        self.assertIn("instructions", config)

        # 2. Rejection of empty credentials
        empty_res = FreshGuardEngine.authenticate_google_user({})
        self.assertFalse(empty_res["success"])
        self.assertTrue(empty_res.get("needs_config") or "Missing" in empty_res["error"])

        # 3. Save config
        save_res = FreshGuardEngine.save_google_oauth_config("test-client-id-123.apps.googleusercontent.com", "test-secret-456")
        self.assertTrue(save_res["success"])
        new_config = FreshGuardEngine.get_google_oauth_config()
        self.assertTrue(new_config["configured"])
        self.assertEqual(new_config["client_id"], "test-client-id-123.apps.googleusercontent.com")

        # 4. Google test mode login
        g_res = FreshGuardEngine.authenticate_google_user({
            "test_mode": True,
            "email": "customer.google.test@gmail.com",
            "name": "Priya Sharma"
        })
        self.assertTrue(g_res["success"])
        self.assertIn("token", g_res)
        self.assertEqual(g_res["user"]["email"], "customer.google.test@gmail.com")
        self.assertTrue(g_res["user"]["is_onboarded"])

    def test_02_barcode_lookup_catalog_and_validation(self):
        # 1. Valid local catalog barcode (Amul Taaza Milk EAN-13)
        res_milk = FreshGuardEngine.lookup_barcode("8901262010053", user_id=self.user_a_id)
        self.assertTrue(res_milk["success"])
        self.assertTrue(res_milk["found"])
        self.assertEqual(res_milk["product"]["brand"], "Amul")
        self.assertEqual(res_milk["product"]["category"], "dairy")
        self.assertFalse(res_milk["is_duplicate_for_user"])

        # 2. Valid local catalog barcode (Britannia Bread)
        res_bread = FreshGuardEngine.lookup_barcode("8901063012487", user_id=self.user_a_id)
        self.assertTrue(res_bread["success"])
        self.assertTrue(res_bread["found"])
        self.assertEqual(res_bread["product"]["brand"], "Britannia")
        self.assertEqual(res_bread["product"]["category"], "packaged food")

        # 3. Invalid barcode format
        res_invalid = FreshGuardEngine.lookup_barcode("12", user_id=self.user_a_id)
        self.assertFalse(res_invalid["success"])
        self.assertIn("Invalid barcode format", res_invalid["error"])

        # 4. Unknown barcode graceful response
        res_unknown = FreshGuardEngine.lookup_barcode("0000111122223", user_id=self.user_a_id)
        self.assertTrue(res_unknown["success"])
        self.assertFalse(res_unknown["found"])
        self.assertIn("not found", res_unknown["message"].lower())

    def test_03_customer_product_validation_rules(self):
        # 1. Blank product name rejected
        res = FreshGuardEngine.add_customer_product(self.user_a_id, {
            "name": "   ",
            "category": "fruits"
        })
        self.assertFalse(res["success"])
        self.assertIn("name", res["errors"])

        # 2. Invalid category rejected
        res = FreshGuardEngine.add_customer_product(self.user_a_id, {
            "name": "Alphonso Mango",
            "category": "electronics" # Invalid
        })
        self.assertFalse(res["success"])
        self.assertIn("category", res["errors"])

        # 3. Expiry date earlier than purchase date rejected
        res = FreshGuardEngine.add_customer_product(self.user_a_id, {
            "name": "Fresh Curd Pouch",
            "category": "dairy",
            "purchase_date": "2026-10-15",
            "expiry_date": "2026-10-10" # Invalid: before purchase!
        })
        self.assertFalse(res["success"])
        self.assertIn("expiry_date", res["errors"])

    def test_04_customer_product_crud_and_duplicate_barcode(self):
        # 1. Add valid product for Customer A
        add_res = FreshGuardEngine.add_customer_product(self.user_a_id, {
            "name": "Ratnagiri Alphonso Mangoes",
            "brand": "Konkan Farms",
            "category": "fruits",
            "barcode": "8908887770011",
            "purchase_date": "2026-10-10",
            "expiry_date": "2026-10-16",
            "storage_instructions": "Keep at room temperature until ripe, then chill",
            "notes": "Sweet seasonal mangoes"
        })
        self.assertTrue(add_res["success"])
        prod_a = add_res["product"]
        prod_a_id = prod_a["id"]
        self.assertEqual(prod_a["name"], "Ratnagiri Alphonso Mangoes")
        self.assertEqual(prod_a["brand"], "Konkan Farms")
        self.assertEqual(prod_a["category"], "fruits")
        self.assertEqual(prod_a["barcode"], "8908887770011")

        # 2. Duplicate barcode for Customer A must be REJECTED
        dup_res = FreshGuardEngine.add_customer_product(self.user_a_id, {
            "name": "Second Box Mangoes",
            "category": "fruits",
            "barcode": "8908887770011" # Same barcode for same customer!
        })
        self.assertFalse(dup_res["success"])
        self.assertIn("barcode", dup_res["errors"])
        self.assertIn("already exists", dup_res["errors"]["barcode"].lower())

        # 3. Barcode lookup shows duplicate warning for Customer A
        check_dup = FreshGuardEngine.lookup_barcode("8908887770011", user_id=self.user_a_id)
        self.assertTrue(check_dup["is_duplicate_for_user"])

        # 4. Same barcode for Customer B is ALLOWED (Isolated private product lists!)
        b_res = FreshGuardEngine.add_customer_product(self.user_b_id, {
            "name": "Vijay's Mangoes",
            "category": "fruits",
            "barcode": "8908887770011"
        })
        self.assertTrue(b_res["success"])

        # 5. Customer A views their product list
        prods_a = FreshGuardEngine.get_customer_products(self.user_a_id)
        self.assertTrue(any(p["id"] == prod_a_id for p in prods_a))

        # 6. Customer A updates their product (retaining existing barcode must succeed)
        edit_res = FreshGuardEngine.update_customer_product(self.user_a_id, prod_a_id, {
            "name": "Ratnagiri Alphonso Mangoes (Grade A)",
            "brand": "Konkan Farms Premium",
            "category": "fruits",
            "barcode": "8908887770011", # Same barcode for same item
            "purchase_date": "2026-10-10",
            "expiry_date": "2026-10-18",
            "storage_instructions": "Chill below 10°C",
            "notes": "Updated grade"
        })
        self.assertTrue(edit_res["success"])
        self.assertEqual(edit_res["product"]["name"], "Ratnagiri Alphonso Mangoes (Grade A)")
        self.assertEqual(edit_res["product"]["expiry_date"], "2026-10-18")

        # 7. Customer B cannot edit or delete Customer A's product (Security isolation!)
        hack_edit = FreshGuardEngine.update_customer_product(self.user_b_id, prod_a_id, {
            "name": "Hacked Mangoes",
            "category": "fruits"
        })
        self.assertFalse(hack_edit["success"])
        self.assertIn("permission", hack_edit["error"].lower())

        hack_del = FreshGuardEngine.delete_customer_product(self.user_b_id, prod_a_id)
        self.assertFalse(hack_del["success"])
        self.assertIn("permission", hack_del["error"].lower())

        # 8. Customer A deletes their product
        del_res = FreshGuardEngine.delete_customer_product(self.user_a_id, prod_a_id)
        self.assertTrue(del_res["success"])

        # 9. Verify product is no longer active in Customer A's list
        prods_a_after = FreshGuardEngine.get_customer_products(self.user_a_id)
        self.assertFalse(any(p["id"] == prod_a_id for p in prods_a_after))

if __name__ == "__main__":
    unittest.main()
