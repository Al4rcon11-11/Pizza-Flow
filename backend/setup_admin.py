"""Create the first administrator locally, without preset passwords or a public signup."""
import getpass
import sqlite3
from init_db import main as initialize
from security import password_hash, username_value
from api import connect


def main():
    initialize()
    with connect() as db:
        if db.execute("SELECT 1 FROM staff_users WHERE role='ADMIN'").fetchone():
            print('Ya existe un administrador. Inicia sesión con esa cuenta; no se modificó su contraseña.')
            return
    print('\nCrea tu administrador. La contraseña no se muestra mientras escribes.')
    username = username_value(input('Usuario: ').strip())
    name = input('Nombre: ').strip()
    if not name or len(name) > 100:
        raise ValueError('Escribe un nombre de hasta 100 caracteres.')
    password = getpass.getpass('Contraseña (12 a 128 caracteres): ')
    if password != getpass.getpass('Repite la contraseña: '):
        raise ValueError('Las contraseñas no coinciden.')
    encoded = password_hash(password)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM staff_users WHERE role='ADMIN'").fetchone():
            raise ValueError('Otro proceso ya creó un administrador.')
        db.execute("INSERT INTO staff_users (pizzeria_id,username,name,password_hash,role) VALUES (1,?,?,?,'ADMIN')",
                   (username, name, encoded))
    print('Administrador creado. Ejecuta python api.py y abre http://127.0.0.1:8000')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, sqlite3.Error) as error:
        print(f'No se pudo crear la cuenta: {error}')
        raise SystemExit(1)
