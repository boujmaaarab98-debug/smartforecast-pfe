import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from data.google_sheets import load_all_data

st.set_page_config(page_title="MRP Pro V4", layout="wide")

# =========================
# LOGIN
# =========================
try:
    APP_PASSWORD = st.secrets.get("APP_PASSWORD", "admin123")
except Exception:
    APP_PASSWORD = "admin123"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("""
    <style>
    .login-box {
        max-width: 420px;
        margin: 120px auto;
        padding: 35px;
        background: white;
        border-radius: 22px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.10);
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-box"><h1>🏭 MRP Pro</h1><p>Accès sécurisé entreprise</p></div>', unsafe_allow_html=True)
    pwd = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter"):
        if pwd == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

# =========================
# CSS
# =========================
st.markdown("""
<style>
.main {background-color:#f6f8fb;}
.kpi-card {
    background:white; border-radius:18px; padding:18px 20px;
    box-shadow:0 4px 14px rgba(0,0,0,0.06);
    border-left:6px solid #2563eb; min-height:120px;
}
.kpi-title {font-size:14px;color:#6b7280;}
.kpi-value {font-size:26px;font-weight:800;color:#111827;margin-top:12px;}
.section-title {font-size:28px;font-weight:800;color:#111827;margin-bottom:4px;}
.section-subtitle {font-size:14px;color:#6b7280;margin-bottom:18px;}
</style>
""", unsafe_allow_html=True)

# =========================
# HELPERS
# =========================
def clean_numeric(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True),
        errors="coerce"
    )

def normalize_columns(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def kpi_card(title, value):
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">{title}</div>
        <div class="kpi-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=60, show_spinner=False)
def get_data():
    data = load_all_data()
    for k in data:
        data[k] = normalize_columns(data[k])
    return data

def prepare_param(param):
    df = param.copy()
    df["code_mp"] = df["code_mp"].astype(str).str.strip()
    df["designation"] = df["designation"].astype(str).str.strip()
    df["lead_time_j"] = clean_numeric(df["lead_time_j"]).fillna(0)
    df["moq_kg"] = clean_numeric(df["moq_kg"]).fillna(0)
    df["stock_actuel"] = clean_numeric(df["stock_actuel"]).fillna(0)
    return df

def prepare_conso(conso):
    df = conso.copy()
    df = df.rename(columns={
        "Ref produit finis": "ref_produit_finis",
        "CODE matière": "code_mp",
        "conso_unitaire": "conso_unit"
    })
    df["ref_produit_finis"] = df["ref_produit_finis"].astype(str).str.strip()
    df["code_mp"] = df["code_mp"].astype(str).str.strip()
    df["conso_unit"] = clean_numeric(df["conso_unit"]).fillna(0)
    return df[df["conso_unit"] > 0]

def prepare_mrp(mrp):
    df = mrp.copy()
    product_col = "Ref produit finis"
    date_cols = [c for c in df.columns if c != product_col]

    df_long = df.melt(
        id_vars=[product_col],
        value_vars=date_cols,
        var_name="date",
        value_name="qte_pf"
    )

    df_long = df_long.rename(columns={product_col: "ref_produit_finis"})
    df_long["ref_produit_finis"] = df_long["ref_produit_finis"].astype(str).str.strip()
    df_long["date"] = pd.to_datetime(df_long["date"], dayfirst=True, errors="coerce")
    df_long["qte_pf"] = clean_numeric(df_long["qte_pf"]).fillna(0)

    return df_long.dropna(subset=["date"]).query("qte_pf > 0")

def prepare_fournisseurs(fournisseurs):
    df = fournisseurs.copy()
    if "code_mp" not in df.columns:
        return pd.DataFrame(columns=["code_mp", "nom_fournisseur"])

    df["code_mp"] = df["code_mp"].astype(str).str.strip()
    df["nom_fournisseur"] = df.get("nom_fournisseur", "").astype(str).str.strip()

    for col in ["fiabilite_%", "taux_service_%", "note_qualite_5", "lead_time_j", "prix_unitaire_eur"]:
        if col in df.columns:
            df[col] = clean_numeric(df[col])

    sort_cols, ascending = [], []
    if "fiabilite_%" in df.columns:
        sort_cols.append("fiabilite_%"); ascending.append(False)
    if "lead_time_j" in df.columns:
        sort_cols.append("lead_time_j"); ascending.append(True)

    if sort_cols:
        df = df.sort_values(sort_cols, ascending=ascending)

    keep = ["code_mp", "nom_fournisseur"]
    for col in ["fiabilite_%", "taux_service_%", "note_qualite_5", "prix_unitaire_eur", "localisation"]:
        if col in df.columns:
            keep.append(col)

    return df.groupby("code_mp", as_index=False).first()[keep]

def calculate_plan(param, conso, mrp_period, fournisseurs, start_date, end_date):
    param_df = prepare_param(param)
    conso_df = prepare_conso(conso)
    fournisseurs_df = prepare_fournisseurs(fournisseurs)

    df_need = mrp_period.merge(conso_df, on="ref_produit_finis", how="left").dropna(subset=["code_mp"])
    df_need["besoin_mp_kg"] = df_need["qte_pf"] * df_need["conso_unit"]

    besoin_mp = df_need.groupby("code_mp", as_index=False)["besoin_mp_kg"].sum().rename(columns={"besoin_mp_kg":"besoin_periode_kg"})
    date_besoin_mp = df_need.groupby("code_mp", as_index=False)["date"].min().rename(columns={"date":"date_besoin"})
    pf_mp = df_need.groupby("code_mp", as_index=False)["ref_produit_finis"].agg(lambda x: ", ".join(sorted(set(map(str, x))))).rename(columns={"ref_produit_finis":"liste_pf"})

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
    df["couverture_j"] = df.apply(lambda r: r["stock_actuel"] / r["conso_moy_jour_kg"] if r["conso_moy_jour_kg"] > 0 else 999999, axis=1)

    df["besoin_total_kg"] = df["besoin_periode_kg"] + df["stock_securite_kg"]
    df["manque"] = df["besoin_total_kg"] - df["stock_actuel"]
    df["qte_commande"] = df["manque"].apply(lambda x: max(x, 0))
    df["qte_commande"] = df.apply(lambda r: r["moq_kg"] if 0 < r["qte_commande"] < r["moq_kg"] else r["qte_commande"], axis=1)

    df["a_commander"] = df["qte_commande"] > 0
    df["date_besoin"] = pd.to_datetime(df["date_besoin"], errors="coerce")
    df["date_commande"] = df["date_besoin"] - pd.to_timedelta(df["lead_time_j"], unit="D")

    today = pd.Timestamp.today().normalize()

    def risk_label(r):
        if r["qte_commande"] <= 0:
            return "OK"
        if pd.notna(r["date_commande"]) and pd.Timestamp(r["date_commande"]).normalize() <= today:
            return "URGENT"
        if r["couverture_j"] < r["lead_time_j"]:
            return "CRITIQUE"
        return "ATTENTION"

    df["statut"] = df.apply(risk_label, axis=1)
    df["valeur_commande_eur"] = df["qte_commande"] * df["prix_unitaire_eur"] if "prix_unitaire_eur" in df.columns else 0

    df["date_besoin"] = df["date_besoin"].dt.date
    df["date_commande"] = pd.to_datetime(df["date_commande"], errors="coerce").dt.date

    status_order = {"URGENT":0, "CRITIQUE":1, "ATTENTION":2, "OK":3}
    df["status_order"] = df["statut"].map(status_order).fillna(9)

    return df.sort_values(["status_order", "qte_commande"], ascending=[True, False]).reset_index(drop=True)

# =========================
# EXPORTS
# =========================
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

    story.append(Paragraph("Résumé Plan Approvisionnement - MRP Pro", styles["Title"]))
    story.append(Paragraph(f"Période analysée : {start_date} au {end_date}", styles["Normal"]))
    story.append(Spacer(1, 12))

    kpis = [
        ["Indicateur", "Valeur"],
        ["Total MP", str(len(plan))],
        ["MP à commander", str(int(plan["a_commander"].sum()))],
        ["Urgents/Critiques", str(int(plan["statut"].isin(["URGENT", "CRITIQUE"]).sum()))],
        ["Quantité commande kg", str(round(plan["qte_commande"].sum(), 2))],
        ["Stock total kg", str(round(plan["stock_actuel"].sum(), 2))]
    ]

    table = Table(kpis)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ]))
    story.append(table)
    story.append(Spacer(1, 18))

    top = plan.head(10)[["code_mp", "nom_fournisseur", "qte_commande", "date_commande", "statut"]]
    data = [["MP", "Fournisseur", "Qté", "Date commande", "Statut"]] + top.astype(str).values.tolist()

    story.append(Paragraph("Top 10 actions prioritaires", styles["Heading2"]))
    table2 = Table(data)
    table2.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.4, colors.grey),
        ("FONTSIZE", (0,0), (-1,-1), 8),
    ]))
    story.append(table2)

    doc.build(story)
    buffer.seek(0)
    return buffer

# =========================
# CHAT IA LOCAL
# =========================
def chat_ia_local(question, plan):
    q = question.lower().strip()

    urgent = plan[plan["statut"].isin(["URGENT", "CRITIQUE"])].copy()
    top = plan.sort_values(["status_order", "qte_commande"], ascending=[True, False]).head(5)

    if q == "":
        return "Pose une question comme : *شنو خاصني ندير اليوم؟* ou *analyse fournisseur lyondellbasell*."

    if "action" in q or "شنو" in q or "اليوم" in q or "urgent" in q:
        lines = ["### Actions prioritaires recommandées"]
        for _, r in top.iterrows():
            if r["qte_commande"] > 0:
                lines.append(f"- **{r['code_mp']}**: commander **{round(r['qte_commande'],2)} kg** chez **{r['nom_fournisseur']}**, statut **{r['statut']}**, avant **{r['date_commande']}**.")
        return "\n".join(lines)

    if "fournisseur" in q or "supplier" in q:
        fournisseur_names = [x for x in plan["nom_fournisseur"].dropna().unique() if str(x) != "-"]
        for f in fournisseur_names:
            if str(f).lower() in q:
                df_f = plan[plan["nom_fournisseur"] == f]
                return f"""
### Analyse fournisseur : {f}
- Nombre MP : **{df_f['code_mp'].nunique()}**
- Qté à commander : **{round(df_f['qte_commande'].sum(),2)} kg**
- MP critiques : **{int(df_f['statut'].isin(['URGENT','CRITIQUE']).sum())}**
- Action : prioriser les MP avec couverture faible et date commande dépassée.
"""
        return "Écris le nom du fournisseur dans ta question, par exemple : *analyse fournisseur lyondellbasell*."

    if "stock" in q or "rupture" in q:
        low = plan[plan["couverture_j"] != 999999].sort_values("couverture_j").head(5)
        lines = ["### Risque stock / rupture"]
        for _, r in low.iterrows():
            lines.append(f"- **{r['code_mp']}**: couverture **{round(r['couverture_j'],1)} jours**, lead time **{r['lead_time_j']} jours**, statut **{r['statut']}**.")
        return "\n".join(lines)

    if "mp" in q:
        for mp in plan["code_mp"].astype(str).unique():
            if mp.lower() in q:
                r = plan[plan["code_mp"].astype(str) == mp].iloc[0]
                return f"""
### Analyse MP : {mp}
- Désignation : **{r['designation']}**
- Fournisseur : **{r['nom_fournisseur']}**
- Stock actuel : **{round(r['stock_actuel'],2)} kg**
- Besoin période : **{round(r['besoin_periode_kg'],2)} kg**
- Qté à commander : **{round(r['qte_commande'],2)} kg**
- Couverture : **{round(r['couverture_j'],1) if r['couverture_j'] != 999999 else 0} jours**
- PF liés : **{r['liste_pf']}**
"""
        return "Écris le code MP dans ta question, par exemple : *analyse MP MP0005*."

    return "Je peux t’aider sur : actions urgentes, fournisseur, stock/rupture, ou analyse d’une MP."

# =========================
# MAIN
# =========================
st.markdown('<div class="section-title">🏭 MRP Pro V4 - Dashboard Intelligent</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">Approvisionnement, fournisseurs, stock, actions prioritaires et assistant IA.</div>', unsafe_allow_html=True)

if st.sidebar.button("🔄 Actualiser maintenant"):
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("🚪 Déconnexion"):
    st.session_state.authenticated = False
    st.rerun()

data = get_data()
param, conso, mrp, fournisseurs = data["param"], data["conso"], data["mrp"], data["fournisseurs"]
mrp_long = prepare_mrp(mrp)

st.sidebar.header("Configuration période")
date_min, date_max = mrp_long["date"].min().date(), mrp_long["date"].max().date()

mode = st.sidebar.selectbox("Mode période", ["Durée prédéfinie", "Intervalle manuel"])
if mode == "Durée prédéfinie":
    duree = st.sidebar.selectbox("Durée", ["14 jours", "30 jours", "60 jours", "90 jours"])
    nb_days = {"14 jours":14, "30 jours":30, "60 jours":60, "90 jours":90}[duree]
    start_date = st.sidebar.date_input("Date début", value=date_min, min_value=date_min, max_value=date_max)
    end_date = min(pd.to_datetime(start_date) + pd.Timedelta(days=nb_days-1), pd.to_datetime(date_max)).date()
else:
    start_date = st.sidebar.date_input("Date début", value=date_min, min_value=date_min, max_value=date_max)
    end_date = st.sidebar.date_input("Date fin", value=date_max, min_value=date_min, max_value=date_max)

mrp_period = mrp_long[(mrp_long["date"] >= pd.to_datetime(start_date)) & (mrp_long["date"] <= pd.to_datetime(end_date))]
plan = calculate_plan(param, conso, mrp_period, fournisseurs, start_date, end_date)

# KPIs
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: kpi_card("Total MP", int(len(plan)))
with c2: kpi_card("MP à commander", int(plan["a_commander"].sum()))
with c3: kpi_card("Urgents/Critiques", int(plan["statut"].isin(["URGENT","CRITIQUE"]).sum()))
with c4: kpi_card("Qté commande kg", f"{round(plan['qte_commande'].sum(),2):,.2f}")
with c5: kpi_card("Stock total kg", f"{round(plan['stock_actuel'].sum(),2):,.2f}")
with c6:
    cov = round(plan["couverture_j"].replace(999999, pd.NA).dropna().mean(),1)
    kpi_card("Couverture moy.", cov)

# Charts
status_colors = {"URGENT":"#dc2626", "CRITIQUE":"#f97316", "ATTENTION":"#facc15", "OK":"#16a34a"}

colA, colB = st.columns(2)

with colA:
    st.subheader("📊 Pareto cumulative MP")
    pareto = plan[plan["qte_commande"] > 0][["code_mp","qte_commande"]].sort_values("qte_commande", ascending=False).head(10)
    if not pareto.empty:
        pareto["cum_pct"] = pareto["qte_commande"].cumsum() / pareto["qte_commande"].sum() * 100
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=pareto["code_mp"], y=pareto["qte_commande"], name="Qté commande", marker_color="#2563eb"), secondary_y=False)
        fig.add_trace(go.Scatter(x=pareto["code_mp"], y=pareto["cum_pct"], name="% cumulé", mode="lines+markers", line=dict(color="#dc2626", width=3)), secondary_y=True)
        fig.update_yaxes(title_text="Qté commande", secondary_y=False)
        fig.update_yaxes(title_text="% cumulé", secondary_y=True, range=[0,110])
        fig.update_layout(height=380, template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

with colB:
    st.subheader("🧭 Répartition statuts")
    status_df = plan["statut"].value_counts().reset_index()
    status_df.columns = ["statut", "count"]
    fig_status = px.pie(status_df, names="statut", values="count", hole=0.55, color="statut", color_discrete_map=status_colors)
    fig_status.update_layout(height=380, template="plotly_white")
    st.plotly_chart(fig_status, use_container_width=True)

colC, colD = st.columns(2)

with colC:
    st.subheader("🏭 Top fournisseurs")
    top_f = plan.groupby("nom_fournisseur", as_index=False)["qte_commande"].sum().sort_values("qte_commande", ascending=False).head(8)
    fig_f = px.bar(top_f, x="nom_fournisseur", y="qte_commande", color="qte_commande", color_continuous_scale="Blues")
    fig_f.update_layout(height=360, template="plotly_white")
    st.plotly_chart(fig_f, use_container_width=True)

with colD:
    st.subheader("📉 Couverture stock faible")
    low_cov = plan[plan["couverture_j"] != 999999].sort_values("couverture_j").head(10)
    fig_cov = px.bar(low_cov, x="code_mp", y="couverture_j", color="statut", color_discrete_map=status_colors)
    fig_cov.update_layout(height=360, template="plotly_white")
    st.plotly_chart(fig_cov, use_container_width=True)

# Action table
st.subheader("🎯 Top actions prioritaires")
top_action = plan.head(10)
st.dataframe(
    top_action[["code_mp","designation","nom_fournisseur","stock_actuel","qte_commande","couverture_j","date_commande","statut"]],
    use_container_width=True,
    hide_index=True
)

# Downloads
excel_file = to_excel(plan, top_action)
pdf_file = to_pdf(plan, start_date, end_date)

d1,d2 = st.columns(2)
with d1:
    st.download_button("📥 Export Excel", data=excel_file, file_name="plan_appro_mrp.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with d2:
    st.download_button("📄 Télécharger PDF résumé", data=pdf_file, file_name="resume_plan_appro.pdf", mime="application/pdf")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["🏭 Fournisseurs", "🧱 Matières Premières", "📋 Plan détaillé", "🤖 Chat IA"])

with tab1:
    fournisseurs_list = sorted([x for x in plan["nom_fournisseur"].dropna().unique() if str(x) not in ["", "-"]])
    if fournisseurs_list:
        f = st.selectbox("Choisir fournisseur", fournisseurs_list)
        df_f = plan[plan["nom_fournisseur"] == f]
        st.metric("Qté totale à commander", round(df_f["qte_commande"].sum(),2))
        st.dataframe(df_f[["code_mp","designation","stock_actuel","besoin_periode_kg","qte_commande","couverture_j","statut"]], use_container_width=True, hide_index=True)

with tab2:
    mp = st.selectbox("Choisir MP", sorted(plan["code_mp"].unique()))
    r = plan[plan["code_mp"] == mp].iloc[0]
    st.metric("Qté commande", round(r["qte_commande"],2))
    st.metric("Couverture jours", round(r["couverture_j"],2) if r["couverture_j"] != 999999 else 0)
    st.write("**PF liés :**")
    st.write(r["liste_pf"])

with tab3:
    selected_status = st.selectbox("Statut", ["Tout","URGENT","CRITIQUE","ATTENTION","OK"])
    df_show = plan if selected_status == "Tout" else plan[plan["statut"] == selected_status]
    st.dataframe(df_show, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("🤖 Assistant IA - Actions Approvisionnement")
    question = st.text_input("Pose ta question")
    if st.button("Analyser"):
        st.markdown(chat_ia_local(question, plan))
