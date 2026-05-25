import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Vóley Stats", layout="wide", initial_sidebar_state="auto")

# CSS responsive (sin triples comillas problemáticas)
st.markdown(
    "<style>"
    "@media (max-width: 768px) {"
    ".stDataFrame div[data-testid='stDataFrameResizable'] table td:nth-child(7),"
    ".stDataFrame div[data-testid='stDataFrameResizable'] table th:nth-child(7) { display: none; }"
    ".stDataFrame div[data-testid='stDataFrameResizable'] table td:nth-child(9),"
    ".stDataFrame div[data-testid='stDataFrameResizable'] table th:nth-child(9) { display: none; }"
    ".stMarkdown, .stSelectbox label, .stMultiSelect label { font-size: 16px; }"
    ".stButton button { font-size: 18px; padding: 8px 16px; width: 100%; }"
    "h1, h2, h3 { font-size: 1.8rem; }"
    ".main > div { padding-left: 1rem; padding-right: 1rem; }"
    "}</style>",
    unsafe_allow_html=True
)

def parse_pdf_to_matches(uploaded_file):
    matches = []
    with pdfplumber.open(uploaded_file) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"
    lines = full_text.split("\n")
    pattern_normal = re.compile(
        r"Categoría:\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.*)",
        re.IGNORECASE
    )
    pattern_wo = re.compile(
        r"Categoría:\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*W/O",
        re.IGNORECASE
    )
    for line in lines:
        line = line.strip()
        if not line:
            continue
        wo_match = pattern_wo.search(line)
        if wo_match:
            category = wo_match.group(1).strip()
            team1 = wo_match.group(2).strip()
            team2 = wo_match.group(3).strip()
            matches.append({
                "categoria": category,
                "team1": team1,
                "team2": team2,
                "sets1": None,
                "sets2": None,
                "set_scores": None,
                "forfeit": team1
            })
            continue
        norm_match = pattern_normal.search(line)
        if norm_match:
            category = norm_match.group(1).strip()
            team1 = norm_match.group(2).strip()
            team2 = norm_match.group(3).strip()
            sets1 = int(norm_match.group(4))
            sets2 = int(norm_match.group(5))
            set_scores_str = norm_match.group(6)
            set_scores = []
            for score in set_scores_str.split(","):
                score = score.strip()
                if "-" in score:
                    parts = score.split("-")
                    if len(parts) == 2:
                        try:
                            p1 = int(parts[0])
                            p2 = int(parts[1])
                            set_scores.append((p1, p2))
                        except:
                            pass
            matches.append({
                "categoria": category,
                "team1": team1,
                "team2": team2,
                "sets1": sets1,
                "sets2": sets2,
                "set_scores": set_scores,
                "forfeit": None
            })
            continue
    return matches

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
        if win:
            points_earned = 2
            loss_normal = False
        else:
            points_earned = 1
            loss_normal = True
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
        forfeit = match["forfeit"]
        if forfeit is not None:
            losing_team = forfeit
            winning_team = team2 if team1 == losing_team else team1
            records.append(create_match_record(winning_team, cat,
                                               win=True, forfeit_opponent=True,
                                               sets_for=3, sets_against=0,
                                               points_for=75, points_against=0))
            records.append(create_match_record(losing_team, cat,
                                               win=False, forfeit=True,
                                               sets_for=0, sets_against=3,
                                               points_for=0, points_against=75))
            continue
        sets1 = match["sets1"]
        sets2 = match["sets2"]
        set_scores = match["set_scores"]
        team1_wins = sets1 > sets2
        points1 = sum(s[0] for s in set_scores) if set_scores else 0
        points2 = sum(s[1] for s in set_scores) if set_scores else 0
        records.append(create_match_record(team1, cat,
                                           win=team1_wins,
                                           forfeit=False,
                                           sets_for=sets1,
                                           sets_against=sets2,
                                           points_for=points1,
                                           points_against=points2))
        records.append(create_match_record(team2, cat,
                                           win=not team1_wins,
                                           forfeit=False,
                                           sets_for=sets2,
                                           sets_against=sets1,
                                           points_for=points2,
                                           points_against=points1))
    df_raw = pd.DataFrame(records)
    def agg_func(group):
        total_pj = len(group)
        total_pg = group["win"].sum()
        total_pp = group["loss_normal"].sum()
        total_ppp = group["loss_forfeit"].sum()
        total_pts = group["points_earned"].sum()
        total_sg = group["sets_for"].sum()
        total_sp = group["sets_against"].sum()
        total_tg = group["points_for"].sum()
        total_tp = group["points_against"].sum()
        return pd.Series({
            "PJ": total_pj,
            "PG": total_pg,
            "PP": total_pp,
            "PPP": total_ppp,
            "PTS": total_pts,
            "SG": total_sg,
            "SP": total_sp,
            "TG": total_tg,
            "TP": total_tp,
            "DS": total_sg - total_sp,
            "DT": total_tg - total_tp
        })
    stats_cat = df_raw.groupby(["categoria", "equipo"]).apply(agg_func).reset_index()
    cols_order = ["categoria", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]
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
    tira["DT"] = tira["TG"] - tira["TP"]
    tira = tira.sort_values(["PTS", "DS", "SG"], ascending=[False, False, False])
    tira.insert(0, "Pos", range(1, len(tira)+1))
    tira = tira[["Pos", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]]
    return stats_cat, tira

st.title("🏐 Vóley Stats Móvil")
st.markdown("Carga un PDF con resultados y obtén la tabla de posiciones **por categoría** y la **Tira general**.")

uploaded_file = st.file_uploader("📂 Sube tu archivo PDF", type="pdf")

if uploaded_file is not None:
    with st.spinner("Procesando..."):
        matches = parse_pdf_to_matches(uploaded_file)
    if not matches:
        st.error("Formato incorrecto. Revisa la ayuda.")
        with st.expander("Ver formato esperado"):
            st.code("Categoría: Sub-18 | Equipo A | Equipo B | 3 | 1 | 25-20,25-22,23-25,25-18")
            st.code("Categoría: Sub-16 | Equipo C | Equipo D | W/O")
        st.stop()
    st.success(f"✅ {len(matches)} partidos procesados")
    stats_cat, tira_df = compute_team_stats(matches)
    with st.sidebar:
        st.header("🔍 Filtros")
        categorias = stats_cat["categoria"].unique()
        equipos = stats_cat["equipo"].unique()
        cat_filter = st.multiselect("Categoría", categorias, default=list(categorias))
        team_filter = st.multiselect("Equipo", equipos, default=[])
    st.subheader("🏆 Tabla de posiciones")
    if cat_filter:
        for cat in cat_filter:
            df_cat = stats_cat[stats_cat["categoria"] == cat].copy()
            if not df_cat.empty:
                with st.expander(f"📌 {cat} (click para ver)", expanded=True):
                    cols_mobile = ["Pos", "equipo", "PTS", "PG", "PJ", "DS", "SG"]
                    st.dataframe(df_cat[cols_mobile], use_container_width=True, height=300)
                    if st.button(f"Ver todas las columnas de {cat}", key=f"full_{cat}"):
                        st.dataframe(df_cat, use_container_width=True)
            else:
                st.info(f"No hay datos para {cat}")
    else:
        st.info("Selecciona al menos una categoría")
    st.subheader("📊 Tira - Suma de todas las categorías")
    st.dataframe(tira_df, use_container_width=True, height=400)
    st.download_button("📥 Descargar Tira (CSV)", tira_df.to_csv(index=False), "tira_voley.csv", "text/csv")
else:
    st.info("Esperando carga de archivo PDF...")
    with st.expander("ℹ️ Ayuda: Formato del PDF"):
        st.markdown(
            "**Formato requerido por línea de partido**:\n\n"
            "```\n"
            "Categoría: Sub-18 | Equipo Rojo | Equipo Azul | 3 | 1 | 25-20,25-22,23-25,25-18\n"
            "```\n\n"
            "**Para partido perdido por no presentación**:\n\n"
            "```\n"
            "Categoría: Sub-16 | Equipo Verde | Equipo Amarillo | W/O\n"
            "```\n\n"
            "(El primer equipo es el que no se presenta)\n\n"
            "**Separador obligatorio**: espacio + pipe + espacio ` | `"
        )