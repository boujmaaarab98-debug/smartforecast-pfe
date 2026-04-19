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
