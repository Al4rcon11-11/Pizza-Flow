# Pizza-Flow

Prototipo local para registrar pedidos de una pizzería pequeña. El recepcionista identifica al cliente, captura el pedido, calcula el total y guarda el pedido solo después de que el cliente lo acepta. Luego registra manualmente el envío de la comanda y la respuesta del local. El MVP termina cuando el local confirma que recibió la comanda.

## Ejecutar el prototipo

Necesitas Python y un navegador. Abre la carpeta del proyecto en Visual Studio Code y deja dos terminales abiertas.

En la primera terminal:

```powershell
cd backend
python init_db.py
python api.py
```

La API queda disponible en `http://127.0.0.1:8000`.

En la segunda terminal, desde la carpeta principal:

```powershell
python -m http.server 5500
```

Abre `http://127.0.0.1:5500/Pizza-Flow_App.html`.

## Ejecutar las pruebas automatizadas

Desde la carpeta principal:

```powershell
python -m unittest backend.test_api -v
```

Las pruebas usan una base temporal y no modifican la base de demostración.

## Contenido

- `Pizza-Flow_App.html`: interfaz web de demostración.
- `backend/`: API, esquema SQLite, inicialización y pruebas.
- `Pizza-Flow_Informe_Consolidado_APA.pdf`: informe integrado con wireframe, Kanban, costos, pruebas y manual de usuario de cuatro páginas dentro de la fase de Transición.

## Límites

Los precios y productos son ficticios. El prototipo no envía mensajes, no procesa pagos, no tiene autenticación ni debe exponerse en Internet como servicio de producción. El envío de la comanda y la respuesta del local los registra manualmente el recepcionista.
