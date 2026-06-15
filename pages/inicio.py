from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from components.ui import metric_card, page_header
from models.config import RiskConfig
from services.analysis_service import AnalysisService
from services.canvas_service import CanvasAPIError, CanvasService
from services.database_service import DatabaseError
from services.demo_service import demo_courses, demo_sections, generate_demo_analysis
from services.runtime import get_database
from utils.data_cleaning import load_wellbeing_csv, merge_wellbeing


ROOT = Path(__file__).resolve().parents[1]
WELLBEING_PATH = ROOT / "data" / "bienestar_base.csv"

page_header(
    "Conexión y análisis semanal",
    "Conecte Canvas, seleccione el curso y ejecute el corte acumulado correspondiente a una de las cinco semanas.",
)

config = RiskConfig.from_dict(st.session_state.get("risk_config"))
db = get_database()

col_mode, col_canvas, col_supabase = st.columns([1.05, 1.65, 1.2])
with col_mode:
    st.subheader("Modo de trabajo")
    demo_mode = st.toggle(
        "Usar demostración",
        value=st.session_state.get("demo_mode", True),
        help="Permite recorrer toda la aplicación sin utilizar un token real.",
    )
    st.session_state.demo_mode = demo_mode
    if demo_mode:
        st.success("Datos simulados activos")
    else:
        st.info("Se consultará Canvas en tiempo real")

with col_canvas:
    st.subheader("Conexión con Canvas")
    canvas_url = st.text_input(
        "URL de Canvas",
        value=st.session_state.get("canvas_url", "https://uvg.instructure.com"),
    )
    token = st.text_input(
        "Token de acceso",
        value=st.session_state.get("canvas_token", ""),
        type="password",
        help="El token permanece únicamente en la sesión activa de Streamlit.",
    )
    st.session_state.canvas_url = canvas_url
    st.session_state.canvas_token = token

    if demo_mode:
        if st.button("Cargar cursos de demostración", type="primary", width="stretch"):
            st.session_state.courses = demo_courses()
            st.session_state.canvas_profile = {"id": "demo", "name": "Asesor de demostración"}
            st.success("Cursos cargados.")
    else:
        if st.button("Probar conexión y cargar cursos", type="primary", width="stretch"):
            canvas = CanvasService(canvas_url, token)
            with st.spinner("Validando token y permisos..."):
                result = canvas.test_connection()
                if result.ok:
                    st.session_state.canvas_profile = result.profile
                    st.session_state.courses = canvas.list_courses()
                    st.success(f"{result.message} Se encontraron {len(st.session_state.courses)} cursos.")
                else:
                    st.error(result.message)

with col_supabase:
    st.subheader("Base histórica")
    if db.connected:
        ok, _message = db.test_connection()
        if ok:
            st.success("Historial conectado")
        else:
            st.warning("Historial temporalmente no disponible")
    else:
        st.info("Historial local durante esta sesión")

st.divider()
st.subheader("Parámetros del corte")

courses = st.session_state.get("courses") or (demo_courses() if demo_mode else [])
if not courses:
    st.info("Primero cargue los cursos desde Canvas o active la demostración.")
    st.stop()

course_options = {
    f"{course.get('name') or course.get('course_code')}  ·  ID {course.get('id')}": course for course in courses
}
left, middle, right = st.columns([2.1, 1.35, 1.35])
with left:
    selected_course_label = st.selectbox("Curso", list(course_options.keys()))
    selected_course = course_options[selected_course_label]

with middle:
    week = st.selectbox("Semana analizada", list(range(1, config.course_weeks + 1)), index=0)
with right:
    analysis_date = st.date_input("Fecha de corte", value=date.today())

section_key = f"sections_{selected_course['id']}_{'demo' if demo_mode else 'real'}"
if section_key not in st.session_state:
    try:
        if demo_mode:
            st.session_state[section_key] = demo_sections(selected_course["id"])
        else:
            canvas = CanvasService(canvas_url, token)
            st.session_state[section_key] = canvas.list_sections(selected_course["id"])
    except CanvasAPIError as exc:
        st.session_state[section_key] = []
        st.warning(f"No fue posible cargar secciones: {exc}")

sections = st.session_state.get(section_key, [])
section_options = {"Todas las secciones": (None, "Todas las secciones")}
for section in sections:
    section_options[f"{section.get('name')} ({section.get('total_students', '—')} estudiantes)"] = (
        section.get("id"),
        section.get("name") or "Sección",
    )

option_col, switches_col = st.columns([1.7, 2.3])
with option_col:
    selected_section_label = st.selectbox("Sección", list(section_options.keys()))
    section_id, section_name = section_options[selected_section_label]
with switches_col:
    opt1, opt2 = st.columns(2)
    with opt1:
        include_page_views = st.toggle(
            "Estimar ingresos con Page Views",
            value=False,
            disabled=demo_mode,
            help="Puede tardar más y requiere permisos adicionales en Canvas.",
        )
    with opt2:
        include_zero_point = st.toggle(
            "Incluir actividades de 0 puntos",
            value=False,
            help="Active esta opción si Canvas usa actividades obligatorias sin ponderación.",
        )

st.caption(
    "La meta acumulada se calcula como: techo(total de actividades × semana / 5). "
    "Las actividades se ordenan por fecha límite y posición en Canvas."
)

if st.button("Ejecutar análisis semanal", type="primary", width="stretch"):
    progress = st.progress(0, text="Preparando análisis...")

    def update_progress(label: str, value: float) -> None:
        progress.progress(min(max(value, 0.0), 1.0), text=label)

    try:
        latest_messages = db.get_latest_messages() if db.connected else pd.DataFrame()
        previous_history = (
            db.get_snapshot_history(course_id=selected_course["id"], limit=5000) if db.connected else pd.DataFrame()
        )
        if demo_mode:
            dataframe, details, diagnostics = generate_demo_analysis(
                course=selected_course,
                section_id=section_id,
                section_name=section_name,
                week=week,
                analysis_date=analysis_date,
                config=config,
                wellbeing_path=WELLBEING_PATH,
            )
            update_progress("Demostración generada", 1.0)
        else:
            canvas = CanvasService(canvas_url, token)
            service = AnalysisService(canvas, config)
            dataframe, details, diagnostics = service.analyze_course(
                course=selected_course,
                section_id=section_id,
                section_name=section_name,
                week=week,
                analysis_date=analysis_date,
                include_page_views=include_page_views,
                include_zero_point=include_zero_point,
                latest_messages=latest_messages,
                previous_history=previous_history,
                progress_callback=update_progress,
            )
            wellbeing = load_wellbeing_csv(WELLBEING_PATH)
            dataframe = merge_wellbeing(dataframe, wellbeing)
            dataframe["advisor_name"] = dataframe["asesor_bienestar"]
            # Actualiza también el detalle individual con la asignación de bienestar.
            advisor_map = dataframe.set_index("canvas_user_id")["asesor_bienestar"].to_dict()
            for user_id, detail in details.items():
                advisor = advisor_map.get(str(user_id), "Sin asignar")
                detail["student"]["asesor_bienestar"] = advisor
                detail["student"]["advisor_name"] = advisor

        st.session_state.analysis_df = dataframe
        st.session_state.analysis_details = details
        st.session_state.analysis_diagnostics = diagnostics
        st.session_state.selected_student_id = dataframe.iloc[0]["canvas_user_id"] if not dataframe.empty else None

        history_saved = False
        if db.connected and not dataframe.empty:
            try:
                wellbeing = load_wellbeing_csv(WELLBEING_PATH)
                db.upsert_students(wellbeing)
                db.upsert_wellbeing_advisors(wellbeing)
                db.sync_wellbeing_assignments(wellbeing)
                db.upsert_students(dataframe.rename(columns={"student_name": "nombre_completo"}))
                run_id = db.create_analysis_run(
                    {
                        "canvas_course_id": str(selected_course["id"]),
                        "course_name": selected_course.get("name"),
                        "canvas_section_id": str(section_id) if section_id else None,
                        "section_name": section_name,
                        "week_number": week,
                        "total_weeks": config.course_weeks,
                        "analysis_cutoff": datetime.combine(analysis_date, datetime.max.time()).replace(tzinfo=timezone.utc).isoformat(),
                        "mode": "demo" if demo_mode else "canvas",
                        "student_count": len(dataframe),
                        "activity_count": diagnostics.get("assignments_analyzed"),
                        "created_by_name": st.session_state.get("academic_advisor"),
                    }
                )
                st.session_state.analysis_run_id = run_id
                db.save_snapshots(run_id, dataframe)
                history_saved = True
            except DatabaseError:
                import logging

                logging.exception("No fue posible guardar el historial del análisis")

        progress.empty()
        st.success(f"Análisis completado para {len(dataframe)} estudiantes.")
        if db.connected and not history_saved:
            st.caption("El resultado quedó disponible en la sesión actual; el historial se actualizará en un próximo intento.")
    except (CanvasAPIError, DatabaseError, ValueError) as exc:
        progress.empty()
        st.error(str(exc))
    except Exception:
        import logging

        progress.empty()
        logging.exception("Error inesperado durante el análisis semanal")
        st.error(
            "Ocurrió un inconveniente inesperado durante el análisis. "
            "Vuelva a intentarlo; los detalles técnicos quedaron registrados en los logs de la aplicación."
        )

if st.session_state.get("analysis_df") is not None:
    dataframe = st.session_state.analysis_df
    if not dataframe.empty:
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            metric_card("Estudiantes analizados", len(dataframe), f"Semana {int(dataframe['week_number'].iloc[0])} de 5")
        with m2:
            metric_card("Actividades del curso", int(dataframe["total_activities"].iloc[0]), "Publicadas y calificables")
        with m3:
            metric_card("Meta acumulada", int(dataframe["expected_activities"].iloc[0]), "Mínimo al cierre de la semana")
        with m4:
            metric_card("Riesgo alto", int((dataframe["overall_risk"] == "Alto").sum()), "Requieren atención prioritaria")

        with st.expander("Ver diagnóstico técnico del último análisis"):
            st.json(st.session_state.get("analysis_diagnostics", {}))
            if st.button("Ir al dashboard general"):
                st.switch_page("pages/dashboard_general.py")
