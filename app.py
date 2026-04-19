import streamlit as st
from data.google_sheets import load_all_data

st.title("Test Google Sheets")

data = load_all_data()

st.subheader("Param")
st.write(data["param"])

st.subheader("MRP")
st.write(data["mrp"])

st.subheader("Fournisseurs")
st.write(data["fournisseurs"])

st.subheader("Conso")
st.write(data["conso"])

import pandas as pd

def calculate_plan(param, conso):
    # merge data
    df = param.merge(conso, on="code_mp")

    # consommation journalière
    df["conso_j"] = df["conso_mensuelle"] / 30

    # couverture
    df["couverture_j"] = df["stock_actuel"] / df["conso_j"]

    # besoin
    df["besoin"] = df["lead_time_j"] - df["couverture_j"]

    # decision
    df["a_commander"] = df["besoin"] > 0

    # quantité
    df["qte_commande"] = df.apply(
        lambda x: x["moq_kg"] if x["a_commander"] else 0,
        axis=1
    )

    return df

data = load_all_data()

df = calculate_plan(data["param"], data["conso"])

st.subheader("Plan Approvisionnement")
st.write(df)
