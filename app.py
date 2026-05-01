import math
from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from data.google_sheets import load_all_data


# ======================
# CONFIG
# ======================
st.set_page_config(page_title="MRP Pro V5", page_icon="🏭", layout="wide")
PASSWORD = "1234"


# ======================
# LOGIN
# ======================
if "logged" not in st.session_state:
    st.session_state.logged = False

if not st.session_state.logged:
    st.markdown(
        """
        <div style="max-width:460px;margin:90px auto;padding:35px;background:white;border-radius:24px;
        box-shadow:0 12px 30px rgba(15,23,42,.12);text-align:center;">
            <h1>🏭 MRP Pro V5</h1>
            <p style="color:#64748b;">Accès sécurisé entreprise</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    p = st.text_input("Mot de passe", type="password")
    if st.button("Connexion"):
        if p == PASSWORD:
            st.session_state.logged = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect")
    st.stop()


# ======================
# CSS
# ======================
st.markdown(
    """
<style>
.main {background-color:#f6f8fb;}

.section-title {
    font-size: 42px;
    font-weight: 800;
    background: linear-gradient(90deg,#60a5fa,#7c3aed);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 5px;
}

.section-subtitle{
    font-size:17px;
    color:#64748b;
    margin-bottom:26px;
}

.kpi-card{
    border-radius:24px;
    padding:26px 28px;
    min-height:155px;
    color:white;
    box-shadow:0 12px 28px rgba(15,23,42,.14);
    overflow:hidden;
    margin-bottom:18px;
}

.kpi-title{
    font-size:22px;
    font-weight:700;
    opacity:.95;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}

.kpi-value{
    font-size:42px;
    font-weight:900;
    margin-top:28px;
    white-space:nowrap;
    overflow:visible;
}

div[data-testid="stDataFrame"]{
    background:white;
    border-radius:18px;
    padding:8px;
}
</style>
""",
    unsafe_allow_html=True,
)


# ======================
# HELPERS
# ======================
def clean_numeric(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True),
        errors="coerce",
    )


def normalize_columns(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def kpi_card(title, value, bg):
    st.markdown(
        f"""
        <div class="kpi-card" style="background:{bg};">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=60, show_spinner=False)
def get_data():
    data = load_all_data()
    for k in data:
        data[k] = normalize_columns(data[k])
    return data


# ======================
# PREPARE DATA
# ======================
def prepare_param(param):
    df = param.copy()
    df.columns = [str(c).strip() for c in df.columns]

    df = df.rename(
        columns={
            "moq": "moq_kg",
            "MOQ": "moq_kg",
            "MOQ KG": "moq_kg",
            "Unité": "unite",
            "Unite": "unite",
        }
    )

    df["code_mp"] = df["code_mp"].astype(str).str.strip()
    df["designation"] = df["designation"].astype(str).str.strip()

    if "type_article" not in df.columns:
        df["type_article"] = ""

    if "unite" not in df.columns:
        df["unite"] = ""

    df["lead_time_j"] = clean_numeric(df["lead_time_j"]).fillna(0)
    df["moq_kg"] = clean_numeric(df["moq_kg"]).fillna(0)
    df["stock_actuel"] = clean_numeric(df["stock_actuel"]).fillna(0)

    return df


def prepare_conso(conso):
    df = conso.copy()
    df.columns = [str(c).strip() for c in df.columns]

    df = df.rename(
        columns={
            "Reference": "ref_produit_finis",
            "Référence": "ref_produit_finis",
            "Ref produit finis": "ref_produit_finis",
            "composant": "code_mp",
            "Composant": "code_mp",
            "CODE matière": "code_mp",
            "Quantité": "conso_unit",
            "Quantite": "conso_unit",
            "conso_unitaire": "conso_unit",
            "Unité": "unite",
            "Unite": "unite",
        }
    )

    required = ["ref_produit_finis", "code_mp", "conso_unit"]
    for col in required:
        if col not in df.columns:
            st.error(f"Colonne manquante dans Conso/BOM : {col}")
            st.stop()

    df["ref_produit_finis"] = df["ref_produit_finis"].astype(str).str.strip()
    df["code_mp"] = df["code_mp"].astype(str).str.strip()
    df["conso_unit"] = clean_numeric(df["conso_unit"]).fillna(0)

    if "unite" not in df.columns:
        df["unite"] = ""

    return df[df["conso_unit"] > 0]


def prepare_mrp(mrp):
    df = mrp.copy()
    product_col = "Ref produit finis"

    if product_col not in df.columns:
        st.error("La colonne 'Ref produit finis' est introuvable dans MRP.")
        st.stop()

    date_cols = [c for c in df.columns if c != product_col]

    df_long = df.melt(
        id_vars=[product_col],
        value_vars=date_cols,
        var_name="date",
        value_name="qte_pf",
    )

    df_long = df_long.rename(columns={product_col: "ref_produit_finis"})
    df_long["ref_produit_finis"] = df_long["ref_produit_finis"].astype(str).str.strip()
    df_long["date"] = pd.to_datetime(df_long["date"], dayfirst=True, errors="coerce")
    df_long["qte_pf"] = clean_numeric(df_long["qte_pf"]).fillna(0)

    df_long = df_long.dropna(subset=["date"])
    df_long = df_long[df_long["qte_pf"] > 0]

    return df_long


def prepare_fournisseurs(fournisseurs):
    df = fournisseurs.copy()

    if "code_mp" not in df.columns:
        return pd.DataFrame(columns=["code_mp", "nom_fournisseur"])

    df["code_mp"] = df["code_mp"].astype(str).str.strip()

    if "nom_fournisseur" in df.columns:
        df["nom_fournisseur"] = df["nom_fournisseur"].astype(str).str.strip()
    else:
        df["nom_fournisseur"] = "-"

    for col in ["fiabilite_%", "taux_service_%", "note_qualite_5", "lead_time_j", "prix_unitaire_eur"]:
        if col in df.columns:
            df[col] = clean_numeric(df[col])

    sort_cols = []
    ascending = []

    if "fiabilite_%" in df.columns:
        sort_cols.append("fiabilite_%")
        ascending.append(False)

    if "lead_time_j" in df.columns:
        sort_cols.append("lead_time_j")
        ascending.append(True)

    if sort_cols:
        df = df.sort_values(sort_cols, ascending=ascending)

    best = df.groupby("code_mp", as_index=False).first()

    keep = ["code_mp", "nom_fournisseur"]
    for col in ["fiabilite_%", "taux_service_%", "note_qualite_5", "prix_unitaire_eur", "localisation"]:
        if col in best.columns:
            keep.append(col)

    return best[keep]


# ======================
# BUSINESS LOGIC
# ======================
def calculate_plan(param, conso, mrp_period, fournisseurs, start_date, end_date):
    param_df = prepare_param(param)
    conso_df = prepare_conso(conso)
    fournisseurs_df = prepare_fournisseurs(fournisseurs)

    df_need = mrp_period.merge(conso_df, on="ref_produit_finis", how="left")
    df_need = df_need.dropna(subset=["code_mp"])
    df_need["besoin_mp_kg"] = df_need["qte_pf"] * df_need["conso_unit"]

    besoin_mp = (
        df_need.groupby("code_mp", as_index=False)["besoin_mp_kg"]
        .sum()
        .rename(columns={"besoin_mp_kg": "besoin_periode_kg"})
    )

    date_besoin_mp = (
        df_need.groupby("code_mp", as_index=False)["date"]
        .min()
        .rename(columns={"date": "date_besoin"})
    )

    pf_mp = (
        df_need.groupby("code_mp", as_index=False)["ref_produit_finis"]
        .agg(lambda x: ", ".join(sorted(set(map(str, x)))))
        .rename(columns={"ref_produit_finis": "liste_pf"})
    )

    df = param_df.merge(besoin_mp, on="code_mp", how="left")
    df = df.merge(date_besoin_mp, on="code_mp", how="left")
    df = df.merge(pf_mp, on="code_mp", how="left")
    df = df.merge(fournisseurs_df, on="code_mp", how="left")

    df["besoin_periode_kg"] = df["besoin_periode_kg"].fillna(0)
    df["liste_pf"] = df["liste_pf"].fillna("")
    df["nom_fournisseur"] = df["nom_fournisseur"].fillna("-")

    nb_days = max((pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1, 1)

    df["conso_moy_jour_kg"] = df["besoin_periode_kg"] / nb_days
    df["stock_securite_kg"] = df["conso_moy_jour_kg"] * 3

    df["couverture_j"] = (
        df["stock_actuel"] / df["conso_moy_jour_kg"].replace(0, pd.NA)
    ).fillna(999999)

    df["besoin_total_kg"] = df["besoin_periode_kg"] + df["stock_securite_kg"]
    df["manque"] = df["besoin_total_kg"] - df["stock_actuel"]

    def calculate_qte(row):
        manque = row["manque"]
        moq = row["moq_kg"]

        if manque <= 0:
            return 0

        if moq <= 0:
            return manque

        return math.ceil(manque / moq) * moq

    df["qte_commande"] = df.apply(calculate_qte, axis=1)
    df["a_commander"] = df["qte_commande"] > 0

    df["date_besoin"] = pd.to_datetime(df["date_besoin"], errors="coerce")
    df["date_commande"] = df["date_besoin"] - pd.to_timedelta(df["lead_time_j"], unit="D")

    def risk_label(row):
        cov = row["couverture_j"]

        if cov <= 4:
            return "URGENT"
        elif cov <= 6:
            return "CRITIQUE"
        elif cov <= 12:
            return "ATTENTION"
        else:
            return "OK"

    df["statut"] = df.apply(risk_label, axis=1)

    if "prix_unitaire_eur" in df.columns:
        df["valeur_commande_eur"] = (df["qte_commande"] * df["prix_unitaire_eur"]).fillna(0)
    else:
        df["valeur_commande_eur"] = 0

    df["date_besoin"] = df["date_besoin"].dt.date
    df["date_commande"] = pd.to_datetime(df["date_commande"], errors="coerce").dt.date

    status_order = {"URGENT": 0, "CRITIQUE": 1, "ATTENTION": 2, "OK": 3}
    df["status_order"] = df["statut"].map(status_order).fillna(9)

    return df.sort_values(["status_order", "qte_commande"], ascending=[True, False]).reset_index(drop=True)


# ======================
# EXPORTS
# ======================
def to_excel(plan, top_action):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        plan.to_excel(writer, index=False, sheet_name="Plan_Detaille")
        top_action.to_excel(writer, index=False, sheet_name="Top_Actions")
    output.seek(0)
    return output


def to_pdf(plan, start_date, end_date):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Résumé Plan Approvisionnement - MRP Pro V5", styles["Title"]))
    story.append(Paragraph(f"Période analysée : {start_date} au {end_date}", styles["Normal"]))
    story.append(Spacer(1, 12))

    kpis = [
        ["Indicateur", "Valeur"],
        ["Total MP", str(len(plan))],
        ["MP à commander", str(int(plan["a_commander"].sum()))],
        ["Urgents/Critiques", str(int(plan["statut"].isin(["URGENT", "CRITIQUE"]).sum()))],
        ["Quantité commande kg", str(round(plan["qte_commande"].sum(), 2))],
        ["Stock total kg", str(round(plan["stock_actuel"].sum(), 2))],
    ]

    table = Table(kpis)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )

    story.append(table)
    story.append(Spacer(1, 18))

    top = plan.head(10)[["code_mp", "nom_fournisseur", "qte_commande", "date_commande", "statut"]]
    data = [["MP", "Fournisseur", "Qté", "Date", "Statut"]] + top.astype(str).values.tolist()

    story.append(Paragraph("Top 10 actions prioritaires", styles["Heading2"]))

    table2 = Table(data)
    table2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story.append(table2)
    doc.build(story)
    buffer.seek(0)
    return buffer


# ======================
# IA LOCAL
# ======================
def chat_ia_local(question, plan):
    q = question.lower().strip()

    if q == "":
        return "Pose une question : actions urgentes, stock, fournisseur, ou analyse MP MP0005."

    top = plan.sort_values(["status_order", "qte_commande"], ascending=[True, False]).head(5)

    if "action" in q or "urgent" in q or "شنو" in q or "اليوم" in q:
        lines = ["### Actions prioritaires"]
        for _, r in top.iterrows():
            if r["qte_commande"] > 0:
                lines.append(
                    f"- **{r['code_mp']}** : commander **{round(r['qte_commande'], 2)} kg** chez **{r['nom_fournisseur']}** avant **{r['date_commande']}**."
                )
        return "\n".join(lines)

    if "stock" in q or "rupture" in q:
        low = plan[plan["couverture_j"] != 999999].sort_values("couverture_j").head(5)
        lines = ["### Risque stock"]
        for _, r in low.iterrows():
            lines.append(
                f"- **{r['code_mp']}** : couverture **{round(r['couverture_j'], 1)} jours**, statut **{r['statut']}**."
            )
        return "\n".join(lines)

    if "fournisseur" in q or "supplier" in q:
        fournisseurs = [x for x in plan["nom_fournisseur"].dropna().unique() if str(x) != "-"]
        for f in fournisseurs:
            if str(f).lower() in q:
                df_f = plan[plan["nom_fournisseur"] == f]
                return (
                    f"### Analyse fournisseur : {f}\n"
                    f"- Nombre MP : **{df_f['code_mp'].nunique()}**\n"
                    f"- Qté à commander : **{round(df_f['qte_commande'].sum(), 2)} kg**\n"
                    f"- MP critiques : **{int(df_f['statut'].isin(['URGENT', 'CRITIQUE']).sum())}**\n"
                )
        return "Écris le nom du fournisseur dans ta question."

    if "mp" in q:
        for mp in plan["code_mp"].astype(str).unique():
            if mp.lower() in q:
                r = plan[plan["code_mp"].astype(str) == mp].iloc[0]
                return (
                    f"### Analyse MP : {mp}\n"
                    f"- Désignation : **{r['designation']}**\n"
                    f"- Fournisseur : **{r['nom_fournisseur']}**\n"
                    f"- Stock actuel : **{round(r['stock_actuel'], 2)} kg**\n"
                    f"- Besoin période : **{round(r['besoin_periode_kg'], 2)} kg**\n"
                    f"- Qté à commander : **{round(r['qte_commande'], 2)} kg**\n"
                    f"- Couverture : **{round(r['couverture_j'], 1)} jours**\n"
                    f"- PF liés : **{r['liste_pf']}**"
                )

        return "Écris le code MP dans ta question. Exemple : analyse MP MP0005."

    return "Je peux t’aider sur : actions urgentes, fournisseur, stock/rupture, ou analyse MP."


# ======================
# MAIN
# ======================
st.markdown('<div class="section-title">📦 ApproVision MRP</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-subtitle">Approvisionnement, stock, matières premières, fournisseurs, plan commande et assistant IA.</div>',
    unsafe_allow_html=True,
)

if st.sidebar.button("🔄 Actualiser maintenant"):
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("🚪 Déconnexion"):
    st.session_state.logged = False
    st.rerun()

data = get_data()
param = data["param"]
conso = data["conso"]
mrp = data["mrp"]
fournisseurs = data["fournisseurs"]

mrp_long = prepare_mrp(mrp)

st.sidebar.header("Configuration période")

date_min = mrp_long["date"].min().date()
date_max = mrp_long["date"].max().date()

mode = st.sidebar.selectbox("Mode période", ["Durée prédéfinie", "Intervalle manuel"])

if mode == "Durée prédéfinie":
    duree = st.sidebar.selectbox("Durée", ["14 jours", "30 jours", "60 jours", "90 jours"])
    nb_days = {"14 jours": 14, "30 jours": 30, "60 jours": 60, "90 jours": 90}[duree]
    start_date = st.sidebar.date_input("Date début", value=date_min, min_value=date_min, max_value=date_max)
    end_date = min(pd.to_datetime(start_date) + pd.Timedelta(days=nb_days - 1), pd.to_datetime(date_max)).date()
else:
    start_date = st.sidebar.date_input("Date début", value=date_min, min_value=date_min, max_value=date_max)
    end_date = st.sidebar.date_input("Date fin", value=date_max, min_value=date_min, max_value=date_max)

if pd.to_datetime(end_date) < pd.to_datetime(start_date):
    st.error("La date fin doit être supérieure ou égale à la date début.")
    st.stop()

mrp_period = mrp_long[
    (mrp_long["date"] >= pd.to_datetime(start_date)) &
    (mrp_long["date"] <= pd.to_datetime(end_date))
]

plan = calculate_plan(param, conso, mrp_period, fournisseurs, start_date, end_date)
top_action = plan.head(10)

tab_dashboard, tab_alertes, tab_stock, tab_mp, tab_fournisseurs, tab_plan, tab_ia = st.tabs(
    [
        "🏠 Dashboard",
        "🚨 Alertes",
        "📊 Stock",
        "📦 Matières Premières",
        "🏭 Fournisseurs",
        "📑 Plan Commande",
        "🤖 IA",
    ]
)

status_colors = {"URGENT": "#dc2626", "CRITIQUE": "#f97316", "ATTENTION": "#facc15", "OK": "#16a34a"}


# ======================
# DASHBOARD
# ======================
with tab_dashboard:
    cov = round(plan["couverture_j"].replace(999999, pd.NA).dropna().mean(), 1)

    r1c1, r1c2, r1c3 = st.columns(3)

    with r1c1:
        kpi_card("Total MP", int(len(plan)), "linear-gradient(135deg,#2563eb,#1e3a8a)")
    with r1c2:
        kpi_card("À commander", int(plan["a_commander"].sum()), "linear-gradient(135deg,#7c3aed,#581c87)")
    with r1c3:
        kpi_card("Critiques", int(plan["statut"].isin(["URGENT", "CRITIQUE"]).sum()), "linear-gradient(135deg,#dc2626,#991b1b)")

    r2c1, r2c2, r2c3 = st.columns(3)

    with r2c1:
        kpi_card("Commande kg", f"{round(plan['qte_commande'].sum(), 0):,.0f}", "linear-gradient(135deg,#ea580c,#9a3412)")
    with r2c2:
        kpi_card("Stock kg", f"{round(plan['stock_actuel'].sum(), 0):,.0f}", "linear-gradient(135deg,#0891b2,#155e75)")
    with r2c3:
        kpi_card("Couverture j", cov, "linear-gradient(135deg,#16a34a,#166534)")

        st.markdown("### 🔎 Filtre analyse")
    vue_type = st.radio(
        "Choisir le type d'article",
        ["Tous", "MP", "C"],
        horizontal=True,
        key="vue_type_dashboard"
    )

    if "type_article" not in plan.columns:
        plan["type_article"] = "MP"

    if vue_type == "Tous":
        plan_vue = plan.copy()
        titre_pareto = "Pareto cumulative Articles"
        titre_statut = "Répartition statuts Articles"
    else:
        plan_vue = plan[plan["type_article"].astype(str).str.upper() == vue_type].copy()
        titre_pareto = f"Pareto cumulative {vue_type}"
        titre_statut = f"Répartition statuts {vue_type}"

    colA, colB = st.columns(2)

    with colA:
        st.subheader(f"📊 {titre_pareto}")

        pareto = (
            plan_vue[plan_vue["qte_commande"] > 0][["code_mp", "qte_commande"]]
            .sort_values("qte_commande", ascending=False)
            .head(10)
        )

        if not pareto.empty:
            pareto["cum_pct"] = pareto["qte_commande"].cumsum() / pareto["qte_commande"].sum() * 100

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Bar(
                    x=pareto["code_mp"],
                    y=pareto["qte_commande"],
                    name="Qté commande",
                    marker_color="#2563eb"
                ),
                secondary_y=False
            )
            fig.add_trace(
                go.Scatter(
                    x=pareto["code_mp"],
                    y=pareto["cum_pct"],
                    name="% cumulé",
                    mode="lines+markers",
                    line=dict(color="#dc2626", width=3)
                ),
                secondary_y=True
            )

            fig.update_yaxes(title_text="Qté commande", secondary_y=False)
            fig.update_yaxes(title_text="% cumulé", secondary_y=True, range=[0, 110])
            fig.update_layout(height=380, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True, key=f"pareto_chart_{vue_type}")
        else:
            st.info("Aucune commande à afficher pour ce type.")

    
    with colB:
        st.subheader("🧭 Répartition statuts")
        status_df = plan["statut"].value_counts().reset_index()
        status_df.columns = ["statut", "count"]
        fig_status = px.pie(status_df, names="statut", values="count", hole=0.55, color="statut", color_discrete_map=status_colors)
        fig_status.update_layout(height=380, template="plotly_white")
        st.plotly_chart(fig_status, use_container_width=True, key=f"status_chart_right_{vue_type}")

    st.markdown("---")
    st.subheader("🏭 Analyse interactive Fournisseurs → MP")

    df_fourn_cmd = (
        plan[plan["qte_commande"] > 0]
        .groupby("nom_fournisseur", as_index=False)["qte_commande"]
        .sum()
        .sort_values("qte_commande", ascending=False)
    )

    colF1, colF2 = st.columns(2)

    with colF1:
        st.markdown("### 📊 Commandes par fournisseur")

        fig_fourn = px.bar(
            df_fourn_cmd,
            x="nom_fournisseur",
            y="qte_commande",
            color="qte_commande",
            color_continuous_scale="Blues",
            text="qte_commande"
        )
        fig_fourn.update_traces(texttemplate="%{text:.0f}", textposition="outside")
        fig_fourn.update_layout(height=420, template="plotly_white")

        event = st.plotly_chart(
            fig_fourn,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key="select_fournisseur_chart"
        )

    selected_fourn = None

    try:
        points = event["selection"]["points"]
        if points:
            selected_fourn = points[0]["x"]
    except Exception:
        selected_fourn = None

    with colF2:
        st.markdown("### 📦 MP liées au fournisseur sélectionné")

        if selected_fourn:
            st.success(f"Fournisseur sélectionné : {selected_fourn}")

            df_mp_fourn = (
                plan[
                    (plan["nom_fournisseur"] == selected_fourn) &
                    (plan["qte_commande"] > 0)
                ]
                .groupby(["code_mp", "designation"], as_index=False)["qte_commande"]
                .sum()
                .sort_values("qte_commande", ascending=False)
            )

            fig_mp = px.bar(
                df_mp_fourn,
                x="code_mp",
                y="qte_commande",
                hover_data=["designation"],
                color="qte_commande",
                color_continuous_scale="Oranges",
                text="qte_commande"
            )
            fig_mp.update_traces(texttemplate="%{text:.0f}", textposition="outside")
            fig_mp.update_layout(height=420, template="plotly_white")

            st.plotly_chart(fig_mp, use_container_width=True)

            st.dataframe(df_mp_fourn, use_container_width=True, hide_index=True)

        else:
            st.info("Clique sur un fournisseur dans le graphique à gauche.")
            


# ======================
# ALERTES
# ======================
with tab_alertes:
    st.subheader("🚨 Alertes & Actions Recommandées")

    alertes = plan[(plan["statut"].isin(["URGENT", "CRITIQUE"])) | (plan["qte_commande"] > 0)].copy()
    urgentes = plan[plan["statut"] == "URGENT"].copy()
    critiques = plan[plan["statut"] == "CRITIQUE"].copy()
    commandes = plan[plan["qte_commande"] > 0].copy()

    a1, a2, a3, a4 = st.columns(4)
    with a1:
        st.metric("Alertes totales", int(len(alertes)))
    with a2:
        st.metric("Urgentes", int(len(urgentes)))
    with a3:
        st.metric("Critiques", int(len(critiques)))
    with a4:
        st.metric("Commandes à lancer", int(len(commandes)))

    actions = commandes.copy()

    def action_recommandee(row):
        if row["statut"] == "URGENT":
            return "Commander immédiatement"
        elif row["statut"] == "CRITIQUE":
            return "Lancer commande en priorité"
        elif row["statut"] == "ATTENTION":
            return "Préparer commande"
        return "Aucune action"

    actions["action_recommandee"] = actions.apply(action_recommandee, axis=1)
    actions = actions.sort_values(["status_order", "date_commande", "qte_commande"], ascending=[True, True, False])

    st.subheader("🎯 Actions recommandées")
    st.dataframe(
        actions[
            [
                "action_recommandee",
                "code_mp",
                "designation",
                "nom_fournisseur",
                "stock_actuel",
                "besoin_total_kg",
                "qte_commande",
                "moq_kg",
                "couverture_j",
                "date_commande",
                "statut",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


# ======================
# STOCK
# ======================
with tab_stock:
    st.subheader("📊 Analyse Stock")

    stock_total = round(plan["stock_actuel"].sum(), 2)
    stock_risque = int((plan["couverture_j"] <= 12).sum())
    stock_ok = int((plan["statut"] == "OK").sum())
    stock_dormant = int((plan["besoin_periode_kg"] == 0).sum())

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric("Stock total kg", stock_total)
    with s2:
        st.metric("MP risque rupture", stock_risque)
    with s3:
        st.metric("MP OK", stock_ok)
    with s4:
        st.metric("Stock dormant", stock_dormant)

    stock_vue = st.radio(
    "Filtrer stock",
    ["MP", "C"],
    horizontal=True,
    key="stock_vue"
)

stock_plan = plan[
    plan["type_article"].astype(str).str.upper() == stock_vue
].copy()
c1, c2 = st.columns(2)

with c1:
        st.subheader("📉 Couverture stock faible - Articles")
        low_cov = stock_plan[stock_plan["couverture_j"] != 999999].sort_values("couverture_j").head(10)
        fig_cov = px.bar(low_cov, x="code_mp", y="couverture_j", color="statut", color_discrete_map=status_colors)
        fig_cov.update_layout(height=360, template="plotly_white")
        st.plotly_chart(fig_cov, use_container_width=True)

with c2:
        st.subheader("📦 Stock par articles")
        top_stock = stock_plan.sort_values("stock_actuel", ascending=False).head(10)
        fig_stock = px.bar(top_stock, x="code_mp", y="stock_actuel", color="stock_actuel", color_continuous_scale="Teal")
        fig_stock.update_layout(height=360, template="plotly_white")
        st.plotly_chart(fig_stock, use_container_width=True)

st.subheader("Table Stock")
st.dataframe(
        plan[["code_mp", "designation", "stock_actuel", "conso_moy_jour_kg", "couverture_j", "lead_time_j", "statut"]],
        use_container_width=True,
        hide_index=True,
    )


# ======================
# MP
# ======================
with tab_mp:
    st.subheader("📦 Articles")

article_type = st.radio(
    "Type d'article",
    ["MP", "C"],
    horizontal=True,
    key="article_type_mp"
)

plan_articles = plan[
    plan["type_article"].astype(str).str.upper() == article_type
].copy()

label_article = "MP" if article_type == "MP" else "Composant"

mp = st.selectbox(
    f"Choisir {label_article}",
    sorted(plan_articles["code_mp"].astype(str).unique())
)
    r = plan_articles[plan_articles["code_mp"].astype(str) == mp].iloc[0]

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Stock actuel", round(r["stock_actuel"], 2))
    with m2:
        st.metric("Besoin période", round(r["besoin_periode_kg"], 2))
    with m3:
        st.metric("Qté commande", round(r["qte_commande"], 2))
    with m4:
        st.metric("Couverture", round(r["couverture_j"], 2) if r["couverture_j"] != 999999 else 0)

    st.write("**Fournisseur :**", r["nom_fournisseur"])
    st.write("**Désignation :**", r["designation"])
    st.write("**PF liés :**", r["liste_pf"])

    st.subheader("Table MP")
    st.dataframe(
        plan[["code_mp", "designation", "nom_fournisseur", "stock_actuel", "besoin_periode_kg", "qte_commande", "liste_pf", "statut"]],
        use_container_width=True,
        hide_index=True,
    )


# ======================
# FOURNISSEURS
# ======================
with tab_fournisseurs:
    st.subheader("🏭 Fournisseurs")

    fournisseurs_valides = plan[plan["nom_fournisseur"].astype(str).str.strip() != "-"].copy()

    nb_fournisseurs = fournisseurs_valides["nom_fournisseur"].nunique()
    total_commande_fourn = fournisseurs_valides["qte_commande"].sum()
    fournisseurs_critiques = fournisseurs_valides[fournisseurs_valides["statut"].isin(["URGENT", "CRITIQUE"])]["nom_fournisseur"].nunique()
    lead_time_moy = fournisseurs_valides["lead_time_j"].mean() if len(fournisseurs_valides) > 0 else 0
    valeur_total_fourn = fournisseurs_valides["valeur_commande_eur"].sum() if "valeur_commande_eur" in fournisseurs_valides.columns else 0

    top_fournisseur_df = (
        fournisseurs_valides.groupby("nom_fournisseur", as_index=False)["qte_commande"]
        .sum()
        .sort_values("qte_commande", ascending=False)
    )

    top_fournisseur = top_fournisseur_df.iloc[0]["nom_fournisseur"] if len(top_fournisseur_df) > 0 else "-"

    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("Nombre fournisseurs", int(nb_fournisseurs))
    with k2:
        st.metric("Fournisseurs critiques", int(fournisseurs_critiques))
    with k3:
        st.metric("Top fournisseur", top_fournisseur)

    k4, k5, k6 = st.columns(3)
    with k4:
        st.metric("Commande totale kg", round(total_commande_fourn, 2))
    with k5:
        st.metric("Lead time moyen", round(lead_time_moy, 1))
    with k6:
        st.metric("Valeur commande €", round(valeur_total_fourn, 2))

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("📊 Commande par fournisseur")
        df_cmd_fourn = (
            fournisseurs_valides.groupby("nom_fournisseur", as_index=False)["qte_commande"]
            .sum()
            .sort_values("qte_commande", ascending=False)
            .head(10)
        )
        fig_cmd_fourn = px.bar(df_cmd_fourn, x="nom_fournisseur", y="qte_commande", color="qte_commande", color_continuous_scale="Blues")
        fig_cmd_fourn.update_layout(height=380, template="plotly_white")
        st.plotly_chart(fig_cmd_fourn, use_container_width=True)

    with c2:
        st.subheader("🚨 Risque par fournisseur")
        df_risque_fourn = (
            fournisseurs_valides[fournisseurs_valides["statut"].isin(["URGENT", "CRITIQUE"])]
            .groupby("nom_fournisseur", as_index=False)["code_mp"]
            .nunique()
            .rename(columns={"code_mp": "nb_mp_critiques"})
            .sort_values("nb_mp_critiques", ascending=False)
            .head(10)
        )

        if len(df_risque_fourn) > 0:
            fig_risque_fourn = px.bar(df_risque_fourn, x="nom_fournisseur", y="nb_mp_critiques", color="nb_mp_critiques", color_continuous_scale="Reds")
            fig_risque_fourn.update_layout(height=380, template="plotly_white")
            st.plotly_chart(fig_risque_fourn, use_container_width=True)
        else:
            st.success("Aucun fournisseur critique.")

    fournisseurs_list = sorted([x for x in fournisseurs_valides["nom_fournisseur"].dropna().unique() if str(x).strip() not in ["", "-"]])

    if fournisseurs_list:
        selected_fournisseur = st.selectbox("Choisir fournisseur", fournisseurs_list)
        df_f = fournisseurs_valides[fournisseurs_valides["nom_fournisseur"] == selected_fournisseur].copy()

        st.subheader("MP liées au fournisseur")
        st.dataframe(
            df_f[["code_mp", "designation", "stock_actuel", "besoin_periode_kg", "qte_commande", "moq_kg", "couverture_j", "date_commande", "statut"]],
            use_container_width=True,
            hide_index=True,
        )


# ======================
# PLAN COMMANDE
# ======================
with tab_plan:
    st.subheader("📑 Plan Commande")

    selected_status = st.selectbox("Filtrer par statut", ["Tout", "URGENT", "CRITIQUE", "ATTENTION", "OK"])

    if selected_status == "Tout":
        df_show = plan.copy()
    else:
        df_show = plan[plan["statut"] == selected_status].copy()

    st.dataframe(
        df_show[
            [
                "nom_fournisseur",
                "code_mp",
                "designation",
                "moq_kg",
                "qte_commande",
                "date_besoin",
                "date_commande",
                "statut",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    excel_file = to_excel(plan, top_action)
    pdf_file = to_pdf(plan, start_date, end_date)

    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "📥 Export Excel",
            data=excel_file,
            file_name="plan_appro_mrp.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with d2:
        st.download_button(
            "📄 Télécharger PDF résumé",
            data=pdf_file,
            file_name="resume_plan_appro.pdf",
            mime="application/pdf",
        )


# ======================
# IA
# ======================
with tab_ia:
    st.subheader("🤖 Assistant IA - Actions Approvisionnement")
    question = st.text_input("Pose ta question")

    if st.button("Analyser"):
        st.markdown(chat_ia_local(question, plan))
