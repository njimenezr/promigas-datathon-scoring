-- =====================================================================
--  Setup completo — App de Scoring Datathon Promigas
-- =====================================================================
--  Crea las 4 tablas de la app y otorga permisos al service principal.
--  Es idempotente (CREATE ... IF NOT EXISTS + GRANT) y replicable: solo
--  editas las 3 variables de abajo y lo corres UNA vez.
--
--  CÓMO USARLO
--  -----------
--  1. Abre este archivo en el editor SQL de Databricks (Query editor).
--  2. Edita SOLO los 3 DEFAULT del bloque de variables.
--  3. Ejecútalo completo (Run) con un usuario que tenga permisos sobre el
--     catálogo/esquema y GRANT sobre las tablas.
--
--  ¿CUÁNDO CORRERLO?
--  ----------------
--  Úsalo si NO quieres darle CREATE TABLE al service principal de la app.
--  Tras correrlo, a la app le basta con SELECT + MODIFY sobre las tablas.
--  Si el SP sí tiene CREATE TABLE en el esquema, la app las crea sola al
--  arrancar (CREATE TABLE IF NOT EXISTS en scoring/store.py) y esto es opcional.
--
--  Los nombres app_respuestas / app_casos / app_calif_a / app_votos_b deben
--  coincidir con DBX_TABLA (app.yaml) y sus tablas hermanas (mismo esquema).
--
--  SP_CLIENT_ID = service_principal_client_id de la app:
--    databricks apps get <app> -> service_principal_client_id
-- =====================================================================

BEGIN
  -- ------------------------------------------------------------------
  -- 👉 EDITA SOLO ESTAS 3 LÍNEAS
  -- ------------------------------------------------------------------
  DECLARE catalogo     STRING DEFAULT 'REEMPLAZAR_CATALOGO';
  DECLARE esquema      STRING DEFAULT 'REEMPLAZAR_ESQUEMA';
  DECLARE sp_client_id STRING DEFAULT 'REEMPLAZAR_SP_CLIENT_ID';

  -- Derivada (no tocar): catálogo.esquema
  DECLARE fq STRING;
  SET fq = catalogo || '.' || esquema;

  -- ------------------------------------------------------------------
  -- 1) Esquema
  -- ------------------------------------------------------------------
  CREATE SCHEMA IF NOT EXISTS IDENTIFIER(fq);

  -- ------------------------------------------------------------------
  -- 2) Tablas (misma estructura que crea la app en scoring/store.py)
  -- ------------------------------------------------------------------
  -- Respuestas del reto (incluye la evidencia de DBUs DE-DBU/AE-DBU)
  CREATE TABLE IF NOT EXISTS IDENTIFIER(fq || '.app_respuestas') (
    id        STRING,   -- uuid del intento
    usuario   STRING,   -- correo (header X-Forwarded-Email)
    track     STRING,   -- data_engineer | analytics_engineer
    nivel     STRING,   -- basico | medio | avanzado | experto
    pregunta  STRING,   -- id de pregunta (p.ej. DE-1, DE-DBU)
    valor     STRING,   -- valor que pegó el participante
    prompt    STRING,   -- prompt de IA usado
    correcto  BOOLEAN,  -- si el valor fue correcto (auto-validado)
    puntos    INT,      -- puntos de la pregunta
    estado    STRING,   -- auto | pendiente | aprobado | rechazado (evidencia)
    ts        DOUBLE    -- epoch seconds (desempate por velocidad)
  ) USING DELTA;

  -- Casos del millón (Pieza B) — uno por equipo
  CREATE TABLE IF NOT EXISTS IDENTIFIER(fq || '.app_casos') (
    id            STRING,   -- uuid
    equipo        STRING,   -- clave lógica (1 caso por equipo)
    area          STRING,   -- área(s) de la compañía
    integrantes   STRING,   -- integrantes (uno por línea)
    nombre_caso   STRING,
    problema      STRING,
    empresas      STRING,   -- empresas del grupo impactadas
    palanca       STRING,   -- palanca(s) de valor
    millon        STRING,   -- cómo estiman el valor
    databricks_ia STRING,   -- rol de Databricks + IA
    link          STRING,   -- link a la presentación (opcional)
    creado_por    STRING,   -- correo de quien registró
    ts            DOUBLE
  ) USING DELTA;

  -- Calificación de la presentación individual (Pieza A) — fila por participante × juez
  CREATE TABLE IF NOT EXISTS IDENTIFIER(fq || '.app_calif_a') (
    id           STRING,
    participante STRING,
    juez         STRING,
    arquitectura INT,       -- 1-5
    ia           INT,       -- 1-5
    valor        INT,       -- 1-5
    comunicacion INT,       -- 1-5
    ts           DOUBLE
  ) USING DELTA;

  -- Voto del jurado a los casos B — fila por equipo × juez
  CREATE TABLE IF NOT EXISTS IDENTIFIER(fq || '.app_votos_b') (
    id            STRING,
    equipo        STRING,
    juez          STRING,
    cuantificable INT,      -- 1-5
    cross_company INT,      -- 1-5
    factible      INT,      -- 1-5
    databricks_ia INT,      -- 1-5
    ts            DOUBLE
  ) USING DELTA;

  -- ------------------------------------------------------------------
  -- 3) Permisos para el service principal de la app
  --    (el principal del GRANT no admite IDENTIFIER(); se construye con
  --     EXECUTE IMMEDIATE para mantenerlo parametrizado por variable)
  -- ------------------------------------------------------------------
  EXECUTE IMMEDIATE 'GRANT USE CATALOG ON CATALOG ' || catalogo || ' TO `' || sp_client_id || '`';
  EXECUTE IMMEDIATE 'GRANT USE SCHEMA  ON SCHEMA  ' || fq       || ' TO `' || sp_client_id || '`';
  EXECUTE IMMEDIATE 'GRANT SELECT, MODIFY ON TABLE ' || fq || '.app_respuestas TO `' || sp_client_id || '`';
  EXECUTE IMMEDIATE 'GRANT SELECT, MODIFY ON TABLE ' || fq || '.app_casos       TO `' || sp_client_id || '`';
  EXECUTE IMMEDIATE 'GRANT SELECT, MODIFY ON TABLE ' || fq || '.app_calif_a     TO `' || sp_client_id || '`';
  EXECUTE IMMEDIATE 'GRANT SELECT, MODIFY ON TABLE ' || fq || '.app_votos_b     TO `' || sp_client_id || '`';

  -- Alternativa: si prefieres que la app cree/gestione las tablas ella misma,
  -- en vez de los 4 GRANT sobre tablas de arriba, otorga a nivel de esquema:
  --   EXECUTE IMMEDIATE 'GRANT CREATE TABLE, SELECT, MODIFY ON SCHEMA ' || fq || ' TO `' || sp_client_id || '`';
END;

-- =====================================================================
--  (OPCIONAL) Reset antes del evento: vaciar datos de prueba.
--  Descoméntalo y córrelo por separado. Edita las 2 primeras líneas.
-- =====================================================================
-- BEGIN
--   DECLARE fq STRING DEFAULT 'REEMPLAZAR_CATALOGO.REEMPLAZAR_ESQUEMA';
--   EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || fq || '.app_respuestas';
--   EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || fq || '.app_casos';
--   EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || fq || '.app_calif_a';
--   EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || fq || '.app_votos_b';
-- END;
