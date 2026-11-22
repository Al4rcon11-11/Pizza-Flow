from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "pizzaflow.sqlite3"
SCHEMA_PATH = ROOT / "schema.sql"


def remove_old_customer_consent_fields(db):
    """Migrate the local demo DB while preserving existing customer/order IDs."""
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'customers'"
    ).fetchone()
    if not exists:
        return
    columns = {row[1] for row in db.execute("PRAGMA table_info(customers)")}
    if not {"consent_status", "consent_channel", "consent_at"}.issubset(columns):
        return

    db.execute("PRAGMA foreign_keys = OFF")
    db.execute("BEGIN")
    try:
        db.execute("""
            CREATE TABLE customers_new (
                id INTEGER PRIMARY KEY,
                pizzeria_id INTEGER NOT NULL REFERENCES pizzerias(id),
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (pizzeria_id, phone)
            )
        """)
        db.execute("""
            INSERT INTO customers_new (id, pizzeria_id, name, phone, created_at)
            SELECT id, pizzeria_id, name, phone, created_at FROM customers
        """)
        db.execute("DROP TABLE customers")
        db.execute("ALTER TABLE customers_new RENAME TO customers")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def main():
    schema = SCHEMA_PATH.read_text(encoding="utf-8-sig")
    with sqlite3.connect(DB_PATH) as db:
        remove_old_customer_consent_fields(db)
        db.executescript(schema)
        db.execute(
            "INSERT OR IGNORE INTO pizzerias (id, name, phone) VALUES (1, ?, ?)",
            ("Pizzeria de demostracion", "3000000000"),
        )
        db.execute(
            "INSERT OR IGNORE INTO products (id, pizzeria_id, name, price_cop, tax_rate_pct) VALUES (1, 1, ?, 18000, 0)",
            ("Pizza personal (dato ficticio)",),
        )
        db.execute(
            "INSERT OR IGNORE INTO products (id, pizzeria_id, name, price_cop, tax_rate_pct) VALUES (2, 1, ?, 32000, 0)",
            ("Pizza mediana (dato ficticio)",),
        )
        db.execute(
            "INSERT OR IGNORE INTO delivery_zones (id, pizzeria_id, name, fee_cop) VALUES (1, 1, ?, 4000)",
            ("Zona de demostracion (tarifa ficticia)",),
        )
    print(f"Base de datos creada: {DB_PATH}")
    print("Se cargaron productos, impuesto y tarifa de ejemplo; reemplazalos por datos autorizados.")


if __name__ == "__main__":
    main()
