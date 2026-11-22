# Backend de Pizza-Flow

Desde esta carpeta, crea el primer administrador con `python setup_admin.py` y luego inicia la aplicación con `python api.py`. Abre http://127.0.0.1:8000.

El procedimiento completo, los permisos y los límites se explican en [la guía principal](../README.md).

## Rutas

- `GET /`: página web.
- `GET /health`, `GET /auth/status`: disponibilidad y configuración inicial.
- `POST /auth/login`: inicio de sesión.
- `GET /auth/me`, `POST /auth/logout`, `POST /auth/password`: sesión y contraseña propia.
- `GET /products`, `GET /zones`, `GET /clients`: catálogo y búsqueda de cliente, con sesión y `pizzeria_id` autorizado.
- `POST /orders`, `GET /orders/{id}`: creación y consulta de pedidos del local.
- `POST /orders/{id}/send-command`, `/confirm-command`, `/no-response`: estados de la comanda.
- `GET /admin/products`, `POST /admin/products`: catálogo completo y guardar producto (con `id` edita; sin `id` crea).
- `GET /admin/zones`, `POST /admin/zones`: zonas y tarifas.
- `GET /admin/users`, `POST /admin/users`, `POST /admin/users/update`: cuentas de recepcionista.

Las rutas administrativas exigen rol ADMIN. Las otras rutas privadas admiten ambos roles. Las mutaciones usan JSON, `X-PizzaFlow: 1` y, salvo login, el token `X-CSRF-Token` de la sesión. El identificador de pizzería y la identidad del operador se verifican en el servidor. No existe registro público de administradores.

`schema.sql` crea las tablas nuevas sin borrar pedidos. `setup_admin.py` conserva las cuentas existentes. El catálogo de ejemplo se carga con `init_db.py` sin reemplazar los productos que ya tienen esos identificadores.

No publiques `pizzaflow.sqlite3`, sus copias ni contraseñas. Este servidor está limitado a loopback y es una versión local, no un alojamiento de producción.

Las cinco pruebas existentes se adaptaron a una sesión autenticada. No se ejecutaron para esta ampliación; no cubren los casos nuevos de autenticación o administración.
