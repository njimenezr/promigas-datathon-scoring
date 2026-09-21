"""Prueba de integración de la capa de store contra un workspace real.

Uso:
  DATABRICKS_CONFIG_PROFILE=fevm-demo DBX_WAREHOUSE_ID=... DBX_TABLA=...test python test_store.py
"""
import time
from scoring.store import Store
from scoring import logic as L

fallos = 0
def check(n, c):
    global fallos
    print(("  ✅" if c else "  ❌") + f" {n}")
    if not c: fallos += 1

s = Store()
print(f"Tabla de prueba: {s.tabla}  |  warehouse: {s.warehouse_id}")

# limpiar y crear
s._exec(f"DROP TABLE IF EXISTS {s.tabla}")
s.crear_tabla()
print("✅ tabla creada")

# ana: básico DE completo (6 correctas) + 1 medio; beto: 3 correctas + 1 incorrecta
basico = L.preguntas_de("data_engineer", "basico")
for p in basico:
    s.registrar("ana@promigas.com", p.id, str(p.esperado), "conté con SQL", True, p.puntos, "auto")
s.registrar("ana@promigas.com", "DE-7", "985", "genie", True, 20, "auto")
for p in basico[:3]:
    s.registrar("beto@promigas.com", p.id, str(p.esperado), "", True, p.puntos, "auto")
s.registrar("beto@promigas.com", "DE-4", "999", "", False, 10, "auto")   # incorrecta
# evidencia pendiente de beto
s.registrar("beto@promigas.com", "DE-34", "usé ai_classify", "prompt: clasifica causa", False, 40, "pendiente")
print("✅ registros insertados")

regs = s.cargar_registros()
check("se cargaron >= 12 registros", len(regs) >= 12)

# filtrado POR USUARIO
ra = s.respuestas_usuario("ana@promigas.com")
rb = s.respuestas_usuario("beto@promigas.com")
check("filtro usuario ana (7 filas)", len(ra) == 7)
check("filtro usuario beto (5 filas)", len(rb) == 5)

# ids correctos por usuario
ca = s.ids_correctos("ana@promigas.com")
cb = s.ids_correctos("beto@promigas.com")
check("ana tiene básico DE completo", L.nivel_completo("data_engineer", "basico", ca))
check("beto NO tiene básico completo (DE-4 incorrecta)", not L.nivel_completo("data_engineer", "basico", cb))
check("ana desbloquea medio", L.nivel_desbloqueado("data_engineer", "medio", ca))
check("beto NO desbloquea medio", not L.nivel_desbloqueado("data_engineer", "medio", cb))

# leaderboard
lb = L.leaderboard(regs, track="data_engineer")
print("  leaderboard:", [(f["puesto"], f["usuario"], f["puntos"]) for f in lb])
check("ana 1º con 80 pts", lb[0]["usuario"] == "ana@promigas.com" and lb[0]["puntos"] == 80)
check("beto 2º con 30 pts (evidencia pendiente NO suma)", lb[1]["puntos"] == 30)

# aprobar evidencia de beto
pend = s.pendientes_evidencia()
check("hay 1 evidencia pendiente", len(pend) == 1)
s.actualizar_estado(pend[0]["id"], "aprobado")
regs2 = s.cargar_registros()
lb2 = L.leaderboard(regs2, track="data_engineer")
beto2 = next(f for f in lb2 if f["usuario"] == "beto@promigas.com")
check("tras aprobar evidencia, beto suma +40 (=70)", beto2["puntos"] == 70)

# limpiar
s._exec(f"DROP TABLE IF EXISTS {s.tabla}")
print("✅ tabla de prueba eliminada")
print("\n" + ("🎉 STORE OK" if fallos == 0 else f"⚠️ {fallos} FALLARON"))
raise SystemExit(1 if fallos else 0)
