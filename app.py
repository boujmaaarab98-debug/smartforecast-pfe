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
if 'messages' not in st.session_state:
    st.session_state['messages'] = []

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

# FONCTIONS
def trouver_colonne(df, noms_possibles):
    for nom in noms_possibles:
        if nom in df.columns:
            return nom
        for col in df.columns:
            if col.lower().strip() == nom.lower().strip():
                return col
    return None

def calculer_score_fournisseur(row):
    score_prix = 10 - (row['prix_unitaire_eur'] / 10)
    score_lead = 10 - (row['lead_time_j'] / 3)
    score_fiab = row['fiabilite_%'] / 10
    score_qual = row['note_qualite_5'] * 2
    score_total = (score_prix * 0.4) + (score_lead * 0.3) + (score_fiab * 0.2) + (score_qual * 0.1)
    return round(max(0, min(10, score_total)), 2)

def determiner_statut_rotation(taux):
    if taux < 100:
        return "🔴 Stock Dormant", "danger"
    elif taux < 150:
        return "🟡 Rotation Faible", "warning"
    elif taux <= 400:
        return "🟢 Normal", "success"
    elif taux <= 600:
        return "🔵 Optimisé", "info"
    else:
        return "🟠 Risque Rupture", "danger"

# MAIN
if fichier_conso and fichier_param:
    df_conso = pd.read_excel(fichier_conso)
    df_param = pd.read_excel(fichier_param)
    df_mrp = st.session_state['fichiers_additionnels'].get('mrp', None)

    st.success(f"✅ {len(df_param)} matières chargées")

    # Nettoyage colonnes
    df_param.columns = df_param.columns.str.strip()
    df_conso.columns = df_conso.columns.str.strip()

    # Détection colonnes
    col_code_mp = trouver_colonne(df_param, ['code_mp', 'Code_MP', 'code', 'Code', 'MP'])
    col_designation = trouver_colonne(df_param, ['designation', 'Designation', 'Nom', 'nom'])
    col_stock = trouver_colonne(df_param, ['stock_secu_actuel', 'Stock_Actuel', 'stock_actuel', 'Stock'])
    col_prix = trouver_colonne(df_param, ['cout_unitaire', 'Cout_Unitaire', 'prix', 'Prix'])
    col_moq = trouver_colonne(df_param, ['moq_kg', 'MOQ_kg', 'MOQ', 'moq'])
    col_lead = trouver_colonne(df_param, ['lead_time_j', 'Lead_Time_J', 'lead_time', 'Delai'])

    col_date_conso = trouver_colonne(df_conso, ['date', 'Date', 'DATE', 'Date_Conso', 'Jour'])
    col_code_mp_conso = trouver_colonne(df_conso, ['code_mp', 'Code_MP', 'Code', 'code', 'MP'])
    col_qte_conso = trouver_colonne(df_conso, ['qte_consommee_kg', 'Qte_Consommee', 'Quantite', 'quantite', 'Qte', 'Consommation'])

    # Vérification
    if not col_code_mp or not col_stock:
        st.error(f"❌ Colonnes manquantes dans Paramètres")
        st.write("**Trouvées:**", list(df_param.columns))
        st.stop()

    if not col_date_conso or not col_code_mp_conso or not col_qte_conso:
        st.error(f"❌ Colonnes manquantes dans Consommation")
        st.write("**Trouvées:**", list(df_conso.columns))
        st.stop()

    df_conso = df_conso.rename(columns={col_date_conso: 'Date', col_code_mp_conso: 'Code_MP', col_qte_conso: 'Qte_Consommee'})

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
                    df_mp = df_conso[df_conso['Code_MP'] == code_mp].copy()
                    df_mp['Date'] = pd.to_datetime(df_mp['Date'], errors='coerce')
                    df_mp = df_mp.dropna(subset=['Date'])
                    df_mp = df_mp.sort_values('Date')

                    if len(df_mp) < 2:
                        continue

                    nb_jours = (df_mp['Date'].max() - df_mp['Date'].min()).days
                    if nb_jours == 0:
                        nb_jours = 365
                    conso_totale = df_mp['Qte_Consommee'].sum()
                    conso_annuelle = (conso_totale / nb_jours * 365) if nb_jours > 0 else 0

                    df_prophet = df_mp.rename(columns={'Date': 'ds', 'Qte_Consommee': 'y'})
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
                            df_mrp_mp['date_besoin'] = pd.to_datetime(df_mrp_mp['date_besoin'], errors='coerce')
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
                        df_fournisseurs.columns = df_fournisseurs.columns.str.strip()
                        df_f_mp = df_fournisseurs[df_fournisseurs['code_mp'] == code_mp].copy()
                        if not df_f_mp.empty:
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
                    jours_rupture = len(df_mp[df_mp['Qte_Consommee'] > stock_actuel])
                    taux_rupture = (jours_rupture / len(df_mp) * 100) if len(df_mp) > 0 else 0

                    # ROTATION WA9I3IYA - SANS PLAFOND
                    if stock_actuel <= 1:
                        rotation = 0
                        taux_rotation_pct = 0
                    else:
                        rotation = conso_annuelle / stock_actuel
                        taux_rotation_pct = rotation * 100

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
                        'Taux_Rotation_%': round(taux_rotation_pct, 1),
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
                    'taux_rotation_pct': df_plan['Taux_Rotation_%'].mean(),
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

                # DASHBOARD KPIs
                st.divider()
                st.subheader("📊 KPIs Supply Chain - Vue Globale")

                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Budget Commande", f"{kpis_globaux['cout_total_commande']:,.0f} EUR")
                col2.metric("📦 Valeur Stock", f"{kpis_globaux['valeur_stock_total']:,.0f} EUR")
                col3.metric("💸 Coût Possession", f"{kpis_globaux['cout_total_possession']:,.0f} EUR/an")

                col4, col5, col6 = st.columns(3)
                col4.metric("🔄 Taux Rotation", f"{kpis_globaux['taux_rotation_pct']:.0f}%")
                col5.metric("📅 Couverture Moy", f"{kpis_globaux['couverture_moyenne']:.0f} jours")
                col6.metric("✅ Taux Service", f"{kpis_globaux['taux_service_global']:.1f}%")

                col7, col8, col9 = st.columns(3)
                col7.metric("⚠️ Taux Rupture", f"{kpis_globaux['taux_rupture_moyen']:.1f}%", delta_color="inverse")
                col8.metric("🔴 MP Critiques", f"{kpis_globaux['nb_mp_critiques']}", delta_color="inverse")
                col9.metric("🎯 Aligné MRP", f"{kpis_globaux['taux_alignement_mrp']:.0f}%",
                           delta=f"{kpis_globaux['nb_non_alignes']} non alignés" if kpis_globaux['nb_non_alignes'] > 0 else "✓ Parfait",
                           delta_color="inverse" if kpis_globaux['nb_non_alignes'] > 0 else "normal")

                # ALERTES
                df_non_aligne = df_plan[df_plan['Alignement_MRP'] == "❌ NON ALIGNÉ"]
                if len(df_non_aligne) > 0:
                    st.divider()
                    st.subheader("🚨 ALERTES: MPs Non Alignées avec Production")

                    fig_alertes = go.Figure()
                    fig_alertes.add_trace(go.Bar(
                        x=df_non_aligne['Code_MP'],
                        y=df_non_aligne['Stock_Actuel_kg'],
                        name='Stock Actuel (kg)',
                        marker_color='#ff9999',
                        text=df_non_aligne['Stock_Actuel_kg'].astype(int).astype(str) + 'kg',
                        textposition='auto',
                        yaxis='y',
                        offsetgroup=1
                    ))
                    fig_alertes.add_trace(go.Bar(
                        x=df_non_aligne['Code_MP'],
                        y=df_non_aligne['Couverture_j'],
                        name='Couverture (jours)',
                        marker_color='#ff4444',
                        text=df_non_aligne['Couverture_j'].round(1).astype(str) + 'j',
                        textposition='auto',
                        yaxis='y2',
                        offsetgroup=2
                    ))
                    fig_alertes.add_trace(go.Scatter(
                        x=df_non_aligne['Code_MP'],
                        y=df_non_aligne['Lead_Time_j'],
                        name='Lead Time Requis (j)',
                        mode='lines+markers',
                        line=dict(color='#000000', width=3, dash='dash'),
                        marker=dict(size=10, color='#000000', symbol='diamond'),
                        yaxis='y2'
                    ))
                    fig_alertes.update_layout(
                        title="⚠️ Stock vs Couverture vs Lead Time",
                        xaxis=dict(title="Code MP"),
                        yaxis=dict(title="Stock (kg)", side='left', showgrid=False),
                        yaxis2=dict(title="Jours", side='right', overlaying='y', showgrid=True),
                        barmode='group',
                        height=450,
                        hovermode='x unified',
                        legend=dict(x=0.7, y=1.1, orientation='h')
                    )
                    fig_alertes.add_hline(y=0, line_dash="solid", line_color="red", yref='y2')
                    st.plotly_chart(fig_alertes, use_container_width=True)

                    st.markdown("**📋 Détails Actions Requises:**")
                    df_details = df_non_aligne[['Code_MP', 'Designation', 'Besoin_MRP_kg', 'Stock_Actuel_kg',
                                               'Couverture_j', 'Lead_Time_j', 'QTE_A_COMMANDER_kg']].copy()
                    df_details.columns = ['Code', 'Désignation', 'Besoin MRP (kg)', 'Stock (kg)',
                                         'Couverture (j)', 'Lead Time (j)', 'À COMMANDER (kg)']
                    st.dataframe(df_details, use_container_width=True, hide_index=True)

                # TABLEAU
                st.divider()
                st.subheader("📋 Plan Appro + Comparaison MRP")
                st.dataframe(df_plan.drop('Urgence', axis=1), use_container_width=True, height=400)

                # GRAPHIQUES - BIN KOL LES MPs
                st.divider()
                st.subheader("📈 Analyses")

                tab1, tab2, tab3 = st.tabs(["📊 MRP vs Prévision", "⚠️ Écarts", "🏭 Fournisseurs"])

                with tab1:
                    # BIN KOLCHI - MACHI GHIR LI FIHOM MRP
                    df_comp = df_plan.head(15)
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        name='MRP Production',
                        x=df_comp['Code_MP'],
                        y=df_comp['Besoin_MRP_kg'],
                        marker_color='#0066cc',
                        text=df_comp['Besoin_MRP_kg'].round(0).astype(int).astype(str),
                        textposition='auto'
                    ))
                    fig.add_trace(go.Bar(
                        name='Prévision Prophet',
                        x=df_comp['Code_MP'],
                        y=df_comp['Prevision_Prophet_kg'],
                        marker_color='#66b3ff',
                        text=df_comp['Prevision_Prophet_kg'].round(0).astype(int).astype(str),
                        textposition='auto'
                    ))
                    fig.update_layout(
                        barmode='group',
                        title="Comparaison Besoins MRP vs Prévision - Tous les MPs",
                        xaxis_title="Code MP",
                        yaxis_title="Quantité (kg)",
                        height=450
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with tab2:
                    # BIN KOLCHI - MACHI GHIR LI FIHOM ÉCART
                    df_ecart = df_plan.sort_values('Ecart_MRP_vs_Prevision', key=abs, ascending=False).head(15)
                    fig = px.bar(
                        df_ecart,
                        x='Code_MP',
                        y='Ecart_MRP_vs_Prevision',
                        color='Alignement_MRP',
                        title="Écarts MRP vs Prévision (kg) - Tous les MPs",
                        color_discrete_map={"✅ ALIGNÉ": "#44ff44", "⚠️ RISQUE": "#ffaa00", "❌ NON ALIGNÉ": "#ff4444"},
                        text='Ecart_MRP_vs_Prevision'
                    )
                    fig.update_traces(texttemplate='%{text:.0f}', textposition='outside')
                    fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=2)
                    fig.update_layout(
                        xaxis_title="Code MP",
                        yaxis_title="Écart (MRP - Prophet) kg",
                        height=450
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with tab3:
                    df_f_count = df_plan['Fournisseur'].value_counts().reset_index()
                    df_f_count.columns = ['Fournisseur', 'Nb_MP']

                    col1, col2 = st.columns([1, 1])
                    with col1:
                        fig = px.pie(df_f_count, values='Nb_MP', names='Fournisseur',
                                     title="Répartition MPs par Fournisseur",
                                     hole=0.3)
                        st.plotly_chart(fig, use_container_width=True)

                    with col2:
                        st.markdown("**Détail par MP:**")
                        df_detail = df_plan[['Code_MP', 'Designation', 'Fournisseur', 'Prix_EUR', 'Lead_Time_j']].copy()
                        st.dataframe(df_detail, use_container_width=True, hide_index=True)

                    st.divider()
                    mps_sans_fournisseur = []
                    if df_fournisseurs is not None:
                        for code_mp_check in df_param[col_code_mp].unique():
                            if code_mp_check not in df_fournisseurs['code_mp'].values:
                                mps_sans_fournisseur.append(code_mp_check)

                    if mps_sans_fournisseur:
                        st.error(f"⚠️ **{len(mps_sans_fournisseur)} MPs sans fournisseur:** {', '.join(mps_sans_fournisseur)}")
                        st.info("💡 **Ajoutez-les dans le fichier Fournisseur pour optimiser**")
                    else:
                        st.success("✅ **Tous les MPs ont un fournisseur assigné**")

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

    col_chat_title, col_clear_btn = st.columns([4, 1])
    with col_chat_title:
        st.header("🧠 Assistant MRP ↔ Appro")
    with col_clear_btn:
        if st.button("🗑️ Effacer Chat", use_container_width=True, type="secondary"):
            st.session_state['messages'] = []

    if len(st.session_state['messages']) == 0:
        st.session_state['messages'].append({
            "role": "assistant",
            "content": "👋 **Salam!** N9der n3awnk f:\n- 📊 **Alignement MRP** - Wach 7na à jour m3a Production?\n- ⚠️ **Écarts** - Far9 bin MRP w Prévision\n- 🔴 **Critiques** - MPs li ghadi ywe99fou Production\n- 💡 **Actions** - Chno ncommandiw daba\n\n**Swel!**"
        })

    for message in st.session_state['messages']:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Swel... Ex: Wach 7na à jour m3a MRP?"):
        st.session_state['messages'].append({"role": "user", "content": prompt})
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
                    response = f"🚨 **MPs CRITIQUES - RISQUE ARRÊT PRODUCTION**\n"
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
