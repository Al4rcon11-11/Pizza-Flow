# Pizza-Flow

Aplicación local para tomar pedidos de una pizzería, con cuentas de administrador y recepcionista. Usa Python (biblioteca estándar), SQLite y una página HTML/CSS/JavaScript.

## Primera apertura

Abre la carpeta en Visual Studio Code. Si la API anterior está funcionando, detenla con **Ctrl+C** en su terminal. Desde la carpeta principal:

```powershell
cd backend
python setup_admin.py
python api.py
```

El primer comando prepara las tablas y pide usuario, nombre y contraseña para el administrador. La contraseña debe tener entre 12 y 128 caracteres y no se muestra al escribir. No hay contraseñas predeterminadas. Si ya existe un administrador, el comando conserva su cuenta.

Abre **http://127.0.0.1:8000**. La página y la API funcionan con una sola terminal. En las siguientes aperturas basta con ejecutar `python api.py` dentro de `backend`.

La versión anterior servida en el puerto 5500 sigue admitida desde `http://127.0.0.1:5500`, pero se recomienda usar el puerto 8000. No abras el archivo con doble clic ni mezcles `localhost` con `127.0.0.1`.

## Permisos

| Función | Administrador | Recepcionista |
|---|---|---|
| Buscar clientes y registrar pedidos | Sí | Sí |
| Registrar envío y respuesta del local | Sí | Sí |
| Crear, editar y desactivar productos | Sí | No |
| Crear, editar y desactivar zonas y tarifas | Sí | No |
| Crear, desactivar o restablecer cuentas de recepcionista | Sí | No |
| Cambiar su propia contraseña | Sí | Sí |

El cliente llama o escribe; no tiene una cuenta en esta versión. La API comprueba los permisos y la pizzería de cada cuenta, aunque se intente acceder directamente a una ruta.

## Administrar el catálogo

1. Inicia sesión como administrador y abre **Administración → Productos**.
2. Completa nombre, precio en pesos enteros e impuesto. Pulsa **Guardar**.
3. Usa **Editar** para cambiar un producto. Desmarca **Disponible para nuevos pedidos** para retirarlo del menú.
4. En **Zonas y tarifas**, configura nombres y costos de envío del mismo modo. Una tarifa de cero permite una zona sin costo de envío.

Los cambios se guardan en SQLite. Desactivar no elimina registros: los pedidos anteriores conservan nombre, precio, impuesto y tarifa aplicados al registrarse. El catálogo inicial es de ejemplo; reemplázalo por los datos de tu pizzería desde la administración.

## Cuentas del equipo

En **Administración → Recepcionistas**, crea una cuenta con nombre, usuario y contraseña inicial. El usuario se escribe con letras sin tildes, números, puntos o guiones. No compartas la cuenta del administrador.

Desde **Editar**, puedes desactivar una cuenta o asignar una nueva contraseña. Ambas acciones invalidan sus sesiones cuando corresponde. El propio usuario puede cambiar su contraseña desde **Mi cuenta**; después debe iniciar sesión nuevamente. No hay recuperación por correo en esta versión.

## Tomar un pedido

1. Busca al cliente por teléfono o prepara sus datos.
2. Selecciona productos, zona, dirección y método de pago.
3. Informa el total al cliente y marca su aceptación. Guarda el pedido.
4. Registra cómo se comunicó la comanda al local y su respuesta.

El medio de contacto del cliente y el medio de envío al local son datos distintos. El pago queda pendiente: elegir un método no equivale a cobrar. La identidad de quien registra el pedido se toma de la sesión y no de un nombre escrito libremente.

Al cambiar cantidades, zona, dirección, método o catálogo se solicita nuevamente la aceptación. Si el total en la API cambió desde que se mostró, no se guarda el pedido con ese nuevo total sin revisarlo. **Actualizar catálogo** permite cargar cambios hechos por otra persona. **Nuevo pedido** inicia otra atención.

## Datos y seguridad local

- `backend/pizzaflow.sqlite3` contiene cuentas y pedidos; no se publica en GitHub.
- Las contraseñas se almacenan mediante PBKDF2-HMAC-SHA256 con sal aleatoria y 600.000 iteraciones.
- La sesión usa una cookie HttpOnly y SameSite=Strict, vence a las ocho horas y se revoca al cerrar sesión. El servidor almacena el hash del token.
- Las operaciones requieren un token CSRF y origen local permitido. Se limitan los intentos de acceso fallidos.
- Los cambios administrativos quedan registrados en `admin_audit`, sin contraseñas.
- Conserva una copia privada de la base de datos con el servidor detenido antes de trasladar el proyecto.

Las decisiones de contraseña y sesión toman como referencia [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) y [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

La aplicación escucha solo en el equipo local. Publicar el código en GitHub no aloja el servicio. Un despliegue real necesita HTTPS, cookies Secure, un servidor apropiado, configuración de secretos, copias de seguridad y revisión de seguridad. Esta versión no integra mensajería, cobros ni entrega de pizzas.

## Estado de las pruebas y del informe

Las cinco pruebas existentes de pedidos se adaptaron para usar una sesión de personal en una base temporal. No se han ejecutado para esta ampliación ni se han agregado pruebas de autenticación o administración. Los resultados históricos del PDF corresponden a la versión anterior.

El PDF documenta el acceso del equipo, la administración y el manual integrado de cinco páginas. Conserva el cierre académico y las cifras de costos aprobadas; identifica esta ampliación como implementada y pendiente de pruebas funcionales.
