"""Pruebas de la lógica de scoring (sin dependencias, sin UI)."""
import time
from scoring import logic as L

fallos = 0
def check(nombre, cond):
    global fallos
    print(("  ✅" if cond else "  ❌") + f" {nombre}")
    if not cond:
        fallos += 1

print("== Conteo de preguntas ==")
de = [p for p in L.PREGUNTAS if p.track == "data_engineer"]
ae = [p for p in L.PREGUNTAS if p.track == "analytics_engineer"]
check(f"DE tiene 37 ítems (={len(de)})", len(de) == 37)
check(f"AE tiene 36 ítems (={len(ae)})", len(ae) == 36)
check("IDs únicos", len(L.POR_ID) == len(L.PREGUNTAS))

print("\n== Validación de valores correctos ==")
check("DE-1 = 10980", L.es_correcto(L.POR_ID["DE-1"], "10980"))
check("AE-2 = 52.3", L.es_correcto(L.POR_ID["AE-2"], "52.3"))
check("DE-24 = COR (código)", L.es_correcto(L.POR_ID["DE-24"], "COR"))
check("DE-24 = Córdoba (alias con tilde)", L.es_correcto(L.POR_ID["DE-24"], "Córdoba"))
check("AE-6 = 'gases del caribe' (minúsculas)", L.es_correcto(L.POR_ID["AE-6"], "gases del caribe"))
check("AE-22 = 'Ballena' (alias corto)", L.es_correcto(L.POR_ID["AE-22"], "Ballena"))

print("\n== Trampas de formato numérico (locale CO) ==")
check("DE-28 '361.409' (punto de miles CO)", L.es_correcto(L.POR_ID["DE-28"], "361.409"))
check("DE-28 '361,409' (coma de miles)", L.es_correcto(L.POR_ID["DE-28"], "361,409"))
check("DE-28 '361409' (sin separador)", L.es_correcto(L.POR_ID["DE-28"], "361409"))
check("DE-15 '92,9' (coma decimal)", L.es_correcto(L.POR_ID["DE-15"], "92,9"))
check("DE-15 '92.9' (punto decimal)", L.es_correcto(L.POR_ID["DE-15"], "92.9"))
check("AE-10 '14.6 %' (con % y espacio)", L.es_correcto(L.POR_ID["AE-10"], "14.6 %"))
check("AE-3 '49' (49.0 sin decimal)", L.es_correcto(L.POR_ID["AE-3"], "49"))

print("\n== Respuestas incorrectas ==")
check("DE-1 = 10981 falla", not L.es_correcto(L.POR_ID["DE-1"], "10981"))
check("AE-12 = Madrugada falla (trampa promedio)", not L.es_correcto(L.POR_ID["AE-12"], "Madrugada"))
check("AE-13 = Gases del Caribe falla (trampa tasa)", not L.es_correcto(L.POR_ID["AE-13"], "Gases del Caribe"))
check("DE-15 = 93.5 fuera de tolerancia", not L.es_correcto(L.POR_ID["DE-15"], "93.5"))
check("vacío falla", not L.es_correcto(L.POR_ID["DE-1"], ""))
check("evidencia nunca auto-correcta", not L.es_correcto(L.POR_ID["DE-34"], "lo que sea"))

print("\n== Cascada de niveles ==")
correctos = set()
check("Básico DE desbloqueado de entrada", L.nivel_desbloqueado("data_engineer", "basico", correctos))
check("Medio DE BLOQUEADO sin básico", not L.nivel_desbloqueado("data_engineer", "medio", correctos))
# completar básico DE (6 preguntas auto)
for p in L.preguntas_de("data_engineer", "basico"):
    correctos.add(p.id)
check("Básico DE completo", L.nivel_completo("data_engineer", "basico", correctos))
check("Medio DE desbloqueado tras básico", L.nivel_desbloqueado("data_engineer", "medio", correctos))
check("Avanzado DE aún bloqueado", not L.nivel_desbloqueado("data_engineer", "avanzado", correctos))
check("Track AE independiente: básico AE desbloqueado", L.nivel_desbloqueado("analytics_engineer", "basico", correctos))
check("Track AE: medio AE bloqueado (no afecta DE)", not L.nivel_desbloqueado("analytics_engineer", "medio", correctos))

print("\n== Experto se completa con auto-validables (evidencia no bloquea) ==")
cor2 = set()
for niv in ["basico", "medio", "avanzado", "experto"]:
    for p in L.preguntas_de("data_engineer", niv):
        if p.auto:
            cor2.add(p.id)
check("Experto DE 'completo' solo con las 3 numéricas", L.nivel_completo("data_engineer", "experto", cor2))

print("\n== Leaderboard: puntaje y desempate por tiempo ==")
t0 = 1_000_000.0
regs = [
    # ana: básico DE completo (6×10=60), rápido
    *[L.Registro("ana", p.id, True, 10, "auto", t0 + i) for i, p in enumerate(p for p in L.preguntas_de("data_engineer", "basico") if p.auto)],
    # beto: mismo puntaje pero más lento
    *[L.Registro("beto", p.id, True, 10, "auto", t0 + 100 + i) for i, p in enumerate(p for p in L.preguntas_de("data_engineer", "basico") if p.auto)],
    # ana además una de medio (20) -> más puntos
    L.Registro("ana", "DE-7", True, 20, "auto", t0 + 50),
    # intento incorrecto no suma
    L.Registro("beto", "DE-8", False, 20, "auto", t0 + 60),
    # duplicado correcto no cuenta doble
    L.Registro("ana", "DE-1", True, 10, "auto", t0 + 5),
]
lb = L.leaderboard(regs, track="data_engineer")
check("ana 1º (80 pts)", lb[0]["usuario"] == "ana" and lb[0]["puntos"] == 80)
check("beto 2º (60 pts)", lb[1]["usuario"] == "beto" and lb[1]["puntos"] == 60)
check("ana no cuenta DE-1 dos veces (6+1 resueltas de básico+medio=7)", lb[0]["resueltas"] == 7)

# empate a puntos -> desempate por tiempo
regs_empate = [
    *[L.Registro("rapido", p.id, True, 10, "auto", t0 + i) for i, p in enumerate(p for p in L.preguntas_de("data_engineer", "basico") if p.auto)],
    *[L.Registro("lento", p.id, True, 10, "auto", t0 + 500 + i) for i, p in enumerate(p for p in L.preguntas_de("data_engineer", "basico") if p.auto)],
]
lb2 = L.leaderboard(regs_empate, track="data_engineer")
check("empate a 60: gana el más rápido", lb2[0]["usuario"] == "rapido" and lb2[1]["usuario"] == "lento")

print("\n== Evidencia: solo suma si 'aprobado' ==")
regs_ev = [
    L.Registro("ana", "DE-34", False, 40, "pendiente", t0),   # no suma
    L.Registro("beto", "DE-34", False, 40, "aprobado", t0),   # suma
]
lb3 = L.leaderboard(regs_ev, track="data_engineer")
puntos = {f["usuario"]: f["puntos"] for f in lb3}
check("evidencia pendiente NO suma (ana=0/ausente)", puntos.get("ana", 0) == 0)
check("evidencia aprobada suma 40 (beto)", puntos.get("beto") == 40)

print("\n" + ("🎉 TODAS LAS PRUEBAS PASARON" if fallos == 0 else f"⚠️  {fallos} PRUEBAS FALLARON"))
raise SystemExit(1 if fallos else 0)
