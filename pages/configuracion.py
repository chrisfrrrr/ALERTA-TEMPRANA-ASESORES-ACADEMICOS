from __future__ import annotations

from pathlib import Path

import streamlit as st

from components.ui import page_header
from models.config import RiskConfig
from services.database_service import DatabaseError
from services.runtime import get_database
from utils.data_cleaning import load_wellbeing_csv


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "data" / "bienestar_base.csv"

page_header(
    "Configuración y administración",
    "Ajuste límites institucionales, valide conexiones y sincronice la asignación de estudiantes con asesores de bienestar.",
)

db_global = get_database()
if not st.session_state.get("risk_config_loaded", False):
    stored_config = db_global.load_risk_config() if db_global.connected else None
    if stored_config:
        st.session_state.risk_config = RiskConfig.from_dict(stored_config).as_dict()
    st.session_state.risk_config_loaded = True

config = RiskConfig.from_dict(st.session_state.get("risk_config"))

rules_tab, database_tab, diagnostics_tab = st.tabs(["Reglas de riesgo", "Supabase y bienestar", "Diagnóstico"])

with rules_tab:
    st.info("Los cursos se analizan en cinco semanas. Los límites pueden ajustarse sin modificar el código.")
    with st.form("risk_rules"):
        st.markdown("#### Cumplimiento de actividades")
        a1, a2 = st.columns(2)
        activity_low = a1.number_input("Bajo desde (%)", 0.0, 100.0, config.activity_low_min, 1.0)
        activity_moderate = a2.number_input("Moderado desde (%)", 0.0, 100.0, config.activity_moderate_min, 1.0)

        st.markdown("#### Calificaciones")
        g1, g2 = st.columns(2)
        grade_low = g1.number_input("Bajo desde (%) ", 0.0, 100.0, config.grade_low_min, 1.0)
        grade_moderate = g2.number_input("Moderado desde (%) ", 0.0, 100.0, config.grade_moderate_min, 1.0)

        st.markdown("#### Actividad en Canvas")
        c1, c2, c3, c4 = st.columns(4)
        access_low = c1.number_input("Ingresos para bajo", 1, 20, config.access_low_min)
        access_moderate = c2.number_input("Ingresos mínimos moderado", 0, 20, config.access_moderate_min)
        inactivity_moderate = c3.number_input("Inactividad moderada (h)", 1.0, 500.0, config.inactivity_moderate_hours)
        inactivity_high = c4.number_input("Inactividad alta (h)", 1.0, 500.0, config.inactivity_high_hours)

        st.markdown("#### Comunicación y derivaciones")
        r1, r2, r3, r4 = st.columns(4)
        response_low = r1.number_input("Respuesta baja (h)", 1.0, 500.0, config.response_low_hours)
        response_moderate = r2.number_input("Respuesta moderada (h)", 1.0, 500.0, config.response_moderate_hours)
        response_high = r3.number_input("Sin respuesta alta (h)", 1.0, 500.0, config.response_high_hours)
        cooldown = r4.number_input("Espera entre derivaciones (días)", 1, 120, config.referral_cooldown_days)

        submitted = st.form_submit_button("Guardar reglas", type="primary")
        if submitted:
            new_config = RiskConfig(
                course_weeks=5,
                activity_low_min=activity_low,
                activity_moderate_min=activity_moderate,
                grade_low_min=grade_low,
                grade_moderate_min=grade_moderate,
                access_low_min=access_low,
                access_moderate_min=access_moderate,
                inactivity_moderate_hours=inactivity_moderate,
                inactivity_high_hours=inactivity_high,
                response_low_hours=response_low,
                response_moderate_hours=response_moderate,
                response_high_hours=response_high,
                referral_cooldown_days=cooldown,
            )
            st.session_state.risk_config = new_config.as_dict()
            if db_global.connected:
                try:
                    db_global.save_risk_config(new_config.as_dict())
                except DatabaseError as exc:
                    st.warning(f"Las reglas se aplicaron en la sesión, pero no se guardaron en Supabase: {exc}")
            st.success("Reglas actualizadas para los próximos análisis.")

with database_tab:
    db = get_database()
    wellbeing = load_wellbeing_csv(BASE_PATH)
    st.markdown("#### Base de asignación de bienestar")
    m1, m2, m3 = st.columns(3)
    m1.metric("Estudiantes válidos", len(wellbeing))
    m2.metric("Asesores", wellbeing["asesor_bienestar"].nunique())
    m3.metric("Sin asignar", int((wellbeing["asesor_bienestar"] == "Sin asignar").sum()))
    st.dataframe(
        wellbeing.groupby("asesor_bienestar").size().reset_index(name="Estudiantes"),
        width="stretch",
        hide_index=True,
    )

    uploaded = st.file_uploader("Actualizar base de bienestar (CSV)", type=["csv"])
    if uploaded is not None:
        try:
            uploaded_df = load_wellbeing_csv(uploaded)
            st.success(f"Archivo válido: {len(uploaded_df)} estudiantes.")
            st.dataframe(uploaded_df.head(20), width="stretch", hide_index=True)
            if st.button("Guardar como nueva base local"):
                uploaded_df.to_csv(BASE_PATH, index=False, encoding="utf-8-sig")
                st.success("Base local actualizada.")
        except ValueError as exc:
            st.error(str(exc))

    st.markdown("#### Sincronización con Supabase")
    if not db.connected:
        st.warning("Agregue SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en los secretos de Streamlit.")
    else:
        ok, _message = db.test_connection()
        if ok:
            st.success("Conexión histórica disponible")
        else:
            st.warning("La conexión histórica no está disponible en este momento.")
        if st.button("Sincronizar estudiantes y asignaciones", type="primary"):
            try:
                students = db.upsert_students(wellbeing)
                advisors = db.upsert_wellbeing_advisors(wellbeing)
                assignments = db.sync_wellbeing_assignments(wellbeing)
                st.success(f"Sincronizados: {students} estudiantes, {advisors} asesores y {assignments} asignaciones.")
            except DatabaseError as exc:
                st.error(str(exc))

with diagnostics_tab:
    st.markdown("#### Estado de la sesión")
    st.json(
        {
            "modo": "demostración" if st.session_state.get("demo_mode") else "Canvas",
            "canvas_url": st.session_state.get("canvas_url"),
            "canvas_conectado": bool(st.session_state.get("canvas_profile")),
            "supabase_conectado": get_database().connected,
            "estudiantes_en_ultimo_analisis": len(st.session_state.get("analysis_df")) if st.session_state.get("analysis_df") is not None else 0,
            "reglas": st.session_state.get("risk_config"),
        }
    )
    st.caption(
        "La consulta de Page Views puede no estar disponible para todos los tokens. Cuando no existe permiso, "
        "la aplicación utiliza la última actividad del enrollment y marca la cantidad de sesiones como no disponible."
    )
