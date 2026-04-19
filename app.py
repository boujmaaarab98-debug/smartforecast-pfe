import streamlit as st
import pandas as pd
from data.google_sheets import load_all_data

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="MRP Pro Dashboard", layout="wide")

# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
    .main {
        background-color: #f7f9fc;
    }
    .kpi-card {
        background: white;
        padding: 18px 20px;
        border-radius: 16px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06);
        border-left: 6px solid #4f46e5;
        margin-bottom: 10px;
    }
    .kpi-title {
        font-size: 15px;
        color: #6b7280;
        margin-bottom: 8px;
    }
    .kpi-value {
        font-size: 32px;
        font-weight: 700;
        color: #111827;
    }
    .section-title {
        font-size: 28px;
        font-weight: 700;
        margin-top: 10px;
        margin-bottom: 10px;
        color: #111827;
    }
    .subtle {
        color: #6b7280;
        font-size: 14px;
    }
    .block-card {
        background: white;
        padding: 18px;
        border-radius: 16px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        margin-bottom: 18px;
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
# PREPARE TABLES
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

    df["priorite_score"] = df.apply(
        lambda row: (row["qte_commande"] / row["besoin_total_kg"]) if row["besoin_total_kg"] > 0 else 0,
        axis=1
    )

    def risk_label(row):
        if row["qte_commande"] <= 0:
            return "🟢 OK"
        if pd.notna(row["date_commande"]) and pd.Timestamp(row["date_commande"]).normalize() <= today:
            return "🔴 URGENT"
        if row["couverture_j"] < row["lead_time_j"]:
            return "🔴 CRITIQUE"
        return "🟠 ATTENTION"

    df["statut"] = df.apply(risk_label, axis=1)

    if "prix_unitaire_eur" in df.columns:
        df["valeur_commande_eur"] = (df["qte_commande"] * df["prix_unitaire_eur"]).fillna(0)
    else:
        df["valeur_commande_eur"] = 0

    df["date_besoin"] = df["date_besoin"].dt.date
    df["date_commande"] = pd.to_datetime(df["date_commande"], errors="coerce").dt.date

    status_order = {"🔴 URGENT": 0, "🔴 CRITIQUE": 1, "🟠 ATTENTION": 2, "🟢 OK": 3}
    df["status_order"] = df["statut"].map(status_order).fillna(9)

    df = df.sort_values(
        by=["status_order", "qte_commande", "priorite_score"],
        ascending=[True, False, False]
    ).reset_index(drop=True)

    return df

# =========================================================
# MAIN
# =========================================================
st.markdown('<div class="section-title">📦 MRP Pro Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="subtle">Vision claire par KPI, fournisseur, matière première et stock.</div>', unsafe_allow_html=True)

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
st.markdown("### 📊 Dashboard Global")

g1, g2, g3, g4, g5 = st.columns(5)
with g1:
    kpi_card("Total MP", int(len(plan)))
with g2:
    kpi_card("MP à commander", int(plan["a_commander"].sum()))
with g3:
    kpi_card("Urgents/Critiques", int(plan["statut"].isin(["🔴 URGENT", "🔴 CRITIQUE"]).sum()))
with g4:
    kpi_card("Qté commande (kg)", round(plan["qte_commande"].sum(), 2))
with g5:
    kpi_card("Valeur commande (€)", round(plan["valeur_commande_eur"].sum(), 2))

# =========================================================
# KPI FOURNISSEURS + STOCK
# =========================================================
row_a, row_b = st.columns([1, 1])

with row_a:
    st.markdown('<div class="block-card">', unsafe_allow_html=True)
    st.markdown("#### 🏭 KPIs Fournisseurs")

    nb_fournisseurs = plan["nom_fournisseur"].fillna("").replace("", pd.NA).dropna().nunique()
    fournisseurs_critiques = plan[plan["statut"].isin(["🔴 URGENT", "🔴 CRITIQUE"])]["nom_fournisseur"].fillna("").replace("", pd.NA).dropna().nunique()
    top_supplier = (
        plan.groupby("nom_fournisseur", dropna=False)["qte_commande"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    top_supplier_name = top_supplier.iloc[0]["nom_fournisseur"] if len(top_supplier) > 0 and pd.notna(top_supplier.iloc[0]["nom_fournisseur"]) and top_supplier.iloc[0]["nom_fournisseur"] != "" else "-"

    f1, f2, f3 = st.columns(3)
    with f1:
        st.metric("Nb fournisseurs", nb_fournisseurs)
    with f2:
        st.metric("Fournisseurs critiques", fournisseurs_critiques)
    with f3:
        st.metric("Top fournisseur", top_supplier_name)

    st.markdown('</div>', unsafe_allow_html=True)

with row_b:
    st.markdown('<div class="block-card">', unsafe_allow_html=True)
    st.markdown("#### 📦 KPIs Stock")

    couverture_moy = round(plan["couverture_j"].replace(999999, pd.NA).dropna().mean(), 1) if len(plan) > 0 else 0
    stock_total = round(plan["stock_actuel"].sum(), 2)
    stock_risque = int((plan["couverture_j"] < plan["lead_time_j"]).sum())

    s1, s2, s3 = st.columns(3)
    with s1:
        st.metric("Stock total (kg)", stock_total)
    with s2:
        st.metric("Couverture moyenne (j)", couverture_moy)
    with s3:
        st.metric("MP risque rupture", stock_risque)

    st.markdown('</div>', unsafe_allow_html=True)

# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Plan Appro",
    "🏭 Vue Fournisseurs",
    "🧱 Vue Matières Premières",
    "🔍 Analyse détaillée"
])

# =========================================================
# TAB 1 - PLAN APPRO
# =========================================================
with tab1:
    st.markdown("### 📋 Plan Approvisionnement")
    t1, t2 = st.columns([1, 1])

    with t1:
        selected_status = st.selectbox("Filtrer par statut", ["Tout", "🔴 URGENT", "🔴 CRITIQUE", "🟠 ATTENTION", "🟢 OK"])
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

    display_cols = [
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
    ]

    st.dataframe(filtered_plan[display_cols], use_container_width=True)

# =========================================================
# TAB 2 - FOURNISSEURS
# =========================================================
with tab2:
    st.markdown("### 🏭 Vue Fournisseurs")

    fournisseurs_list = sorted([x for x in plan["nom_fournisseur"].dropna().unique() if str(x).strip() != ""])
    selected_fournisseur = st.selectbox("Choisir un fournisseur", fournisseurs_list)

    df_f = plan[plan["nom_fournisseur"] == selected_fournisseur].copy()

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Nb MP", int(df_f["code_mp"].nunique()))
    with k2:
        st.metric("Qté commande (kg)", round(df_f["qte_commande"].sum(), 2))
    with k3:
        st.metric("MP critiques", int(df_f["statut"].isin(["🔴 URGENT", "🔴 CRITIQUE"]).sum()))
    with k4:
        st.metric("Stock moyen (kg)", round(df_f["stock_actuel"].mean(), 2) if len(df_f) else 0)

    st.markdown("#### MP liés à ce fournisseur")
    st.dataframe(
        df_f[[
            "code_mp", "designation", "stock_actuel", "besoin_periode_kg",
            "qte_commande", "couverture_j", "date_commande", "statut"
        ]],
        use_container_width=True
    )

# =========================================================
# TAB 3 - MP
# =========================================================
with tab3:
    st.markdown("### 🧱 Vue Matières Premières")

    mp_list = sorted(plan["code_mp"].dropna().unique())
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

        st.markdown("#### Détails MP")
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

        st.markdown("#### PF liés à cette MP")
        pf_list = [x.strip() for x in str(row["liste_pf"]).split(",") if x.strip()]
        pf_df = pd.DataFrame({"Produit fini lié": pf_list})
        st.dataframe(pf_df, use_container_width=True, hide_index=True)

# =========================================================
# TAB 4 - ANALYSE DETAILLEE
# =========================================================
with tab4:
    left, right = st.columns([1, 1])

    with left:
        st.markdown("### 🔴 Top MP critiques")
        critical_df = plan[plan["statut"].isin(["🔴 URGENT", "🔴 CRITIQUE"])].copy()
        st.dataframe(
            critical_df[[
                "code_mp", "designation", "nom_fournisseur",
                "stock_actuel", "qte_commande", "date_commande", "statut"
            ]],
            use_container_width=True
        )

    with right:
        st.markdown("### 📉 MP avec plus faible couverture")
        low_cov = plan.sort_values("couverture_j", ascending=True).copy()
        st.dataframe(
            low_cov[[
                "code_mp", "designation", "couverture_j",
                "lead_time_j", "stock_actuel", "statut"
            ]].head(10),
            use_container_width=True
        )

    st.markdown("### 🔍 Données sources")
    with st.expander("Voir MRP filtré"):
        st.dataframe(mrp_period, use_container_width=True)

    with st.expander("Voir colonnes"):
        st.write("Param:", list(param.columns))
        st.write("Conso:", list(conso.columns))
        st.write("MRP:", list(mrp.columns))
        st.write("Fournisseurs:", list(fournisseurs.columns))
