import streamlit as st
import pandas as pd
import plotly.express as px
from data.google_sheets import load_all_data

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="MRP Pro Dashboard V3", layout="wide")

# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
    .main {
        background-color: #f6f8fb;
    }

    .section-title {
        font-size: 26px;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 4px;
    }

    .section-subtitle {
        font-size: 14px;
        color: #6b7280;
        margin-bottom: 18px;
    }

    .kpi-card {
        background: white;
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.06);
        border-left: 6px solid #4f46e5;
        min-height: 125px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        margin-bottom: 14px;
    }

    .kpi-title {
        font-size: 14px;
        color: #6b7280;
        line-height: 1.4;
        word-break: break-word;
    }

    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #111827;
        line-height: 1.2;
        margin-top: 10px;
        word-break: break-word;
    }

    .panel-card {
        background: white;
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.06);
        margin-bottom: 18px;
    }

    .panel-title {
        font-size: 18px;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 12px;
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        border-radius: 14px;
        padding: 14px 16px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        border: 1px solid #eef2f7;
    }

    div[data-testid="stTabs"] {
        margin-top: 8px;
    }

    div[data-testid="stDataFrame"] {
        background: white;
        border-radius: 14px;
        padding: 6px;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# HELPERS
# =========================================================
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
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# =========================================================
# LOAD DATA
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def get_data():
    data = load_all_data()
    for k in data:
        data[k] = normalize_columns(data[k])
    return data

# =========================================================
# PREP TABLES
# =========================================================
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

    required = ["ref_produit_finis", "code_mp", "conso_unit"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Colonne manquante dans Conso: {col}")

    df["ref_produit_finis"] = df["ref_produit_finis"].astype(str).str.strip()
    df["code_mp"] = df["code_mp"].astype(str).str.strip()
    df["conso_unit"] = clean_numeric(df["conso_unit"]).fillna(0)
    df = df[df["conso_unit"] > 0]
    return df

def prepare_mrp(mrp):
    df = mrp.copy()
    product_col = "Ref produit finis"

    if product_col not in df.columns:
        raise ValueError("La colonne 'Ref produit finis' est introuvable dans MRP.")

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

    df_long = df_long.dropna(subset=["date"])
    df_long = df_long[df_long["qte_pf"] > 0]
    return df_long

def prepare_fournisseurs(fournisseurs):
    df = fournisseurs.copy()

    if "code_mp" not in df.columns:
        return pd.DataFrame(columns=["code_mp", "nom_fournisseur"])

    df["code_mp"] = df["code_mp"].astype(str).str.strip()

    if "nom_fournisseur" not in df.columns:
        df["nom_fournisseur"] = ""
    else:
        df["nom_fournisseur"] = df["nom_fournisseur"].astype(str).str.strip()

    for col in ["fiabilite_%", "taux_service_%", "note_qualite_5", "lead_time_j", "moq_kg", "prix_unitaire_eur"]:
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

    cols_to_keep = ["code_mp", "nom_fournisseur"]
    for col in ["fiabilite_%", "taux_service_%", "note_qualite_5", "prix_unitaire_eur", "localisation"]:
        if col in best.columns:
            cols_to_keep.append(col)

    return best[cols_to_keep]

# =========================================================
# BUSINESS LOGIC
# =========================================================
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

    df_pf_mp = (
        df_need.groupby("code_mp", as_index=False)["ref_produit_finis"]
        .agg(lambda x: ", ".join(sorted(set(map(str, x)))))
        .rename(columns={"ref_produit_finis": "liste_pf"})
    )

    df = param_df.merge(besoin_mp, on="code_mp", how="left")
    df = df.merge(date_besoin_mp, on="code_mp", how="left")
    df = df.merge(df_pf_mp, on="code_mp", how="left")
    df = df.merge(fournisseurs_df, on="code_mp", how="left")

    df["besoin_periode_kg"] = df["besoin_periode_kg"].fillna(0)
    df["liste_pf"] = df["liste_pf"].fillna("")
    df["nom_fournisseur"] = df["nom_fournisseur"].fillna("-")

    nb_days = max((pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1, 1)

    df["conso_moy_jour_kg"] = df["besoin_periode_kg"] / nb_days
    df["stock_securite_kg"] = df["conso_moy_jour_kg"] * 3

    df["couverture_j"] = df.apply(
        lambda row: row["stock_actuel"] / row["conso_moy_jour_kg"]
        if row["conso_moy_jour_kg"] > 0 else 999999,
        axis=1
    )

    df["besoin_total_kg"] = df["besoin_periode_kg"] + df["stock_securite_kg"]
    df["manque"] = df["besoin_total_kg"] - df["stock_actuel"]
    df["qte_commande"] = df["manque"].apply(lambda x: max(x, 0))

    df["qte_commande"] = df.apply(
        lambda row: row["moq_kg"] if 0 < row["qte_commande"] < row["moq_kg"] else row["qte_commande"],
        axis=1
    )

    df["a_commander"] = df["qte_commande"] > 0
    df["date_besoin"] = pd.to_datetime(df["date_besoin"], errors="coerce")
    df["date_commande"] = df["date_besoin"] - pd.to_timedelta(df["lead_time_j"], unit="D")

    today = pd.Timestamp.today().normalize()

    def risk_label(row):
        if row["qte_commande"] <= 0:
            return "OK"
        if pd.notna(row["date_commande"]) and pd.Timestamp(row["date_commande"]).normalize() <= today:
            return "URGENT"
        if row["couverture_j"] < row["lead_time_j"]:
            return "CRITIQUE"
        return "ATTENTION"

    df["statut"] = df.apply(risk_label, axis=1)

    if "prix_unitaire_eur" in df.columns:
        df["valeur_commande_eur"] = (df["qte_commande"] * df["prix_unitaire_eur"]).fillna(0)
    else:
        df["valeur_commande_eur"] = 0

    df["date_besoin"] = df["date_besoin"].dt.date
    df["date_commande"] = pd.to_datetime(df["date_commande"], errors="coerce").dt.date

    status_order = {"URGENT": 0, "CRITIQUE": 1, "ATTENTION": 2, "OK": 3}
    df["status_order"] = df["statut"].map(status_order).fillna(9)

    df = df.sort_values(
        by=["status_order", "qte_commande"],
        ascending=[True, False]
    ).reset_index(drop=True)

    return df

# =========================================================
# MAIN
# =========================================================
st.markdown('<div class="section-title">📊 Dashboard Global</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">Vue synthétique des approvisionnements, fournisseurs et stock.</div>', unsafe_allow_html=True)

if st.sidebar.button("🔄 Actualiser maintenant"):
    st.cache_data.clear()
    st.rerun()

data = get_data()

param = data["param"]
conso = data["conso"]
mrp = data["mrp"]
fournisseurs = data["fournisseurs"]

mrp_long = prepare_mrp(mrp)

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.header("Configuration")

date_min = mrp_long["date"].min().date()
date_max = mrp_long["date"].max().date()

mode = st.sidebar.selectbox("Mode période", ["Durée prédéfinie", "Intervalle manuel"])

if mode == "Durée prédéfinie":
    duree = st.sidebar.selectbox("Choisir la durée", ["14 jours", "30 jours", "60 jours", "90 jours"])
    nb_days = {"14 jours": 14, "30 jours": 30, "60 jours": 60, "90 jours": 90}[duree]
    start_date = st.sidebar.date_input("Date début", value=date_min, min_value=date_min, max_value=date_max)
    end_date = min(pd.to_datetime(start_date) + pd.Timedelta(days=nb_days - 1), pd.to_datetime(date_max)).date()
    st.sidebar.info(f"Date fin auto : {end_date}")
else:
    start_date = st.sidebar.date_input("Date début", value=date_min, min_value=date_min, max_value=date_max)
    end_date = st.sidebar.date_input("Date fin", value=date_max, min_value=date_min, max_value=date_max)

if pd.to_datetime(end_date) < pd.to_datetime(start_date):
    st.error("La date fin doit être supérieure ou égale à la date début.")
    st.stop()

mrp_period = mrp_long[
    (mrp_long["date"] >= pd.to_datetime(start_date)) &
    (mrp_long["date"] <= pd.to_datetime(end_date))
].copy()

plan = calculate_plan(param, conso, mrp_period, fournisseurs, start_date, end_date)

# =========================================================
# KPI GLOBAL
# =========================================================
g1, g2, g3, g4, g5, g6 = st.columns(6)

with g1:
    kpi_card("Total MP", int(len(plan)))
with g2:
    kpi_card("MP à commander", int(plan["a_commander"].sum()))
with g3:
    kpi_card("MP urgentes/critiques", int(plan["statut"].isin(["URGENT", "CRITIQUE"]).sum()))
with g4:
    kpi_card("Qté commande (kg)", f"{round(plan['qte_commande'].sum(), 2):,.2f}")
with g5:
    kpi_card("Stock total (kg)", f"{round(plan['stock_actuel'].sum(), 2):,.2f}")
with g6:
    couverture_moy = round(plan["couverture_j"].replace(999999, pd.NA).dropna().mean(), 1) if len(plan) > 0 else 0
    kpi_card("Couverture moy. (j)", couverture_moy)

# =========================================================
# CHARTS
# =========================================================
chart1, chart2 = st.columns(2)

with chart1:
    st.markdown("### Pareto MP à commander")
    pareto_df = plan[plan["qte_commande"] > 0][["code_mp", "qte_commande"]].copy()
    pareto_df = pareto_df.sort_values("qte_commande", ascending=False).head(10)

    if not pareto_df.empty:
        fig_pareto = px.bar(
            pareto_df,
            x="code_mp",
            y="qte_commande",
            title="Top 10 MP par quantité à commander"
        )
        fig_pareto.update_layout(height=380)
        st.plotly_chart(fig_pareto, use_container_width=True)
    else:
        st.info("Aucune MP à commander.")

with chart2:
    st.markdown("### Répartition des statuts")
    status_df = plan["statut"].value_counts().reset_index()
    status_df.columns = ["statut", "count"]

    if not status_df.empty:
        fig_status = px.pie(
            status_df,
            names="statut",
            values="count",
            hole=0.55,
            title="Statuts approvisionnement"
        )
        fig_status.update_layout(height=380)
        st.plotly_chart(fig_status, use_container_width=True)

chart3, chart4 = st.columns(2)

with chart3:
    st.markdown("### Top fournisseurs")
    top_fourn = (
        plan.groupby("nom_fournisseur", as_index=False)["qte_commande"]
        .sum()
        .sort_values("qte_commande", ascending=False)
        .head(8)
    )

    if not top_fourn.empty:
        fig_fourn = px.bar(
            top_fourn,
            x="nom_fournisseur",
            y="qte_commande",
            title="Quantité commandée par fournisseur"
        )
        fig_fourn.update_layout(height=380)
        st.plotly_chart(fig_fourn, use_container_width=True)

with chart4:
    st.markdown("### Couverture stock faible")
    low_cov = plan.copy()
    low_cov = low_cov[low_cov["couverture_j"] != 999999].sort_values("couverture_j", ascending=True).head(10)

    if not low_cov.empty:
        fig_cov = px.bar(
            low_cov,
            x="code_mp",
            y="couverture_j",
            title="Top 10 MP avec plus faible couverture"
        )
        fig_cov.update_layout(height=380)
        st.plotly_chart(fig_cov, use_container_width=True)

# =========================================================
# MAIN ACTION TABLE
# =========================================================
st.markdown("### 📋 Top 10 MP à traiter")
top_action = plan.sort_values(["status_order", "qte_commande"], ascending=[True, False]).head(10)
st.dataframe(
    top_action[[
        "code_mp",
        "designation",
        "nom_fournisseur",
        "stock_actuel",
        "qte_commande",
        "couverture_j",
        "date_commande",
        "statut"
    ]],
    use_container_width=True,
    hide_index=True
)

# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3 = st.tabs([
    "🏭 Vue Fournisseurs",
    "🧱 Vue Matières Premières",
    "📋 Plan détaillé"
])

with tab1:
    st.markdown("### Vue Fournisseurs")

    fournisseurs_list = sorted([x for x in plan["nom_fournisseur"].dropna().unique() if str(x).strip() not in ["", "-"]])

    if fournisseurs_list:
        selected_fournisseur = st.selectbox("Choisir un fournisseur", fournisseurs_list)
        df_f = plan[plan["nom_fournisseur"] == selected_fournisseur].copy()

        r1, r2, r3, r4 = st.columns(4)
        with r1:
            st.metric("Nb MP", int(df_f["code_mp"].nunique()))
        with r2:
            st.metric("Qté commande (kg)", round(df_f["qte_commande"].sum(), 2))
        with r3:
            st.metric("Besoin total (kg)", round(df_f["besoin_total_kg"].sum(), 2))
        with r4:
            cov_f = round(df_f["couverture_j"].replace(999999, pd.NA).dropna().mean(), 1) if len(df_f) else 0
            st.metric("Couverture moy (j)", cov_f)

        fig_f_detail = px.bar(
            df_f.sort_values("qte_commande", ascending=False),
            x="code_mp",
            y="qte_commande",
            title=f"MP liés à {selected_fournisseur}"
        )
        fig_f_detail.update_layout(height=360)
        st.plotly_chart(fig_f_detail, use_container_width=True)

        st.dataframe(
            df_f[[
                "code_mp", "designation", "stock_actuel", "besoin_periode_kg",
                "qte_commande", "couverture_j", "date_commande", "statut"
            ]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Aucun fournisseur disponible.")

with tab2:
    st.markdown("### Vue Matières Premières")

    mp_list = sorted(plan["code_mp"].dropna().unique())
    if mp_list:
        selected_mp = st.selectbox("Choisir une MP", mp_list)
        df_mp = plan[plan["code_mp"] == selected_mp].copy()

        if len(df_mp) > 0:
            row = df_mp.iloc[0]

            a1, a2, a3, a4 = st.columns(4)
            with a1:
                st.metric("Stock actuel", round(row["stock_actuel"], 2))
            with a2:
                st.metric("Besoin période", round(row["besoin_periode_kg"], 2))
            with a3:
                st.metric("Qté commande", round(row["qte_commande"], 2))
            with a4:
                st.metric("Couverture (jours)", round(row["couverture_j"], 2) if row["couverture_j"] != 999999 else 0)

            details_df = pd.DataFrame({
                "Champ": [
                    "Code MP", "Désignation", "Fournisseur", "Lead Time", "MOQ",
                    "Date besoin", "Date commande", "Statut"
                ],
                "Valeur": [
                    row["code_mp"],
                    row["designation"],
                    row["nom_fournisseur"],
                    row["lead_time_j"],
                    row["moq_kg"],
                    row["date_besoin"],
                    row["date_commande"],
                    row["statut"]
                ]
            })
            st.dataframe(details_df, use_container_width=True, hide_index=True)

            st.markdown("#### Produits finis liés")
            pf_list = [x.strip() for x in str(row["liste_pf"]).split(",") if x.strip()]
            pf_df = pd.DataFrame({"Produit fini lié": pf_list})
            st.dataframe(pf_df, use_container_width=True, hide_index=True)

with tab3:
    st.markdown("### Plan Appro détaillé")

    t1, t2 = st.columns(2)
    with t1:
        selected_status = st.selectbox("Filtrer par statut", ["Tout", "URGENT", "CRITIQUE", "ATTENTION", "OK"])
    with t2:
        search_term = st.text_input("Recherche MP / désignation / fournisseur")

    filtered_plan = plan.copy()

    if selected_status != "Tout":
        filtered_plan = filtered_plan[filtered_plan["statut"] == selected_status]

    if search_term:
        s = search_term.strip().lower()
        filtered_plan = filtered_plan[
            filtered_plan["code_mp"].astype(str).str.lower().str.contains(s, na=False)
            | filtered_plan["designation"].astype(str).str.lower().str.contains(s, na=False)
            | filtered_plan["nom_fournisseur"].astype(str).str.lower().str.contains(s, na=False)
        ]

    st.dataframe(
        filtered_plan[[
            "code_mp",
            "designation",
            "nom_fournisseur",
            "stock_actuel",
            "conso_moy_jour_kg",
            "couverture_j",
            "besoin_periode_kg",
            "qte_commande",
            "date_besoin",
            "date_commande",
            "statut"
        ]],
        use_container_width=True,
        hide_index=True
    )
