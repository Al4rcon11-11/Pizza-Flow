PRAGMA foreign_keys = ON;

-- Prototipo de una pizzeria piloto. Los importes se almacenan en pesos enteros.
CREATE TABLE IF NOT EXISTS pizzerias (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    pizzeria_id INTEGER NOT NULL REFERENCES pizzerias(id),
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (pizzeria_id, phone)
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    pizzeria_id INTEGER NOT NULL REFERENCES pizzerias(id),
    name TEXT NOT NULL,
    price_cop INTEGER NOT NULL CHECK (price_cop > 0),
    tax_rate_pct REAL NOT NULL DEFAULT 0 CHECK (tax_rate_pct >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    UNIQUE (pizzeria_id, name)
);

CREATE TABLE IF NOT EXISTS delivery_zones (
    id INTEGER PRIMARY KEY,
    pizzeria_id INTEGER NOT NULL REFERENCES pizzerias(id),
    name TEXT NOT NULL,
    fee_cop INTEGER NOT NULL CHECK (fee_cop >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    UNIQUE (pizzeria_id, name)
);

-- El metodo elegido no significa que el pago ya fue recibido.
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    pizzeria_id INTEGER NOT NULL REFERENCES pizzerias(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    delivery_zone_id INTEGER NOT NULL REFERENCES delivery_zones(id),
    delivery_address TEXT NOT NULL,
    capture_channel TEXT NOT NULL CHECK (capture_channel IN ('PHONE', 'WHATSAPP', 'SELF_SERVICE')),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('CASH_ON_DELIVERY', 'DIGITAL')),
    payment_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (payment_status IN ('PENDING', 'PAID', 'FAILED')),
    order_status TEXT NOT NULL DEFAULT 'RECIBIDO' CHECK (order_status IN ('RECIBIDO', 'ENVIADO_AL_LOCAL', 'CONFIRMADO_LOCAL')),
    subtotal_cop INTEGER NOT NULL DEFAULT 0 CHECK (subtotal_cop >= 0),
    tax_total_cop INTEGER NOT NULL DEFAULT 0 CHECK (tax_total_cop >= 0),
    delivery_fee_cop INTEGER NOT NULL DEFAULT 0 CHECK (delivery_fee_cop >= 0),
    total_cop INTEGER NOT NULL DEFAULT 0 CHECK (total_cop >= 0),
    notes TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Copia nombre, precio e impuesto al momento del pedido para preservar el historico.
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    product_name_snapshot TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cop INTEGER NOT NULL CHECK (unit_price_cop > 0),
    tax_rate_pct_snapshot REAL NOT NULL CHECK (tax_rate_pct_snapshot >= 0),
    line_subtotal_cop INTEGER NOT NULL CHECK (line_subtotal_cop >= 0),
    line_tax_cop INTEGER NOT NULL CHECK (line_tax_cop >= 0)
);

-- Una comanda puede confirmarse o quedar pendiente de seguimiento manual.
CREATE TABLE IF NOT EXISTS dispatch_commands (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
    channel TEXT CHECK (channel IN ('WHATSAPP_MANUAL', 'PHONE', 'IN_PERSON')),
    command_status TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (command_status IN ('PENDIENTE', 'ENVIADA', 'CONFIRMADA', 'SIN_CONFIRMAR')),
    sent_at TEXT,
    confirmed_at TEXT,
    confirmed_by TEXT,
    notes TEXT,
    CHECK (command_status <> 'CONFIRMADA' OR (confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS order_status_history (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(pizzeria_id, phone);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(pizzeria_id, order_status, created_at);
CREATE INDEX IF NOT EXISTS idx_commands_status ON dispatch_commands(command_status, sent_at);
