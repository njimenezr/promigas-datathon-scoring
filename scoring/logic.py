"""Lógica pura de scoring del Datathon Promigas.

Sin dependencias externas: validación, puntaje, cascada de niveles y leaderboard.
Es 100% testeable sin UI ni base de datos.
"""
from __future__ import annotations
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

NIVELES = ["basico", "medio", "avanzado", "experto"]
PUNTOS_POR_NIVEL = {"basico": 10, "medio": 20, "avanzado": 30, "experto": 40}
NIVEL_LABEL = {"basico": "🟢 Básico", "medio": "🟡 Medio",
               "avanzado": "🔴 Avanzado", "experto": "🟣 Experto"}
TRACK_LABEL = {"data_engineer": "🛠️ Data Engineer",
               "analytics_engineer": "📊 Analytics Engineer"}

# Consulta de consumo de DBUs (Genie). Se corre UNA vez por track y se registra
# como evidencia (el total depende de la actividad de cada participante).
CONSULTA_DBUS = """SELECT
  usage_metadata.genie.surface    AS genie_surface,
  usage_metadata.genie.channel    AS genie_channel,
  identity_metadata.run_by         AS user_email,
  SUM(usage_quantity)             AS total_dbus,
  COUNT(*)                         AS num_records
FROM system.billing.usage
WHERE usage_metadata.genie.channel IS NOT NULL
  AND usage_date >= '2026-09-20'
GROUP BY
  usage_metadata.genie.surface,
  usage_metadata.genie.channel,
  identity_metadata.run_by
ORDER BY total_dbus DESC
LIMIT 20;"""


@dataclass
class Pregunta:
    id: str
    track: str
    nivel: str
    orden: int
    tipo: str            # "int" | "float" | "texto" | "evidencia"
    texto: str
    esperado: object = None          # int/float/None
    alias: tuple = ()                 # respuestas de texto aceptadas (normalizadas)
    decimales: int = 1
    consulta: str = ""                # SQL opcional para copiar/pegar en la app

    @property
    def puntos(self) -> int:
        return PUNTOS_POR_NIVEL[self.nivel]

    @property
    def auto(self) -> bool:
        return self.tipo in ("int", "float", "texto")


# ---------------------------------------------------------------------------
# Answer key (server-side). Verificado con DuckDB contra el dataset congelado.
# ---------------------------------------------------------------------------
def _p(*a, **k):
    return Pregunta(*a, **k)

PREGUNTAS: list[Pregunta] = [
    # ===================== DATA ENGINEER =====================
    # Básico
    _p("DE-1", "data_engineer", "basico", 1, "int", "Filas en bronce_despachos", 10980),
    _p("DE-2", "data_engineer", "basico", 2, "int", "Filas en bronce_despachos_interrumpidos", 2940),
    _p("DE-3", "data_engineer", "basico", 3, "int", "Filas en clima_por_nodo", 3650),
    _p("DE-4", "data_engineer", "basico", 4, "int", "Columnas en bronce_despachos", 25),
    _p("DE-5", "data_engineer", "basico", 5, "int", "Días distintos en fecha_despacho (válidos)", 365),
    _p("DE-6", "data_engineer", "basico", 6, "int", "Nodos de salida distintos (válidos)", 8),
    _p("DE-DBU", "data_engineer", "basico", 99, "evidencia",
       "Observabilidad de consumo: corre la consulta UNA vez y registra tus DBUs (pega tu total_dbus)",
       consulta=CONSULTA_DBUS),
    # Medio
    _p("DE-7", "data_engineer", "medio", 7, "int", "Filas en calidad_datos_cuarentena", 985),
    _p("DE-8", "data_engineer", "medio", 8, "int", "Filas válidas en plata_despachos", 12935),
    _p("DE-9", "data_engineer", "medio", 9, "int", "Fallas id_unidad_longitud_invalida (bd+bi)", 351),
    _p("DE-10", "data_engineer", "medio", 10, "int", "Fallas modelo_nulo", 131),
    _p("DE-11", "data_engineer", "medio", 11, "int", "Fallas remitente_nulo (bd+bi)", 133),
    _p("DE-12", "data_engineer", "medio", 12, "int", "Fallas nodo_salida_nulo (bd+bi)", 82),
    _p("DE-13", "data_engineer", "medio", 13, "int", "Grupos de duplicados distintos (bd+bi)", 50),
    _p("DE-14", "data_engineer", "medio", 14, "int", "Filas en cuarentena por duplicados (todas las copias)", 100),
    _p("DE-15", "data_engineer", "medio", 15, "float", "% de Bronce que pasa a Plata", 92.9),
    _p("DE-16", "data_engineer", "medio", 16, "int", "Filas de cuarentena que vienen de interrumpidos (bi)", 190),
    # Avanzado
    _p("DE-17", "data_engineer", "avanzado", 17, "int", "tipo_desbalance_salida = 'Alto >60'", 4168),
    _p("DE-18", "data_engineer", "avanzado", 18, "int", "tipo_tramo NULL", 1837),
    _p("DE-19", "data_engineer", "avanzado", 19, "int", "marca_otro_desbalance = 1", 4648),
    _p("DE-20", "data_engineer", "avanzado", 20, "float", "% desbalance atribuible a clima", 18.3),
    _p("DE-21", "data_engineer", "avanzado", 21, "float", "% desbalance NO explicado", 69.5),
    _p("DE-22", "data_engineer", "avanzado", 22, "int", "'Alto >60' en Troncal y NO interrumpidos", 1013),
    _p("DE-23", "data_engineer", "avanzado", 23, "int", "Pérdida en tránsito (salida - entrada > 20)", 7376),
    _p("DE-24", "data_engineer", "avanzado", 24, "texto", "2º departamento_salida por desbalance total",
       alias=("cor", "cordoba", "monteria")),
    _p("DE-25", "data_engineer", "avanzado", 25, "texto", "Remitente con mayor stddev(desbalance_salida)",
       alias=("gases del caribe",)),
    _p("DE-26", "data_engineer", "avanzado", 26, "float", "p95 de duracion_transito", 630.0),
    _p("DE-27", "data_engineer", "avanzado", 27, "int", "Despachos con las 5 causas marcadas a la vez", 4402),
    _p("DE-28", "data_engineer", "avanzado", 28, "int", "Desbalance neto (sum salida - sum entrada)", 361409),
    _p("DE-29", "data_engineer", "avanzado", 29, "int", "Mes con mayor crecimiento MoM de despachos", 3),
    _p("DE-30", "data_engineer", "avanzado", 30, "int", "Unidades con >=3 despachos 'Alto >60'", 89),
    _p("DE-31", "data_engineer", "avanzado", 31, "int", "Nº departamentos con desbalance prom. > media global", 3),
    # Experto
    _p("DE-32", "data_engineer", "experto", 32, "int", "Filas ingeridas a Bronce por el Job", 13920),
    _p("DE-33A", "data_engineer", "experto", 33, "int", "Metric View: desbalance_total_sistema", 675881),
    _p("DE-33B", "data_engineer", "experto", 34, "float", "Metric View: pct_no_explicado (%)", 69.5),
    _p("DE-34", "data_engineer", "experto", 35, "evidencia", "IA (ai_classify/ai_gen) sobre causa"),
    _p("DE-35", "data_engineer", "experto", 36, "evidencia", "Gobierno: tag + máscara + linaje"),

    # ===================== ANALYTICS ENGINEER =====================
    # Básico
    _p("AE-1", "analytics_engineer", "basico", 1, "int", "Total de despachos", 12935),
    _p("AE-2", "analytics_engineer", "basico", 2, "float", "avg(desbalance_salida)", 52.3),
    _p("AE-3", "analytics_engineer", "basico", 3, "float", "Mediana de desbalance_salida", 49.0),
    _p("AE-4", "analytics_engineer", "basico", 4, "float", "p95 de duracion_transito", 630.0),
    _p("AE-5", "analytics_engineer", "basico", 5, "float", "avg(antiguedad_unidad)", 14.5),
    _p("AE-6", "analytics_engineer", "basico", 6, "texto", "Remitente con más despachos",
       alias=("gases del caribe",)),
    _p("AE-DBU", "analytics_engineer", "basico", 99, "evidencia",
       "Observabilidad de consumo: corre la consulta UNA vez y registra tus DBUs (pega tu total_dbus)",
       consulta=CONSULTA_DBUS),
    # Medio
    _p("AE-7", "analytics_engineer", "medio", 7, "int", "Mes con más despachos", 7),
    _p("AE-8", "analytics_engineer", "medio", 8, "int", "Mes con menos despachos", 2),
    _p("AE-9", "analytics_engineer", "medio", 9, "texto", "departamento_salida mayor desbalance promedio",
       alias=("mag", "magdalena")),
    _p("AE-10", "analytics_engineer", "medio", 10, "float", "Tasa de interrupción (%)", 14.6),
    _p("AE-11", "analytics_engineer", "medio", 11, "float", "% despachos en fin de semana", 28.5),
    _p("AE-12", "analytics_engineer", "medio", 12, "texto", "Franja con mayor desbalance promedio",
       alias=("noche",)),
    _p("AE-13", "analytics_engineer", "medio", 13, "texto", "Remitente con mayor tasa de 'Alto >60'",
       alias=("efigas",)),
    _p("AE-14", "analytics_engineer", "medio", 14, "texto", "Remitente con menor desbalance promedio",
       alias=("gasnacer",)),
    _p("AE-15", "analytics_engineer", "medio", 15, "float", "% del desbalance total del depto #1", 24.5),
    _p("AE-16", "analytics_engineer", "medio", 16, "float", "% de despachos 'Alto >60'", 32.2),
    _p("AE-17", "analytics_engineer", "medio", 17, "float", "Cuota de los 2 remitentes con más despachos (%)", 41.0),
    _p("AE-18", "analytics_engineer", "medio", 18, "int", "Nº departamentos con desbalance prom. > media global", 3),
    # Avanzado
    _p("AE-19", "analytics_engineer", "avanzado", 19, "int", "Filas con desbalance_clima >= 15", 3355),
    _p("AE-20", "analytics_engineer", "avanzado", 20, "int", "desbalance_clima > desbalance_operacional", 6201),
    _p("AE-21", "analytics_engineer", "avanzado", 21, "int", "Filas-resumen (fecha × nodo de entrada)", 730),
    _p("AE-22", "analytics_engineer", "avanzado", 22, "texto", "Nodo de entrada con mayor tasa de 'Alto >60'",
       alias=("ballena (entrada guajira)", "ballena", "balle")),
    _p("AE-23", "analytics_engineer", "avanzado", 23, "int", "Racha máx. días consecutivos desbal.>60 en Ballena", 2),
    _p("AE-24", "analytics_engineer", "avanzado", 24, "int", "Días con desbal. prom. diario del sistema >60", 20),
    _p("AE-25", "analytics_engineer", "avanzado", 25, "int", "Días con precip.>0 en los 10 nodos a la vez", 329),
    _p("AE-26", "analytics_engineer", "avanzado", 26, "int", "Mes con mayor crecimiento MoM de despachos", 3),
    _p("AE-27", "analytics_engineer", "avanzado", 27, "int", "Unidades con >=3 despachos 'Alto >60'", 89),
    _p("AE-28", "analytics_engineer", "avanzado", 28, "int", "Unidades con >=5 despachos", 104),
    _p("AE-29", "analytics_engineer", "avanzado", 29, "int", "Días pronosticados ai_forecast (Surtigas, ene-2024)", 31),
    # Experto
    _p("AE-30", "analytics_engineer", "experto", 30, "int", "AutoML: filas de entrenamiento", 12935),
    _p("AE-30B", "analytics_engineer", "experto", 31, "evidencia", "AutoML: mejor modelo + métrica"),
    _p("AE-31A", "analytics_engineer", "experto", 32, "int", "Metric View: desbalance_total_sistema", 675881),
    _p("AE-31B", "analytics_engineer", "experto", 33, "float", "Metric View: pct_no_explicado (%)", 69.5),
    _p("AE-32", "analytics_engineer", "experto", 34, "evidencia", "Resumen ejecutivo ai_query/ai_gen"),
    _p("AE-33", "analytics_engineer", "experto", 35, "evidencia", "Gobierno: tag + alerta SQL"),
]

POR_ID = {p.id: p for p in PREGUNTAS}


def preguntas_de(track: str, nivel: str) -> list[Pregunta]:
    return sorted([p for p in PREGUNTAS if p.track == track and p.nivel == nivel],
                  key=lambda p: p.orden)


# ---------------------------------------------------------------------------
# Normalización y validación
# ---------------------------------------------------------------------------
def normaliza_texto(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")  # quita tildes
    return " ".join(s.split())  # colapsa espacios


def parse_numero(raw: str, tipo: str) -> Optional[float]:
    """Convierte texto a número tolerando separadores locales (coma decimal,
    punto/coma de miles) y sufijo %."""
    s = (raw or "").strip().replace("%", "").replace(" ", "")
    if not s:
        return None
    if tipo == "int":
        # solo dígitos y signo (elimina cualquier separador de miles)
        neg = s.startswith("-")
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None
        return -int(digits) if neg else int(digits)
    # float: manejar coma decimal europea
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")   # 1.234,5 -> 1234.5
    elif "," in s:
        s = s.replace(",", ".")                     # 92,9 -> 92.9
    try:
        return float(s)
    except ValueError:
        return None


def es_correcto(pregunta: Pregunta, raw: str) -> bool:
    if pregunta.tipo == "evidencia":
        return False  # nunca auto-correcto; lo revisa el organizador
    if pregunta.tipo == "texto":
        n = normaliza_texto(raw)
        return bool(n) and n in pregunta.alias
    val = parse_numero(raw, pregunta.tipo)
    if val is None:
        return False
    if pregunta.tipo == "int":
        return int(val) == int(pregunta.esperado)
    return abs(val - float(pregunta.esperado)) <= 0.05  # tolerancia 1 decimal


# ---------------------------------------------------------------------------
# Cascada de niveles
# ---------------------------------------------------------------------------
def nivel_completo(track: str, nivel: str, ids_correctos: set) -> bool:
    """Un nivel se completa cuando TODAS sus preguntas auto-validables están
    correctas (las de evidencia no bloquean)."""
    auto = [p.id for p in preguntas_de(track, nivel) if p.auto]
    return bool(auto) and all(pid in ids_correctos for pid in auto)


def nivel_desbloqueado(track: str, nivel: str, ids_correctos: set) -> bool:
    idx = NIVELES.index(nivel)
    if idx == 0:
        return True
    return nivel_completo(track, NIVELES[idx - 1], ids_correctos)


def progreso_track(track: str, ids_correctos: set) -> dict:
    return {n: {"desbloqueado": nivel_desbloqueado(track, n, ids_correctos),
                "completo": nivel_completo(track, n, ids_correctos),
                "correctas": sum(1 for p in preguntas_de(track, n) if p.id in ids_correctos),
                "auto_total": sum(1 for p in preguntas_de(track, n) if p.auto)}
            for n in NIVELES}


# ---------------------------------------------------------------------------
# Puntaje y leaderboard
# ---------------------------------------------------------------------------
@dataclass
class Registro:
    """Una fila de respuesta almacenada."""
    usuario: str
    pregunta: str
    correcto: bool
    puntos: int
    estado: str          # "auto" | "pendiente" | "aprobado" | "rechazado"
    ts: float            # epoch seconds


def puntos_usuario(registros: list[Registro]) -> dict:
    """Puntaje por usuario: cada pregunta cuenta UNA vez.
    Auto-validables: si tiene algún registro correcto. Evidencia: si 'aprobado'."""
    mejor: dict[tuple, tuple] = {}   # (usuario,pregunta) -> (puntos, ts)
    for r in registros:
        cuenta = r.correcto or r.estado == "aprobado"
        if not cuenta:
            continue
        key = (r.usuario, r.pregunta)
        if key not in mejor or r.ts < mejor[key][1]:
            mejor[key] = (r.puntos, r.ts)
    agg: dict[str, dict] = {}
    for (usuario, _preg), (pts, ts) in mejor.items():
        a = agg.setdefault(usuario, {"puntos": 0, "ultimo_ts": 0.0, "resueltas": 0})
        a["puntos"] += pts
        a["resueltas"] += 1
        a["ultimo_ts"] = max(a["ultimo_ts"], ts)
    return agg


def leaderboard(registros: list[Registro], track: Optional[str] = None) -> list[dict]:
    """Ranking por puntos desc, desempate por tiempo (último acierto más temprano gana)."""
    if track:
        ids = {p.id for p in PREGUNTAS if p.track == track}
        registros = [r for r in registros if r.pregunta in ids]
    agg = puntos_usuario(registros)
    filas = [{"usuario": u, **v} for u, v in agg.items()]
    filas.sort(key=lambda x: (-x["puntos"], x["ultimo_ts"]))
    for i, f in enumerate(filas, 1):
        f["puesto"] = i
    return filas
