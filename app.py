import streamlit as st
from data.google_sheets import load_all_data

st.title("Test Colonnes")

data = load_all_data()

st.subheader("Colonnes Param")
st.write(list(data["param"].columns))

st.subheader("Colonnes Conso")
st.write(list(data["conso"].columns))
