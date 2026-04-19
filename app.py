import streamlit as st
import pandas as pd
from data.google_sheets import load_all_data

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="MRP - Plan Appro", layout="wide")


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


# =========================================================
# DATA LOADING
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

    rename_map = {
        "Ref produit finis": "ref_produit_finis",
        "CODE matière": "code_mp",
        "conso_unitaire": "conso_unit",
    }
    df = df.rename(columns=rename_map)

    required_cols = ["ref_produit_finis", "code_mp", "conso_unit"]
    for col in required_cols:
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

    if "nom_fournisseur" in df.columns:
        df["nom_fournisseur"] = df["nom_fournisseur"].astype(str).str.strip()
    else:
        df["nom_fournisseur"] = ""

    # nettoyage colonnes utiles si موجودين
    for col in ["fiabilite_%", "taux_service_%", "note_qualite_5", "lead_time_j", "moq_kg", "prix_unitaire_eur"]:
        if col in df.columns:
            df[col] = clean_numeric(df[col])

    # اختيار supplier الأفضل لكل MP: fiabilité الأعلى + lead time الأقل
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

    # MRP x Conso
    df_need = mrp_period.merge(conso_df, on="ref_produit_finis", how="left")
    df_need = df_need.dropna(subset=["code_mp"])
    df_need["besoin_mp_kg"] = df_need["qte_pf"] * df_need["conso_unit"]

    # besoin total par MP
    besoin_mp = (
        df_need.groupby("code_mp", as_index=False)["besoin_mp_kg"]
        .sum()
        .rename(columns={"besoin_mp_kg": "besoin_periode_kg"})
    )

    # أول تاريخ besoin لكل MP
    date_besoin_mp = (
        df_need.groupby("code_mp", as_index=False)["date"]
        .min()
        .rename(columns={"date": "date_besoin"})
    )

    # merge مع param
    df = param_df.merge(besoin_mp, on="code_mp", how="left")
    df = df.merge(date_besoin_mp, on="code_mp", how="left")
    df = df.merge(fournisseurs_df, on="code_mp", how="left")

    df["besoin_periode_kg"] = df["besoin_periode_kg"].fillna(0)

    # المدة المختارة بالأيام
    nb_days = max((pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1, 1)

    # conso moyenne sur période
    df["conso_moy_jour_kg"] = df["besoin_periode_kg"] / nb_days

    # stock sécurité بسيط
    df["stock_securite_kg"] = df["conso_moy_jour_kg"] * 3

    # couverture jours
    df["couverture_j"] = df.apply(
        lambda row: row["stock_actuel"] / row["conso_moy_jour_kg"]
        if row["conso_moy_jour_kg"] > 0 else 999999,
        axis=1
    )

    # besoin total = besoin période + stock sécurité
    df["besoin_total_kg"] = df["besoin_periode_kg"] + df["stock_securite_kg"]

    # manque
    df["manque"] = df["besoin_total_kg"] - df["stock_actuel"]

    # qte commande
    df["qte_commande"] = df["manque"].apply(lambda x: max(x, 0))

    # respecter MOQ
    df["qte_commande"] = df.apply(
        lambda row: row["moq_kg"] if 0 < row["qte_commande"] < row["moq_kg"] else row["qte_commande"],
        axis=1
    )

    # a commander
    df["a_commander"] = df["qte_commande"] > 0

    # date commande
    df["date_besoin"] = pd.to_datetime(df["date_besoin"], errors="coerce")
    df["date_commande"] = df["date_besoin"] - pd.to_timedelta(df["lead_time_j"], unit="D")

    today = pd.Timestamp.today().normalize()

    # priorité
    df["priorite_score"] = df.apply(
        lambda row: (row["qte_commande"] / row["besoin_total_kg"]) if row["besoin_total_kg"] > 0 else 0,
        axis=1
    )

    def risk_label(row):
        if row["qte_commande"] <= 0:
            return "🟢 OK"
        if pd.notna(row["date_commande"]) and row["date_commande"].normalize() <= today:
            return "🔴 URGENT"
        if row["couverture_j"] < row["lead_time_j"]:
            return "🔴 CRITIQUE"
        return "🟠 ATTENTION"

    df["statut"] = df.apply(risk_label, axis=1)

    # coût risque تقريبي إذا كان prix موجود
    if "prix_unitaire_eur" in df.columns:
        df["valeur_commande_eur"] = (df["qte_commande"] * df["prix_unitaire_eur"]).fillna(0)
    else:
        df["valeur_commande_eur"] = 0

    # formatting dates
    df["date_besoin"] = df["date_besoin"].dt.date
    df["date_commande"] = pd.to_datetime(df["date_commande"], errors="coerce").dt.date

    # tri
    status_order = {"🔴 URGENT": 0, "🔴 CRITIQUE": 1, "🟠 ATTENTION": 2, "🟢 OK": 3}
    df["status_order"] = df["statut"].map(status_order).fillna(9)

    df = df.sort_values(
        by=["status_order", "qte_commande", "priorite_score"],
        ascending=[True, False, False]
    ).reset_index(drop=True)

    return df


# =========================================================
# UI
# =========================================================
st.title("📦 Plan Approvisionnement Intelligent")

if st.sidebar.button("🔄 Actualiser maintenant"):
    st.cache_data.clear()
    st.rerun()

data = get_data()

param = data["param"]
conso = data["conso"]
mrp = data["mrp"]
fournisseurs = data["fournisseurs"]

mrp_long = prepare_mrp(mrp)

st.sidebar.header("Période")
mode = st.sidebar.selectbox("Mode", ["Durée prédéfinie", "Intervalle manuel"])

date_min = mrp_long["date"].min().date()
date_max = mrp_long["date"].max().date()

if mode == "Durée prédéfinie":
    duree = st.sidebar.selectbox("Choisir la durée", ["14 jours", "30 jours", "60 jours", "90 jours"])
    nb_days = {"14 jours": 14, "30 jours": 30, "60 jours": 60, "90 jours": 90}[duree]

    start_date = st.sidebar.date_input("Date début", value=date_min, min_value=date_min, max_value=date_max)
    end_date = min(pd.to_datetime(start_date) + pd.Timedelta(days=nb_days - 1), pd.to_datetime(date_max))
    end_date = end_date.date()
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
# KPIs
# =========================================================
st.subheader("📊 KPIs")

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total MP", int(len(plan)))
col2.metric("À commander", int((plan["a_commander"]).sum()))
col3.metric("Urgents/Critiques", int(plan["statut"].isin(["🔴 URGENT", "🔴 CRITIQUE"]).sum()))
col4.metric("Qté totale commande (kg)", round(plan["qte_commande"].sum(), 2))
col5.metric("Valeur commande (€)", round(plan["valeur_commande_eur"].sum(), 2))

st.caption(f"Période analysée : du {start_date} au {end_date}")

# =========================================================
# FILTERS
# =========================================================
with st.expander("⚙️ Filtres"):
    status_options = ["Tout", "🔴 URGENT", "🔴 CRITIQUE", "🟠 ATTENTION", "🟢 OK"]
    selected_status = st.selectbox("Filtrer par statut", status_options)

    search_term = st.text_input("Recherche MP / désignation / fournisseur")

filtered_plan = plan.copy()

if selected_status != "Tout":
    filtered_plan = filtered_plan[filtered_plan["statut"] == selected_status]

if search_term:
    s = search_term.strip().lower()
    filtered_plan = filtered_plan[
        filtered_plan["code_mp"].astype(str).str.lower().str.contains(s, na=False)
        | filtered_plan["designation"].astype(str).str.lower().str.contains(s, na=False)
        | filtered_plan.get("nom_fournisseur", pd.Series("", index=filtered_plan.index)).astype(str).str.lower().str.contains(s, na=False)
    ]

# =========================================================
# TABLE
# =========================================================
st.subheader("📋 Plan Approvisionnement")

display_cols = [
    "code_mp",
    "designation",
    "nom_fournisseur",
    "lead_time_j",
    "moq_kg",
    "stock_actuel",
    "conso_moy_jour_kg",
    "stock_securite_kg",
    "besoin_periode_kg",
    "besoin_total_kg",
    "manque",
    "qte_commande",
    "couverture_j",
    "date_besoin",
    "date_commande",
    "statut",
]

display_cols = [c for c in display_cols if c in filtered_plan.columns]

st.dataframe(filtered_plan[display_cols], use_container_width=True)

# =========================================================
# DEBUG / RAW DATA
# =========================================================
with st.expander("🔍 Voir MRP filtré"):
    st.dataframe(mrp_period, use_container_width=True)

with st.expander("🧪 Vérification colonnes"):
    st.write("Param:", list(param.columns))
    st.write("Conso:", list(conso.columns))
    st.write("MRP:", list(mrp.columns))
    st.write("Fournisseurs:", list(fournisseurs.columns))
