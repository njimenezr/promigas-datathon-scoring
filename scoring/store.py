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

from .logic import Registro, POR_ID

WAREHOUSE_ID = os.getenv("DBX_WAREHOUSE_ID", "")
TABLA = os.getenv("DBX_TABLA", "serverless_demo_nj_catalog.promigas_datathon.app_respuestas")


class Store:
    def __init__(self, warehouse_id: Optional[str] = None, tabla: Optional[str] = None):
        self.w = WorkspaceClient()
        self.warehouse_id = warehouse_id or WAREHOUSE_ID
        self.tabla = tabla or TABLA
        if not self.warehouse_id:
            raise ValueError("Falta DBX_WAREHOUSE_ID")

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
