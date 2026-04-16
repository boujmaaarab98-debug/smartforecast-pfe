import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import io
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="MRP vs Appro", layout="wide", page_icon="🔄")

st.title("🔄 MRP vs Approvisionnement - Logistique ↔ Production")
st.markdown("### Vérifier si on est à jour avec les demandes Production")

HORIZON_JOURS = 30
TAUX_POSSESSION_ANNUEL = 0.20

# SESSION STATE
if 'historique_plans' not in st.session_state:
    st.session_state['historique_plans'] = []
if 'fichiers_additionnels' not in st.session_state:
    st.session_state['fichiers_additionnels'] = {}

# SIDEBAR
with st.sidebar:
    st.header("📁 Fichiers")

    with st.expander("⚙️ Données Base", expanded=True):
        fichier_conso = st.file_uploader("📊 Historique Consommation", type=['xlsx'],
                                         help="date, code_mp, qte_consommee_kg")
        fichier_param = st.file_uploader("⚙️ Paramètres MP", type=['xlsx'],
                                         help="code_mp, designation, cout_unitaire, stock_secu_actuel, moq_kg, lead_time_j")

    with st.expander("🏭 Production & Fournisseurs"):
        fichier_mrp = st.file_uploader("📋 MRP Production", type=['xlsx'],
                                       help="date_besoin, code_mp, qte_besoin_kg, ordre_fabrication")
        fichier_fournisseur = st.file_uploader("🏭 Fournisseurs", type=['xlsx'])

        if fichier_mrp:
            df_mrp = pd.read_excel(fichier_mrp)
            st.session_state['fichiers_additionnels']['mrp'] = df_mrp
            st.success(f"✅ MRP: {len(df_mrp)} besoins")

        if fichier_fournisseur:
            df_fournisseur = pd.read_excel(fichier_fournisseur)
            st.session_state['fichiers_additionnels']['fournisseurs'] = df_fournisseur
            st.success(f"✅ {len(df_fournisseur['code_fournisseur'].unique())} fournisseurs")

    st.divider()
    HORIZON_JOURS = st.slider("Horizon (jours)", 7, 90, 30)
    TAUX_POSSESSION_ANNUEL = st.slider("Coût Stock (%/an)", 5, 40, 20) / 100

    st.divider()
    st.header("💾 Plans Sauvegardés")
    if st.session_state['historique_plans']:
        for idx, plan in enumerate(st.session_state['historique_plans'][:5]):
            if st.button(f"📄 {plan['date']}", key=f"load_{idx}", use_container_width=True):
                st.session_state['df_resultat'] = plan['data']
                st.session_state['kpis'] = plan.get('kpis', {})
                st.rerun()

# MAIN
if fichier_conso and fichier_param:
    df_conso = pd.read_excel(fichier_conso)
    df_param = pd.read_excel(fichier_param)
    df_mrp = st.session_state['fichiers_additionnels'].get('mrp', None)

    st.success(f"✅ {len(df_param)} matières chargées")

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

    if df_mrp is not None:
        st.info(f"📋 **MRP Chargé:** {len(df_mrp)} besoins production")
    else:
        st.warning("⚠️ **Pas de fichier MRP** - Utilisation prévision Prophet")

    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        generate = st.button("🚀 Analyser MRP vs Appro", type="primary", use_container_width=True)
    with col_btn2:
        save_plan = st.button("💾 Sauvegarder", use_container_width=True, disabled='df_resultat' not in st.session_state)

    if generate:
        with st.spinner("⏳ Analyse MRP + Prophet + Écarts..."):
            liste_mp = df_param[col_code_mp].unique()
            resultats_globaux = []
            forecasts_dict = {}
            progress_bar = st.progress(0)

            df_fournisseurs = st.session_state['fichiers_additionnels'].get('fournisseurs', None)

            for i, code_mp in enumerate(liste_mp):
                try:
                    df_mp = df_conso[df_conso[col_code_mp] == code_mp].copy()
                    df_mp[col_date_conso] = pd.to_datetime(df_mp[col_date_conso])
                    df_mp = df_mp.sort_values(col_date_conso)

                    if len(df_mp) < 2:
                        continue

                    nb_jours = (df_mp[col_date_conso].max() - df_mp[col_date_conso].min()).days
                    conso_totale = df_mp[col_qte_conso].sum()
                    conso_annuelle = (conso_totale / nb_jours * 365) if nb_jours > 0 else 0

                    df_prophet = df_mp.rename(columns={col_date_conso: 'ds', col_qte_conso: 'y'})
                    model = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True)
                    model.fit(df_prophet)
                    future = model.make_future_dataframe(periods=HORIZON_JOURS)
                    forecast = model.predict(future)
                    forecasts_dict[code_mp] = forecast

                    besoin_prevu_prophet = forecast['yhat'].tail(HORIZON_JOURS).sum()

                    besoin_mrp = 0
                    if df_mrp is not None:
                        df_mrp_mp = df_mrp[df_mrp['code_mp'] == code_mp].copy()
                        if not df_mrp_mp.empty:
                            df_mrp_mp['date_besoin'] = pd.to_datetime(df_mrp_mp['date_besoin'])
                            date_fin = pd.Timestamp.now() + pd.Timedelta(days=HORIZON_JOURS)
                            df_mrp_mp = df_mrp_mp[df_mrp_mp['date_besoin'] <= date_fin]
                            besoin_mrp = df_mrp_mp['qte_besoin_kg'].sum()

                    besoin_final = besoin_mrp if besoin_mrp > 0 else besoin_prevu_prophet
                    source_besoin = "MRP Production" if besoin_mrp > 0 else "Prévision Prophet"

                    stock_actuel = df_param[df_param[col_code_mp] == code_mp][col_stock].values[0]
                    prix_param = df_param[df_param[col_code_mp] == code_mp][col_prix].values[0]
                    moq_param = df_param[df_param[col_code_mp] == code_mp][col_moq].values[0]
                    lead_param = df_param[df_param[col_code_mp] == code_mp][col_lead].values[0]
                    designation = df_param[df_param[col_code_mp] == code_mp][col_designation].values[0]

                    fournisseur_recommande = "Standard"
                    prix_optimal = prix_param
                    lead_optimal = lead_param

                    if df_fournisseurs is not None:
                        df_f_mp = df_fournisseurs[df_fournisseurs['code_mp'] == code_mp].copy()
                        if not df_f_mp.empty:
                            prix_min = df_f_mp['prix_unitaire_eur'].min()
                            df_f_mp['score'] = (
                                df_f_mp.get('fiabilite_%', 90) * 0.4 +
                                df_f_mp.get('taux_service_%', 90) * 0.3 +
                                df_f_mp.get('note_qualite_5', 4) * 20 * 0.3
                            )
                            best_f = df_f_mp.loc[df_f_mp['score'].idxmax()]
                            fournisseur_recommande = best_f['nom_fournisseur']
                            prix_optimal = best_f['prix_unitaire_eur']
                            lead_optimal = best_f['lead_time_j']

                    besoin_net = max(0, besoin_final - stock_actuel)
                    qte_commander = np.ceil(besoin_net / moq_param) * moq_param if besoin_net > 0 else 0
                    couverture_jours = stock_actuel / (besoin_final / HORIZON_JOURS) if besoin_final > 0 else 999

                    ecart_mrp_prophet = besoin_mrp - besoin_prevu_prophet if besoin_mrp > 0 else 0
                    jours_rupture = len(df_mp[df_mp[col_qte_conso] > stock_actuel])
                    taux_rupture = (jours_rupture / len(df_mp) * 100) if len(df_mp) > 0 else 0
                    rotation = conso_annuelle / stock_actuel if stock_actuel > 0 else 0
                    cout_possession = stock_actuel * prix_optimal * TAUX_POSSESSION_ANNUEL

                    if couverture_jours < lead_optimal:
                        status = "🔴 CRITIQUE"
                        urgence = 3
                        alignement = "❌ NON ALIGNÉ"
                    elif couverture_jours < lead_optimal + 7:
                        status = "🟠 Attention"
                        urgence = 2
                        alignement = "⚠️ RISQUE"
                    else:
                        status = "🟢 À JOUR"
                        urgence = 1
                        alignement = "✅ ALIGNÉ"

                    date_commande = pd.Timestamp.now() + pd.Timedelta(days=max(0, int(couverture_jours - lead_optimal)))

                    resultats_globaux.append({
                        'Code_MP': code_mp,
                        'Designation': designation,
                        'Stock_Actuel_kg': stock_actuel,
                        'Besoin_MRP_kg': round(besoin_mrp, 1),
                        'Prevision_Prophet_kg': round(besoin_prevu_prophet, 1),
                        'Ecart_MRP_vs_Prevision': round(ecart_mrp_prophet, 1),
                        'Besoin_Retenu_kg': round(besoin_final, 1),
                        'Source_Besoin': source_besoin,
                        'QTE_A_COMMANDER_kg': qte_commander,
                        'Fournisseur': fournisseur_recommande,
                        'Prix_EUR': round(prix_optimal, 2),
                        'Lead_Time_j': lead_optimal,
                        'Cout_Commande_EUR': round(qte_commander * prix_optimal, 2),
                        'Couverture_j': round(couverture_jours, 1),
                        'Rotation_x/an': round(rotation, 2),
                        'Taux_Rupture_%': round(taux_rupture, 1),
                        'Cout_Possession_EUR/an': round(cout_possession, 2),
                        'Date_Commande': date_commande.strftime('%Y-%m-%d'),
                        'Alignement_MRP': alignement,
                        'Status': status,
                        'Urgence': urgence
                    })
                except Exception as e:
                    continue

                progress_bar.progress((i + 1) / len(liste_mp))

            if resultats_globaux:
                df_plan = pd.DataFrame(resultats_globaux).sort_values('Urgence', ascending=False)

                kpis_globaux = {
                    'cout_total_commande': df_plan['Cout_Commande_EUR'].sum(),
                    'valeur_stock_total': (df_plan['Stock_Actuel_kg'] * df_plan['Prix_EUR']).sum(),
                    'rotation_moyenne': df_plan['Rotation_x/an'].mean(),
                    'couverture_moyenne': df_plan['Couverture_j'].mean(),
                    'taux_service_global': 100 - df_plan['Taux_Rupture_%'].mean(),
                    'cout_total_possession': df_plan['Cout_Possession_EUR/an'].sum(),
                    'taux_rupture_moyen': df_plan['Taux_Rupture_%'].mean(),
                    'nb_mp_critiques': len(df_plan[df_plan['Urgence'] == 3]),
                    'nb_non_alignes': len(df_plan[df_plan['Alignement_MRP'] == "❌ NON ALIGNÉ"]),
                    'taux_alignement_mrp': (len(df_plan[df_plan['Alignement_MRP'] == "✅ ALIGNÉ"]) / len(df_plan) * 100)
                }

                st.session_state['df_resultat'] = df_plan
                st.session_state['kpis'] = kpis_globaux
                st.session_state['date_generation'] = datetime.now().strftime('%Y-%m-%d %H:%M')

                st.success(f"✅ Analyse Complète!")

                # DASHBOARD KPIs - 3 × 3 = 9 KPIs WADH7IN
                st.divider()
                st.subheader("📊 KPIs Supply Chain - Vue Globale")

                # STR 1 - FINANCIER
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Budget Commande", f"{kpis_globaux['cout_total_commande']:,.0f} EUR", help="Total à commander maintenant")
                col2.metric("📦 Valeur Stock", f"{kpis_globaux['valeur_stock_total']:,.0f} EUR", help="Stock immobilisé actuellement")
                col3.metric("💸 Coût Possession", f"{kpis_globaux['cout_total_possession']:,.0f} EUR/an", help="20% de la valeur stock")

                # STR 2 - PERFORMANCE STOCK
                col4, col5, col6 = st.columns(3)
                col4.metric("🔄 Rotation Moyenne", f"{kpis_globaux['rotation_moyenne']:.1f}x/an", help="Objectif: 12x/an")
                col5.metric("📅 Couverture Moy", f"{kpis_globaux['couverture_moyenne']:.0f} jours", help="Objectif: 30 jours")
                col6.metric("✅ Taux Service", f"{kpis_globaux['taux_service_global']:.1f}%", help="Commandes satisfaites")

                # STR 3 - RISQUES & ALIGNEMENT
                col7, col8, col9 = st.columns(3)
                col7.metric("⚠️ Taux Rupture", f"{kpis_globaux['taux_rupture_moyen']:.1f}%", help="Historique rupture", delta_color="inverse")
                col8.metric("🔴 MP Critiques", f"{kpis_globaux['nb_mp_critiques']}", help="Risque arrêt production", delta_color="inverse")
                col9.metric("🎯 Aligné MRP", f"{kpis_globaux['taux_alignement_mrp']:.0f}%",
                           delta=f"{kpis_globaux['nb_non_alignes']} non alignés" if kpis_globaux['nb_non_alignes'] > 0 else "✓ Parfait",
                           delta_color="inverse" if kpis_globaux['nb_non_alignes'] > 0 else "normal",
                           help="Alignement avec Production")

                # ALERTES
                df_non_aligne = df_plan[df_plan['Alignement_MRP'] == "❌ NON ALIGNÉ"]
                if len(df_non_aligne) > 0:
                    st.divider()
                    st.subheader("🚨 ALERTES: MPs Non Alignées avec Production")
                    for _, row in df_non_aligne.iterrows():
                        st.error(f"🔴 **{row['Code_MP']} - {row['Designation']}**\n"
                                f"MRP demande: {row['Besoin_MRP_kg']:.0f}kg | Stock: {row['Stock_Actuel_kg']:.0f}kg | "
                                f"Couverture: {row['Couverture_j']:.0f}j < Lead Time: {row['Lead_Time_j']:.0f}j\n"
                                f"**ACTION:** Commander {row['QTE_A_COMMANDER_kg']:.0f}kg MAINTENANT → Risque arrêt production!")

                # TABLEAU
                st.divider()
                st.subheader("📋 Plan Appro + Comparaison MRP")
                st.dataframe(df_plan.drop('Urgence', axis=1), use_container_width=True, height=400)

                # GRAPHIQUES
                st.divider()
                st.subheader("📈 Analyses")

                tab1, tab2, tab3 = st.tabs(["📊 MRP vs Prévision", "⚠️ Écarts", "🏭 Fournisseurs"])

                with tab1:
                    df_comp = df_plan[df_plan['Besoin_MRP_kg'] > 0].head(15)
                    if not df_comp.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Bar(name='MRP Production', x=df_comp['Code_MP'], y=df_comp['Besoin_MRP_kg']))
                        fig.add_trace(go.Bar(name='Prévision Prophet', x=df_comp['Code_MP'], y=df_comp['Prevision_Prophet_kg']))
                        fig.update_layout(barmode='group', title="Comparaison Besoins MRP vs Prévision")
                        st.plotly_chart(fig, use_container_width=True)

                with tab2:
                    df_ecart = df_plan[df_plan['Ecart_MRP_vs_Prevision'].abs() > 0].nlargest(15, 'Ecart_MRP_vs_Prevision', keep='all')
                    if not df_ecart.empty:
                        fig = px.bar(df_ecart, x='Code_MP', y='Ecart_MRP_vs_Prevision', color='Alignement_MRP',
                                    title="Écarts MRP vs Prévision (kg)",
                                    color_discrete_map={"✅ ALIGNÉ": "#44ff44", "⚠️ RISQUE": "#ffaa00", "❌ NON ALIGNÉ": "#ff4444"})
                        st.plotly_chart(fig, use_container_width=True)

                with tab3:
                    df_f_count = df_plan['Fournisseur'].value_counts().reset_index()
                    df_f_count.columns = ['Fournisseur', 'Nb_MP']
                    fig = px.pie(df_f_count, values='Nb_MP', names='Fournisseur', title="Répartition MPs par Fournisseur")
                    st.plotly_chart(fig, use_container_width=True)

                # DOWNLOAD
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_plan.to_excel(writer, index=False, sheet_name='Plan_MRP_Appro')
                    pd.DataFrame([kpis_globaux]).to_excel(writer, index=False, sheet_name='KPIs')
                st.download_button("📥 Télécharger Rapport MRP vs Appro", output.getvalue(),
                                 f"Rapport_MRP_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 use_container_width=True)

    if save_plan and 'df_resultat' in st.session_state:
        nouveau_plan = {
            'date': st.session_state['date_generation'],
            'nb_mp': len(st.session_state['df_resultat']),
            'cout_total': st.session_state['kpis']['cout_total_commande'],
            'kpis': st.session_state['kpis'],
            'data': st.session_state['df_resultat']
        }
        st.session_state['historique_plans'].insert(0, nouveau_plan)
        st.success(f"✅ Plan sauvegardé!")
        st.rerun()

# CHAT IA
if 'df_resultat' in st.session_state:
    st.divider()
    st.header("🧠 Assistant MRP ↔ Appro")

    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant",
            "content": "👋 **Salam!** N9der n3awnk f:\n- 📊 **Alignement MRP** - Wach 7na à jour m3a Production?\n- ⚠️ **Écarts** - Far9 bin MRP w Prévision\n- 🔴 **Critiques** - MPs li ghadi ywe99fou Production\n- 💡 **Actions** - Chno ncommandiw daba\n\n**Swel!**"
        })

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Swel... Ex: Wach 7na à jour m3a MRP?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            df = st.session_state['df_resultat']
            kpis = st.session_state['kpis']
            prompt_lower = prompt.lower()

            if "aligné" in prompt_lower or "jour" in prompt_lower or "mrp" in prompt_lower:
                response = f"🔄 **ÉTAT ALIGNEMENT MRP ↔ APPRO**\n\n"
                response += f"**Taux Alignement Global:** {kpis['taux_alignement_mrp']:.0f}%\n"
                response += f"**MPs Non Alignés:** {kpis['nb_non_alignes']} / {len(df)}\n"
                response += f"**MPs Critiques:** {kpis['nb_mp_critiques']}\n\n"

                if kpis['nb_non_alignes'] > 0:
                    response += f"🚨 **ALERTE: {kpis['nb_non_alignes']} MPs NON ALIGNÉS**\n\n"
                    df_non = df[df['Alignement_MRP'] == "❌ NON ALIGNÉ"]
                    for _, row in df_non.iterrows():
                        response += f"**🔴 {row['Code_MP']} - {row['Designation']}**\n"
                        response += f" - MRP demande: {row['Besoin_MRP_kg']:.0f}kg\n"
                        response += f" - Stock actuel: {row['Stock_Actuel_kg']:.0f}kg\n"
                        response += f" - Couverture: {row['Couverture_j']:.0f}j < Lead Time: {row['Lead_Time_j']:.0f}j\n"
                        response += f" - **ACTION:** Commander {row['QTE_A_COMMANDER_kg']:.0f}kg MAINTENANT\n\n"
                    response += f"**💡 Conclusion:** Logistique **MACHI à jour** m3a Production ⚠️"
                else:
                    response += f"✅ **PARFAIT!** Logistique **À JOUR** m3a Production 💪\n"
                    response += f"Kolchi les MPs 3ndhom couverture suffisante."

            elif "écart" in prompt_lower or "différence" in prompt_lower:
                df_ecart = df[df['Ecart_MRP_vs_Prevision'].abs() > 0].sort_values('Ecart_MRP_vs_Prevision', key=abs, ascending=False)
                if not df_ecart.empty:
                    response = f"📊 **ÉCARTS MRP vs PRÉVISION PROPHET**\n\n"
                    response += f"**Top 10 Écarts:**\n\n"
                    for _, row in df_ecart.head(10).iterrows():
                        sens = "⬆️ MRP > Prévision" if row['Ecart_MRP_vs_Prevision'] > 0 else "⬇️ MRP < Prévision"
                        response += f"**{row['Code_MP']}:** {sens}\n"
                        response += f" - MRP: {row['Besoin_MRP_kg']:.0f}kg | Prophet: {row['Prevision_Prophet_kg']:.0f}kg\n"
                        response += f" - Écart: {abs(row['Ecart_MRP_vs_Prevision']):.0f}kg\n\n"
                else:
                    response = "✅ **Pas d'écarts significatifs** - MRP w Prévision mt9arbin"

            elif "critique" in prompt_lower or "urgent" in prompt_lower:
                df_crit = df[df['Urgence'] == 3]
                if not df_crit.empty:
                    response = f"🚨 **MPs CRITIQUES - RISQUE ARRÊT PRODUCTION**\n\n"
                    for _, row in df_crit.iterrows():
                        response += f"**🔴 {row['Code_MP']} - {row['Designation']}**\n"
                        response += f" - Besoin MRP: {row['Besoin_MRP_kg']:.0f}kg\n"
                        response += f" - Stock: {row['Stock_Actuel_kg']:.0f}kg\n"
                        response += f" - Couverture: {row['Couverture_j']:.0f}j\n"
                        response += f" - Lead Time: {row['Lead_Time_j']:.0f}j\n"
                        response += f" - **COMMANDER: {row['QTE_A_COMMANDER_kg']:.0f}kg MAINTENANT**\n"
                        response += f" - Fournisseur: {row['Fournisseur']}\n\n"
                    response += f"**⏰ Timeline:** Si ma commandinach daba → **Arrêt production dans {df_crit['Couverture_j'].min():.0f} jours** ⚠️"
                else:
                    response = "✅ **Aucun MP critique** - Kolchi à jour m3a Production!"

            else:
                response = f"""**📊 RÉSUMÉ ALIGNEMENT MRP:**

✅ **Taux Alignement:** {kpis['taux_alignement_mrp']:.0f}%
🔴 **Critiques:** {kpis['nb_mp_critiques']} MPs
⚠️ **Non Alignés:** {kpis['nb_non_alignes']} MPs
📅 **Couverture Moy:** {kpis['couverture_moyenne']:.0f} jours
💰 **Budget:** {kpis['cout_total_commande']:,.0f} EUR

**Swel 3la:** aligné, écart, critique, couverture"""

            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.info("👆 Uploadi fichiers (Conso + Param + MRP) w click 'Analyser MRP vs Appro'")
