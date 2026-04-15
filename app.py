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
    
    # WERI LES COLONNES BACH T3REF CHNO FIH FICHIER DYALK
    with st.expander("🔍 Vérifier les colonnes de tes fichiers"):
        st.write("**Colonnes Conso:**", df_conso.columns.tolist())
        st.write("**Colonnes Param:**", df_param.columns.tolist())
    
    # AUTO-DETECT LES NOMS DYAL COLONNES
    col_code_mp = None
    for col in ['Code_MP', 'Code MP', 'code_mp', 'CodeMP', 'Ref_MP', 'Ref']:
        if col in df_param.columns:
            col_code_mp = col
            break
    
    col_designation = None
    for col in ['Designation', 'Désignation', 'Nom', 'Libelle', 'Produit']:
        if col in df_param.columns:
            col_designation = col
            break
    
    col_stock = None
    for col in ['Stock_Actuel', 'Stock Actuel', 'Stock', 'Qte_Stock']:
        if col in df_param.columns:
            col_stock = col
            break
    
    col_prix = None
    for col in ['Prix_Unitaire_EUR', 'Prix', 'Prix_Unitaire', 'Cout']:
        if col in df_param.columns:
            col_prix = col
            break
    
    # CHECK ILA L9A LES COLONNES
    if not col_code_mp:
        st.error("❌ Ma l9itch colonne dyal Code MP f param.xlsx. Check smiyat les colonnes foug")
        st.stop()
    
    if st.button("🚀 Générer Plan Appro b IA", type="primary"):
        with st.spinner("⏳ Calcul en cours..."):
            
            liste_mp = df_param[col_code_mp].unique()
            resultats_globaux = []
            progress_bar = st.progress(0)
            
            for i, code_mp in enumerate(liste_mp):
                try:
                    df_mp = df_conso[df_conso[col_code_mp] == code_mp].copy()
                    df_mp['Date'] = pd.to_datetime(df_mp['Date'])
                    df_mp = df_mp.sort_values('Date')
                    
                    df_prophet = df_mp.rename(columns={'Date': 'ds', 'Qte_Consommee': 'y'})
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
                    st.warning(f"⚠️ {code_mp}: {str(e)}")
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
# CHAT IA - KAYBAN GHIR MN B3D MA TGÉNÉRI L PLAN
# ============================================
if 'df_resultat' in st.session_state:
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
            df = st.session_state['df_resultat']
            cout = st.session_state.get('cout_total', 0)
            
            if "MP_PP" in prompt.upper():
                mp_pp = df[df['Code_MP'].str.contains('MP_PP', na=False, case=False)]
                if not mp_pp.empty:
                    qte = mp_pp['QTE_A_COMMANDER_kg'].values[0]
                    response = f"**MP_PP - PP Noir:** Khassk t commander **{qte:,.0f} kg** 💪"
                else:
                    response = "MP_PP ma kaynach f plan d'appro had chhar ✅"
            elif "coût" in prompt.lower() or "cout" in prompt.lower() or "total" in prompt.lower():
                response = f"**Coût Total matw9e3:** {cout:,.0f} EUR l {HORIZON_JOURS} jours 📊"
            elif "akbar" in prompt.lower():
                max_row = df.loc[df['QTE_A_COMMANDER_kg'].idxmax()]
                response = f"**Akbar quantité:** {max_row['Designation']} → **{max_row['QTE_A_COMMANDER_kg']:,.0f} kg**"
            else:
                response = f"""**Plan d'appro dyalk:**

{df[['Code_MP', 'Designation', 'QTE_A_COMMANDER_kg']].head().to_string(index=False)}

**Coût total:** {cout:,.0f} EUR

Swel 3la chi matière b t7did!"""
                
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.info("👆 Uploadi l fichiers w click 'Générer Plan Appro b IA' bach yt7ll lik Chat")
