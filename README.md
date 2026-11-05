# Tickets API

Backend sencillo de un sistema de tickets construido con FastAPI y SQLite.

## Características

- Autenticación con JWT (registro, login y usuario actual).
- Inicio de sesión con OAuth2 (GitHub y Google).
- Refresco de tokens con rotación, revocación en base de datos y detección de reutilización.
- Gestión de usuarios restringida a administradores (listado, detalle y eliminación).
- CRUD de tickets (crear, listar, obtener, actualizar, eliminar).
- Filtros por estado y prioridad, y búsqueda por texto.
- Comentarios asociados a cada ticket.
- Paginación básica.
- Documentación interactiva automática (Swagger UI y ReDoc).
- Interfaz web incluida (login, listado, detalle, comentarios y filtros).

## Autenticación

Las rutas de tickets y comentarios requieren un token JWT válido. El flujo es:

1. Registrar un usuario en `POST /api/auth/register`.
2. Iniciar sesión en `POST /api/auth/login` (formulario `username`/`password`).
3. Enviar el token en la cabecera `Authorization: Bearer <token>`.

### Refresco de tokens

El login devuelve dos tokens:

- **access token**: corto (30 minutos por defecto), se usa en la cabecera `Authorization`.
- **refresh token**: largo (7 días por defecto), sirve solo para obtener access tokens nuevos.

El refresh token se entrega de dos formas a la vez:

- En el cuerpo de la respuesta (`refresh_token`), para clientes que gestionan el token ellos mismos.
- En una cookie `httpOnly` llamada `tickets_refresh_token`, restringida a `/api/auth`, que es la vía recomendada porque el navegador la envía sola y JavaScript no puede leerla.

`POST /api/auth/refresh` acepta el token en la cookie (tiene prioridad) o en el cuerpo
(`{"refresh_token": "..."}`), y aplica rotación:

1. Cada refresco emite un refresh token nuevo y revoca el anterior.
2. Los tokens rotados quedan encadenados por una **familia** (la sesión).
3. Si se vuelve a presentar un token ya rotado, el servidor detecta la **reutilización**,
   revoca toda la familia y corta la sesión (respuesta `401`).
4. `POST /api/auth/logout` revoca la familia de la sesión actual y borra la cookie.
5. `POST /api/auth/logout-all` revoca todas las sesiones del usuario.
6. `GET /api/auth/sessions` lista las sesiones activas y revocadas del usuario.

Solo se guarda el `jti` del token en la tabla `refresh_tokens` (nunca el token en claro),
junto con su familia, caducidad, motivo de revocación, IP y user agent.

La configuración se lee de variables de entorno:

| Variable                     | Por defecto             | Descripción                                   |
|------------------------------|-------------------------|-----------------------------------------------|
| `SECRET_KEY`                 | `dev-secret-change-me`  | Clave para firmar los access tokens           |
| `REFRESH_SECRET_KEY`         | valor de `SECRET_KEY`   | Clave para firmar los refresh tokens          |
| `JWT_ALGORITHM`              | `HS256`                 | Algoritmo de firma                            |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| `30`                    | Minutos de validez del access token            |
| `REFRESH_TOKEN_EXPIRE_DAYS`  | `7`                     | Días de validez del refresh token             |
| `JWT_ISSUER`                 | `tickets-api`           | Claim `iss` obligatorio en los tokens          |
| `JWT_AUDIENCE`               | `tickets-web`           | Claim `aud` obligatorio en los tokens          |
| `JWT_LEEWAY_SECONDS`         | `5`                     | Tolerancia de reloj al validar `exp`          |
| `REFRESH_COOKIE_NAME`        | `tickets_refresh_token` | Nombre de la cookie del refresh token         |
| `REFRESH_COOKIE_PATH`        | `/api/auth`             | Ruta para la que se envía la cookie           |
| `REFRESH_COOKIE_SECURE`      | `false`                 | Marca la cookie como `Secure` (obligatorio en HTTPS) |
| `REFRESH_COOKIE_SAMESITE`    | `lax`                   | Política `SameSite` de la cookie              |
| `CORS_ORIGINS`               | `*`                     | Orígenes permitidos, separados por comas       |

### Inicio de sesión con OAuth2 (GitHub y Google)

Además del usuario/contraseña, la API permite iniciar sesión con OAuth2
(flujo *authorization code*) a través de GitHub y Google. Cada proveedor se
configura con sus propias credenciales; si un proveedor no está configurado,
su botón devuelve un error y el resto de la autenticación sigue funcionando.

| Variable                   | Por defecto            | Descripción                                      |
|----------------------------|------------------------|--------------------------------------------------|
| `GITHUB_CLIENT_ID`         | —                      | Client ID de la OAuth App de GitHub              |
| `GITHUB_CLIENT_SECRET`     | —                      | Client Secret de la OAuth App de GitHub          |
| `GOOGLE_CLIENT_ID`         | —                      | Client ID del cliente OAuth de Google            |
| `GOOGLE_CLIENT_SECRET`     | —                      | Client Secret del cliente OAuth de Google        |
| `OAUTH_CALLBACK_BASE_URL`  | URL de la petición     | Base pública para construir el `redirect_uri` (detrás de proxies) |
| `OAUTH_FRONTEND_REDIRECT`  | `/`                    | URL del frontend a la que se vuelve tras el login |
| `OAUTH_HTTP_TIMEOUT_SECONDS` | `10`                 | Timeout de las llamadas a los proveedores        |

URLs de callback que hay que registrar en cada proveedor:

- GitHub: `{base}/api/auth/oauth/github/callback`
- Google: `{base}/api/auth/oauth/google/callback`

El flujo es:

1. El navegador entra en `GET /api/auth/oauth/{provider}/login`.
2. La API redirige al proveedor con un `state` aleatorio guardado en una cookie
   `httpOnly` para prevenir CSRF.
3. El proveedor vuelve a `GET /api/auth/oauth/{provider}/callback` con el código.
4. La API canjea el código, lee el perfil, busca o crea el usuario local y
   vincula la cuenta externa en la tabla `oauth_accounts`.
5. Se emite el mismo par de tokens JWT que en el login normal: el refresh token
   va en la cookie `httpOnly` y se redirige al frontend con `?oauth=success`.
   La SPA canjea esa cookie por un access token llamando a `/api/auth/refresh`.

Si el correo del proveedor está verificado y coincide con un usuario local, la
cuenta externa se vincula a ese usuario. Los usuarios creados solo por OAuth
reciben una contraseña aleatoria, por lo que no pueden entrar con usuario y
contraseña hasta que se les establezca una.

## Requisitos

- Python 3.10+

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecución

```bash
uvicorn app.main:app --reload
```

Quedará disponible en:

- Interfaz web: http://127.0.0.1:8000/
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Frontend

La interfaz web es una SPA ligera (HTML/CSS/JS sin dependencias de build) servida
por el propio FastAPI desde `app/static/`. Guarda el access token JWT en
`localStorage` y lo envía en la cabecera `Authorization`. El refresh token viaja
en una cookie `httpOnly`, así que el navegador lo renueva de forma automática.
Al abrirla:

1. Crea una cuenta, inicia sesión con usuario/contraseña o con GitHub/Google.
2. Crea, filtra y busca tickets.
3. Abre un ticket para ver/editar su estado y gestionar comentarios.

Si el access token caduca, la SPA pide uno nuevo a `POST /api/auth/refresh`
(usando la cookie), reintenta la petición original y solo cierra la sesión si
el refresh también falla.

## Endpoints

### Autenticación

| Método | Ruta                    | Descripción                                |
|--------|-------------------------|--------------------------------------------|
| POST   | `/api/auth/register`    | Registra un usuario                        |
| POST   | `/api/auth/login`       | Obtiene access token y refresh token        |
| POST   | `/api/auth/refresh`     | Rota el refresh token y emite uno nuevo     |
| POST   | `/api/auth/logout`      | Revoca la sesión actual y borra la cookie   |
| POST   | `/api/auth/logout-all`  | Revoca todas las sesiones del usuario      |
| GET    | `/api/auth/sessions`    | Lista las sesiones del usuario              |
| GET    | `/api/auth/me`          | Devuelve el usuario autenticado            |
| GET    | `/api/auth/oauth/providers`          | Lista los proveedores OAuth configurados |
| GET    | `/api/auth/oauth/{provider}/login`    | Redirige al proveedor (github, google)   |
| GET    | `/api/auth/oauth/{provider}/callback` | Callback del proveedor                   |

### Tickets

| Método | Ruta                  | Descripción                     |
|--------|-----------------------|---------------------------------|
| GET    | `/api/tickets`        | Lista tickets (filtros y paginación) |
| POST   | `/api/tickets`        | Crea un ticket                  |
| GET    | `/api/tickets/{id}`   | Obtiene un ticket               |
| PATCH  | `/api/tickets/{id}`   | Actualiza parcialmente un ticket |
| DELETE | `/api/tickets/{id}`   | Elimina un ticket               |

Parámetros de listado: `status`, `priority`, `search`, `skip`, `limit`.

Todas las rutas de tickets y comentarios requieren la cabecera
`Authorization: Bearer <token>`.

### Comentarios

| Método | Ruta                                | Descripción               |
|--------|-------------------------------------|---------------------------|
| GET    | `/api/tickets/{id}/comments`        | Lista comentarios del ticket |
| POST   | `/api/tickets/{id}/comments`        | Añade un comentario       |
| DELETE | `/api/comments/{id}`                | Elimina un comentario     |

### Usuarios (solo administradores)

| Método | Ruta                  | Descripción                      |
|--------|-----------------------|----------------------------------|
| GET    | `/api/users`          | Lista usuarios (filtros y paginación) |
| GET    | `/api/users/{id}`     | Obtiene un usuario               |
| DELETE | `/api/users/{id}`     | Elimina un usuario               |

Estas rutas requieren rol `admin` (o `is_superuser`); cualquier otro rol recibe
`403`. La respuesta nunca incluye el hash de la contraseña.

Parámetros de listado: `search` (busca en `username` y `email`), `role`,
`is_active`, `skip`, `limit`.

Al eliminar un usuario:

- Se revocan sus sesiones (los refresh tokens dejan de ser válidos).
- Sus tickets **no** se borran: quedan con `owner_id` a `NULL` y conservan sus
  comentarios.
- Un administrador no puede eliminarse a sí mismo (`400`).

## Ejemplos

Registrar un usuario:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "ana", "email": "ana@example.com", "password": "secreto123"}'
```

Iniciar sesión y guardar el token:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -d "username=ana&password=secreto123" | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
```

Crear un ticket:

```bash
curl -X POST http://127.0.0.1:8000/api/tickets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Error al iniciar sesión", "description": "No carga el login", "priority": "high"}'
```

Listar tickets abiertos de alta prioridad:

```bash
curl "http://127.0.0.1:8000/api/tickets?status=open&priority=high" \
  -H "Authorization: Bearer $TOKEN"
```

Actualizar estado:

```bash
curl -X PATCH http://127.0.0.1:8000/api/tickets/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'
```

Añadir comentario:

```bash
curl -X POST http://127.0.0.1:8000/api/tickets/1/comments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"author": "ana", "body": "Estoy revisando el problema"}'
```

Renovar el access token usando la cookie de sesión (`-c`/`-b` mantienen el
refresh token entre peticiones):

```bash
curl -c cookies -X POST http://127.0.0.1:8000/api/auth/login \
  -d "username=ana&password=secreto123"

curl -b cookies -c cookies -X POST http://127.0.0.1:8000/api/auth/refresh
```

Cerrar la sesión (revoca el refresh token en el servidor):

```bash
curl -b cookies -X POST http://127.0.0.1:8000/api/auth/logout
```

Listar usuarios (necesita un token de administrador):

```bash
curl "http://127.0.0.1:8000/api/users?role=admin&limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

Eliminar un usuario:

```bash
curl -X DELETE http://127.0.0.1:8000/api/users/2 \
  -H "Authorization: Bearer $TOKEN"
```

## Estructura

```
app/
├── main.py          # Aplicación FastAPI y configuración
├── database.py      # Motor, sesión y Base de SQLAlchemy
├── models.py        # Modelos ORM (tickets, comentarios, usuarios, refresh tokens)
├── schemas.py       # Esquemas Pydantic
├── crud.py          # Lógica de acceso a datos
├── security.py      # Hash de contraseñas, JWT y ajustes de cookies
├── oauth.py         # Cliente OAuth2 de GitHub y Google
├── deps.py          # Dependencias (usuario autenticado)
├── routers/
│   ├── auth.py      # Registro, login, refresco y cierre de sesión
│   ├── oauth.py     # Login OAuth2 (GitHub y Google)
│   ├── tickets.py   # Endpoints de tickets
│   ├── comments.py  # Endpoints de comentarios
│   └── users.py     # Endpoints de usuarios (solo admin)
└── static/          # Frontend web (SPA)
    ├── index.html
    ├── styles.css
    └── app.js
```
