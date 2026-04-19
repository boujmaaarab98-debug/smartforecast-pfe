import streamlit as st
import pandas as pd
from data.google_sheets import load_all_data

# -----------------------------
# 🎯 Fonction calcul Plan Appro
# -----------------------------
def calculate_plan(param, conso):
    conso = conso.copy()

    # 🔧 توحيد أسماء الأعمدة
    conso = conso.rename(columns={
        "CODE matière": "code_mp",
        "conso journaliere MP en KG": "conso_jour_kg"
    })

    # 🔢 تجميع الاستهلاك حسب MP
    conso_grouped = conso.groupby("code_mp", as_index=False)["conso_jour_kg"].sum()

    # 🔗 Merge
    df = param.merge(conso_grouped, on="code_mp", how="left")

    # 🧼 تنظيف القيم
    df["conso_jour_kg"] = df["conso_jour_kg"].fillna(0)

    # 📊 Couverture (jours)
    df["couverture_j"] = df.apply(
        lambda row: row["stock_actuel"] / row["conso_jour_kg"] if row["conso_jour_kg"] > 0 else 999,
        axis=1
    )

    # 📦 Besoin pendant lead time
    df["besoin_lt"] = df["conso_jour_kg"] * df["lead_time_j"]

    # 🧠 Decision achat
    df["a_commander"] = df["stock_actuel"] < df["besoin_lt"]

    # 📥 Quantité à commander
    df["qte_commande"] = df.apply(
        lambda row: max(row["moq_kg"], row["besoin_lt"] - row["stock_actuel"]) if row["a_commander"] else 0,
        axis=1
    )

    # 🚨 Statut
    df["statut"] = df.apply(
        lambda row: "CRITIQUE" if row["a_commander"] else "OK",
        axis=1
    )

    return df

# -----------------------------
# 🚀 Streamlit App
# -----------------------------
st.set_page_config(page_title="Smart Forecast", layout="wide")

st.title("📊 Smart Forecast - Plan Approvisionnement")

# Load data
data = load_all_data()

# Display raw data
with st.expander("📂 Voir les données brutes"):
    st.write("Param")
    st.dataframe(data["param"])

    st.write("Conso")
    st.dataframe(data["conso"])

# Calculate
df = calculate_plan(data["param"], data["conso"])

# Display result
st.subheader("📦 Plan Approvisionnement")

st.dataframe(df)

# KPI simple
st.subheader("📊 Indicateurs")

col1, col2, col3 = st.columns(3)

col1.metric("Total Articles", len(df))
col2.metric("Articles à commander", df["a_commander"].sum())
col3.metric("Stock critique", (df["statut"] == "CRITIQUE").sum())
