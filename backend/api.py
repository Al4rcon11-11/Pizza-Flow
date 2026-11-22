"""Local Pizza-Flow application with staff sessions and administrator permissions."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlparse
from security import StaffMixin, AccessError, public_user

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "pizzaflow.sqlite3"


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def as_dict(row):
    return dict(row) if row is not None else None


def money_tax(subtotal_cop, rate_pct):
    amount = Decimal(subtotal_cop) * Decimal(str(rate_pct)) / Decimal("100")
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class APIHandler(StaffMixin, BaseHTTPRequestHandler):
    connect = staticmethod(connect)

    def allowed_origins(self):
        return {f'http://{host}:{port}' for host in ('127.0.0.1', 'localhost')
                for port in (self.server.server_port, 5500)}

    def check_origin(self):
        hosts = {f'{host}:{self.server.server_port}' for host in ('127.0.0.1', 'localhost')}
        if self.headers.get('Host') not in hosts:
            raise AccessError(403, 'Accede usando la dirección local de Pizza-Flow.')
        origin = self.headers.get('Origin')
        if origin and origin not in self.allowed_origins():
            raise AccessError(403, 'Origen no permitido. Abre http://127.0.0.1:8000.')

    def cors_headers(self):
        origin = self.headers.get('Origin')
        if origin in self.allowed_origins():
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-PizzaFlow, X-CSRF-Token')

    def send_json(self, status, data, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.cors_headers()
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        try:
            self.check_origin()
        except AccessError as exc:
            return self.send_json(exc.status, {'error': str(exc)})
        self.send_response(204)
        self.cors_headers()
        self.end_headers()

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("El cuerpo JSON está vacío o supera 1 MB.")
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('El cuerpo JSON debe ser un objeto.')
            return body
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("El cuerpo no contiene JSON válido.") from exc

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            self.check_origin()
            if parsed.path in ('/', '/Pizza-Flow_App.html'):
                content = (ROOT.parent / 'Pizza-Flow_App.html').read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('X-Frame-Options', 'DENY')
                self.end_headers()
                return self.wfile.write(content)
            if parsed.path == "/health":
                return self.send_json(200, {"status": "ok", "prototype": "Pizza-Flow backend"})
            if parsed.path == '/auth/status':
                with connect() as db:
                    configured = db.execute("SELECT 1 FROM staff_users WHERE role='ADMIN'").fetchone() is not None
                return self.send_json(200, {'configured': configured})
            self.authenticate()
            if parsed.path == '/auth/me':
                return self.send_json(200, {'user': public_user(self.user), 'csrf_token': self.user['csrf_token']})
            if parsed.path in ('/admin/products', '/admin/zones', '/admin/users'):
                return self.admin_list(parsed.path.rsplit('/', 1)[1])
            if parsed.path == "/products":
                pizzeria_id = self.own_pizzeria(self.require_query_int(query, "pizzeria_id"))
                with connect() as db:
                    rows = db.execute(
                        "SELECT id, name, price_cop, tax_rate_pct FROM products "
                        "WHERE pizzeria_id = ? AND active = 1 ORDER BY name", (pizzeria_id,)
                    ).fetchall()
                return self.send_json(200, [as_dict(row) for row in rows])
            if parsed.path == "/zones":
                pizzeria_id = self.own_pizzeria(self.require_query_int(query, "pizzeria_id"))
                with connect() as db:
                    rows = db.execute(
                        "SELECT id, name, fee_cop FROM delivery_zones "
                        "WHERE pizzeria_id = ? AND active = 1 ORDER BY name", (pizzeria_id,)
                    ).fetchall()
                return self.send_json(200, [as_dict(row) for row in rows])
            if parsed.path == "/clients":
                pizzeria_id = self.own_pizzeria(self.require_query_int(query, "pizzeria_id"))
                phone = (query.get("phone") or [""])[0].strip()
                if not phone:
                    raise ValueError("Indica el teléfono del cliente.")
                with connect() as db:
                    row = db.execute(
                        "SELECT id, pizzeria_id, name, phone "
                        "FROM customers WHERE pizzeria_id = ? AND phone = ?", (pizzeria_id, phone)
                    ).fetchone()
                if row is None:
                    return self.send_json(404, {"error": "Cliente no encontrado."})
                return self.send_json(200, as_dict(row))
            if parsed.path.startswith("/orders/"):
                order_id = self.path_id(parsed.path, "/orders/")
                self.own_order(order_id)
                with connect() as db:
                    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
                    if order is None:
                        return self.send_json(404, {"error": "Pedido no encontrado."})
                    items = db.execute(
                        "SELECT product_id, product_name_snapshot, quantity, unit_price_cop, "
                        "tax_rate_pct_snapshot, line_subtotal_cop, line_tax_cop "
                        "FROM order_items WHERE order_id = ? ORDER BY id", (order_id,)
                    ).fetchall()
                    command = db.execute(
                        "SELECT * FROM dispatch_commands WHERE order_id = ?", (order_id,)
                    ).fetchone()
                    history = db.execute(
                        "SELECT previous_status, new_status, changed_by, changed_at, note "
                        "FROM order_status_history WHERE order_id = ? ORDER BY id", (order_id,)
                    ).fetchall()
                result = as_dict(order)
                result["items"] = [as_dict(row) for row in items]
                result["command"] = as_dict(command)
                result["status_history"] = [as_dict(row) for row in history]
                return self.send_json(200, result)
            return self.send_json(404, {"error": "Ruta no encontrada."})
        except AccessError as exc:
            return self.send_json(exc.status, {'error': str(exc)})
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        except sqlite3.Error:
            return self.send_json(503, {"error": 'No se pudo consultar la base de datos. Reintenta en un momento.'})

    def do_POST(self):
        try:
            self.check_origin()
            if self.headers.get('X-PizzaFlow') != '1' or self.headers.get_content_type() != 'application/json':
                raise AccessError(403, 'Solicitud no permitida. Usa la aplicación Pizza-Flow.')
            body = self.read_json()
            path = urlparse(self.path).path
            if path == '/auth/login':
                return self.login(body)
            self.authenticate(admin=path.startswith('/admin/'), mutation=True)
            if path == '/auth/logout':
                return self.logout()
            if path == '/auth/password':
                return self.change_password(body)
            if path in ('/admin/products', '/admin/zones'):
                return self.save_catalog(path.rsplit('/', 1)[1], body)
            if path == '/admin/users':
                return self.save_receptionist(body)
            if path == '/admin/users/update':
                return self.update_receptionist(body)
            body['created_by'] = self.user['name']
            body['changed_by'] = self.user['name']
            body['confirmed_by'] = self.user['name']
            if path.startswith('/orders/'):
                self.own_order(self.path_id(path, '/orders/', '/' + path.rsplit('/', 1)[1]))
            if path == "/orders":
                return self.create_order(body)
            if path.startswith("/orders/") and path.endswith("/send-command"):
                order_id = self.path_id(path, "/orders/", "/send-command")
                return self.send_command(order_id, body)
            if path.startswith("/orders/") and path.endswith("/confirm-command"):
                order_id = self.path_id(path, "/orders/", "/confirm-command")
                return self.confirm_command(order_id, body)
            if path.startswith("/orders/") and path.endswith("/no-response"):
                order_id = self.path_id(path, "/orders/", "/no-response")
                return self.mark_no_response(order_id, body)
            return self.send_json(404, {"error": "Ruta no encontrada."})
        except AccessError as exc:
            return self.send_json(exc.status, {'error': str(exc)})
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        except sqlite3.IntegrityError:
            return self.send_json(409, {"error": 'Ya existe un registro con ese nombre, teléfono o usuario, o los datos entran en conflicto.'})
        except sqlite3.Error:
            return self.send_json(503, {"error": 'No se pudo guardar el cambio. Reintenta en un momento.'})

    def create_order(self, body):
        pizzeria_id = self.own_pizzeria(self.require_int(body, "pizzeria_id"))
        if body.get("customer_accepted") is not True:
            raise ValueError("Registra la aceptación del cliente antes de guardar el pedido.")
        new_customer = body.get("new_customer")
        customer_id = body.get("customer_id")
        if (customer_id is None) == (new_customer is None):
            raise ValueError("Indica un cliente existente o los datos de un cliente nuevo.")
        if new_customer is not None and not isinstance(new_customer, dict):
            raise ValueError("new_customer debe incluir nombre y teléfono.")
        if new_customer is not None:
            new_customer_name = self.require_text(new_customer, "name")
            new_customer_phone = self.require_text(new_customer, "phone")
        else:
            customer_id = self.require_int(body, "customer_id")
        zone_id = self.require_int(body, "delivery_zone_id")
        address = self.require_text(body, "delivery_address")
        channel = body.get("capture_channel")
        if channel not in ("PHONE", "WHATSAPP", "SELF_SERVICE"):
            raise ValueError("capture_channel debe ser PHONE, WHATSAPP o SELF_SERVICE.")
        payment_method = body.get("payment_method")
        if payment_method not in ("CASH_ON_DELIVERY", "DIGITAL"):
            raise ValueError("payment_method debe ser CASH_ON_DELIVERY o DIGITAL.")
        entries = body.get("items")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Agrega al menos un producto al pedido.")
        with connect() as db:
            if new_customer is not None:
                customer_cursor = db.execute(
                    "INSERT INTO customers (pizzeria_id, name, phone) VALUES (?, ?, ?)",
                    (pizzeria_id, new_customer_name, new_customer_phone),
                )
                customer_id = customer_cursor.lastrowid
            else:
                customer = db.execute(
                    "SELECT id FROM customers WHERE id = ? AND pizzeria_id = ?",
                    (customer_id, pizzeria_id),
                ).fetchone()
                if customer is None:
                    raise ValueError("El cliente no existe en esta pizzería.")
            zone = db.execute(
                "SELECT id, fee_cop FROM delivery_zones WHERE id = ? AND pizzeria_id = ? AND active = 1",
                (zone_id, pizzeria_id),
            ).fetchone()
            if zone is None:
                raise ValueError("La zona no existe, está inactiva o no pertenece a esta pizzería.")
            lines = []
            subtotal = 0
            tax_total = 0
            for entry in entries:
                product_id = self.require_int(entry, "product_id")
                quantity = self.require_int(entry, "quantity")
                if quantity < 1:
                    raise ValueError("La cantidad debe ser mayor que cero.")
                product = db.execute(
                    "SELECT id, name, price_cop, tax_rate_pct FROM products "
                    "WHERE id = ? AND pizzeria_id = ? AND active = 1",
                    (product_id, pizzeria_id),
                ).fetchone()
                if product is None:
                    raise ValueError(f"El producto {product_id} no existe o no está activo.")
                line_subtotal = product["price_cop"] * quantity
                line_tax = money_tax(line_subtotal, product["tax_rate_pct"])
                subtotal += line_subtotal
                tax_total += line_tax
                lines.append((product, quantity, line_subtotal, line_tax))
            delivery_fee = zone["fee_cop"]
            total = subtotal + tax_total + delivery_fee
            if 'expected_total_cop' in body and self.require_int(body, 'expected_total_cop') != total:
                raise AccessError(409, 'El catálogo o la tarifa cambiaron. Actualiza el catálogo y solicita nuevamente la aceptación del total.')
            cursor = db.execute(
                "INSERT INTO orders (pizzeria_id, customer_id, delivery_zone_id, delivery_address, "
                "capture_channel, payment_method, order_status, subtotal_cop, tax_total_cop, "
                "delivery_fee_cop, total_cop, notes, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, 'RECIBIDO', ?, ?, ?, ?, ?, ?)",
                (pizzeria_id, customer_id, zone_id, address, channel, payment_method,
                 subtotal, tax_total, delivery_fee, total, body.get("notes"), body.get("created_by")),
            )
            order_id = cursor.lastrowid
            for product, quantity, line_subtotal, line_tax in lines:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, product_name_snapshot, quantity, "
                    "unit_price_cop, tax_rate_pct_snapshot, line_subtotal_cop, line_tax_cop) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (order_id, product["id"], product["name"], quantity, product["price_cop"],
                     product["tax_rate_pct"], line_subtotal, line_tax),
                )
            db.execute(
                "INSERT INTO dispatch_commands (order_id, command_status) VALUES (?, 'PENDIENTE')",
                (order_id,),
            )
            db.execute(
                "INSERT INTO order_status_history (order_id, previous_status, new_status, changed_by, note) "
                "VALUES (?, NULL, 'RECIBIDO', ?, 'Pedido confirmado por el cliente')",
                (order_id, body.get("created_by")),
            )
        return self.send_json(201, {
            "id": order_id, "customer_id": customer_id,
            "order_status": "RECIBIDO", "payment_method": payment_method,
            "payment_status": "PENDING", "subtotal_cop": subtotal, "tax_total_cop": tax_total,
            "delivery_fee_cop": delivery_fee, "total_cop": total,
            "discounts": "Fuera del MVP; no se aplicaron descuentos.",
        })

    def send_command(self, order_id, body):
        channel = body.get("channel")
        if channel not in ("WHATSAPP_MANUAL", "PHONE", "IN_PERSON"):
            raise ValueError("channel debe ser WHATSAPP_MANUAL, PHONE o IN_PERSON.")
        sent_at = now_utc()
        with connect() as db:
            order = db.execute("SELECT order_status FROM orders WHERE id = ?", (order_id,)).fetchone()
            command = db.execute("SELECT command_status FROM dispatch_commands WHERE order_id = ?", (order_id,)).fetchone()
            if order is None or command is None:
                return self.send_json(404, {"error": "Pedido o comanda no encontrados."})
            if command["command_status"] != "PENDIENTE":
                return self.send_json(409, {"error": "La comanda ya fue enviada o resuelta."})
            db.execute(
                "UPDATE dispatch_commands SET channel = ?, command_status = 'ENVIADA', sent_at = ? WHERE order_id = ?",
                (channel, sent_at, order_id),
            )
            db.execute(
                "UPDATE orders SET order_status = 'ENVIADO_AL_LOCAL' WHERE id = ?", (order_id,)
            )
            db.execute(
                "INSERT INTO order_status_history (order_id, previous_status, new_status, changed_by, note) "
                "VALUES (?, ?, 'ENVIADO_AL_LOCAL', ?, 'Comanda enviada al local')",
                (order_id, order["order_status"], body.get("changed_by")),
            )
        return self.send_json(200, {"order_id": order_id, "order_status": "ENVIADO_AL_LOCAL", "command_status": "ENVIADA", "sent_at": sent_at})

    def confirm_command(self, order_id, body):
        confirmer = self.require_text(body, "confirmed_by")
        confirmed_at = now_utc()
        with connect() as db:
            command = db.execute("SELECT command_status FROM dispatch_commands WHERE order_id = ?", (order_id,)).fetchone()
            order = db.execute("SELECT order_status FROM orders WHERE id = ?", (order_id,)).fetchone()
            if command is None or order is None:
                return self.send_json(404, {"error": "Pedido o comanda no encontrados."})
            if command["command_status"] != "ENVIADA":
                return self.send_json(409, {"error": "Solo se confirma una comanda que ya fue enviada."})
            db.execute(
                "UPDATE dispatch_commands SET command_status = 'CONFIRMADA', confirmed_at = ?, confirmed_by = ? WHERE order_id = ?",
                (confirmed_at, confirmer, order_id),
            )
            db.execute("UPDATE orders SET order_status = 'CONFIRMADO_LOCAL' WHERE id = ?", (order_id,))
            db.execute(
                "INSERT INTO order_status_history (order_id, previous_status, new_status, changed_by, note) "
                "VALUES (?, ?, 'CONFIRMADO_LOCAL', ?, 'El local confirmó recepción; cierre del MVP')",
                (order_id, order["order_status"], confirmer),
            )
        return self.send_json(200, {"order_id": order_id, "order_status": "CONFIRMADO_LOCAL", "command_status": "CONFIRMADA", "confirmed_by": confirmer, "confirmed_at": confirmed_at, "mvp_complete": True})

    def mark_no_response(self, order_id, body):
        with connect() as db:
            command = db.execute("SELECT command_status FROM dispatch_commands WHERE order_id = ?", (order_id,)).fetchone()
            order = db.execute("SELECT order_status FROM orders WHERE id = ?", (order_id,)).fetchone()
            if command is None or order is None:
                return self.send_json(404, {"error": "Pedido o comanda no encontrados."})
            if command["command_status"] != "ENVIADA":
                return self.send_json(409, {"error": "La comanda debe estar enviada antes de marcar falta de respuesta."})
            db.execute(
                "UPDATE dispatch_commands SET command_status = 'SIN_CONFIRMAR', notes = ? WHERE order_id = ?",
                (body.get("notes", "Requiere seguimiento manual"), order_id),
            )
        return self.send_json(200, {"order_id": order_id, "order_status": order["order_status"], "command_status": "SIN_CONFIRMAR", "next_action": "Seguimiento manual"})

    @staticmethod
    def require_int(payload, key):
        try:
            value = payload[key]
            if type(value) is not int and not (isinstance(value, str) and value.isascii() and value.isdigit()):
                raise ValueError()
            return int(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{key} debe ser un número entero.") from exc

    @staticmethod
    def require_query_int(query, key):
        try:
            return int(query[key][0])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"Indica {key} como número entero.") from exc

    @staticmethod
    def require_text(payload, key):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} es obligatorio.")
        return value.strip()

    @staticmethod
    def path_id(path, prefix, suffix=""):
        raw = path[len(prefix):-len(suffix)] if suffix else path[len(prefix):]
        if "/" in raw or not raw.isdigit():
            raise ValueError("Identificador de pedido inválido.")
        return int(raw)

    def log_message(self, format_string, *args):
        print("[API] " + format_string % args)


def main():
    with connect() as db:
        db.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8-sig'))
    server = ThreadingHTTPServer(("127.0.0.1", 8000), APIHandler)
    print("Pizza-Flow disponible en http://127.0.0.1:8000 (página y API)")
    print("Presiona Ctrl+C para detener el servidor.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
