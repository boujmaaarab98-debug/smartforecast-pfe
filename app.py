import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import io

st.set_page_config(page_title="Smart Forecast - Plan d'Approvisionnement", layout="wide")

st.title("🚀 Smart Forecast - Plan d'Approvisionnement IA")
st.markdown("### Prophet + Fenêtre Glissante + Chat IA")

HORIZON_JOURS = 30

col1, col2 = st.columns(2)
with col1:
    fichier_conso = st.file_uploader("📊 Upload Fichier Consommation (conso.xlsx)", type=['xlsx'])
with col2:
    fichier_param = st.file_uploader("⚙️ Upload Fichier Paramètres (param.xlsx)", type=['xlsx'])

if fichier_conso and fichier_param:
    df_conso = pd.read_excel(fichier_conso)
    df_param = pd.read_excel(fichier_param)

    st.success(f"✅ Fichiers chargés: {len(df_conso)} lignes conso, {len(df_param)} matières")

    with st.expander("🔍 Vérifier les colonnes de tes fichiers"):
        st.write("**Colonnes Conso:**", df_conso.columns.tolist())
        st.write("**Colonnes Param:**", df_param.columns.tolist())

    # AUTO-DETECT COLONNES PARAM
    col_code_mp = None
    for col in ['code_mp', 'Code_MP', 'Code MP', 'CodeMP', 'Ref_MP', 'Ref', 'Code']:
        if col in df_param.columns:
            col_code_mp = col
            break

    col_designation = None
    for col in ['designation', 'Designation', 'Désignation', 'Nom', 'Libelle', 'Produit', 'Libellé']:
        if col in df_param.columns:
            col_designation = col
            break

    col_stock = None
    for col in ['stock_actuel', 'Stock_Actuel', 'Stock Actuel', 'Stock', 'Qte_Stock', 'Stock_Initial']:
        if col in df_param.columns:
            col_stock = col
            break

    col_prix = None
    for col in ['prix_unitaire_eur', 'Prix_Unitaire_EUR', 'Prix', 'Prix_Unitaire', 'Cout', 'Prix_Unit']:
        if col in df_param.columns:
            col_prix = col
            break

    # AUTO-DETECT COLONNES CONSO
    col_date_conso = None
    for col in ['date', 'Date', 'Date_Consommation', 'Date_Conso', 'Jour']:
        if col in df_conso.columns:
            col_date_conso = col
            break

    col_qte_conso = None
    for col in ['qte_consommee_kg', 'Qte_Consommee', 'Qte_Consommée', 'Quantite', 'Qte', 'Consommation', 'Qte_Conso']:
        if col in df_conso.columns:
            col_qte_conso = col
            break

    # CHECK
    erreurs = []
    if not col_code_mp: erreurs.append("code_mp")
    if not col_date_conso: erreurs.append("date")
    if not col_qte_conso: erreurs.append("qte_consommee_kg")
    if not col_stock: erreurs.append("stock_actuel")
    if not col_prix: erreurs.append("prix_unitaire_eur")
    if not col_designation: erreurs.append("designation")

    if erreurs:
        st.error(f"❌ Ma l9itch had les colonnes: {', '.join(erreurs)}")
        st.stop()

    if st.button("🚀 Générer Plan Appro b IA", type="primary"):
        with st.spinner("⏳ Calcul en cours..."):

            liste_mp = df_param[col_code_mp].unique()
            resultats_globaux = []
            progress_bar = st.progress(0)

            for i, code_mp in enumerate(liste_mp):
                try:
                    df_mp = df_conso[df_conso[col_code_mp] == code_mp].copy()
                    df_mp[col_date_conso] = pd.to_datetime(df_mp[col_date_conso])
                    df_mp = df_mp.sort_values(col_date_conso)

                    if len(df_mp) < 2:
                        continue

                    df_prophet = df_mp.rename(columns={col_date_conso: 'ds', col_qte_conso: 'y'})
                    model = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True)
                    model.fit(df_prophet)
                    future = model.make_future_dataframe(periods=HORIZON_JOURS)
                    forecast = model.predict(future)

                    besoin_total = forecast['yhat'].tail(HORIZON_JOURS).sum()
                    stock_actuel = df_param[df_param[col_code_mp] == code_mp][col_stock].values[0]
                    qte_commander = max(0, besoin_total - stock_actuel)
                    prix = df_param[df_param[col_code_mp] == code_mp][col_prix].values[0]
                    cout = qte_commander * prix
                    designation = df_param[df_param[col_code_mp] == code_mp][col_designation].values[0]

                    resultats_globaux.append({
                        'Code_MP': code_mp,
                        'Designation': designation,
                        'Stock_Actuel_kg': stock_actuel,
                        'Besoin_Prevu_kg': besoin_total,
                        'QTE_A_COMMANDER_kg': qte_commander,
                        'Prix_Unitaire_EUR': prix,
                        'Cout_Commande_EUR': cout
                    })
                except Exception as e:
                    continue

                progress_bar.progress((i + 1) / len(liste_mp))

            if resultats_globaux:
                df_plan = pd.DataFrame(resultats_globaux).sort_values('Cout_Commande_EUR', ascending=False)
                total_cout = df_plan['Cout_Commande_EUR'].sum()
                st.session_state['df_resultat'] = df_plan
                st.session_state['cout_total'] = total_cout
                st.success(f"✅ Salina! Plan Appro jdid wajd")
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Coût Total", f"{total_cout:,.0f} EUR")
                col2.metric("📦 MP à Commander", f"{len(df_plan[df_plan['QTE_A_COMMANDER_
