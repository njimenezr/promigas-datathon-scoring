"""Datathon Promigas — App de Scoring (Streamlit / Databricks Apps).

- Identifica al usuario por el header X-Forwarded-Email (auto en Databricks Apps).
- Guarda respuestas en una tabla Delta compartida.
- Niveles en cascada por track, leaderboard por velocidad, revisión de evidencia.
"""
import os
import streamlit as st

from scoring import logic as L
from scoring.store import Store

st.set_page_config(page_title="Datathon Promigas — Scoring", page_icon="⛽", layout="wide")


# --------------------------------------------------------------------------- identidad
def usuario_actual() -> str:
    dev = os.getenv("DEV_USUARIO")
    if dev:
        return dev
    try:
        h = st.context.headers
        return (h.get("X-Forwarded-Email") or h.get("X-Forwarded-Preferred-Username")
                or "anónimo")
    except Exception:
        return "anónimo"


ORGANIZADORES = {e.strip().lower() for e in os.getenv("ORGANIZADORES", "").split(",") if e.strip()}


@st.cache_resource
def get_store():
    s = Store()
    s.crear_tabla()
    return s


usuario = usuario_actual()
try:
    store = get_store()
except ValueError as e:
    # Error de configuración (p. ej. falta DBX_TABLA / DBX_WAREHOUSE_ID)
    st.error(f"⚙️ Falta configurar la app: {e}")
    st.info("Edita **`app.yaml`** y define `DBX_TABLA` con tu `catalogo.esquema.tabla` "
            "(y `DBX_WAREHOUSE_ID` con tu SQL Warehouse). Luego vuelve a desplegar.")
    st.stop()
except Exception as e:
    st.error(f"No se pudo conectar al almacenamiento: {e}")
    st.stop()


# --------------------------------------------------------------------------- sidebar
st.sidebar.title("⛽ Datathon Promigas")
st.sidebar.caption("Formación · Plataforma de inteligencia de transporte de gas")
st.sidebar.markdown(f"**Participante:**\n\n`{usuario}`")

track = st.sidebar.radio(
    "Elige tu track",
    options=["data_engineer", "analytics_engineer"],
    format_func=lambda t: L.TRACK_LABEL[t],
)

ids_ok = store.ids_correctos(usuario)
prog = L.progreso_track(track, ids_ok)
pts_track = sum(L.POR_ID[i].puntos for i in ids_ok if L.POR_ID[i].track == track)
st.sidebar.metric("Tus puntos en este track", pts_track)

st.sidebar.markdown("### Progreso")
for niv in L.NIVELES:
    p = prog[niv]
    icono = "🔒" if not p["desbloqueado"] else ("✅" if p["completo"] else "▶️")
    st.sidebar.write(f"{icono} {L.NIVEL_LABEL[niv]} — {p['correctas']}/{p['auto_total']}")


# --------------------------------------------------------------------------- tabs
es_org = usuario.lower() in ORGANIZADORES
tabs_labels = ["📝 Reto", "💡 Caso del millón", "🏆 Leaderboard"] + (
    ["🛠️ Organizador / Jurado"] if es_org else [])
tabs = st.tabs(tabs_labels)


# ============================================================ TAB RETO
with tabs[0]:
    st.header(L.TRACK_LABEL[track])
    st.caption("Pega el **valor calculado** y, si usaste IA, el **prompt**. "
               "Los niveles se desbloquean en cascada.")

    for niv in L.NIVELES:
        p = prog[niv]
        estado = "🔒 Bloqueado" if not p["desbloqueado"] else (
            "✅ Completo" if p["completo"] else f"{p['correctas']}/{p['auto_total']}")
        with st.expander(f"{L.NIVEL_LABEL[niv]} — {L.PUNTOS_POR_NIVEL[niv]} pts/pregunta  ·  {estado}",
                         expanded=p["desbloqueado"] and not p["completo"]):
            if not p["desbloqueado"]:
                st.info("Completa el nivel anterior para desbloquear este.")
                continue
            for q in L.preguntas_de(track, niv):
                ya = q.id in ids_ok
                col1, col2 = st.columns([3, 1])
                col1.markdown(f"**{q.id}.** {q.texto}")
                if q.consulta:
                    col1.caption("Copia y pega esta consulta en un editor SQL, córrela una vez y registra tu total de DBUs:")
                    col1.code(q.consulta, language="sql")
                if ya:
                    col2.success("✅ Resuelta")
                    continue
                if q.tipo == "evidencia":
                    # ¿pendiente?
                    pend = any(r.pregunta == q.id and r.estado == "pendiente"
                               for r in store.respuestas_usuario(usuario))
                    if pend:
                        col2.info("⏳ En revisión")
                        if col2.button("↩️ Rehacer", key=f"redo_{q.id}",
                                       help="Elimina tu envío en revisión y habilita "
                                            "de nuevo el formulario para reenviarlo"):
                            store.eliminar_pendiente(usuario, q.id)
                            st.rerun()
                        continue
                with st.form(f"form_{q.id}", clear_on_submit=True):
                    if q.tipo == "evidencia":
                        valor = st.text_input("Tu resultado / descripción", key=f"v_{q.id}")
                        prompt = st.text_area("Prompt usado (y describe tu evidencia)", key=f"p_{q.id}")
                        etiqueta = "Enviar para revisión"
                    else:
                        valor = st.text_input("Valor calculado", key=f"v_{q.id}")
                        prompt = st.text_area("Prompt de IA (opcional)", key=f"p_{q.id}")
                        etiqueta = "Enviar respuesta"
                    enviado = st.form_submit_button(etiqueta)
                if enviado:
                    if not valor.strip():
                        st.warning("Escribe un valor.")
                    elif q.tipo == "evidencia":
                        store.registrar(usuario, q.id, valor, prompt, False, q.puntos, "pendiente")
                        st.success("Enviado para revisión del organizador.")
                        st.rerun()
                    else:
                        ok = L.es_correcto(q, valor)
                        store.registrar(usuario, q.id, valor, prompt, ok, q.puntos,
                                        "auto")
                        if ok:
                            st.success(f"¡Correcto! +{q.puntos} pts 🎉")
                        else:
                            st.error("No es el valor esperado. Revisa la definición e inténtalo de nuevo.")
                        st.rerun()


# ============================================================ TAB CASO DEL MILLÓN
with tabs[1]:
    st.header("💡 El caso del millón de dólares")
    st.caption("Por **equipos**: registren **un** caso de uso de datos + IA con mucho "
               "revenue, impacto o valor para **varias empresas del Grupo Promigas**. "
               "El '$1M' es una metáfora — lo importante es el tamaño del valor.")

    PALANCAS = ["Nuevo revenue", "Ahorro de costos", "Riesgo evitado", "Eficiencia operativa"]

    with st.form("form_caso", clear_on_submit=False):
        c1, c2 = st.columns(2)
        equipo = c1.text_input("Nombre del equipo *")
        area = c2.text_input("Área(s) de la compañía")
        integrantes = st.text_area("Integrantes (una persona por línea)",
                                   help="Nombres o correos, uno por línea")
        nombre_caso = st.text_input("Nombre del caso (pegajoso) *")
        problema = st.text_area("Problema / oportunidad (1–2 frases) *")
        empresas = st.text_input("Empresas del grupo impactadas",
                                 help="Ej: Promigas, Gases del Caribe, Surtigas, Efigas, Brilla, Cálidda…")
        palanca = st.multiselect("Palanca de valor", PALANCAS)
        millon = st.text_area("El 'millón': ¿cómo estiman el valor? (su supuesto) *")
        databricks_ia = st.text_area("Rol de Databricks + IA en la solución *")
        link = st.text_input("Link a la presentación (opcional)")
        guardar = st.form_submit_button("💾 Registrar / actualizar caso de mi equipo")

    if guardar:
        faltan = [n for n, v in [("equipo", equipo), ("nombre del caso", nombre_caso),
                                 ("problema", problema), ("el millón", millon),
                                 ("rol de Databricks+IA", databricks_ia)] if not v.strip()]
        if faltan:
            st.warning("Faltan campos obligatorios: " + ", ".join(faltan))
        else:
            store.guardar_caso({
                "equipo": equipo, "area": area, "integrantes": integrantes,
                "nombre_caso": nombre_caso, "problema": problema, "empresas": empresas,
                "palanca": ", ".join(palanca), "millon": millon,
                "databricks_ia": databricks_ia, "link": link,
            }, usuario)
            st.success(f"Caso de **{equipo}** registrado. Pueden volver y actualizarlo cuando quieran.")
            st.rerun()

    st.divider()
    st.subheader("Casos registrados")
    casos = store.listar_casos()
    if not casos:
        st.write("_Aún no hay casos registrados._")
    for c in casos:
        with st.container(border=True):
            st.markdown(f"**{c['nombre_caso']}** · equipo `{c['equipo']}`"
                        + (f" · {c['area']}" if c['area'] else ""))
            if c["palanca"]:
                st.caption(f"Palanca: {c['palanca']}  ·  Empresas: {c['empresas'] or '—'}")
            st.write(c["problema"])


# ============================================================ TAB LEADERBOARD
with tabs[2]:
    st.header("🏆 Leaderboard")
    st.caption("Ranking por puntos. Desempate por **velocidad** (quien llega antes, arriba).")
    regs = store.cargar_registros()
    for t in ["data_engineer", "analytics_engineer"]:
        st.subheader(L.TRACK_LABEL[t])
        lb = L.leaderboard(regs, track=t)
        if not lb:
            st.write("_Sin participantes aún._")
            continue
        st.dataframe(
            [{"Puesto": f["puesto"], "Participante": f["usuario"],
              "Puntos": f["puntos"], "Resueltas": f["resueltas"]} for f in lb],
            hide_index=True, use_container_width=True)


# ============================================================ TAB ORGANIZADOR / JURADO
if es_org:
    with tabs[3]:
        o_tabs = st.tabs(["📥 Evidencia", "🎤 Calificar A", "💡 Votar casos B", "🏁 Rankings"])

        # ---------- datos compartidos
        regs = store.cargar_registros()
        dbus = store.dbu_por_usuario()
        lb_de = {f["usuario"]: f["puntos"] for f in L.leaderboard(regs, track="data_engineer")}
        lb_ae = {f["usuario"]: f["puntos"] for f in L.leaderboard(regs, track="analytics_engineer")}
        participantes = sorted(set(lb_de) | set(lb_ae) | set(dbus))

        def _track_y_puntos(u):
            pde, pae = lb_de.get(u, 0), lb_ae.get(u, 0)
            return ("data_engineer", pde) if pde >= pae else ("analytics_engineer", pae)

        # ---------- Evidencia
        with o_tabs[0]:
            st.subheader("Revisión de evidencia")
            pend = store.pendientes_evidencia()
            if not pend:
                st.success("No hay evidencias pendientes. 🎉")
            for e in pend:
                q = L.POR_ID.get(e["pregunta"])
                with st.container(border=True):
                    st.markdown(f"**{e['pregunta']}** · `{e['usuario']}` · {q.texto if q else ''}")
                    st.write(f"**Resultado:** {e['valor']}")
                    st.write(f"**Prompt/evidencia:** {e['prompt']}")
                    c1, c2, _ = st.columns([1, 1, 4])
                    if c1.button("✅ Aprobar", key=f"ap_{e['id']}"):
                        store.actualizar_estado(e["id"], "aprobado")
                        st.rerun()
                    if c2.button("❌ Rechazar", key=f"re_{e['id']}"):
                        store.actualizar_estado(e["id"], "rechazado")
                        st.rerun()

        # ---------- Calificar presentación A
        with o_tabs[1]:
            st.subheader("Calificar presentación individual (A)")
            st.caption(f"Calificas como **{usuario}**. Escala 1–5 por dimensión. "
                       "El puntaje del datathon y los DBUs son automáticos.")
            if not participantes:
                st.info("Aún no hay participantes con actividad.")
            else:
                sel = st.selectbox("Participante", participantes, key="calif_sel")
                track, pts = _track_y_puntos(sel)
                st.caption(f"Track: {L.TRACK_LABEL[track]} · Datathon: {pts}/{L.max_puntos_track(track)} "
                           f"· DBUs Genie: {dbus.get(sel, '—')}")
                previo = next((r for r in store.calif_a()
                               if r["participante"] == sel and r["juez"] == usuario), {})
                with st.form(f"calif_{sel}"):
                    vals = {}
                    for dim in L.DIMS_JUEZ_A:
                        vals[dim] = st.slider(L.DIM_A_LABEL[dim], 1, 5,
                                              int(previo.get(dim, 3)), key=f"sl_{dim}_{sel}")
                    if st.form_submit_button("💾 Guardar calificación"):
                        store.guardar_calif_a(sel, usuario, vals)
                        st.success("Calificación guardada.")
                        st.rerun()

        # ---------- Votar casos B
        with o_tabs[2]:
            st.subheader("Votar casos del millón (B)")
            st.caption(f"Votas como **{usuario}**. Escala 1–5 por criterio.")
            casos = store.listar_casos()
            votos_all = store.votos_b()
            if not casos:
                st.info("Aún no hay casos registrados.")
            for c in casos:
                previo = next((r for r in votos_all
                               if r["equipo"] == c["equipo"] and r["juez"] == usuario), {})
                with st.expander(f"{c['nombre_caso']} — equipo {c['equipo']}"):
                    st.write(c["problema"])
                    st.caption(f"Palanca: {c['palanca'] or '—'} · Empresas: {c['empresas'] or '—'}")
                    if c["millon"]:
                        st.write(f"**El millón:** {c['millon']}")
                    if c["databricks_ia"]:
                        st.write(f"**Databricks + IA:** {c['databricks_ia']}")
                    if c["link"]:
                        st.write(f"[Presentación]({c['link']})")
                    with st.form(f"voto_{c['equipo']}"):
                        vals = {}
                        for cri in L.CRITERIOS_B:
                            vals[cri] = st.slider(L.CRIT_B_LABEL[cri], 1, 5,
                                                  int(previo.get(cri, 3)), key=f"vb_{cri}_{c['equipo']}")
                        if st.form_submit_button("💾 Guardar voto"):
                            store.guardar_voto_b(c["equipo"], usuario, vals)
                            st.success("Voto guardado.")
                            st.rerun()

        # ---------- Rankings
        with o_tabs[3]:
            st.subheader("🏁 Ranking final — Individual (A)")
            jur = {}
            for r in store.calif_a():
                d = jur.setdefault(r["participante"], {dim: [] for dim in L.DIMS_JUEZ_A})
                for dim in L.DIMS_JUEZ_A:
                    d[dim].append(r[dim])
            dbus_todos = list(dbus.values())
            filas_a = []
            for u in participantes:
                track, pts = _track_y_puntos(u)
                res = L.score_a(track, pts, dbus.get(u), dbus_todos, jur.get(u, {}))
                comp = res["componentes"]
                filas_a.append({
                    "Participante": u, "Track": L.TRACK_LABEL[track],
                    "Total": round(res["total"], 1),
                    "Datathon": round(comp["datathon"]), "DBUs": round(comp["dbu"]),
                    "Arq": round(comp["arquitectura"]), "IA": round(comp["ia"]),
                    "Valor": round(comp["valor"]), "Com": round(comp["comunicacion"]),
                })
            filas_a.sort(key=lambda x: -x["Total"])
            if filas_a:
                st.dataframe([{"#": i, **f} for i, f in enumerate(filas_a, 1)],
                             hide_index=True, use_container_width=True)
                st.caption("Componentes en 0–100 (sin ponderar). Total ya ponderado: "
                           "Datathon 25% · DBUs 10% · Arq 20% · IA 15% · Valor 20% · Com 10%.")
            else:
                st.write("_Sin datos aún._")

            st.divider()
            st.subheader("🏁 Ranking — Casos del millón (B)")
            by_eq = {}
            for r in store.votos_b():
                d = by_eq.setdefault(r["equipo"], {cri: [] for cri in L.CRITERIOS_B})
                for cri in L.CRITERIOS_B:
                    d[cri].append(r[cri])
            filas_b = [{"Equipo": c["equipo"], "Caso": c["nombre_caso"],
                        "Puntaje": round(L.score_caso_b(by_eq.get(c["equipo"], {})), 1)}
                       for c in store.listar_casos()]
            filas_b.sort(key=lambda x: -x["Puntaje"])
            if filas_b:
                st.dataframe([{"#": i, **f} for i, f in enumerate(filas_b, 1)],
                             hide_index=True, use_container_width=True)
            else:
                st.write("_Sin casos/votos aún._")
