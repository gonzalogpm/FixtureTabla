import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO

# ------------------------------------------------------------
# Funciones de parseo del PDF
# ------------------------------------------------------------
def parse_pdf_to_matches(uploaded_file):
    """
    Extrae los partidos del PDF.
    Formato esperado por línea:
    Categoría: <nombre> | EquipoA | EquipoB | setsA | setsB | set1,set2,...
    O con W/O: Categoría: ... | EquipoA | EquipoB | W/O
    """
    matches = []
    with pdfplumber.open(uploaded_file) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"

    lines = full_text.split("\n")
    # Expresiones regulares
    # Partido normal con sets y detalles de tantos
    pattern_normal = re.compile(
        r"Categoría:\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.*)",
        re.IGNORECASE
    )
    # Partido por no presentación
    pattern_wo = re.compile(
        r"Categoría:\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*W/O",
        re.IGNORECASE
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Buscar no presentación
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
                "forfeit": team1  # el equipo que no se presenta será el que aparece como perdedor? asumimos team1 es el que no se presenta? Mejor: reordenar.
                # En este formato no sabemos quién falta. Asumiremos que el primero es el que no se presenta.
                # En la práctica, lo definimos: el equipo que no se presenta es team1, team2 gana por walkover.
                # Lo trataremos en el cálculo.
            })
            continue

        # Partido normal
        norm_match = pattern_normal.search(line)
        if norm_match:
            category = norm_match.group(1).strip()
            team1 = norm_match.group(2).strip()
            team2 = norm_match.group(3).strip()
            sets1 = int(norm_match.group(4))
            sets2 = int(norm_match.group(5))
            set_scores_str = norm_match.group(6)
            # Parsear los sets: "25-20,25-22,23-25,25-18"
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

        # Si no coincide ninguna línea, se omite
    return matches

# ------------------------------------------------------------
# Cálculo de estadísticas por equipo y categoría
# ------------------------------------------------------------
def compute_team_stats(matches):
    """
    Retorna dos DataFrames:
    - stats_por_categoria: multiíndice (categoria, equipo)
    - stats_tira: agregado por equipo (suma de todas las categorías)
    """
    records = []  # list para construir el DF final

    for match in matches:
        cat = match["categoria"]
        team1 = match["team1"]
        team2 = match["team2"]
        forfeit = match["forfeit"]

        # Caso walkover / no presentación
        if forfeit is not None:
            # Quien no se presenta: pierde 0 puntos, PPP+1
            # El otro equipo gana 2 puntos, PG+1, sets 3-0, tantos 75-0
            losing_team = forfeit
            winning_team = team2 if team1 == losing_team else team1

            # Ganador
            records.append(create_match_record(winning_team, cat,
                                               win=True, forfeit_opponent=True,
                                               sets_for=3, sets_against=0,
                                               points_for=75, points_against=0))
            # Perdedor por no presentación
            records.append(create_match_record(losing_team, cat,
                                               win=False, forfeit=True,
                                               sets_for=0, sets_against=3,
                                               points_for=0, points_against=75))
            continue

        # Partido normal con datos de sets y tantos
        sets1 = match["sets1"]
        sets2 = match["sets2"]
        set_scores = match["set_scores"]

        # Determinar ganador
        team1_wins = sets1 > sets2
        # Calcular tantos totales por equipo a partir de set_scores
        points1 = sum(s[0] for s in set_scores) if set_scores else 0
        points2 = sum(s[1] for s in set_scores) if set_scores else 0

        # Registro para team1
        records.append(create_match_record(team1, cat,
                                           win=team1_wins,
                                           forfeit=False,
                                           sets_for=sets1,
                                           sets_against=sets2,
                                           points_for=points1,
                                           points_against=points2))
        # Registro para team2
        records.append(create_match_record(team2, cat,
                                           win=not team1_wins,
                                           forfeit=False,
                                           sets_for=sets2,
                                           sets_against=sets1,
                                           points_for=points2,
                                           points_against=points1))

    df_raw = pd.DataFrame(records)

    # Agrupar por categoria y equipo
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
    # Reordenar columnas según lo pedido
    cols_order = ["categoria", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]
    stats_cat = stats_cat[cols_order]

    # Calcular posición dentro de cada categoría
    stats_cat["Pos"] = stats_cat.groupby("categoria").apply(
        lambda g: g.sort_values(["PTS", "DS", "SG"], ascending=[False, False, False]).reset_index(drop=True).index + 1
    ).reset_index(level=0, drop=True)

    # Reordenar columnas para que Pos sea la primera
    stats_cat = stats_cat[["categoria", "Pos", "equipo", "PTS", "PG", "PJ", "PP", "PPP", "DS", "SG", "SP", "DT", "TG", "TP"]]

    # Tabla TIRA: sumar todas las categorías para cada equipo
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

def create_match_record(team, category, win, forfeit, forfeit_opponent=False,
                        sets_for=0, sets_against=0, points_for=0, points_against=0):
    """Crea un registro de un partido para un equipo específico."""
    if forfeit:
        # Equipo que no se presenta
        points_earned = 0
        loss_normal = False
        loss_forfeit = True
        win_flag = False
    elif forfeit_opponent:
        # Equipo que gana por no presentación del rival
        points_earned = 2
        loss_normal = False
        loss_forfeit = False
        win_flag = True
    else:
        # Partido normal
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

# ------------------------------------------------------------
# Interfaz Streamlit
# ------------------------------------------------------------
st.set_page_config(page_title="Estadísticas Vóley", layout="wide")
st.title("🏐 App de Resultados de Vóley")
st.markdown("Carga un PDF con los resultados de los partidos y obtén tablas de posiciones por categoría y la **Tira** general.")

uploaded_file = st.file_uploader("📂 Sube tu archivo PDF", type="pdf")

if uploaded_file is not None:
    with st.spinner("Procesando el PDF..."):
        matches = parse_pdf_to_matches(uploaded_file)

    if not matches:
        st.error("No se encontraron partidos en el PDF. Verifica el formato (ver ayuda más abajo).")
        with st.expander("📖 Ver formato esperado del PDF"):
            st.markdown("""
            Cada partido debe estar en una línea con el siguiente formato: