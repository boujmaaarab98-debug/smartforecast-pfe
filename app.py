import streamlit as st
import pandas as pd
from data.google_sheets import load_all_data

# -----------------------------
# Nettoyage numérique
# -----------------------------
def clean_numeric(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True),
        errors="coerce"
    )

# -----------------------------
# Préparation MRP (wide → long)
# -----------------------------
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

    df_long = df_long.rename(columns={
        "Ref produit finis": "ref_produit_finis"
    })

    df_long["date"] = pd.to_datetime(df_long["date"], dayfirst=True, errors="coerce")
    df_long["qte_pf"] = clean_numeric(df_long["qte_pf"]).fillna(0)

    df_long = df_long.dropna(subset=["date"])
    df_long = df_long[df_long["qte_pf"] > 0]

    return df_long

# -----------------------------
# Calcul MRP → MP
# -----------------------------
def calculate_plan(param, conso, mrp_period):

    # nettoyage param
    param["lead_time_j"] = clean_numeric(param["lead_time_j"])
    param["moq_kg"] = clean_numeric(param["moq_kg"])
    param["stock_actuel"] = clean_numeric(param["stock_actuel"])

    # rename conso
    conso = conso.rename(columns={
        "CODE matière": "code_mp",
        "Ref produit finis": "ref_produit_finis",
        "conso_unitaire": "conso_unit"
    })

    conso["conso_unit"] = clean_numeric(conso["conso_unit"])

    # merge MRP + Conso
    df_need = mrp_period.merge(conso, on="ref_produit_finis", how="left")

    # besoin MP
    df_need["besoin_mp_kg"] = df_need["qte_pf"] * df_need["conso_unit"]

    # agrégation par MP
    besoin_mp = df_need.groupby("code_mp", as_index=False)["besoin_mp_kg"].sum()

    # merge avec param
    df = param.merge(besoin_mp, on="code_mp", how="left")
    df["besoin_mp_kg"] = df["besoin_mp_kg"].fillna(0)

    # calcul commande
    df["manque"] = df["besoin_mp_kg"] - df["stock_actuel"]

    df["qte_commande"] = df["manque"].apply(lambda x: max(x, 0))

    # respect MOQ
    df["qte_commande"] = df.apply(
        lambda row: row["moq_kg"] if 0 < row["qte_commande"] < row["moq_kg"] else row["qte_commande"],
        axis=1
    )

    # statut
    df["statut"] = df["qte_commande"].apply(
        lambda x: "🔴 CRITIQUE" if x > 0 else "🟢 OK"
    )

    # priorité (tri)
    df = df.sort_values(by="qte_commande", ascending=False)

    return df

# -----------------------------
# APP
# -----------------------------
st.set_page_config(layout="wide")
st.title("📊 MRP - Plan Approvisionnement Intelligent")

data = load_all_data()

param = data["param"]
conso = data["conso"]
mrp = data["mrp"]

mrp_long = prepare_mrp(mrp)

# 🎯 اختيار المدة
st.sidebar.header("Période")

duree = st.sidebar.selectbox(
    "Choisir la durée",
    ["14 jours", "30 jours", "60 jours", "90 jours"]
)

nb_days = {
    "14 jours": 14,
    "30 jours": 30,
    "60 jours": 60,
    "90 jours": 90
}[duree]

date_start = mrp_long["date"].min()
date_end = date_start + pd.Timedelta(days=nb_days)

mrp_period = mrp_long[
    (mrp_long["date"] >= date_start) &
    (mrp_long["date"] <= date_end)
]

# 🔥 calcul final
plan = calculate_plan(param, conso, mrp_period)

# -----------------------------
# KPIs
# -----------------------------
st.subheader("📊 KPIs")

c1, c2, c3 = st.columns(3)

c1.metric("Total MP", len(plan))
c2.metric("À commander", int((plan["qte_commande"] > 0).sum()))
c3.metric("Qté totale (kg)", round(plan["qte_commande"].sum(), 2))

# -----------------------------
# TABLE
# -----------------------------
st.subheader("📦 Plan Approvisionnement")

st.dataframe(plan, use_container_width=True)
