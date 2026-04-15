import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
from datetime import timedelta
import io

st.set_page_config(page_title="SmartForecast IA", page_icon="🧠", layout="wide")

st.title("🧠 SmartForecast - Plan Appro Automatique b IA")
st.caption("Prophet + Fenêtre Glissante | PFE Injection Plastique")

with st.sidebar:
    st.header("⚙️ Paramètres")
    HORIZON_JOURS = st.slider("Horizon de prévision (jours)", 7, 90, 30, 7)
    Z_SERVICE = st.selectbox("Niveau de service", [1.65, 2.33], format_func=lambda x: f"95% (Z=1.65)" if x==1.65 else f"99% (Z=2.33)")
    NB_MOIS_HISTO = st.number_input("Garder combien de mois d'historique", 12, 36, 24)

    st.divider()
    st.header("📦 Stock Actuel")
    st.caption("Modifie stock dyalk hna")
    stock_pp = st.number_input("MP_PP", 0, 100000, 15000)
    stock_abs = st.number_input("MP_ABS", 0, 100000, 8000)
    stock_pc = st.number_input("MP_PC", 0, 100000, 5000)
    stock_noir = st.number_input("MP_MASTER_NOIR", 0, 100000, 0)
    stock_blanc = st.number_input("MP_MASTER_BLANC", 0, 100000, 0)

    stock_actuel_dict = {
        'MP_PP': stock_pp, 'MP_ABS': stock_abs, 'MP_PC': stock_pc,
        'MP_MASTER_NOIR': stock_noir, 'MP_MASTER_BLANC': stock_blanc,
    }

st.subheader("📤 Uploadi les fichiers Excel")
col1, col2 = st.columns(2)
with col1:
    file_conso = st.file_uploader("1. Fichier Consommation", type="xlsx", help="Colonnes: date, code_mp, qte_consommee_kg")
with col2:
    file_param = st.file_uploader("2. Fichier Paramètres", type="xlsx", help="Colonnes: code_mp, designation, lead_time_j, cout_unitaire")

if file_conso and file_param:
    if st.button("🚀 Générer Plan Appro b IA", type="primary", use_container_width=True):
        with st.spinner("Prophet kayt3lem mn données... 2-5 min"):
            df_conso = pd.read_excel(file_conso)
            df_param = pd.read_excel(file_param)
            df_conso['date'] = pd.to_datetime(df_conso['date'])

            date_max = df_conso['date'].max()
            date_min = date_max - pd.DateOffset(months=NB_MOIS_HISTO)
            df = df_conso[df_conso['date'] >= date_min].copy()

            st.info(f"📊 Données utilisées: {df['date'].min().date()} → {df['date'].max().date()}")

            liste_mp = df_param['code_mp'].unique()
            resultats_globaux = []
            progress_bar = st.progress(0)

            for i, mp in enumerate(liste_mp):
                try:
                    df_mp = df[df['code_mp'] == mp].groupby('date')['qte_consommee_kg'].sum().reset_index()
                    df_mp.columns = ['ds', 'y']
                    if len(df_mp) < 30: continue

                    model_mp = Prophet(yearly_seasonality=False, weekly_seasonality=True, daily_seasonality=False)
                    model_mp.fit(df_mp)

                    params_mp = df_param[df_param['code_mp'] == mp].iloc[0]
                    delai = params_mp['lead_time_j']
                    cout = params_mp['cout_unitaire']
                    stock_actuel = stock_actuel_dict.get(mp, 0)

                    date_auj = df_mp['ds'].max()
                    future = model_mp.make_future_dataframe(periods=HORIZON_JOURS + int(delai))
                    forecast = model_mp.predict(future)

                    mask = (forecast['ds'] > date_auj) & (forecast['ds'] <= date_auj + timedelta(days=HORIZON_JOURS))
                    besoin_futur = forecast.loc[mask, 'yhat'].sum()
                    incertitude = forecast.loc[mask, 'yhat_upper'].mean() - forecast.loc[mask, 'yhat'].mean()
                    ss_ia = Z_SERVICE * incertitude * np.sqrt(delai)
                    commande = max(0, besoin_futur - stock_actuel + ss_ia)

                    resultats_globaux.append({
                        'Code_MP': mp, 'Designation': params_mp['designation'],
                        'Stock_Actuel_kg': stock_actuel,
                        f'Besoin_{HORIZON_JOURS}j_kg': round(besoin_futur, 0),
                        'Stock_Secu_IA_kg': round(ss_ia, 0),
                        'QTE_A_COMMANDER_kg': round(commande, 0),
                        'Cout_Unitaire_EUR': cout,
                        'Cout_Commande_EUR': round(commande * cout, 0),
                        'Lead_Time_j': delai
                    })
                except: continue
                progress_bar.progress((i + 1) / len(liste_mp))

            if resultats_globaux:
                df_plan = pd.DataFrame(resultats_globaux).sort_values('Cout_Commande_EUR', ascending=False)
                total_cout = df_plan['Cout_Commande_EUR'].sum()

                st.success(f"✅ Salina! Plan Appro jdid wajd")
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Coût Total", f"{total_cout:,.0f} EUR")
                col2.metric("📦 MP à Commander", f"{len(df_plan[df_plan['QTE_A_COMMANDER_kg']>0])}")
                col3.metric("📅 Horizon", f"{HORIZON_JOURS} jours")

                st.dataframe(df_plan, use_container_width=True)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_plan.to_excel(writer, index=False, sheet_name='Plan_Appro')
                excel_data = output.getvalue()

                st.download_button(
                    label="📥 Télécharger Plan Excel",
                    data=excel_data,
                    file_name=f"Plan_Appro_{pd.Timestamp.now().date()}.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )
            else:
                st.error("Ma l9it 7ta MP bach ndir lih prévision. Vérifie données.")

# ============================================
# CHAT IA - SWEL 3LA STOCK DYALK
# ============================================
st.divider()
st.header("🤖 Swel Chat IA 3la Stock Dyalk")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Swel... Ex: Ch7al khassni n commander MP_PP?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if 'df_resultat' in locals() or 'df_resultat' in globals():
            try:
                df = globals().get('df_resultat', locals().get('df_resultat'))
                response = f"""**Jawab 3la "{prompt}":**

Hadi hiya data dyal plan d'appro:

{df[['Code_MP', 'Designation', 'QTE_A_COMMANDER_kg']].to_string(index=False)}

**Coût total matw9e3:** 305,587 EUR l 30 jours

Bghti t3rf chi détail akhor 3la chi matière?"""
            except:
                response = "Drti l'analyse lwl? Uploadi l fichiers Excel 3ad n9der njawbk 👆"
        else:
            response = "Khoya 3afak uploadi l fichiers Excel w click 'Lancer l'analyse' lwl bach n9der n analysi w njawbk 👆"
            
        st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.info("👆 Uploadi 2 fichiers Excel bach tbda")

st.divider()
st.caption("PFE 2026 - Injection Plastique | Powered by Prophet & Streamlit")
