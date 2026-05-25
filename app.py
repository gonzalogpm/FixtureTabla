import streamlit as st
import pandas as pd
import re
import requests

# --- Configuración de la página ---
st.set_page_config(page_title="Vóley Stats - MetroVoley", layout="wide")
st.markdown("""
<style>
    @media (max-width: 768px) {
        .stDataFrame div[data-testid="stDataFrameResizable"] table td:nth-child(7),
        .stDataFrame div[data-testid="stDataFrameResizable"] table th:nth-child(7) { display: none; }
        .stDataFrame div[data-testid="stDataFrameResizable"] table td:nth-child(9),
        .stDataFrame div[data-testid="stDataFrameResizable"] table th:nth-child(9) { display: none; }
        .stMarkdown, .stSelectbox label, .stMultiSelect label { font-size: 16px; }
        .stButton button { font-size: 18px; padding: 8px 16px; width: 100%; }
        h1, h2, h3 { font-size: 1.8rem; }
        .main > div { padding-left: 1rem; padding-right: 1rem; }
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# Funciones de extracción desde la web
# ------------------------------------------------------------
def fetch_table_from_web(url):
    """
    Obtiene la tabla de posiciones desde una URL de MetroVoley usando r.jina.ai.
    """
    api_url = f"https://r.jina.ai/{url}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        content = response.text
        return content
    except requests.RequestException as e:
        st.error(f"Error al obtener los datos desde la web: {e}")
        return None

def parse_web_content(content):
    """
    Parsea el contenido Markdown devuelto por r.jina.ai y extrae la tabla de posiciones.
    """
    lines = content.split("\n")
    data = []
    start_parsing = False
    for line in lines:
        # Buscar el inicio de la tabla
        if line.startswith("| Pos | Equipo | PTS |"):
            start_parsing = True
            continue
        if start_parsing and line.startswith("|"):
            # Limpiar la línea y dividir por '|'
            parts = [part.strip() for part in line.split("|") if part.strip()]
            if len(parts) >= 12:  # Asegurar que tenemos suficientes columnas
                # Extraer solo el nombre del equipo (eliminar el marcado de la imagen)
                equipo = re.sub(r'!\[.*?\]\(.*?\)', '', parts[1]).strip()
                try:
                    row = {
                        "Pos": int(parts[0]),
                        "equipo": equipo,
                        "PTS": int(parts[2]),
                        "PG": int(parts[3]),
                        "PJ": int(parts[4]),
                        "PP": int(parts[5]),
                        "PPP": int(parts[6]),
                        "DS": int(parts[7]),
                        "SG": int(parts[8]),
                        "SP": int(parts[9]),
                        "DT": int(parts[10]),
                        "TG": int(parts[11]),
                        "TP": int(parts[12]) if len(parts) > 12 else 0,
                    }
                    data.append(row)
                except (ValueError, IndexError):
                    continue
        elif start_parsing and not line.startswith("|"):
            break
    return pd.DataFrame(data)

# ------------------------------------------------------------
# Funciones de procesamiento de datos (igual que antes)
# ------------------------------------------------------------
def create_match_record(team, category, win, sets_for, sets_against):
    points_earned = 2 if win else 1
    return {
        "equipo": team,
        "categoria": category,
        "win": win,
        "loss_normal": not win,
        "loss_forfeit": False,
        "points_earned": points_earned,
        "sets_for": sets_for,
        "sets_against": sets_against,
        "points_for": 0,
        "points_against": 0
    }

def compute_team_stats(matches):
    records = []
    for match in matches:
        cat = match["categoria"]
        team1 = match["team1"]
        team2 = match["team2"]
        sets1 = match["sets1"]
        sets2 = match["sets2"]
        team1_wins = sets1 > sets2
        records.append(create_match_record(team1, cat, team1_wins, sets1, sets2))
        records.append(create_match_record(team2, cat, not team1_wins, sets2, sets1))
    
    if not records:
        return pd.DataFrame(), pd.DataFrame()
    
    df_raw = pd.DataFrame(records)
    
    def agg_func(group):
        total_pj = len(group)
        total_pg = group["win"].sum()
        total_pp = group["loss_normal"].sum()
        total_ppp = group["loss_forfeit"].sum()
        total_pts = group["points_earned"].sum()
        total_sg = group["sets_for"].sum()
        total_sp = group["sets_against"].sum()
        return pd.Series({
            "PJ": total_pj,
            "PG": total_pg,
            "PP": total_pp,
            "PPP": total_ppp,
            "PTS": total_pts,
            "SG": total_sg,
            "SP": total_sp,
            "TG": 0,
            "TP": 0,
            "DS": total_sg - total_sp,
            "DT": 0
        })
    
    stats_cat = df_raw.groupby(["categoria", "equipo"]).apply(agg_func).reset_index()
    numeric_cols = ["PTS", "PG", "PJ", "PP", "PPP", "SG", "SP", "DS", "DT", "TG", "TP"]
    for col in numeric_cols:
        if col in stats_cat.columns:
            stats_cat[col] = pd.to_numeric(stats_cat[col], errors='coerce').fillna(0).astype(int)
    
    # Ordenar y asignar posición
    stats_cat_sorted = []
    for cat in stats_cat["categoria"].unique():
        df_cat = stats_cat[stats_cat["categoria"] == cat].copy()
        df_cat = df_cat.sort_values(["PTS", "DS", "SG"], ascending=[False, False, False])
        df_cat["Pos"] = range(1, len(df_cat) + 1)
        stats_cat_sorted.append(df_cat)
    stats_cat = pd.concat(stats_cat_sorted, ignore_index=True)
    cols_order = ["categoria", "Pos", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]
    stats_cat = stats_cat[cols_order]
    
    # Tira
    tira = stats_cat.groupby("equipo").agg({
        "PTS": "sum", "PG": "sum", "PJ": "sum", "PP": "sum", "PPP": "sum",
        "SG": "sum", "SP": "sum", "TG": "sum", "TP": "sum"
    }).reset_index()
    tira["DS"] = tira["SG"] - tira["SP"]
    tira["DT"] = 0
    tira = tira.sort_values(["PTS", "DS", "SG"], ascending=[False, False, False])
    tira.insert(0, "Pos", range(1, len(tira)+1))
    tira = tira[["Pos", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]]
    for col in ["PTS", "PG", "PJ", "PP", "PPP", "SG", "SP", "DS"]:
        tira[col] = tira[col].astype(int)
    return stats_cat, tira

# ------------------------------------------------------------
# Interfaz de usuario
# ------------------------------------------------------------
st.title("🏐 Vóley Stats - MetroVoley")
st.markdown("Cargá los datos desde la web de MetroVoley o desde un archivo PDF.")

# Crear pestañas para elegir la fuente de datos
tab1, tab2 = st.tabs(["🌐 Desde la Web", "📄 Desde un PDF"])

with tab1:
    st.subheader("Obtener datos desde MetroVoley")
    url = st.text_input("Ingresá la URL del torneo (ej. https://metrovoley.com.ar/tournaments/570?stage=1420&group=3723&category=14)")
    if st.button("Obtener Tabla de Posiciones"):
        if url:
            with st.spinner("Obteniendo datos desde la web..."):
                content = fetch_table_from_web(url)
                if content:
                    df_web = parse_web_content(content)
                    if not df_web.empty:
                        st.success("✅ Datos obtenidos correctamente.")
                        st.subheader("Tabla de Posiciones")
                        st.dataframe(df_web, use_container_width=True)
                        
                        # Convertir la tabla de posiciones al formato de partidos para la Tira
                        # Como la tabla web ya tiene la suma por equipo, la usamos directamente para la Tira
                        tira_web = df_web[["equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]].copy()
                        tira_web.insert(0, "Pos", range(1, len(tira_web)+1))
                        st.subheader("📊 Tira - Sumatoria de todas las categorías")
                        st.dataframe(tira_web, use_container_width=True, height=400)
                        
                        st.download_button(
                            label="📥 Descargar Tira (CSV)",
                            data=tira_web.to_csv(index=False).encode("utf-8"),
                            file_name="tira_voley.csv",
                            mime="text/csv"
                        )
                    else:
                        st.error("No se pudo extraer la tabla de posiciones. Verificá la URL.")
                else:
                    st.error("No se pudo obtener el contenido de la URL.")
        else:
            st.warning("Por favor, ingresá una URL.")

with tab2:
    st.subheader("Procesar un archivo PDF")
    uploaded_file = st.file_uploader("📂 Subí tu archivo PDF", type="pdf")
    if uploaded_file is not None:
        st.warning("La funcionalidad de procesamiento de PDF está en desarrollo. Por ahora, usá la opción desde la web.")
        # Aquí iría el código para procesar el PDF (similar al anterior)
