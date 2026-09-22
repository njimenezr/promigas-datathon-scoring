"""Capa de almacenamiento: tabla Delta compartida vía el SDK de Databricks.

Funciona dentro de una Databricks App (autenticación automática del service
principal) y en local (perfil CLI, vía DATABRICKS_CONFIG_PROFILE).
"""
from __future__ import annotations
import os
import time
import uuid
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

from .logic import Registro, POR_ID, parse_numero, CAMPOS_CASO, DIMS_JUEZ_A, CRITERIOS_B

WAREHOUSE_ID = os.getenv("DBX_WAREHOUSE_ID", "")
TABLA = os.getenv("DBX_TABLA", "")


def _tabla_sin_configurar(t: str) -> bool:
    """True si la tabla no está configurada o sigue con el placeholder de app.yaml."""
    return (not t) or ("REEMPLAZAR" in t.upper())


class Store:
    def __init__(self, warehouse_id: Optional[str] = None, tabla: Optional[str] = None):
        self.w = WorkspaceClient()
        self.warehouse_id = warehouse_id or WAREHOUSE_ID
        self.tabla = tabla or TABLA
        if not self.warehouse_id:
            raise ValueError("Falta DBX_WAREHOUSE_ID")
        if _tabla_sin_configurar(self.tabla):
            raise ValueError(
                "Falta DBX_TABLA: configura tu tabla (catalogo.esquema.tabla) "
                "en app.yaml antes de desplegar.")
        # Tablas hermanas (mismo catálogo.esquema) para casos y calificaciones.
        base = self.tabla.rsplit(".", 1)[0]
        self.tabla_casos = f"{base}.app_casos"
        self.tabla_calif_a = f"{base}.app_calif_a"
        self.tabla_votos_b = f"{base}.app_votos_b"

    # ------------------------------------------------------------------
    def _exec(self, statement: str, params: Optional[list] = None):
        r = self.w.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            statement=statement,
            parameters=params or [],
            wait_timeout="30s",
        )
        # Poll si sigue en ejecución
        import time as _t
        while r.status and r.status.state and r.status.state.value in ("PENDING", "RUNNING"):
            _t.sleep(1)
            r = self.w.statement_execution.get_statement(r.statement_id)
        if r.status and r.status.state and r.status.state.value == "FAILED":
            raise RuntimeError(r.status.error.message if r.status.error else "SQL FAILED")
        return r

    @staticmethod
    def _s(name, value):
        return StatementParameterListItem(name=name, value=None if value is None else str(value))

    # ------------------------------------------------------------------
    def crear_tabla(self):
        self._exec(f"""
            CREATE TABLE IF NOT EXISTS {self.tabla} (
                id STRING, usuario STRING, track STRING, nivel STRING, pregunta STRING,
                valor STRING, prompt STRING, correcto BOOLEAN, puntos INT,
                estado STRING, ts DOUBLE
            ) USING DELTA
        """)
        # Caso del millón (uno por equipo)
        self._exec(f"""
            CREATE TABLE IF NOT EXISTS {self.tabla_casos} (
                id STRING, equipo STRING, area STRING, integrantes STRING,
                nombre_caso STRING, problema STRING, empresas STRING, palanca STRING,
                millon STRING, databricks_ia STRING, link STRING,
                creado_por STRING, ts DOUBLE
            ) USING DELTA
        """)
        # Calificación de la presentación A (una fila por participante × juez)
        self._exec(f"""
            CREATE TABLE IF NOT EXISTS {self.tabla_calif_a} (
                id STRING, participante STRING, juez STRING,
                arquitectura INT, ia INT, valor INT, comunicacion INT, ts DOUBLE
            ) USING DELTA
        """)
        # Voto del jurado a los casos B (una fila por equipo × juez)
        self._exec(f"""
            CREATE TABLE IF NOT EXISTS {self.tabla_votos_b} (
                id STRING, equipo STRING, juez STRING,
                cuantificable INT, cross_company INT, factible INT, databricks_ia INT, ts DOUBLE
            ) USING DELTA
        """)

    def registrar(self, usuario, pregunta_id, valor, prompt, correcto, puntos, estado):
        p = POR_ID[pregunta_id]
        self._exec(
            f"""INSERT INTO {self.tabla}
                (id, usuario, track, nivel, pregunta, valor, prompt, correcto, puntos, estado, ts)
                VALUES (:id, :usuario, :track, :nivel, :pregunta, :valor, :prompt,
                        CAST(:correcto AS BOOLEAN), CAST(:puntos AS INT), :estado, CAST(:ts AS DOUBLE))""",
            [
                self._s("id", uuid.uuid4().hex),
                self._s("usuario", usuario),
                self._s("track", p.track),
                self._s("nivel", p.nivel),
                self._s("pregunta", pregunta_id),
                self._s("valor", valor),
                self._s("prompt", prompt or ""),
                self._s("correcto", "true" if correcto else "false"),
                self._s("puntos", puntos),
                self._s("estado", estado),
                self._s("ts", time.time()),
            ],
        )

    def _filas(self, statement, params=None):
        r = self._exec(statement, params)
        if not r.result or not r.result.data_array:
            return []
        return r.result.data_array

    def cargar_registros(self) -> list[Registro]:
        filas = self._filas(
            f"SELECT usuario, pregunta, correcto, puntos, estado, ts FROM {self.tabla}")
        out = []
        for usuario, pregunta, correcto, puntos, estado, ts in filas:
            out.append(Registro(
                usuario=usuario, pregunta=pregunta,
                correcto=str(correcto).lower() == "true",
                puntos=int(puntos), estado=estado, ts=float(ts)))
        return out

    def respuestas_usuario(self, usuario: str) -> list[Registro]:
        """Filtrado POR USUARIO (server-side)."""
        filas = self._filas(
            f"SELECT usuario, pregunta, correcto, puntos, estado, ts FROM {self.tabla} WHERE usuario = :u",
            [self._s("u", usuario)])
        out = []
        for u, pregunta, correcto, puntos, estado, ts in filas:
            out.append(Registro(usuario=u, pregunta=pregunta,
                                 correcto=str(correcto).lower() == "true",
                                 puntos=int(puntos), estado=estado, ts=float(ts)))
        return out

    def ids_correctos(self, usuario: str) -> set:
        """IDs de preguntas que el usuario ya tiene correctas o con evidencia aprobada."""
        filas = self._filas(
            f"""SELECT DISTINCT pregunta FROM {self.tabla}
                WHERE usuario = :u AND (correcto = true OR estado = 'aprobado')""",
            [self._s("u", usuario)])
        return {f[0] for f in filas}

    def pendientes_evidencia(self) -> list[dict]:
        filas = self._filas(
            f"""SELECT id, usuario, pregunta, valor, prompt, ts FROM {self.tabla}
                WHERE estado = 'pendiente' ORDER BY ts""")
        return [{"id": i, "usuario": u, "pregunta": p, "valor": v, "prompt": pr, "ts": float(t)}
                for i, u, p, v, pr, t in filas]

    def actualizar_estado(self, registro_id: str, estado: str):
        self._exec(f"UPDATE {self.tabla} SET estado = :e WHERE id = :id",
                   [self._s("e", estado), self._s("id", registro_id)])

    def eliminar_pendiente(self, usuario: str, pregunta_id: str):
        """Borra el envío de evidencia en revisión de un usuario para una pregunta,
        para que pueda devolverse y reenviar uno nuevo."""
        self._exec(
            f"""DELETE FROM {self.tabla}
                WHERE usuario = :u AND pregunta = :q AND estado = 'pendiente'""",
            [self._s("u", usuario), self._s("q", pregunta_id)])

    # ------------------------------------------------------------------ DBUs
    def dbu_por_usuario(self) -> dict:
        """{usuario: dbus} a partir del valor registrado en la pregunta de DBUs
        (DE-DBU/AE-DBU). Toma el último registro por usuario. Alimenta el score A."""
        filas = self._filas(
            f"""SELECT usuario, valor, ts FROM {self.tabla}
                WHERE pregunta IN ('DE-DBU', 'AE-DBU')""")
        ultimo: dict[str, tuple] = {}   # usuario -> (ts, valor)
        for usuario, valor, ts in filas:
            t = float(ts)
            if usuario not in ultimo or t > ultimo[usuario][0]:
                ultimo[usuario] = (t, valor)
        out = {}
        for usuario, (_t, valor) in ultimo.items():
            n = parse_numero(valor, "float")
            if n is not None:
                out[usuario] = n
        return out

    # ------------------------------------------------------------------ Casos (B)
    def guardar_caso(self, datos: dict, creado_por: str):
        """Upsert por equipo: 1 caso por equipo. `datos` con las claves de CAMPOS_CASO."""
        equipo = (datos.get("equipo") or "").strip()
        self._exec(f"DELETE FROM {self.tabla_casos} WHERE equipo = :e",
                   [self._s("e", equipo)])
        cols = CAMPOS_CASO  # equipo, area, integrantes, ...
        placeholders = ", ".join(f":{c}" for c in cols)
        params = [self._s(c, datos.get(c, "")) for c in cols]
        self._exec(
            f"""INSERT INTO {self.tabla_casos}
                (id, {", ".join(cols)}, creado_por, ts)
                VALUES (:id, {placeholders}, :cb, CAST(:ts AS DOUBLE))""",
            [self._s("id", uuid.uuid4().hex), *params,
             self._s("cb", creado_por), self._s("ts", time.time())])

    def listar_casos(self) -> list[dict]:
        cols = ["id", *CAMPOS_CASO, "creado_por", "ts"]
        filas = self._filas(
            f"SELECT {', '.join(cols)} FROM {self.tabla_casos} ORDER BY equipo")
        return [dict(zip(cols, f)) for f in filas]

    def eliminar_caso(self, equipo: str):
        self._exec(f"DELETE FROM {self.tabla_casos} WHERE equipo = :e",
                   [self._s("e", equipo)])

    # ------------------------------------------------------------------ Calificación A (jurado)
    def guardar_calif_a(self, participante: str, juez: str, scores: dict):
        """Upsert de la calificación de un juez a un participante (dims 1-5)."""
        self._exec(
            f"DELETE FROM {self.tabla_calif_a} WHERE participante = :p AND juez = :j",
            [self._s("p", participante), self._s("j", juez)])
        self._exec(
            f"""INSERT INTO {self.tabla_calif_a}
                (id, participante, juez, arquitectura, ia, valor, comunicacion, ts)
                VALUES (:id, :p, :j, CAST(:a AS INT), CAST(:i AS INT),
                        CAST(:v AS INT), CAST(:c AS INT), CAST(:ts AS DOUBLE))""",
            [self._s("id", uuid.uuid4().hex), self._s("p", participante), self._s("j", juez),
             self._s("a", scores.get("arquitectura", 0)), self._s("i", scores.get("ia", 0)),
             self._s("v", scores.get("valor", 0)), self._s("c", scores.get("comunicacion", 0)),
             self._s("ts", time.time())])

    def calif_a(self) -> list[dict]:
        cols = ["participante", "juez", *DIMS_JUEZ_A]
        filas = self._filas(
            f"SELECT participante, juez, arquitectura, ia, valor, comunicacion FROM {self.tabla_calif_a}")
        return [dict(zip(cols, [f[0], f[1], int(f[2]), int(f[3]), int(f[4]), int(f[5])])) for f in filas]

    # ------------------------------------------------------------------ Votos B (jurado)
    def guardar_voto_b(self, equipo: str, juez: str, scores: dict):
        """Upsert del voto de un juez a un caso (criterios 1-5)."""
        self._exec(
            f"DELETE FROM {self.tabla_votos_b} WHERE equipo = :e AND juez = :j",
            [self._s("e", equipo), self._s("j", juez)])
        self._exec(
            f"""INSERT INTO {self.tabla_votos_b}
                (id, equipo, juez, cuantificable, cross_company, factible, databricks_ia, ts)
                VALUES (:id, :e, :j, CAST(:q AS INT), CAST(:x AS INT),
                        CAST(:f AS INT), CAST(:d AS INT), CAST(:ts AS DOUBLE))""",
            [self._s("id", uuid.uuid4().hex), self._s("e", equipo), self._s("j", juez),
             self._s("q", scores.get("cuantificable", 0)), self._s("x", scores.get("cross_company", 0)),
             self._s("f", scores.get("factible", 0)), self._s("d", scores.get("databricks_ia", 0)),
             self._s("ts", time.time())])

    def votos_b(self) -> list[dict]:
        cols = ["equipo", "juez", *CRITERIOS_B]
        filas = self._filas(
            f"SELECT equipo, juez, cuantificable, cross_company, factible, databricks_ia FROM {self.tabla_votos_b}")
        return [dict(zip(cols, [f[0], f[1], int(f[2]), int(f[3]), int(f[4]), int(f[5])])) for f in filas]
