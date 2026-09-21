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
tabs_labels = ["📝 Reto", "🏆 Leaderboard"] + (["🛠️ Organizador"] if es_org else [])
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
                if ya:
                    col2.success("✅ Resuelta")
                    continue
                if q.tipo == "evidencia":
                    # ¿pendiente?
                    pend = any(r.pregunta == q.id and r.estado == "pendiente"
                               for r in store.respuestas_usuario(usuario))
                    if pend:
                        col2.info("⏳ En revisión")
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


# ============================================================ TAB LEADERBOARD
with tabs[1]:
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


# ============================================================ TAB ORGANIZADOR
if es_org:
    with tabs[2]:
        st.header("🛠️ Revisión de evidencia")
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
