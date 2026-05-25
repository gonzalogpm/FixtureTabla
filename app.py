import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Vóley Stats - Inferiores", layout="wide")

# CSS responsive
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
# Parseador con búsqueda en rango y depuración
# ------------------------------------------------------------
def parse_pdf_to_matches(uploaded_file):
    matches = []
    with pdfplumber.open(uploaded_file) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    
    lines = full_text.split("\n")
    lines = [line.strip() for line in lines if line.strip()]
    
    # Patrón para resultado
    result_pattern = re.compile(
        r'([A-Z0-9\-]+)\s+(\d+)\s*[-–]\s*(\d+)\s+([A-Z0-9\-]+)',
        re.IGNORECASE
    )
    # Patrón para categoría
    cat_pattern = re.compile(r'(?:Sub|Sáb|Sab)\s*(\d{1,2})', re.IGNORECASE)
    
    # Correcciones
    corrections = {
        "LPA-MPV": "LPV-MFV", "FEBRO": "FERRO", "FERR0": "FERRO",
        "SHOLEM": "SHOLEM", "CAI": "CAI", "VIAVE": "VIAVE",
        "BPLP": "BPLP", "BPLP B": "BPLP", "GLORIAS": "GLORIAS",
        "CAPAL": "CAPAL", "COUNTRY": "COUNTRY", "LANUS": "LANUS",
        "ULP": "ULP", "GMB": "GMB", "LPV-MFV": "LPV-MFV",
        "ANDO": "LANUS"
    }
    
    for i, line in enumerate(lines):
        # Ignorar líneas con "vs"
        if re.search(r'\bvs\b', line, re.IGNORECASE):
            continue
        
        result_match = result_pattern.search(line)
        if not result_match:
            continue
        
        raw_team1 = result_match.group(1)
        sets1 = int(result_match.group(2))
        sets2 = int(result_match.group(3))
        raw_team2 = result_match.group(4)
        
        team1 = corrections.get(raw_team1, raw_team1)
        team2 = corrections.get(raw_team2, raw_team2)
        
        # Buscar categoría en un rango de ±5 líneas
        categoria = None
        for offset in range(-5, 6):
            idx = i + offset
            if 0 <= idx < len(lines):
                cat_match = cat_pattern.search(lines[idx])
                if cat_match:
                    cat_num = int(cat_match.group(1))
                    if 11 <= cat_num <= 21:
                        categoria = f"Sub {cat_num}"
                        break
        
        if not categoria:
            continue
        
        matches.append({
            "categoria": categoria,
            "team1": team1,
            "team2": team2,
            "sets1": sets1,
            "sets2": sets2,
        })
    
    return matches, lines

# ------------------------------------------------------------
# Funciones de estadísticas (igual que antes)
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
st.title("🏐 Vóley Stats - Inferiores")
st.markdown("Cargá el PDF con los resultados. El programa detecta automáticamente el formato.")
st.info("ℹ️ **Nota:** El PDF no contiene los tantos por set. Las columnas `TG`, `TP` y `DT` se muestran como **0**.")

uploaded_file = st.file_uploader("📂 Subí tu archivo PDF", type="pdf")

if uploaded_file is not None:
    with st.spinner("Procesando el PDF..."):
        matches, lines = parse_pdf_to_matches(uploaded_file)
    
    # Mostrar partidos detectados para depuración
    with st.expander("🔍 Ver partidos detectados (para verificar categorías)"):
        if matches:
            df_matches = pd.DataFrame(matches)
            st.dataframe(df_matches)
            st.write(f"Total partidos: {len(matches)}")
        else:
            st.warning("No se detectaron partidos.")
            st.text("Primeras 30 líneas del PDF:")
            for i, line in enumerate(lines[:30]):
                st.text(f"{i+1}: {line}")
    
    if not matches:
        st.error("No se encontraron partidos. Revisá la depuración arriba.")
        st.stop()
    
    st.success(f"✅ Se procesaron {len(matches)} partidos.")
    stats_cat, tira_df = compute_team_stats(matches)
    
    with st.sidebar:
        st.header("🔍 Filtros")
        categorias = sorted(stats_cat["categoria"].unique())
        equipos = sorted(stats_cat["equipo"].unique())
        cat_filter = st.multiselect("Categorías", categorias, default=categorias)
        team_filter = st.multiselect("Equipos", equipos, default=[])
    
    st.subheader("🏆 Tabla de posiciones por categoría")
    if cat_filter:
        for cat in cat_filter:
            df_cat = stats_cat[stats_cat["categoria"] == cat].copy()
            if not df_cat.empty:
                cols_mobile = ["Pos", "equipo", "PTS", "PG", "PJ", "DS", "SG"]
                df_mobile = df_cat[cols_mobile]
                with st.expander(f"📌 {cat}", expanded=True):
                    st.dataframe(df_mobile, use_container_width=True, height=300)
                    if st.button(f"Ver todas las columnas de {cat}", key=f"full_{cat}"):
                        st.dataframe(df_cat, use_container_width=True)
            else:
                st.info(f"No hay datos para {cat}")
    else:
        st.info("Seleccioná al menos una categoría en el filtro lateral.")
    
    st.subheader("📊 Tira - Sumatoria de todas las categorías")
    st.dataframe(tira_df, use_container_width=True, height=400)
    st.download_button(
        label="📥 Descargar Tira (CSV)",
        data=tira_df.to_csv(index=False).encode("utf-8"),
        file_name="tira_voley.csv",
        mime="text/csv"
    )
else:
    st.info("Esperando la carga del archivo PDF...")