import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import io
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="Smart Forecast Pro", layout="wide", page_icon="🚀")

st.title("🚀 Smart Forecast Pro - Plan d'Approvisionnement IA")
st.markdown("### Prophet AI + Alertes Intelligentes + Dashboard Pro")

HORIZON_JOURS = 30

# SIDEBAR - SETTINGS
with st.sidebar:
    st.header("⚙️ Paramètres")
    HORIZON_JOURS = st.slider("Horizon Prévision (jours)", 7, 90, 30)
    st.divider()
    st.markdown("**📊 Fichiers Requis:**")
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

    st.success(f"✅ Fichiers chargés: {len(df_conso)} lignes conso, {len(df_param)} matières")

    # AUTO-DETECT COLONNES
    col_code_mp = 'code_mp'
    col_designation = 'designation'
    col_stock = 'stock_secu_actuel'
    col_prix = 'cout_unitaire'
    col_moq = 'moq_kg'
    col_lead = 'lead_time_j'
    col_date_conso = 'date'
    col_qte_conso = 'qte_consommee_kg'

    # CHECK
    required_cols = [col_code_mp, col_designation, col_stock, col_prix, col_moq, col_lead]
    missing = [c for c in required_cols if c not in df_param.columns]
    if missing:
        st.error(f"❌ Colonnes manquantes f param.xlsx: {', '.join(missing)}")
        st.stop()

    if st.button("🚀 Générer Plan Appro + Dashboard IA", type="primary", use_container_width=True):
        with st.spinner("⏳ Calcul IA + Génération Dashboard..."):
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

                    # LOGIQUE MOQ + ALERTES
                    besoin_net = max(0, besoin_total - stock_actuel)
                    qte_commander = np.ceil(besoin_net / moq) * moq if besoin_net > 0 else 0

                    # STATUS + URGENCE
                    couverture_jours = stock_actuel / (besoin_total / HORIZON_JOURS) if besoin_total > 0 else 999
                    if couverture_jours < lead_time:
                        status = "🔴 URGENT - Risque Rupture"
                        urgence = 3
                    elif couverture_jours < lead_time + 7:
                        status = "🟠 Attention - Stock Faible"
                        urgence = 2
                    else:
                        status = "🟢 OK - Stock Suffisant"
                        urgence = 1

                    date_commande = datetime.now() + timedelta(days=max(0, int(couverture_jours - lead_time)))

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
                        'Status': status,
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

                # ========== DASHBOARD KPIs ==========
                st.divider()
                st.subheader("📊 Dashboard KPIs")

                col1, col2, col3, col4 = st.columns(4)
                total_cout = df_plan['Cout_Commande_EUR'].sum()
                nb_urgent = len(df_plan[df_plan['Urgence'] == 3])
                nb_attention = len(df_plan[df_plan['Urgence'] == 2])
                nb_commander = len(df_plan[df_plan['QTE_A_COMMANDER_kg'] > 0])

                col1.metric("💰 Coût Total", f"{total_cout:,.0f} EUR", delta=f"{nb_commander} MP")
                col2.metric("🔴 Urgent", f"{nb_urgent}", delta="Risque rupture", delta_color="inverse")
                col3.metric("🟠 Attention", f"{nb_attention}", delta="Stock faible", delta_color="off")
                col4.metric("📦 À Commander", f"{nb_commander}/{len(df_plan)}", delta=f"{HORIZON_JOURS}j")

                # ========== ALERTES ==========
                st.divider()
                st.subheader("⚠️ Alertes Critiques")

                df_urgent = df_plan[df_plan['Urgence'] >= 2]
                if len(df_urgent) > 0:
                    for _, row in df_urgent.iterrows():
                        if row['Urgence'] == 3:
                            st.error(f"🔴 **{row['Code_MP']} - {row['Designation']}**: Stock {row['Stock_Actuel_kg']:.0f}kg | Couverture {row['Couverture_jours']:.0f}j < Lead Time {row['Lead_Time_j']:.0f}j | **COMMANDER {row['QTE_A_COMMANDER_kg']:.0f}kg MAINTENANT**")
                        else:
                            st.warning(f"🟠 **{row['Code_MP']} - {row['Designation']}**: Stock {row['Stock_Actuel_kg']:.0f}kg | Couverture {row['Couverture_jours']:.0f}j | Suggéré: {row['QTE_A_COMMANDER_kg']:.0f}kg le {row['Date_Commande_Suggeree']}")
                else:
                    st.success("✅ Aucune alerte - Tous les stocks sont suffisants!")

                # ========== TABLEAU INTERACTIF ==========
                st.divider()
                st.subheader("📋 Plan d'Approvisionnement Détaillé")

                # Filtres
                colf1, colf2 = st.columns(2)
                with colf1:
                    filtre_status = st.multiselect("Filtrer par Status", df_plan['Status'].unique(), default=df_plan['Status'].unique())
                with colf2:
                    show_only_order = st.checkbox("Afficher seulement MP à commander", value=False)

                df_display = df_plan[df_plan['Status'].isin(filtre_status)]
                if show_only_order:
                    df_display = df_display[df_display['QTE_A_COMMANDER_kg'] > 0]

                st.dataframe(df_display.drop('Urgence', axis=1), use_container_width=True, height=400)

                # ========== GRAPHIQUES ==========
                st.divider()
                st.subheader("📈 Visualisations")

                tab1, tab2, tab3 = st.tabs(["💰 Coûts par MP", "📦 Top 10 Quantités", "📊 Prévision Détaillée"])

                with tab1:
                    df_chart = df_plan[df_plan['Cout_Commande_EUR'] > 0].nlargest(15, 'Cout_Commande_EUR')
                    fig = px.bar(df_chart, x='Code_MP', y='Cout_Commande_EUR', color='Status',
                                title="Top 15 Coûts de Commande",
                                labels={'Cout_Commande_EUR': 'Coût (EUR)', 'Code_MP': 'Matière'},
                                color_discrete_map={'🔴 URGENT - Risque Rupture': '#ff4444',
                                                   '🟠 Attention - Stock Faible': '#ffaa00',
                                                   '🟢 OK - Stock Suffisant': '#44ff44'})
                    st.plotly_chart(fig, use_container_width=True)

                with tab2:
                    df_top = df_plan.nlargest(10, 'QTE_A_COMMANDER_kg')
                    fig = px.bar(df_top, x='QTE_A_COMMANDER_kg', y='Designation', orientation='h',
                                title="Top 10 Quantités à Commander",
                                labels={'QTE_A_COMMANDER_kg': 'Quantité (kg)', 'Designation': 'Matière'},
                                color='Urgence', color_continuous_scale='Reds')
                    st.plotly_chart(fig, use_container_width=True)

                with tab3:
                    mp_select = st.selectbox("Choisir MP pour voir prévision", df_plan['Code_MP'].tolist())
                    if mp_select in forecasts_dict:
                        forecast = forecasts_dict[mp_select]
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat'], mode='lines', name='Prévision', line=dict(color='#1f77b4')))
                        fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_upper'], fill=None, mode='lines', line_color='rgba(0,0,0,0)', showlegend=False))
                        fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_lower'], fill='tonexty', mode='lines', line_color='rgba(0,0,0,0)', name='Intervalle Confiance'))
                        fig.add_vline(x=datetime.now(), line_dash="dash", line_color="red", annotation_text="Aujourd'hui")
                        fig.update_layout(title=f"Prévision Prophet - {mp_select}", xaxis_title="Date", yaxis_title="Quantité (kg)")
                        st.plotly_chart(fig, use_container_width=True)

                # DOWNLOAD
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_plan.to_excel(writer, index=False, sheet_name='Plan_Appro')
                st.download_button("📥 Télécharger Plan Complet Excel", output.getvalue(),
                                 f"Plan_Appro_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 use_container_width=True)
            else:
                st.error("❌ Makaynch résultats")

# CHAT IA AMÉLIORÉ
if 'df_resultat' in st.session_state:
    st.divider()
    st.header("🤖 Assistant IA - Analyse Intelligente")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Swel... Ex: Chkoun 3ndo risque rupture? Ch7al coût total?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            df = st.session_state['df_resultat']
            cout = st.session_state.get('cout_total', 0)

            prompt_lower = prompt.lower()

            if "urgent" in prompt_lower or "rupture" in prompt_lower or "risque" in prompt_lower:
                df_urgent = df[df['Urgence'] == 3]
                if not df_urgent.empty:
                    response = f"🔴 **MPs f risque rupture ({len(df_urgent)}):**\n\n"
                    for _, row in df_urgent.iterrows():
                        response += f"- **{row['Code_MP']}** ({row['Designation']}): Stock {row['Stock_Actuel_kg']:.0f}kg, Couverture {row['Couverture_jours']:.0f}j < Lead Time {row['Lead_Time_j']:.0f}j\n → **Commander {row['QTE_A_COMMANDER_kg']:.0f}kg MAINTENANT** 💥\n\n"
                else:
                    response = "✅ Ma kayn 7ta MP f risque rupture! Kolchi mazyan 💪"

            elif "coût" in prompt_lower or "cout" in prompt_lower or "total" in prompt_lower or "budget" in prompt_lower:
                nb_mp = len(df[df['QTE_A_COMMANDER_kg'] > 0])
                response = f"💰 **Budget Total Matw9e3:** {cout:,.0f} EUR\n\n📦 **MP à Commander:** {nb_mp} matières\n📅 **Horizon:** {HORIZON_JOURS} jours\n\n**Top 3 Coûts:**\n"
                top3 = df.nlargest(3, 'Cout_Commande_EUR')
                for _, row in top3.iterrows():
                    response += f"- {row['Code_MP']}: {row['Cout_Commande_EUR']:,.0f} EUR ({row['QTE_A_COMMANDER_kg']:.0f}kg)\n"

            elif "akbar" in prompt_lower or "plus" in prompt_lower or "max" in prompt_lower:
                max_row = df.loc[df['QTE_A_COMMANDER_kg'].idxmax()]
                response = f"📦 **Akbar quantité à commander:**\n\n**{max_row['Code_MP']} - {max_row['Designation']}**\n- Quantité: **{max_row['QTE_A_COMMANDER_kg']:,.0f} kg**\n- Coût: {max_row['Cout_Commande_EUR']:,.0f} EUR\n- Status: {max_row['Status']}\n- Date Commande: {max_row['Date_Commande_Suggeree']}"

            elif any(mp in prompt.upper() for mp in df['Code_MP'].tolist()):
                for mp in df['Code_MP'].tolist():
                    if mp in prompt.upper():
                        row = df[df['Code_MP'] == mp].iloc[0]
                        response = f"**{row['Code_MP']} - {row['Designation']}**\n\n"
                        response += f"📊 Stock Actuel: {row['Stock_Actuel_kg']:.0f} kg\n"
                        response += f"📈 Besoin Prévu: {row['Besoin_Prevu_kg']:.0f} kg ({HORIZON_JOURS}j)\n"
                        response += f"📦 À Commander: **{row['QTE_A_COMMANDER_kg']:.0f} kg** (MOQ: {row['MOQ_kg']:.0f}kg)\n"
                        response += f"💰 Coût: {row['Cout_Commande_EUR']:,.0f} EUR\n"
                        response += f"⏰ Lead Time: {row['Lead_Time_j']:.0f} jours\n"
                        response += f"📅 Couverture: {row['Couverture_jours']:.1f} jours\n"
                        response += f"🎯 Status: {row['Status']}\n"
                        response += f"📆 Date Commande Suggérée: {row['Date_Commande_Suggeree']}"
                        break
            else:
                response = f"""**📊 Résumé Plan d'Appro:**

💰 **Coût Total:** {cout:,.0f} EUR
🔴 **Urgent:** {len(df[df['Urgence']==3])} MP
🟠 **Attention:** {len(df[df['Urgence']==2])} MP
📦 **À Commander:** {len(df[df['QTE_A_COMMANDER_kg']>0])} MP

**Top 5 MP à commander:**
{df[df['QTE_A_COMMANDER_kg']>0].nlargest(5, 'QTE_A_COMMANDER_kg')[['Code_MP', 'QTE_A_COMMANDER_kg', 'Status']].to_string(index=False)}

**Swel 3la:** risque rupture, coût total, akbar quantité, wla smiya dyal MP"""

            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.info("👆 Uploadi l fichiers w click 'Générer Plan Appro + Dashboard IA' bach yt7ll lik kolchi")
