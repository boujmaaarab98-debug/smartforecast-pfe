import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import io
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Smart Forecast Pro", layout="wide", page_icon="🚀")

st.title("🚀 Smart Forecast Pro - Assistant IA Supply Chain")
st.markdown("### Prophet AI + Alertes + Consultant Stratégique IA")

HORIZON_JOURS = 30

with st.sidebar:
    st.header("⚙️ Paramètres")
    HORIZON_JOURS = st.slider("Horizon Prévision (jours)", 7, 90, 30)
    st.divider()
    st.markdown("**📊 Fichiers:**")
    st.markdown("- `conso.xlsx`: date, code_mp, qte_consommee_kg")
    st.markdown("- `param.xlsx`: code_mp, designation, cout_unitaire, stock_secu_actuel, moq_kg, lead_time_j")

col1, col2 = st.columns(2)
with col1:
    fichier_conso = st.file_uploader("📊 Upload Consommation", type=['xlsx'])
with col2:
    fichier_param = st.file_uploader("⚙️ Upload Paramètres", type=['xlsx'])

if fichier_conso and fichier_param:
    df_conso = pd.read_excel(fichier_conso)
    df_param = pd.read_excel(fichier_param)

    st.success(f"✅ Fichiers chargés: {len(df_conso)} lignes, {len(df_param)} matières")

    col_code_mp = 'code_mp'
    col_designation = 'designation'
    col_stock = 'stock_secu_actuel'
    col_prix = 'cout_unitaire'
    col_moq = 'moq_kg'
    col_lead = 'lead_time_j'
    col_date_conso = 'date'
    col_qte_conso = 'qte_consommee_kg'

    required_cols = [col_code_mp, col_designation, col_stock, col_prix, col_moq, col_lead]
    missing = [c for c in required_cols if c not in df_param.columns]
    if missing:
        st.error(f"❌ Colonnes manquantes: {', '.join(missing)}")
        st.stop()

    if st.button("🚀 Générer Plan + Dashboard IA", type="primary", use_container_width=True):
        with st.spinner("⏳ Calcul IA + Analyse Stratégique..."):
            liste_mp = df_param[col_code_mp].unique()
            resultats_globaux = []
            forecasts_dict = {}
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

                    forecasts_dict[code_mp] = forecast

                    besoin_total = forecast['yhat'].tail(HORIZON_JOURS).sum()
                    stock_actuel = df_param[df_param[col_code_mp] == code_mp][col_stock].values[0]
                    prix = df_param[df_param[col_code_mp] == code_mp][col_prix].values[0]
                    moq = df_param[df_param[col_code_mp] == code_mp][col_moq].values[0]
                    lead_time = df_param[df_param[col_code_mp] == code_mp][col_lead].values[0]
                    designation = df_param[df_param[col_code_mp] == code_mp][col_designation].values[0]

                    besoin_net = max(0, besoin_total - stock_actuel)
                    qte_commander = np.ceil(besoin_net / moq) * moq if besoin_net > 0 else 0

                    couverture_jours = stock_actuel / (besoin_total / HORIZON_JOURS) if besoin_total > 0 else 999
                    if couverture_jours < lead_time:
                        status = "🔴 URGENT - Risque Rupture"
                        urgence = 3
                        risque = "CRITIQUE"
                    elif couverture_jours < lead_time + 7:
                        status = "🟠 Attention - Stock Faible"
                        urgence = 2
                        risque = "MOYEN"
                    else:
                        status = "🟢 OK - Stock Suffisant"
                        urgence = 1
                        risque = "FAIBLE"

                    date_commande = pd.Timestamp.now() + pd.Timedelta(days=max(0, int(couverture_jours - lead_time)))
                    jours_retard = max(0, lead_time - couverture_jours)

                    resultats_globaux.append({
                        'Code_MP': code_mp,
                        'Designation': designation,
                        'Stock_Actuel_kg': stock_actuel,
                        'Besoin_Prevu_kg': round(besoin_total, 1),
                        'QTE_A_COMMANDER_kg': qte_commander,
                        'MOQ_kg': moq,
                        'Prix_Unitaire_EUR': prix,
                        'Cout_Commande_EUR': round(qte_commander * prix, 2),
                        'Lead_Time_j': lead_time,
                        'Couverture_jours': round(couverture_jours, 1),
                        'Date_Commande_Suggeree': date_commande.strftime('%Y-%m-%d'),
                        'Jours_Retard_Potentiel': round(jours_retard, 1),
                        'Status': status,
                        'Risque': risque,
                        'Urgence': urgence
                    })
                except Exception as e:
                    continue

                progress_bar.progress((i + 1) / len(liste_mp))

            if resultats_globaux:
                df_plan = pd.DataFrame(resultats_globaux).sort_values('Urgence', ascending=False)
                st.session_state['df_resultat'] = df_plan
                st.session_state['forecasts'] = forecasts_dict
                st.session_state['cout_total'] = df_plan['Cout_Commande_EUR'].sum()

                st.success(f"✅ Dashboard Généré! {len(df_plan)} matières analysées")

                st.divider()
                st.subheader("📊 Dashboard KPIs")

                col1, col2, col3, col4 = st.columns(4)
                total_cout = df_plan['Cout_Commande_EUR'].sum()
                nb_urgent = len(df_plan[df_plan['Urgence'] == 3])
                nb_attention = len(df_plan[df_plan['Urgence'] == 2])
                nb_commander = len(df_plan[df_plan['QTE_A_COMMANDER_kg'] > 0])

                col1.metric("💰 Coût Total", f"{total_cout:,.0f} EUR", delta=f"{nb_commander} MP")
                col2.metric("🔴 Critique", f"{nb_urgent}", delta="Action immédiate", delta_color="inverse")
                col3.metric("🟠 Attention", f"{nb_attention}", delta="À surveiller", delta_color="off")
                col4.metric("📦 À Commander", f"{nb_commander}/{len(df_plan)}", delta=f"{HORIZON_JOURS}j")

                st.divider()
                st.subheader("⚠️ Alertes Critiques")

                df_urgent = df_plan[df_plan['Urgence'] >= 2]
                if len(df_urgent) > 0:
                    for _, row in df_urgent.iterrows():
                        if row['Urgence'] == 3:
                            st.error(f"🔴 **{row['Code_MP']} - {row['Designation']}**: Stock {row['Stock_Actuel_kg']:.0f}kg | Couverture {row['Couverture_jours']:.0f}j < Lead Time {row['Lead_Time_j']:.0f}j | **Retard potentiel: {row['Jours_Retard_Potentiel']:.0f}j** | COMMANDER {row['QTE_A_COMMANDER_kg']:.0f}kg MAINTENANT")
                        else:
                            st.warning(f"🟠 **{row['Code_MP']} - {row['Designation']}**: Stock {row['Stock_Actuel_kg']:.0f}kg | Couverture {row['Couverture_jours']:.0f}j | Commander {row['QTE_A_COMMANDER_kg']:.0f}kg avant {row['Date_Commande_Suggeree']}")
                else:
                    st.success("✅ Aucune alerte - Tous les stocks sont suffisants!")

                st.divider()
                st.subheader("📋 Plan d'Approvisionnement")

                colf1, colf2 = st.columns(2)
                with colf1:
                    filtre_status = st.multiselect("Filtrer par Status", df_plan['Status'].unique(), default=df_plan['Status'].unique())
                with colf2:
                    show_only_order = st.checkbox("Afficher seulement MP à commander", value=False)

                df_display = df_plan[df_plan['Status'].isin(filtre_status)]
                if show_only_order:
                    df_display = df_display[df_display['QTE_A_COMMANDER_kg'] > 0]

                st.dataframe(df_display.drop('Urgence', axis=1), use_container_width=True, height=400)

                st.divider()
                st.subheader("📈 Visualisations")

                tab1, tab2, tab3 = st.tabs(["💰 Coûts", "📦 Quantités", "📊 Prévision"])

                with tab1:
                    df_chart = df_plan[df_plan['Cout_Commande_EUR'] > 0].nlargest(15, 'Cout_Commande_EUR')
                    fig = px.bar(df_chart, x='Code_MP', y='Cout_Commande_EUR', color='Status',
                                title="Top 15 Coûts de Commande",
                                color_discrete_map={'🔴 URGENT - Risque Rupture': '#ff4444',
                                                   '🟠 Attention - Stock Faible': '#ffaa00',
                                                   '🟢 OK - Stock Suffisant': '#44ff44'})
                    st.plotly_chart(fig, use_container_width=True)

                with tab2:
                    df_top = df_plan.nlargest(10, 'QTE_A_COMMANDER_kg')
                    fig = px.bar(df_top, x='QTE_A_COMMANDER_kg', y='Designation', orientation='h',
                                title="Top 10 Quantités à Commander", color='Urgence', color_continuous_scale='Reds')
                    st.plotly_chart(fig, use_container_width=True)

                with tab3:
                    mp_select = st.selectbox("Choisir MP pour voir prévision", df_plan['Code_MP'].tolist())
                    if mp_select in forecasts_dict:
                        forecast = forecasts_dict[mp_select]
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat'], mode='lines', name='Prévision'))
                        fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_upper'], fill=None, mode='lines', line_color='rgba(0,0,0,0)', showlegend=False))
                        fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_lower'], fill='tonexty', mode='lines', name='Intervalle Confiance'))
                        fig.update_layout(title=f"Prévision Prophet - {mp_select}")
                        st.plotly_chart(fig, use_container_width
