from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pandas as pd

from utils.ids import extract_carne


STANDARD_COLUMNS = [
    "carne",
    "nombre_completo",
    "correo",
    "carrera",
    "asesor_bienestar",
    "estado_bienestar",
    "etapa_bienestar",
    "solicitudes_particulares",
    "riesgo_ciclo_regular",
]


def load_wellbeing_csv(source: str | Path | BinaryIO) -> pd.DataFrame:
    """Lee y normaliza la base de bienestar, incluso si viene en CSV latino y con ;."""
    attempts = [
        {"sep": ";", "encoding": "latin1", "engine": "python"},
        {"sep": ",", "encoding": "utf-8-sig", "engine": "python"},
        {"sep": ",", "encoding": "latin1", "engine": "python"},
    ]
    last_error: Exception | None = None
    for options in attempts:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            raw = pd.read_csv(source, **options)
            if len(raw.columns) >= 2:
                return normalize_wellbeing_dataframe(raw)
        except Exception as exc:  # pragma: no cover - fallback de formatos
            last_error = exc
    raise ValueError(f"No fue posible leer la base de bienestar: {last_error}")


def normalize_wellbeing_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "Carné": "carne",
        "Carne": "carne",
        "carné": "carne",
        "Nombre completo": "nombre_completo",
        "Nombre": "nombre_completo",
        "Correo": "correo",
        "Correo electrónico": "correo",
        "Email": "correo",
        "Carrera": "carrera",
        "Programa": "carrera",
        "Asesor de bienestar": "asesor_bienestar",
        "Estado bienestar": "estado_bienestar",
        "Etapa en bienestar": "etapa_bienestar",
        "Solicitudes particulares": "solicitudes_particulares",
        "Nivel de riesgo ciclo regular": "riesgo_ciclo_regular",
    }
    df = raw.rename(columns=aliases).copy()

    if "carne" not in df.columns and "correo" in df.columns:
        df["carne"] = df["correo"].map(extract_carne)
    if "nombre_completo" not in df.columns:
        raise ValueError("La base debe contener una columna de nombre completo.")

    for column in STANDARD_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df["carne"] = pd.to_numeric(df["carne"], errors="coerce").astype("Int64")
    df = df[df["carne"].notna() & (df["carne"] > 0)].copy()

    for column in STANDARD_COLUMNS[1:]:
        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )
        df.loc[df[column].isin(["0", "0.0", "nan", "None"]), column] = ""

    df.loc[df["asesor_bienestar"] == "", "asesor_bienestar"] = "Sin asignar"
    df = df[STANDARD_COLUMNS].drop_duplicates("carne", keep="last")
    return df.sort_values("nombre_completo").reset_index(drop=True)


def merge_wellbeing(analysis: pd.DataFrame, wellbeing: pd.DataFrame) -> pd.DataFrame:
    if analysis.empty:
        return analysis.copy()
    left = analysis.copy()
    left["carne"] = left["carne"].astype(str).str.replace(r"\.0$", "", regex=True)
    right = wellbeing.copy()
    right["carne"] = right["carne"].astype(str).str.replace(r"\.0$", "", regex=True)
    columns = [
        "carne",
        "correo",
        "carrera",
        "asesor_bienestar",
        "estado_bienestar",
        "etapa_bienestar",
        "solicitudes_particulares",
        "riesgo_ciclo_regular",
    ]
    merged = left.merge(right[columns], on="carne", how="left", suffixes=("", "_base"))
    if "correo" in merged.columns:
        merged["email"] = merged["email"].fillna("")
        merged.loc[merged["email"].astype(str).str.strip() == "", "email"] = merged["correo"]
    if "carrera" in merged.columns:
        merged["career"] = merged["career"].fillna("")
        merged.loc[merged["career"].astype(str).str.strip() == "", "career"] = merged["carrera"]
    merged["asesor_bienestar"] = merged["asesor_bienestar"].fillna("Sin asignar")
    return merged
