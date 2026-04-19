import streamlit as st
import pandas as pd
from data.google_sheets import load_all_data

# -----------------------------
# Nettoyage colonnes numériques
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
# Fonction calcul Plan Appro
# -----------------------------
def calculate_plan(param, conso):
    param = param.copy()
    conso = conso.copy()

    # Nettoyage colonnes param
    param["lead_time_j"] = clean_numeric(param["lead_time_j"])
    param["moq_kg"] = clean_numeric(param["moq_kg"])
    param["stock_actuel"] = clean_numeric(param["stock_actuel"])

    # Renommer colonnes conso
    conso = conso.rename(columns={
        "CODE matière": "code_mp",
        "conso journaliere MP en KG": "conso_jour_kg"
    })

    # Nettoyage conso
    conso["conso_jour_kg"] = clean_numeric(conso["conso_jour_kg"])

    # Agrégation conso par matière
    conso_grouped = (
        conso.groupby("code_mp", as_index=False)["conso_jour_kg"]
        .sum()
    )

    # Merge
    df = param.merge(conso_grouped, on="code_mp", how="left")

    # Valeurs nulles
    df["conso_jour_kg"] = df["conso_jour_kg"].fillna(0)

    # Couverture en jours
    df["couverture_j"] = df.apply(
        lambda row: row["stock_actuel"] / row["conso_jour_kg"]
        if row["conso_jour_kg"] > 0 else 999,
        axis=1
    )

    # Besoin pendant lead time
    df["besoin_lt"] = df["conso_jour_kg"] * df["lead_time_j"]

    # Décision achat
    df["a_commander"] = df["stock_actuel"] < df["besoin_lt"]

    # Quantité à commander
    df["qte_commande"] = df.apply(
        lambda row: max(row["moq_kg"], row["besoin_lt"] - row["stock_actuel"])
        if row["a_commander"] else 0,
        axis=1
    )

    # Statut
    df["statut"] = df["a_commander"].apply(
        lambda x: "CRITIQUE" if x else "OK"
    )

    return df

# -----------------------------
# App Streamlit
# -----------------------------
st.set_page_config(page_title="Smart Forecast", layout="wide")

st.title("📊 Smart Forecast - Plan Approvisionnement")

# Chargement data
data = load_all_data()

# Debug optionnel
with st.expander("Voir colonnes"):
    st.write("Param:", list(data["param"].columns))
    st.write("Conso:", list(data["conso"].columns))

# Calcul
df = calculate_plan(data["param"], data["conso"])

# KPIs
st.subheader("📌 KPIs")
col1, col2, col3 = st.columns(3)

col1.metric("Total matières", len(df))
col2.metric("À commander", int(df["a_commander"].sum()))
col3.metric("Critiques", int((df["statut"] == "CRITIQUE").sum()))

# Tableau final
st.subheader("📦 Plan Approvisionnement")
st.dataframe(df, use_container_width=True)
