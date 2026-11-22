"""Pruebas de aceptación automatizadas para la API local de Pizza-Flow."""

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from itertools import count
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
import api  # noqa: E402


class PizzaFlowApiTests(unittest.TestCase):
    phone_sequence = count(1)

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="pizzaflow-tests-")
        cls.database_path = Path(cls.temp_dir.name) / "test.sqlite3"
        cls.previous_database_path = api.DB_PATH
        api.DB_PATH = cls.database_path

        with sqlite3.connect(cls.database_path) as db:
            db.executescript((BACKEND_DIR / "schema.sql").read_text(encoding="utf-8-sig"))
            db.execute("INSERT INTO pizzerias (id, name) VALUES (1, 'Pizzería de prueba')")
            db.execute(
                "INSERT INTO products (id, pizzeria_id, name, price_cop, tax_rate_pct) "
                "VALUES (1, 1, 'Pizza de prueba', 32000, 0)"
            )
            db.execute(
                "INSERT INTO delivery_zones (id, pizzeria_id, name, fee_cop) "
                "VALUES (1, 1, 'Zona de prueba', 4000)"
            )

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), api.APIHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)
        api.DB_PATH = cls.previous_database_path
        cls.temp_dir.cleanup()

    def request_json(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def create_order(self, customer_id=None, items=None, customer_accepted=True):
        payload = {
            "pizzeria_id": 1,
            "delivery_zone_id": 1,
            "delivery_address": "Calle de prueba 123",
            "capture_channel": "PHONE",
            "payment_method": "CASH_ON_DELIVERY",
            "customer_accepted": customer_accepted,
            "created_by": "Recepcionista de prueba",
            "items": items if items is not None else [{"product_id": 1, "quantity": 2}],
        }
        if customer_id is None:
            payload["new_customer"] = {
                "name": "Cliente de prueba",
                "phone": f"300{next(self.phone_sequence):07d}",
            }
            self.last_new_customer_phone = payload["new_customer"]["phone"]
        else:
            payload["customer_id"] = customer_id
        return self.request_json("POST", "/orders", payload)

    def test_health_reports_api_available(self):
        status, result = self.request_json("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "ok")

    def test_order_calculates_amount_and_tracks_local_confirmation(self):
        status, order = self.create_order()

        self.assertEqual(status, 201)
        self.assertEqual(order["order_status"], "RECIBIDO")
        self.assertEqual(order["payment_status"], "PENDING")
        self.assertIsNotNone(order["customer_id"])
        self.assertEqual(order["subtotal_cop"], 64000)
        self.assertEqual(order["tax_total_cop"], 0)
        self.assertEqual(order["delivery_fee_cop"], 4000)
        self.assertEqual(order["total_cop"], 68000)

        order_id = order["id"]
        status, result = self.request_json(
            "POST", f"/orders/{order_id}/send-command", {
                "channel": "WHATSAPP_MANUAL",
                "changed_by": "Recepcionista de prueba",
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["order_status"], "ENVIADO_AL_LOCAL")
        self.assertEqual(result["command_status"], "ENVIADA")

        status, result = self.request_json(
            "POST", f"/orders/{order_id}/confirm-command", {
                "confirmed_by": "Encargado de prueba",
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["order_status"], "CONFIRMADO_LOCAL")
        self.assertTrue(result["mvp_complete"])

        status, saved = self.request_json("GET", f"/orders/{order_id}")
        self.assertEqual(status, 200)
        self.assertEqual(saved["command"]["command_status"], "CONFIRMADA")
        self.assertEqual(len(saved["items"]), 1)
        self.assertEqual(len(saved["status_history"]), 3)
        status, saved_customer = self.request_json(
            "GET", f"/clients?pizzeria_id=1&phone={self.last_new_customer_phone}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(saved_customer["id"], order["customer_id"])

    def test_missing_local_response_requires_manual_follow_up(self):
        status, order = self.create_order()
        self.assertEqual(status, 201)

        status, _ = self.request_json(
            "POST", f"/orders/{order['id']}/send-command", {
                "channel": "PHONE",
                "changed_by": "Recepcionista de prueba",
            }
        )
        self.assertEqual(status, 200)
        status, result = self.request_json(
            "POST", f"/orders/{order['id']}/no-response", {"notes": "Pendiente"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["command_status"], "SIN_CONFIRMAR")
        self.assertEqual(result["next_action"], "Seguimiento manual")
        self.assertEqual(result["order_status"], "ENVIADO_AL_LOCAL")

    def test_order_without_items_is_rejected(self):
        status, created = self.create_order()
        self.assertEqual(status, 201)
        status, result = self.create_order(customer_id=created["customer_id"], items=[])
        self.assertEqual(status, 400)
        self.assertIn("Agrega al menos un producto", result["error"])

    def test_new_customer_is_not_saved_without_acceptance(self):
        phone = "3009999999"
        status, result = self.request_json("POST", "/orders", {
            "pizzeria_id": 1,
            "new_customer": {"name": "Cliente sin aceptar", "phone": phone},
            "delivery_zone_id": 1,
            "delivery_address": "Calle de prueba 123",
            "capture_channel": "PHONE",
            "payment_method": "CASH_ON_DELIVERY",
            "items": [{"product_id": 1, "quantity": 1}],
        })
        self.assertEqual(status, 400)
        self.assertIn("aceptación del cliente", result["error"])
        status, result = self.request_json("GET", f"/clients?pizzeria_id=1&phone={phone}")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
