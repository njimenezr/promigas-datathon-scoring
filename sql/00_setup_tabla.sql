-- =====================================================================
-- Setup de la tabla de respuestas — App de Scoring Datathon Promigas
-- =====================================================================
-- Úsalo si en el workspace de Promigas NO quieres que el service principal
-- de la app tenga permiso de CREATE TABLE. Corre esto UNA vez (como alguien
-- con permisos sobre el esquema), y a la app le basta MODIFY + SELECT.
--
-- Si el SP sí tiene CREATE TABLE, la app crea la tabla sola al arrancar
-- (CREATE TABLE IF NOT EXISTS en scoring/store.py) y este script es opcional.
--
-- Reemplaza:
--   <CATALOGO>.<ESQUEMA>   -> el esquema donde vive DBX_TABLA (app.yaml)
--   <SP_CLIENT_ID>         -> service_principal_client_id de la app
--                            (databricks apps get <app> -> service_principal_client_id)
-- =====================================================================

-- 1) Esquema (si no existe)
CREATE SCHEMA IF NOT EXISTS <CATALOGO>.<ESQUEMA>;

-- 2) Tabla de respuestas (misma estructura que crea la app)
CREATE TABLE IF NOT EXISTS <CATALOGO>.<ESQUEMA>.app_respuestas (
    id        STRING,   -- uuid del intento
    usuario   STRING,   -- correo (header X-Forwarded-Email)
    track     STRING,   -- data_engineer | analytics_engineer
    nivel     STRING,   -- basico | medio | avanzado | experto
    pregunta  STRING,   -- id de pregunta (p.ej. DE-1)
    valor     STRING,   -- valor que pegó el participante
    prompt    STRING,   -- prompt de IA usado
    correcto  BOOLEAN,  -- si el valor fue correcto (auto-validado)
    puntos    INT,      -- puntos de la pregunta
    estado    STRING,   -- auto | pendiente | aprobado | rechazado (evidencia)
    ts        DOUBLE    -- epoch seconds (desempate por velocidad)
) USING DELTA;

-- 3) Permisos para el service principal de la app
GRANT USE CATALOG ON CATALOG <CATALOGO> TO `<SP_CLIENT_ID>`;
GRANT USE SCHEMA  ON SCHEMA  <CATALOGO>.<ESQUEMA> TO `<SP_CLIENT_ID>`;
GRANT SELECT, MODIFY ON TABLE <CATALOGO>.<ESQUEMA>.app_respuestas TO `<SP_CLIENT_ID>`;
-- Si prefieres que la app pueda crear/gestionar la tabla ella misma, en vez de
-- los dos GRANT de arriba sobre la tabla, otorga a nivel de esquema:
--   GRANT CREATE TABLE, MODIFY, SELECT ON SCHEMA <CATALOGO>.<ESQUEMA> TO `<SP_CLIENT_ID>`;

-- 4) (Opcional) Reset antes del evento: vaciar respuestas de pruebas
-- TRUNCATE TABLE <CATALOGO>.<ESQUEMA>.app_respuestas;
