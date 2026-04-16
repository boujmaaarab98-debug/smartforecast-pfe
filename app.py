import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import io
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Smart Forecast Pro", layout="wide", page_icon="🚀")

st.title("🚀 Smart Forecast Pro - Supply Chain Complet")
st.markdown("### Plan Appro + KPIs Fournisseurs + Consultant IA")

HORIZON_JOURS = 30

# SESSION STATE
if 'historique_plans' not in st.session_state:
    st.session_state['historique_plans'] = []
if 'fichiers_additionnels' not in st.session_state:
    st.session_state['fichiers_additionnels'] = {}

# SIDEBAR
with st.sidebar:
    st.header("📁 Fichiers")

    with st.expander("⚙️ Principaux", expanded=True):
        fichier_conso = st.file_uploader("📊 Consommation", type=['xlsx'], key="conso")
        fichier_param = st.file_uploader("⚙️ Paramètres MP", type=['xlsx'], key="param")

    with st.expander("🏭 Fournisseurs & Autres"):
        fichier_fournisseur = st.file_uploader("🏭 Fichier Fournisseurs", type=['xlsx'], key="fournisseur")
        fichier_historique = st.file_uploader("📜 Historique Commandes", type=['xlsx'], key="hist")

        if fichier_fournisseur:
            df_fournisseur = pd.read_excel(fichier_fournisseur)
            st.session_state['fichiers_additionnels']['fournisseurs'] = df_fournisseur
            st.success(f"✅ {len(df_fournisseur['code_fournisseur'].unique())} fournisseurs")

        if fichier_historique:
            df_hist = pd.read_excel(fichier_historique)
            st.session_state['fichiers_additionnels']['historique'] = df_hist
            st.success(f"✅ {len(df_hist)} commandes historiques")

    st.divider()
    HORIZON_JOURS = st.slider("Horizon (jours)", 7, 90, 30)

    # HISTORIQUE
    st.divider()
    st.header("💾 Historique Plans")
    if st.session_state['historique_plans']:
        for idx, plan in enumerate(st.session_state['historique_plans'][:5]):
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button(f"📄 {plan['date']}", key=f"load_{idx}", use_container_width=True):
                    st.session_state['df_resultat'] = plan['data']
                    st.session_state['cout_total'] = plan['cout_total']
                    st.rerun()
            with col2:
                if st.button("🗑️", key=f"del_{idx}"):
                    st.session_state['historique_plans'].pop(idx)
                    st.rerun()
    else:
        st.info("Aucun plan sauvegardé")

# MAIN
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

    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        generate = st.button("🚀 Générer Plan Complet", type="primary", use_container_width=True)
    with col_btn2:
        save_plan = st.button("💾 Sauvegarder", use_container_width=True, disabled='df_resultat' not in st.session_state)

    if generate:
        with st.spinner("⏳ Calcul IA + KPIs Fournisseurs..."):
            liste_mp = df_param[col_code_mp].unique()
            resultats_globaux = []
            forecasts_dict = {}
            progress_bar = st.progress(0)

            # CHARGER FOURNISSEURS SI KAYN
            df_fournisseurs = st.session_state['fichiers_additionnels'].get('fournisseurs', None)

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
                    prix_param = df_param[df_param[col_code_mp] == code_mp][col_prix].values[0]
                    moq_param = df_param[df_param[col_code_mp] == code_mp][col_moq].values[0]
                    lead_param = df_param[df_param[col_code_mp] == code_mp][col_lead].values[0]
                    designation = df_param[df_param[col_code_mp] == code_mp][col_designation].values[0]

                    # FOURNISSEUR OPTIMAL SI FICHIER KAYN
                    fournisseur_recommande = "N/A"
                    prix_optimal = prix_param
                    lead_optimal = lead_param
                    score_fournisseur = 0

                    if df_fournisseurs is not None:
                        df_f_mp = df_fournisseurs[df_fournisseurs['code_mp'] == code_mp].copy()
                        if not df_f_mp.empty:
                            # Score: (fiabilite * 0.4) + (taux_service * 0.3) + (qualite * 20 * 0.2) + (100-prix_rel * 0.1)
                            prix_min = df_f_mp['prix_unitaire_eur'].min()
                            df_f_mp['score'] = (
                                df_f_mp['fiabilite_%'] * 0.4 +
                                df_f_mp['taux_service_%'] * 0.3 +
                                df_f_mp['note_qualite_5'] * 20 * 0.2 +
                                (100 - (df_f_mp['prix_unitaire_eur'] / prix_min * 100 - 100)) * 0.1
                            )
                            best_f = df_f_mp.loc[df_f_mp['score'].idxmax()]
                            fournisseur_recommande = f"{best_f['nom_fournisseur']} ({best_f['code_fournisseur']})"
                            prix_optimal = best_f['prix_unitaire_eur']
                            lead_optimal = best_f['lead_time_j']
                            score_fournisseur = best_f['score']

                    besoin_net = max(0, besoin_total - stock_actuel)
                    qte_commander = np.ceil(besoin_net / moq_param) * moq_param if besoin_net > 0 else 0

                    couverture_jours = stock_actuel / (besoin_total / HORIZON_JOURS) if besoin_total > 0 else 999
                    if couverture_jours < lead_optimal:
                        status = "🔴 URGENT"
                        urgence = 3
                    elif couverture_jours < lead_optimal + 7:
                        status = "🟠 Attention"
                        urgence = 2
                    else:
                        status = "🟢 OK"
                        urgence = 1

                    date_commande = pd.Timestamp.now() + pd.Timedelta(days=max(0, int(couverture_jours - lead_optimal)))

                    resultats_globaux.append({
                        'Code_MP': code_mp,
                        'Designation': designation,
                        'Stock_Actuel_kg': stock_actuel,
                        'Besoin_Prevu_kg': round(besoin_total, 1),
                        'QTE_A_COMMANDER_kg': qte_commander,
                        'Fournisseur_Recommande': fournisseur_recommande,
                        'Prix_Optimal_EUR': round(prix_optimal, 2),
                        'Lead_Time_Optimal_j': lead_optimal,
                        'Score_Fournisseur': round(score_fournisseur, 1),
                        'Cout_Commande_EUR': round(qte_commander * prix_optimal, 2),
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
                st.session_state['date_generation'] = datetime.now().strftime('%Y-%m-%d %H:%M')

                st.success(f"✅ Plan Généré! {len(df_plan)} matières")

                # DASHBOARD
                st.divider()
                col1, col2, col3, col4 = st.columns(4)
                total_cout = df_plan['Cout_Commande_EUR'].sum()
                nb_urgent = len(df_plan[df_plan['Urgence'] == 3])
                nb_fournisseurs = df_plan['Fournisseur_Recommande'].nunique() if 'Fournisseur_Recommande' in df_plan else 0
                economie = (df_plan['QTE_A_COMMANDER_kg'] * (df_param.set_index('code_mp')['cout_unitaire'] - df_plan.set_index('Code_MP')['Prix_Optimal_EUR'])).sum()

                col1.metric("💰 Coût Total", f"{total_cout:,.0f} EUR")
                col2.metric("🔴 Critique", f"{nb_urgent}")
                col3.metric("🏭 Fournisseurs", f"{nb_fournisseurs}")
                col4.metric("💡 Économie", f"{economie:,.0f} EUR", delta="vs prix standard")

                # TABLEAU
                st.divider()
                st.subheader("📋 Plan + Fournisseurs Recommandés")
                st.dataframe(df_plan.drop('Urgence', axis=1), use_container_width=True, height=400)

                # KPIs FOURNISSEURS
                if df_fournisseurs is not None:
                    st.divider()
                    st.subheader("🏭 KPIs Fournisseurs")

                    tab1, tab2, tab3 = st.tabs(["📊 Performance", "💰 Comparaison Prix", "⭐ Top Fournisseurs"])

                    with tab1:
                        df_kpi = df_fournisseurs.groupby('nom_fournisseur').agg({
                            'fiabilite_%': 'mean',
                            'taux_service_%': 'mean',
                            'note_qualite_5': 'mean',
                            'lead_time_j': 'mean'
                        }).round(1).reset_index()
                        st.dataframe(df_kpi, use_container_width=True)

                        fig = px.bar(df_kpi, x='nom_fournisseur', y=['fiabilite_%', 'taux_service_%'],
                                    barmode='group', title="Fiabilité & Taux de Service")
                        st.plotly_chart(fig, use_container_width=True)

                    with tab2:
                        fig = px.box(df_fournisseurs, x='code_mp', y='prix_unitaire_eur', color='nom_fournisseur',
                                    title="Comparaison Prix par MP")
                        st.plotly_chart(fig, use_container_width=True)

                    with tab3:
                        df_top_f = df_fournisseurs.groupby('nom_fournisseur').agg({
                            'fiabilite_%': 'mean',
                            'taux_service_%': 'mean',
                            'note_qualite_5': 'mean'
                        }).reset_index()
                        df_top_f['Score_Global'] = (
                            df_top_f['fiabilite_%'] * 0.4 +
                            df_top_f['taux_service_%'] * 0.3 +
                            df_top_f['note_qualite_5'] * 20 * 0.3
                        ).round(1)
                        df_top_f = df_top_f.sort_values('Score_Global', ascending=False)
                        st.dataframe(df_top_f, use_container_width=True)

                # GRAPHIQUES
                st.divider()
                mp_select = st.selectbox("Voir Prévision MP", df_plan['Code_MP'].tolist())
                if mp_select in forecasts_dict:
                    forecast = forecasts_dict[mp_select]
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat'], mode='lines', name='Prévision'))
                    fig.update_layout(title=f"Prévision - {mp_select}")
                    st.plotly_chart(fig, use_container_width=True)

                # DOWNLOAD
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_plan.to_excel(writer, index=False, sheet_name='Plan_Appro')
                    if df_fournisseurs is not None:
                        df_fournisseurs.to_excel(writer, index=False, sheet_name='Fournisseurs')
                st.download_button("📥 Télécharger Plan Complet", output.getvalue(),
                                 f"Plan_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 use_container_width=True)

    if save_plan and 'df_resultat' in st.session_state:
        nouveau_plan = {
            'date': st.session_state['date_generation'],
            'nb_mp': len(st.session_state['df_resultat']),
            'cout_total': st.session_state['cout_total'],
            'data': st.session_state['df_resultat']
        }
        st.session_state['historique_plans'].insert(0, nouveau_plan)
        st.success(f"✅ Plan sauvegardé!")
        st.rerun()

# CHAT IA
if 'df_resultat' in st.session_state:
    st.divider()
    st.header("🧠 Consultant IA - Fournisseurs & Actions")

    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant",
            "content": "👋 **Salam!** N9der n3awnk f:\n- 🏭 **KPIs Fournisseurs** - Chkoun a7sen fournisseur?\n- 💰 **Comparaison prix** - Fin nl9a rkhis?\n- 🔍 **Analyse risques** - Rupture, retard\n- 💡 **Plans d'action** - Chno ndir?\n\n**Swel!**"
        })

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Swel... Ex: Chkoun a7sen fournisseur? Comparaison prix MP_PP?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            df = st.session_state['df_resultat']
            df_fournisseurs = st.session_state['fichiers_additionnels'].get('fournisseurs', None)
            prompt_lower = prompt.lower()

            if "fournisseur" in prompt_lower or "a7sen" in prompt_lower or "meilleur" in prompt_lower:
                if df_fournisseurs is not None:
                    df_top = df_fournisseurs.groupby('nom_fournisseur').agg({
                        'fiabilite_%': 'mean',
                        'taux_service_%': 'mean',
                        'note_qualite_5': 'mean',
                        'lead_time_j': 'mean'
                    }).reset_index()
                    df_top['Score'] = (df_top['fiabilite_%'] * 0.4 + df_top['taux_service_%'] * 0.3 + df_top['note_qualite_5'] * 20 * 0.3).round(1)
                    df_top = df_top.sort_values('Score', ascending=False)

                    response = f"🏆 **TOP FOURNISSEURS (par Score Global):**\n\n"
                    for idx, row in df_top.iterrows():
                        response += f"**{idx+1}. {row['nom_fournisseur']}** - Score: {row['Score']}/100\n"
                        response += f" - Fiabilité: {row['fiabilite_%']:.0f}% | Service: {row['taux_service_%']:.0f}%\n"
                        response += f" - Qualité: {row['note_qualite_5']:.1f}/5 | Lead Time: {row['lead_time_j']:.0f}j\n\n"

                    response += f"**💡 RECOMMANDATION:**\n"
                    response += f"1. **{df_top.iloc[0]['nom_fournisseur']}** - A7sen score global\n"
                    response += f"2. Diversifier m3a Top 3 bach t9ll risque\n"
                    response += f"3. Négocier m3a {df_top.iloc[0]['nom_fournisseur']} contrat annuel"
                else:
                    response = "⚠️ Ma kaynach fichier fournisseurs. Uploadih f sidebar bach n3tik KPIs!"

            elif "prix" in prompt_lower or "comparaison" in prompt_lower:
                if df_fournisseurs is not None:
                    response = f"💰 **COMPARAISON PRIX PAR MP:**\n\n"
                    for mp in df['Code_MP'].unique():
                        df_f_mp = df_fournisseurs[df_fournisseurs['code_mp'] == mp]
                        if not df_f_mp.empty:
                            min_prix = df_f_mp['prix_unitaire_eur'].min()
                            max_prix = df_f_mp['prix_unitaire_eur'].max()
                            economie = max_prix - min_prix
                            best_f = df_f_mp.loc[df_f_mp['prix_unitaire_eur'].idxmin()]
                            response += f"**{mp}:**\n"
                            response += f" - Moins cher: {best_f['nom_fournisseur']} à {min_prix:.2f} EUR\n"
                            response += f" - Plus cher: {max_prix:.2f} EUR\n"
                            response += f" - Économie potentielle: {economie:.2f} EUR/kg 💰\n\n"
                else:
                    response = "⚠️ Uploadi fichier fournisseurs f sidebar!"

            elif "rupture" in prompt_lower or "risque" in prompt_lower:
                df_critique = df[df['Urgence'] == 3]
                if not df_critique.empty:
                    response = f"🚨 **PLAN D'ACTION RUPTURE:**\n\n"
                    for _, row in df_critique.iterrows():
                        response += f"### 🔴 {row['Code_MP']}\n"
                        response += f"**Fournisseur Recommandé:** {row['Fournisseur_Recommande']}\n"
                        response += f"**Actions:**\n"
                        response += f"1. Commander {row['QTE_A_COMMANDER_kg']:.0f}kg MAINTENANT\n"
                        response += f"2. Contacter {row['Fournisseur_Recommande']} - urgence\n"
                        response += f"3. Lead time: {row['Lead_Time_Optimal_j']:.0f}j\n\n"
                else:
                    response = "✅ Ma kayn 7ta risque rupture!"

            else:
                response = f"""**📊 RÉSUMÉ:**

💰 Budget: {st.session_state['cout_total']:,.0f} EUR
🔴 Critique: {len(df[df['Urgence']==3])} MP
🏭 Fournisseurs: {df['Fournisseur_Recommande'].nunique() if 'Fournisseur_Recommande' in df else 'N/A'}

**Swel 3la:** fournisseurs, prix, rupture, [Code_MP]"""

            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.info("👆 Uploadi fichiers w click 'Générer Plan' bach yban kolchi")
