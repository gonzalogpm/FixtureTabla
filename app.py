import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Vóley Stats - Inferiores", layout="wide")

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

def parse_pdf_to_matches(uploaded_file):
    matches = []
    debug_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    
    lines = full_text.split("\n")
    pattern = re.compile(
        r'Sub\s+(\d+)\s+([A-Z0-9\-]+)\s+(\d+)\s*[-–]\s*(\d+)\s+([A-Z0-9\-]+)',
        re.IGNORECASE
    )
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        debug_lines.append(line)
        if re.search(r'\bvs\b', line, re.IGNORECASE):
            continue
        match = pattern.search(line)
        if match:
            category_num = match.group(1)
            team1 = match.group(2)
            sets1 = int(match.group(3))
            sets2 = int(match.group(4))
            team2 = match.group(5)
            categoria = f"Sub {category_num}"
            matches.append({
                "categoria": categoria,
                "team1": team1,
                "team2": team2,
                "sets1": sets1,
                "sets2": sets2,
                "set_scores": None,
                "forfeit": None
            })
    return matches, debug_lines

def create_match_record(team, category, win, forfeit, forfeit_opponent=False,
                        sets_for=0, sets_against=0, points_for=0, points_against=0):
    if forfeit:
        points_earned = 0
        loss_normal = False
        loss_forfeit = True
        win_flag = False
    elif forfeit_opponent:
        points_earned = 2
        loss_normal = False
        loss_forfeit = False
        win_flag = True
    else:
        points_earned = 2 if win else 1
        loss_normal = not win
        loss_forfeit = False
        win_flag = win
    return {
        "equipo": team,
        "categoria": category,
        "win": win_flag,
        "loss_normal": loss_normal,
        "loss_forfeit": loss_forfeit,
        "points_earned": points_earned,
        "sets_for": sets_for,
        "sets_against": sets_against,
        "points_for": points_for,
        "points_against": points_against
    }

def compute_team_stats(matches):
    records = []
    for match in matches:
        cat = match["categoria"]
        team1 = match["team1"]
        team2 = match["team2"]
        sets1 = match["sets1"]
        sets2 = match["sets2"]
        if match.get("forfeit"):
            losing_team = match["forfeit"]
            winning_team = team2 if team1 == losing_team else team1
            records.append(create_match_record(winning_team, cat,
                                               win=True, forfeit_opponent=True,
                                               sets_for=3, sets_against=0))
            records.append(create_match_record(losing_team, cat,
                                               win=False, forfeit=True,
                                               sets_for=0, sets_against=3))
            continue
        team1_wins = sets1 > sets2
        records.append(create_match_record(team1, cat,
                                           win=team1_wins,
                                           forfeit=False,
                                           sets_for=sets1,
                                           sets_against=sets2))
        records.append(create_match_record(team2, cat,
                                           win=not team1_wins,
                                           forfeit=False,
                                           sets_for=sets2,
                                           sets_against=sets1))
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
    cols_order = ["categoria", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]
    for col in cols_order:
        if col not in stats_cat.columns:
            stats_cat[col] = 0
    stats_cat = stats_cat[cols_order]
    stats_cat["Pos"] = stats_cat.groupby("categoria").apply(
        lambda g: g.sort_values(["PTS", "DS", "SG"], ascending=[False, False, False]).reset_index(drop=True).index + 1
    ).reset_index(level=0, drop=True)
    stats_cat = stats_cat[["categoria", "Pos", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]]
    tira = stats_cat.groupby("equipo").agg({
        "PTS": "sum",
        "PG": "sum",
        "PJ": "sum",
        "PP": "sum",
        "PPP": "sum",
        "SG": "sum",
        "SP": "sum",
        "TG": "sum",
        "TP": "sum"
    }).reset_index()
    tira["DS"] = tira["SG"] - tira["SP"]
    tira["DT"] = 0
    tira = tira.sort_values(["PTS", "DS", "SG"], ascending=[False, False, False])
    tira.insert(0, "Pos", range(1, len(tira)+1))
    tira = tira[["Pos", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]]
    return stats_cat, tira

st.title("🏐 Vóley Stats - Inferiores")
st.markdown("Cargá el PDF con los resultados (formato **Sub XX EQUIPOLOCAL X - Y EQUIPOVISITANTE**).")
st.info("ℹ️ **Nota:** El PDF no contiene los tantos por set. Las columnas `TG`, `TP` y `DT` se muestran como **0**.")

uploaded_file = st.file_uploader("📂 Subí tu archivo PDF", type="pdf")

if uploaded_file is not None:
    with st.spinner("Procesando el PDF..."):
        matches, debug_lines = parse_pdf_to_matches(uploaded_file)
    
    if not matches:
        st.error("No se encontraron partidos en el formato esperado.")
        with st.expander("🔍 Ver líneas leídas del PDF (primeras 30)"):
            for i, line in enumerate(debug_lines[:30]):
                st.text(f"{i+1}: {line}")
        with st.expander("ℹ️ Explicación del formato esperado"):
            st.markdown("""
            Se espera una línea como alguna de estas variantes:
            - `Sub 11 LANUS 0 - 2 ULP`
            - `Sub 12 CAPAL 2-1 VIAVE`
            - `Sub 18 GMB 3-0 FERRO`
            
            **Condiciones:**
            - Los nombres de equipos deben ser una sola palabra (pueden contener guiones, ej. `LPV-MFV`).
            - El resultado debe tener dos números separados por un guión (con o sin espacios).
            - No debe tener la palabra `vs` en la línea.
            """)
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
                with st.expander(f"📌 {cat}", expanded=True):
                    cols_mobile = ["Pos", "equipo", "PTS", "PG", "PJ", "DS", "SG"]
                    st.dataframe(df_cat[cols_mobile], use_container_width=True, height=300)
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