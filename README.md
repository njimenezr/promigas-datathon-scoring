# App de Scoring — Datathon Promigas

App **Streamlit** para Databricks Apps. Los participantes registran sus respuestas (valor + prompt de IA) por pregunta; la app valida contra el answer key, controla los **niveles en cascada** por track y muestra un **leaderboard por velocidad**. Las preguntas de **evidencia** las revisa el organizador.

> ⚠️ Esta carpeta es **solo del organizador** (contiene el answer key en `scoring/logic.py`). **No** se entrega a los participantes.

## Cómo funciona

- **Identidad automática:** toma el correo del header `X-Forwarded-Email` que inyecta Databricks Apps → filtrado por usuario sin login. En local, usa la variable `DEV_USUARIO`.
- **Almacenamiento:** una tabla Delta compartida (`DBX_TABLA`) escrita/leída con el SDK de Databricks vía un SQL Warehouse (`DBX_WAREHOUSE_ID`). Todos los participantes comparten la misma tabla → leaderboard global.
- **Cascada:** un nivel se desbloquea cuando todas las preguntas auto-validables del anterior están correctas (la evidencia no bloquea).
- **Puntaje:** Básico 10 · Medio 20 · Avanzado 30 · Experto 40 por pregunta. Cada pregunta cuenta una vez. Desempate por tiempo.

## Estructura

```
app-scoring/
├── app.py                 # UI Streamlit
├── app.yaml               # config de Databricks Apps (command + env)
├── requirements.txt
├── scoring/
│   ├── logic.py           # answer key + validación + cascada + leaderboard (testeable)
│   └── store.py           # tabla Delta vía SDK (in-app SP / local perfil CLI)
├── test_logic.py          # pruebas de lógica (sin dependencias)
└── test_store.py          # prueba de integración contra un workspace real
```

## Probar en local

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
# lógica (sin credenciales):
.venv/bin/python test_logic.py
# almacenamiento (contra un workspace real):
DATABRICKS_CONFIG_PROFILE=<perfil> DBX_WAREHOUSE_ID=<id> \
  DBX_TABLA=<catalogo.esquema.tabla_test> .venv/bin/python test_store.py
# UI:
DATABRICKS_CONFIG_PROFILE=<perfil> DBX_WAREHOUSE_ID=<id> DBX_TABLA=<...> \
  DEV_USUARIO=tu@correo.com ORGANIZADORES=tu@correo.com \
  .venv/bin/streamlit run app.py
```

## Desplegar en Databricks Apps

1. **Clona este repo** como Git folder en el workspace **compartido de Promigas** (o `databricks sync .`).
2. Edita `app.yaml`:
   - `DBX_WAREHOUSE_ID` = **ID del SQL Warehouse** (valor directo; más robusto que `valueFrom`, que solo resuelve si el resource ya está registrado al desplegar).
   - `DBX_TABLA` = catálogo.esquema.tabla donde se guardan las respuestas.
   - `ORGANIZADORES` = correos que verán la pestaña de revisión.
   - En el bloque `resources`, pon el **mismo** warehouse id (esto le otorga `CAN_USE` al service principal de la app).
3. Crea y despliega la app:
   ```bash
   databricks apps create promigas-datathon-scoring
   databricks sync . "/Workspace/Users/<tu>/promigas-datathon-scoring"
   databricks apps deploy promigas-datathon-scoring \
     --source-code-path "/Workspace/Users/<tu>/promigas-datathon-scoring"
   ```
   (También puedes crear la app y añadir el recurso de warehouse desde la **UI de Databricks Apps**.)
4. Da permisos al **service principal** de la app:
   - `CAN USE` sobre el SQL Warehouse (o añádelo como resource en la UI, que otorga CAN_USE).
   - `USE CATALOG` / `USE SCHEMA` / `MODIFY` + `SELECT` sobre el esquema de `DBX_TABLA`.
   - La tabla se crea sola al primer arranque (`CREATE TABLE IF NOT EXISTS`) si el SP tiene `CREATE TABLE`. Si no quieres dar `CREATE TABLE`, **pre-crea la tabla** con [`sql/00_setup_tabla.sql`](sql/00_setup_tabla.sql) y deja al SP solo `MODIFY`/`SELECT`.
5. Comparte la app con los participantes (necesitan cuenta y permiso en ese workspace — las apps **no** son públicas).

**Identidad:** desplegada, la app toma el usuario del header `X-Forwarded-Email` que inyecta Databricks Apps (no configures `DEV_USUARIO`; eso es solo para local).

## Estado

✅ Lógica probada (36 ítems DE / 35 AE, trampas de formato locale, cascada, leaderboard, evidencia).
✅ Almacenamiento probado contra `fevm-serverless-demo-nj` (crear tabla, filtro por usuario, aprobar evidencia).
✅ UI probada en navegador real (identidad, envío con validación, progreso en cascada, sin errores de consola).
