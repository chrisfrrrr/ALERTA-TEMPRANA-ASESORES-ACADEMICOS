# AVE — Sistema de alerta temprana y seguimiento académico

Aplicación profesional en Streamlit para analizar cursos de **cinco semanas**, clasificar el riesgo académico, enviar mensajes por Canvas, generar derivaciones a bienestar y conservar el historial en Supabase.

## Funciones incluidas

- Conexión a Canvas mediante URL y token ingresado por el asesor.
- Selección de curso, sección, semana 1–5 y fecha de corte.
- Meta semanal acumulada: `techo(total de actividades × semana / 5)`.
- Análisis de actividades, promedio, puntualidad, actividad en Canvas y respuesta a comunicaciones.
- Dashboard general y expediente individual por estudiante.
- Mensajes personalizados por riesgo y envío mediante Conversations API de Canvas.
- Registro de mensajes y sincronización posterior de respuestas.
- Selección múltiple de estudiantes para derivación.
- Generación de un ZIP con carpetas por asesor de bienestar, informe general e Excel individual por estudiante.
- Detección de derivaciones recientes para evitar duplicados.
- Historial semanal en Supabase y visualización de mejora, estabilidad o deterioro.
- Modo demostración completamente navegable sin credenciales.
- Base de bienestar limpia incluida en `data/bienestar_base.csv`.

## Estructura

```text
app.py
pages/                  Páginas de Streamlit
services/               Canvas, riesgo, Supabase, mensajes y derivaciones
components/             Diseño y gráficas
models/                  Configuración tipada
utils/                   Fechas, limpieza y extracción de carné
sql/schema.sql           Estructura completa de Supabase
data/bienestar_base.csv  Base inicial normalizada
tests/                   Pruebas del cálculo semanal y del motor de riesgo
```

## Instalación local

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Configurar Supabase

1. Cree un proyecto en Supabase.
2. Abra **SQL Editor**.
3. Ejecute todo el contenido de `sql/schema.sql`.
4. Copie `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml`.
5. Complete `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`.

La `service_role` debe permanecer exclusivamente en los secretos del servidor. No la coloque en el repositorio ni en campos visibles de la aplicación.

## Secrets de Streamlit

```toml
CANVAS_URL = "https://uvg.instructure.com"
SUPABASE_URL = "https://SU-PROYECTO.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "SU_SERVICE_ROLE_KEY"
USE_SUPABASE = true
```

El token de Canvas se solicita dentro de la interfaz y se mantiene únicamente durante la sesión activa.

## Uso recomendado

1. Entre a **Conexión y análisis**.
2. Desactive el modo demostración.
3. Ingrese el token de Canvas y pruebe la conexión.
4. Seleccione curso, sección, semana y fecha de corte.
5. Active Page Views solo cuando el token tenga permiso y se necesite estimar sesiones.
6. Ejecute el análisis.
7. Revise el dashboard general y los expedientes individuales.
8. Envíe mensajes desde **Mensajería Canvas**.
9. Prepare derivaciones desde **Derivaciones**.
10. Compare cortes desde **Historial y evolución**.

## Regla semanal

Para 15 actividades:

| Semana | Meta acumulada |
|---:|---:|
| 1 | 3 |
| 2 | 6 |
| 3 | 9 |
| 4 | 12 |
| 5 | 15 |

Para cantidades no divisibles entre cinco se utiliza redondeo hacia arriba. Por ejemplo, 17 actividades producen metas acumuladas de 4, 7, 11, 14 y 17.

## Consideraciones de Canvas

- El conteo exacto de ingresos depende del permiso para consultar Page Views.
- Cuando Page Views no está disponible, la app utiliza `last_activity_at` de la inscripción y no inventa una cantidad de sesiones.
- Las actividades se filtran para excluir elementos no publicados y no calificables. Las actividades de cero puntos pueden incluirse desde la interfaz.
- Las entregas tardías cuentan como actividades completadas, pero afectan el indicador de puntualidad.
- La detección de respuestas se realiza sobre conversaciones enviadas por la aplicación y registradas en Supabase.

## Pruebas

```bash
pytest -q
```

Las pruebas verifican, entre otros casos, la distribución de 15 y 17 actividades a lo largo de cinco semanas.

## Actualización 1.1: estabilidad de Canvas

La consulta de entregas se realiza en lotes pequeños por estudiante y actividad, con reintentos automáticos y un tiempo de lectura ampliado. Esto evita cargar en una sola respuesta todas las entregas de cursos con muchos estudiantes. Los errores técnicos de conexión ya no se muestran directamente en la interfaz.

Si una sección contiene una cantidad especialmente alta de estudiantes, seleccione la sección concreta antes de ejecutar el análisis para reducir todavía más el tiempo de consulta.
