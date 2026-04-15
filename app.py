import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import io

st.set_page_config(page_title="Smart Forecast - Plan d'Approvisionnement", layout="wide")

st.title("🚀 Smart Forecast - Plan d'Approvisionnement IA")
st.markdown("### Prophet + Fenêtre Glissante + Chat IA")

# Paramètres
HORIZON_JOURS = 30
SEUIL_RUPTURE = 7

# Upload fichiers
col1, col2 = st.columns(2)
with col1:
    fichier_conso = st.file_uploader("📊 Upload Fichier Consommation (conso.xlsx)", type=['xlsx'])
with col2:
    fichier_param = st.file_uploader("⚙️ Upload Fichier Paramètres (param.xlsx)", type=['xlsx'])

if fichier_conso and fichier_param:
    df_conso = pd.read_excel(fichier_conso)
    df_param = pd.read_excel(fichier_param)
    
    st.success(f"✅ Fichiers chargés: {len(df_conso)} lignes conso, {len(df_param)} matières")
    
    if st.button("🚀 Générer Plan Appro b IA", type="primary"):
        with st.spinner("⏳ Calcul en cours avec Prophet + Fenêtre Glissante..."):
            
            liste_mp = df_param['Code_MP'].unique()
            resultats_globaux = []
            progress_bar = st.progress(0)
            
            for i, code_mp in enumerate(liste_mp):
                try:
                    # Filter data for this MP
                    df_mp = df_conso[df_conso['Code_MP'] == code_mp].copy()
                    df_mp['Date'] = pd.to_datetime(df_mp['Date'])
                    df_mp = df_mp.sort_values('Date')
                    
                    # Prophet Forecast
                    df_prophet = df_mp.rename(columns={'Date': 'ds', 'Qte_Consommee': 'y'})
                    model = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True)
                    model.fit(df_prophet)
                    future = model.make_future_dataframe(periods=HORIZON_JOURS)
                    forecast = model.predict(future)
                    
                    # Calcul QTE_A_COMMANDER
                    besoin_total = forecast['yhat'].tail(HORIZON_JOURS).sum()
                    stock_actuel = df_param[df_param['Code_MP'] == code_mp]['Stock_Actuel'].values[0]
                    qte_commander = max(0, besoin_total - stock_actuel)
                    
                    # Cout
                    prix = df_param[df_param['Code_MP'] == code_mp]['Prix_Unitaire_EUR'].values[0]
                    cout = qte_commander * prix
                    
                    designation = df_param[df_param['Code_MP'] == code_mp]['Designation'].values[0]
                    
                    resultats_globaux.append({
                        'Code_MP': code_mp,
                        'Designation': designation,
                        'Stock_Actuel_kg': stock_actuel,
                        'Besoin_Prevu_kg': besoin_total,
                        'QTE_A_COMMANDER_kg': qte_commander,
                        'Prix_Unitaire_EUR': prix,
                        'Cout_Commande_EUR': cout
                    })
                except:
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
                col2.metric("📦 MP à Commander", f"{len(df_plan[df_plan['QTE_A_COMMANDER_kg']>0])}")
                col3.metric("📅 Horizon", f"{HORIZON_JOURS} jours")
                
                st.dataframe(df_plan, use_container_width=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_plan.to_excel(writer, index=False, sheet_name='Plan_Appro')
                st.download_button(
                    label="📥 Télécharger Plan Appro Excel",
                    data=output.getvalue(),
                    file_name=f"Plan_Appro_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("❌ Makaynch résultats")

# ============================================
# CHAT IA - SW
