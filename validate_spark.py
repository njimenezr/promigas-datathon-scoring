"""Valida TODAS las respuestas numéricas del answer key en Spark/Databricks
(el motor real que usarán los participantes), no en DuckDB.

Carga los CSV congelados a un volumen del workspace, crea tablas y corre cada
consulta en Spark SQL comparando contra scoring.logic.POR_ID.
"""
import os, io, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem
from scoring.logic import POR_ID, normaliza_texto

CAT = os.getenv("VAL_CATALOG", "serverless_demo_nj_catalog")
SCH = os.getenv("VAL_SCHEMA", "promigas_datathon")
VOL = "val_crudos"
WID = os.getenv("DBX_WAREHOUSE_ID", "c6d413e83558a43d")
DATASETS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "promigas_datathon", "datasets"))

w = WorkspaceClient()

def sql(stmt):
    r = w.statement_execution.execute_statement(warehouse_id=WID, statement=stmt,
                                                catalog=CAT, schema=SCH, wait_timeout="50s")
    while r.status and r.status.state and r.status.state.value in ("PENDING", "RUNNING"):
        time.sleep(1); r = w.statement_execution.get_statement(r.statement_id)
    if r.status and r.status.state and r.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"SQL FAIL: {r.status.error.message if r.status.error else '?'}\n{stmt[:200]}")
    return r

def scalar(stmt):
    r = sql(stmt)
    return r.result.data_array[0][0] if r.result and r.result.data_array else None

vol_path = f"/Volumes/{CAT}/{SCH}/{VOL}"
print(f"Workspace warehouse {WID} · {CAT}.{SCH}")
sql(f"CREATE VOLUME IF NOT EXISTS {CAT}.{SCH}.{VOL}")

# --- subir CSVs ---
uploads = {
    "gold_gas_flows.csv": "analytics_engineer/gold_gas_flows.csv",
    "weather.csv": "analytics_engineer/weather_meteo_by_node.csv",
    "nodos.csv": "analytics_engineer/nodos.csv",
    "gas_flows.csv": "data_engineer/gas_flows.csv",
    "gas_interrupted.csv": "data_engineer/gas_interrupted.csv",
}
for dst, src in uploads.items():
    with open(os.path.join(DATASETS, src), "rb") as f:
        w.files.upload(f"{vol_path}/{dst}", f, overwrite=True)
print("✅ CSVs subidos al volumen")

# --- crear tablas ---
sql(f"CREATE OR REPLACE TABLE val_oro AS SELECT * FROM read_files('{vol_path}/gold_gas_flows.csv', format=>'csv', header=>true)")
sql(f"CREATE OR REPLACE TABLE val_clima AS SELECT * FROM read_files('{vol_path}/weather.csv', format=>'csv', header=>true)")
# crudos como STRING (equivalente a all_varchar de DuckDB)
sql(f"CREATE OR REPLACE TABLE val_bd AS SELECT * FROM read_files('{vol_path}/gas_flows.csv', format=>'csv', header=>true, inferColumnTypes=>false)")
sql(f"CREATE OR REPLACE TABLE val_bi AS SELECT * FROM read_files('{vol_path}/gas_interrupted.csv', format=>'csv', header=>true, inferColumnTypes=>false)")
print("✅ tablas creadas (val_oro, val_clima, val_bd, val_bi)\n")

# reglas de calidad (Spark) sobre crudos-string
def nl(c): return f"({c} IS NULL OR {c}='null' OR {c}='')"
RBD = "(" + " OR ".join([nl("dia_semana"), nl("remitente"), nl("nodo_entrada"), nl("nodo_salida"), nl("modelo"), "NOT(length(id_unidad) BETWEEN 5 AND 6)"]) + ")"
RBI = "(" + " OR ".join([nl("dia_semana"), nl("remitente"), nl("nodo_entrada"), nl("nodo_salida"), "NOT(length(id_unidad) BETWEEN 5 AND 6)"]) + ")"
# cuarentena = fail OR duplicado (todas las copias); md5(row) identifica duplicados exactos
Q_BD = f"SELECT count(*) FROM (SELECT *, count(*) OVER (PARTITION BY md5(to_json(struct(*)))) nn FROM val_bd) t WHERE {RBD} OR nn>1"
Q_BI = f"SELECT count(*) FROM (SELECT *, count(*) OVER (PARTITION BY md5(to_json(struct(*)))) nn FROM val_bi) t WHERE {RBI} OR nn>1"

# --- consultas por pregunta ---
Q = {
 # DE Básico
 "DE-1": "SELECT count(*) FROM val_bd",
 "DE-2": "SELECT count(*) FROM val_bi",
 "DE-3": f"SELECT count(*) FROM read_files('{vol_path}/weather.csv', format=>'csv', header=>true)",
 "DE-4": f"SELECT count(*) FROM {CAT}.information_schema.columns WHERE table_schema='{SCH}' AND table_name='val_bd' AND column_name <> '_rescued_data'",
 "DE-5": f"SELECT count(DISTINCT fecha_despacho) FROM val_bd WHERE NOT {nl('fecha_despacho')}",
 "DE-6": f"SELECT count(DISTINCT nodo_salida) FROM val_bd WHERE NOT {nl('nodo_salida')}",
 # DE Medio (calidad)
 "DE-7": f"SELECT ({Q_BD})+({Q_BI})",
 "DE-8": f"SELECT (SELECT count(*) FROM val_bd)+(SELECT count(*) FROM val_bi)-(({Q_BD})+({Q_BI}))",
 "DE-9": f"SELECT (SELECT count(*) FROM val_bd WHERE NOT(length(id_unidad) BETWEEN 5 AND 6))+(SELECT count(*) FROM val_bi WHERE NOT(length(id_unidad) BETWEEN 5 AND 6))",
 "DE-10": f"SELECT count(*) FROM val_bd WHERE {nl('modelo')}",
 "DE-11": f"SELECT (SELECT count(*) FROM val_bd WHERE {nl('remitente')})+(SELECT count(*) FROM val_bi WHERE {nl('remitente')})",
 "DE-12": f"SELECT (SELECT count(*) FROM val_bd WHERE {nl('nodo_salida')})+(SELECT count(*) FROM val_bi WHERE {nl('nodo_salida')})",
 "DE-13": "SELECT (SELECT count(*) FROM (SELECT md5(to_json(struct(*))) h FROM val_bd GROUP BY 1 HAVING count(*)>1))+(SELECT count(*) FROM (SELECT md5(to_json(struct(*))) h FROM val_bi GROUP BY 1 HAVING count(*)>1))",
 "DE-14": "SELECT (SELECT count(*) FROM (SELECT *, count(*) OVER (PARTITION BY md5(to_json(struct(*)))) nn FROM val_bd) WHERE nn>1)+(SELECT count(*) FROM (SELECT *, count(*) OVER (PARTITION BY md5(to_json(struct(*)))) nn FROM val_bi) WHERE nn>1)",
 "DE-15": f"SELECT round(100.0*((SELECT count(*) FROM val_bd)+(SELECT count(*) FROM val_bi)-(({Q_BD})+({Q_BI})))/((SELECT count(*) FROM val_bd)+(SELECT count(*) FROM val_bi)),1)",
 "DE-16": Q_BI,
 # DE Avanzado (oro)
 "DE-17": "SELECT count(*) FROM val_oro WHERE tipo_desbalance_salida='Alto >60'",
 "DE-18": "SELECT count(*) FROM val_oro WHERE tipo_tramo IS NULL",
 "DE-19": "SELECT count(*) FROM val_oro WHERE marca_otro_desbalance=1",
 "DE-20": "SELECT round(100.0*sum(desbalance_clima)/sum(desbalance_salida),1) FROM val_oro",
 "DE-21": "SELECT round(100.0*sum(otro_desbalance)/sum(desbalance_salida),1) FROM val_oro",
 "DE-22": "SELECT count(*) FROM val_oro WHERE tipo_desbalance_salida='Alto >60' AND tipo_tramo='Troncal >300Km' AND interrumpido=false",
 "DE-23": "SELECT count(*) FROM val_oro WHERE (desbalance_salida-desbalance_entrada)>20",
 "DE-24": "SELECT departamento_salida FROM val_oro GROUP BY 1 ORDER BY sum(desbalance_salida) DESC LIMIT 1 OFFSET 1",
 "DE-25": "SELECT remitente FROM val_oro GROUP BY 1 ORDER BY stddev(desbalance_salida) DESC LIMIT 1",
 "DE-26": "SELECT round(percentile(duracion_transito,0.95),1) FROM val_oro",
 "DE-27": "SELECT count(*) FROM val_oro WHERE marca_desbalance_operacional=1 AND marca_desbalance_clima=1 AND marca_desbalance_sistema=1 AND marca_desbalance_integridad=1 AND marca_desbalance_aguas_arriba=1",
 "DE-28": "SELECT round(sum(desbalance_salida)-sum(desbalance_entrada)) FROM val_oro",
 "DE-29": "SELECT mm FROM (SELECT mes_despacho mm, count(*)-lag(count(*)) OVER (ORDER BY mes_despacho) d FROM val_oro GROUP BY mes_despacho) ORDER BY d DESC NULLS LAST LIMIT 1",
 "DE-30": "SELECT count(*) FROM (SELECT id_unidad FROM val_oro WHERE tipo_desbalance_salida='Alto >60' GROUP BY 1 HAVING count(*)>=3)",
 "DE-31": "SELECT count(*) FROM (SELECT departamento_salida FROM val_oro GROUP BY 1 HAVING avg(desbalance_salida)>(SELECT avg(desbalance_salida) FROM val_oro))",
 # AE
 "AE-1": "SELECT count(*) FROM val_oro",
 "AE-2": "SELECT round(avg(desbalance_salida),1) FROM val_oro",
 "AE-3": "SELECT round(percentile(desbalance_salida,0.5),1) FROM val_oro",
 "AE-4": "SELECT round(percentile(duracion_transito,0.95),1) FROM val_oro",
 "AE-5": "SELECT round(avg(antiguedad_unidad),1) FROM val_oro",
 "AE-6": "SELECT remitente FROM val_oro GROUP BY 1 ORDER BY count(*) DESC LIMIT 1",
 "AE-7": "SELECT mes_despacho FROM val_oro GROUP BY 1 ORDER BY count(*) DESC LIMIT 1",
 "AE-8": "SELECT mes_despacho FROM val_oro GROUP BY 1 ORDER BY count(*) ASC LIMIT 1",
 "AE-9": "SELECT departamento_salida FROM val_oro GROUP BY 1 ORDER BY avg(desbalance_salida) DESC LIMIT 1",
 "AE-10": "SELECT round(100.0*sum(CASE WHEN interrumpido THEN 1 ELSE 0 END)/count(*),1) FROM val_oro",
 "AE-11": "SELECT round(100.0*sum(CASE WHEN dia_semana IN (6,7) THEN 1 ELSE 0 END)/count(*),1) FROM val_oro",
 "AE-12": "SELECT franja_horaria FROM val_oro GROUP BY 1 ORDER BY avg(desbalance_salida) DESC LIMIT 1",
 "AE-13": "SELECT remitente FROM val_oro GROUP BY 1 ORDER BY avg(CASE WHEN tipo_desbalance_salida='Alto >60' THEN 1.0 ELSE 0 END) DESC LIMIT 1",
 "AE-14": "SELECT remitente FROM val_oro GROUP BY 1 ORDER BY avg(desbalance_salida) ASC LIMIT 1",
 "AE-15": "SELECT round(100.0*max(s)/sum(s),1) FROM (SELECT departamento_salida, sum(desbalance_salida) s FROM val_oro GROUP BY 1)",
 "AE-16": "SELECT round(100.0*sum(CASE WHEN tipo_desbalance_salida='Alto >60' THEN 1 ELSE 0 END)/count(*),1) FROM val_oro",
 "AE-17": "SELECT round(100.0*(SELECT sum(n) FROM (SELECT count(*) n FROM val_oro GROUP BY remitente ORDER BY n DESC LIMIT 2))/(SELECT count(*) FROM val_oro),1)",
 "AE-18": "SELECT count(*) FROM (SELECT departamento_salida FROM val_oro GROUP BY 1 HAVING avg(desbalance_salida)>(SELECT avg(desbalance_salida) FROM val_oro))",
 "AE-19": "SELECT count(*) FROM val_oro WHERE desbalance_clima>=15",
 "AE-20": "SELECT count(*) FROM val_oro WHERE desbalance_clima>desbalance_operacional",
 "AE-21": "SELECT count(*) FROM (SELECT DISTINCT fecha_despacho, codigo_nodo_entrada FROM val_oro)",
 "AE-22": "SELECT nombre_nodo_entrada FROM val_oro GROUP BY 1 ORDER BY avg(CASE WHEN tipo_desbalance_salida='Alto >60' THEN 1.0 ELSE 0 END) DESC LIMIT 1",
 "AE-23": ("WITH d AS (SELECT fecha_despacho f, avg(desbalance_salida) a FROM val_oro WHERE nombre_nodo_entrada='Ballena (Entrada Guajira)' GROUP BY 1),"
           " h AS (SELECT f, CASE WHEN a>60 THEN 1 ELSE 0 END hi FROM d),"
           " g AS (SELECT f, hi, row_number() OVER (ORDER BY f) - row_number() OVER (PARTITION BY hi ORDER BY f) gid FROM h)"
           " SELECT max(c) FROM (SELECT count(*) c FROM g WHERE hi=1 GROUP BY gid)"),
 "AE-24": "SELECT count(*) FROM (SELECT fecha_despacho FROM val_oro GROUP BY 1 HAVING avg(desbalance_salida)>60)",
 "AE-25": "SELECT count(*) FROM (SELECT fecha FROM val_clima WHERE precipitacion>0 GROUP BY fecha HAVING count(DISTINCT id_nodo)=10)",
 "AE-26": "SELECT mm FROM (SELECT mes_despacho mm, count(*)-lag(count(*)) OVER (ORDER BY mes_despacho) d FROM val_oro GROUP BY mes_despacho) ORDER BY d DESC NULLS LAST LIMIT 1",
 "AE-27": "SELECT count(*) FROM (SELECT id_unidad FROM val_oro WHERE tipo_desbalance_salida='Alto >60' GROUP BY 1 HAVING count(*)>=3)",
 "AE-28": "SELECT count(*) FROM (SELECT id_unidad FROM val_oro GROUP BY 1 HAVING count(*)>=5)",
}

fallos, total = 0, 0
for pid, stmt in Q.items():
    p = POR_ID[pid]; total += 1
    try:
        got = scalar(stmt)
    except Exception as e:
        print(f"  ❌ {pid}: ERROR {e}"); fallos += 1; continue
    if p.tipo == "texto":
        ok = normaliza_texto(str(got)) in p.alias
    elif p.tipo == "int":
        ok = int(float(got)) == int(p.esperado)
    else:
        ok = abs(float(got) - float(p.esperado)) <= 0.05
    esp = p.esperado if p.tipo != "texto" else "/".join(p.alias)
    print(("  ✅" if ok else "  ❌") + f" {pid}: Spark={got}  esperado={esp}")
    if not ok: fallos += 1

# limpieza
for t in ["val_oro", "val_clima", "val_bd", "val_bi"]:
    sql(f"DROP TABLE IF EXISTS {t}")
sql(f"DROP VOLUME IF EXISTS {CAT}.{SCH}.{VOL}")
print(f"\n{'🎉 TODAS OK EN SPARK' if fallos==0 else f'⚠️ {fallos}/{total} DIFIEREN'}  ({total-fallos}/{total})")
raise SystemExit(1 if fallos else 0)
