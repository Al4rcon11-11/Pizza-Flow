"""Local staff authentication and administrator operations (Python standard library)."""
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError

ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60
COOKIE_NAME = 'pizzaflow_session'
_attempts = {}
_attempt_lock = threading.Lock()


class AccessError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def username_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', value):
        raise ValueError('El usuario debe tener de 3 a 40 letras, números, puntos, guiones o guiones bajos.')
    return value.lower()


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('La contraseña debe tener entre 12 y 128 caracteres.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}'


def password_matches(password, encoded):
    if not isinstance(password, str) or len(password) > 128:
        return False
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


# Same cost for unknown accounts, avoiding a quick username-existence response.
_DUMMY_HASH = password_hash(secrets.token_urlsafe(24))


def public_user(user):
    return {key: user[key] for key in ('id', 'pizzeria_id', 'username', 'name', 'role')}


class StaffMixin:
    def session_cookie(self, token='', clear=False):
        # HTTP is limited to loopback. A hosted version must use HTTPS + Secure.
        return f'{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else SESSION_SECONDS}'

    def cookie_token(self):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookies[COOKIE_NAME].value if COOKIE_NAME in cookies else ''
            return token if len(token) <= 128 else ''
        except CookieError:
            return ''

    def session_digest(self):
        return hashlib.sha256(self.cookie_token().encode()).hexdigest()

    def authenticate(self, admin=False, mutation=False):
        with self.connect() as db:
            user = db.execute(
                'SELECT u.*, s.csrf_token FROM staff_sessions s JOIN staff_users u ON u.id=s.user_id '
                'WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',
                (self.session_digest(), int(time.time())),
            ).fetchone()
        if user is None:
            raise AccessError(401, 'Inicia sesión para continuar.')
        if admin and user['role'] != 'ADMIN':
            raise AccessError(403, 'Esta acción requiere una cuenta de administrador.')
        if mutation and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), user['csrf_token']):
            raise AccessError(403, 'La sesión debe actualizarse. Vuelve a iniciar sesión.')
        self.user = dict(user)
        return self.user

    def login(self, body):
        username = username_value(body.get('username'))
        password = body.get('password')
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise ValueError('Indica una contraseña válida.')
        now = time.time()
        keys = [('ip', self.client_address[0]), ('user', username)]
        with _attempt_lock:
            for key in list(_attempts):
                _attempts[key] = [t for t in _attempts[key] if t > now - 900]
                if not _attempts[key]:
                    del _attempts[key]
            for key, limit in zip(keys, (30, 5)):
                if len(_attempts.get(key, [])) >= limit:
                    raise AccessError(429, 'Demasiados intentos. Espera 15 minutos antes de volver a intentarlo.')
            for key in keys:
                _attempts.setdefault(key, []).append(now)
        with self.connect() as db:
            user = db.execute('SELECT * FROM staff_users WHERE username=?', (username,)).fetchone()
            matches = password_matches(password, user['password_hash'] if user else _DUMMY_HASH)
            if not matches or not user or not user['active']:
                raise AccessError(401, 'Usuario o contraseña incorrectos.')
            # Serialize session creation with password changes / account deactivation.
            db.execute('BEGIN IMMEDIATE')
            fresh = db.execute('SELECT password_hash,active FROM staff_users WHERE id=?', (user['id'],)).fetchone()
            if not fresh or not fresh['active'] or fresh['password_hash'] != user['password_hash']:
                raise AccessError(401, 'La cuenta cambió. Inicia sesión nuevamente.')
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.execute('DELETE FROM staff_sessions WHERE expires_at<=? OR token_hash=?',
                       (int(now), self.session_digest()))
            db.execute('INSERT INTO staff_sessions (token_hash,user_id,csrf_token,expires_at) VALUES (?,?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), user['id'], csrf, int(now)+SESSION_SECONDS))
        with _attempt_lock:
            _attempts.pop(('user', username), None)
        return self.send_json(200, {'user': public_user(user), 'csrf_token': csrf},
                              cookie=self.session_cookie(token))

    def logout(self):
        with self.connect() as db:
            db.execute('DELETE FROM staff_sessions WHERE token_hash=?', (self.session_digest(),))
        return self.send_json(200, {'ok': True}, cookie=self.session_cookie(clear=True))

    def own_pizzeria(self, value):
        if value != self.user['pizzeria_id']:
            raise AccessError(403, 'No tienes acceso a esta pizzería.')
        return value

    def own_order(self, order_id):
        with self.connect() as db:
            row = db.execute('SELECT id FROM orders WHERE id=? AND pizzeria_id=?',
                             (order_id, self.user['pizzeria_id'])).fetchone()
        if row is None:
            raise AccessError(404, 'Pedido no encontrado.')

    def admin_list(self, resource):
        self.authenticate(admin=True)
        table, fields = {
            'products': ('products', 'id,name,price_cop,tax_rate_pct,active'),
            'zones': ('delivery_zones', 'id,name,fee_cop,active'),
            'users': ('staff_users', 'id,username,name,role,active'),
        }[resource]
        with self.connect() as db:
            rows = db.execute(f'SELECT {fields} FROM {table} WHERE pizzeria_id=? ORDER BY name',
                              (self.user['pizzeria_id'],)).fetchall()
        return self.send_json(200, [dict(row) for row in rows])

    def audit(self, db, action, entity_id, detail):
        db.execute('INSERT INTO admin_audit (user_id,action,entity_id,detail) VALUES (?,?,?,?)',
                   (self.user['id'], action, entity_id, json.dumps(detail, ensure_ascii=False)))

    def save_catalog(self, resource, body):
        name = self.require_text(body, 'name')
        if len(name) > 120:
            raise ValueError('El nombre no debe superar 120 caracteres.')
        active = body.get('active', True)
        if type(active) is not bool:
            raise ValueError('Indica si el registro está activo.')
        item_id = self.require_int(body, 'id') if body.get('id') is not None else None
        if resource == 'products':
            price = self.require_int(body, 'price_cop')
            if not 1 <= price <= 100_000_000:
                raise ValueError('El precio debe estar entre 1 y 100.000.000 COP, sin decimales.')
            rate = body.get('tax_rate_pct', 0)
            if type(rate) not in (float, int) or not math.isfinite(rate) or not 0 <= rate <= 100:
                raise ValueError('El impuesto debe ser un porcentaje entre 0 y 100.')
            table, columns, values = 'products', ['name', 'price_cop', 'tax_rate_pct', 'active'], [name, price, rate, int(active)]
        else:
            fee = self.require_int(body, 'fee_cop')
            if not 0 <= fee <= 100_000_000:
                raise ValueError('La tarifa debe estar entre 0 y 100.000.000 COP, sin decimales.')
            table, columns, values = 'delivery_zones', ['name', 'fee_cop', 'active'], [name, fee, int(active)]
        with self.connect() as db:
            if item_id is None:
                cursor = db.execute(f'INSERT INTO {table} (pizzeria_id,{",".join(columns)}) VALUES ({",".join("?" for _ in range(len(values)+1))})',
                                    [self.user['pizzeria_id'], *values])
                item_id = cursor.lastrowid
                status = 201
            else:
                cursor = db.execute(f'UPDATE {table} SET {",".join(c+"=?" for c in columns)} WHERE id=? AND pizzeria_id=?',
                                    [*values, item_id, self.user['pizzeria_id']])
                if cursor.rowcount != 1:
                    raise AccessError(404, 'Registro no encontrado.')
                status = 200
            self.audit(db, f'save_{resource}', item_id, dict(zip(columns, values)))
        return self.send_json(status, {'id': item_id, 'message': 'Cambios guardados.'})

    def save_receptionist(self, body):
        name = self.require_text(body, 'name')
        if len(name) > 100:
            raise ValueError('El nombre no debe superar 100 caracteres.')
        username = username_value(body.get('username'))
        encoded = password_hash(body.get('password'))
        if body.get('role', 'RECEPTIONIST') != 'RECEPTIONIST':
            raise ValueError('Esta pantalla crea cuentas de recepcionista.')
        with self.connect() as db:
            cursor = db.execute('INSERT INTO staff_users (pizzeria_id,username,name,password_hash,role) VALUES (?,?,?,?,?)',
                                (self.user['pizzeria_id'], username, name, encoded, 'RECEPTIONIST'))
            self.audit(db, 'create_receptionist', cursor.lastrowid, {'username': username})
        return self.send_json(201, {'id': cursor.lastrowid, 'message': 'Cuenta creada.'})

    def update_receptionist(self, body):
        user_id = self.require_int(body, 'id')
        active = body.get('active')
        if type(active) is not bool:
            raise ValueError('Indica si la cuenta está activa.')
        encoded = password_hash(body['password']) if body.get('password') else None
        with self.connect() as db:
            row = db.execute("SELECT id FROM staff_users WHERE id=? AND pizzeria_id=? AND role='RECEPTIONIST'",
                             (user_id, self.user['pizzeria_id'])).fetchone()
            if row is None:
                raise AccessError(404, 'Cuenta de recepcionista no encontrada.')
            db.execute('UPDATE staff_users SET active=? WHERE id=?', (int(active), user_id))
            if encoded:
                db.execute('UPDATE staff_users SET password_hash=? WHERE id=?', (encoded, user_id))
            if not active or encoded:
                db.execute('DELETE FROM staff_sessions WHERE user_id=?', (user_id,))
            self.audit(db, 'update_receptionist', user_id, {'active': active, 'password_reset': bool(encoded)})
        return self.send_json(200, {'message': 'Cuenta actualizada.'})

    def change_password(self, body):
        if not password_matches(body.get('current_password'), self.user['password_hash']):
            raise AccessError(403, 'La contraseña actual no es correcta.')
        encoded = password_hash(body.get('new_password'))
        with self.connect() as db:
            db.execute('UPDATE staff_users SET password_hash=? WHERE id=?', (encoded, self.user['id']))
            db.execute('DELETE FROM staff_sessions WHERE user_id=?', (self.user['id'],))
        return self.send_json(200, {'message': 'Contraseña actualizada. Inicia sesión de nuevo.'}, cookie=self.session_cookie(clear=True))
