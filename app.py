from __future__ import annotations

import streamlit as st

from components.ui import inject_global_css, render_sidebar_brand
from models.config import RiskConfig


st.set_page_config(
    page_title="AVE | Alerta temprana",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


def initialize_state() -> None:
    defaults = {
        "demo_mode": True,
        "canvas_url": "https://uvg.instructure.com",
        "canvas_token": "",
        "canvas_profile": None,
        "courses": [],
        "sections": [],
        "analysis_df": None,
        "analysis_details": {},
        "analysis_diagnostics": {},
        "analysis_run_id": None,
        "selected_student_id": None,
        "preselected_message_students": [],
        "preselected_referral_students": [],
        "message_log": [],
        "referral_package": None,
        "referral_records": [],
        "academic_advisor": "Ing. Christian Pocol",
        "risk_config": RiskConfig().as_dict(),
        "risk_config_loaded": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()
inject_global_css()
render_sidebar_brand()

pages = {
    "Operación": [
        st.Page("pages/inicio.py", title="Conexión y análisis", icon="🔄"),
        st.Page("pages/dashboard_general.py", title="Dashboard general", icon="📊"),
        st.Page("pages/estudiante.py", title="Expediente individual", icon="👤"),
    ],
    "Intervenciones": [
        st.Page("pages/mensajeria.py", title="Mensajería Canvas", icon="✉️"),
        st.Page("pages/derivaciones.py", title="Derivaciones", icon="📁"),
        st.Page("pages/historial.py", title="Historial y evolución", icon="📈"),
    ],
    "Administración": [
        st.Page("pages/configuracion.py", title="Configuración", icon="⚙️"),
    ],
}

navigation = st.navigation(pages)
navigation.run()
