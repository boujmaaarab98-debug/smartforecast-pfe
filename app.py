import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="MRP Analyse Pro", page_icon="🏭", layout="wide")

# ==================== 1. CHARGEMENT & TRAITEMENT DATA ====================
@st.cache_data
def load_and_process_data(fichier):
    # --- A. Chargement des 4 sheets ---
    df_param = pd.read_excel(fichier, sheet_name="Param")
    df_conso = pd.read_excel(fichier, sheet_name="Conso", skiprows=1) # Skip header fusionné
    df_fournis = pd.read_excel(fichier, sheet_name="Fournisseurs")
    df_prev_pf = pd.read_excel(fichier, sheet_name="MRP")

    # --- B. Nettoyage & Renommage Colonnes ---
    df_param = df_param.rename(columns={'code_mp': 'Code_MP', 'designation': 'Désignation', 'lead_time_j': 'Délai', 'moq_kg': 'MOQ', 'stock_secu_actuel': 'Stock_Sécu'})

    df_conso = df_conso.rename(columns={
        'Ref produit finis': 'Ref_PF', 'CODE matière': 'Code_MP',
        'conso journaliere MP en KG': 'Conso_U_Unitaire', 'Couverture : 2 semaine NBR OCTABIN': 'Couverture_Octab'
    })
    df_conso = df_conso.dropna(subset=['Code_MP', 'Ref_PF'])
    df_conso['Stock_Actuel_MP'] = df_conso['Couverture_Octab'] * df_conso['Conso_U_Unitaire']

    df_fournis = df_fournis.rename(columns={'code_mp': 'Code_MP', 'nom_fournisseur': 'Fournisseur', 'prix_unitaire_eur': 'Prix_EUR'})
    df_prev_pf = df_prev_pf.rename(columns={'Ref produit finis': 'Ref_PF'})

    # --- C. Explosion du Prévisionnel PF -> Besoin MP Journalier ---
    df_prev_melt = df_prev_pf.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
    df_prev_melt = df_prev_melt.dropna(subset=['Qte_PF_Prévue'])
    df_prev_melt['Date'] = pd.to_datetime(df_prev_melt['Date'], dayfirst=True, errors='coerce')
    df_prev_melt = df_prev_melt.dropna(subset=['Date'])

    # Lien avec la nomenclature (BOM) de Conso
    df_besoin_mp = pd.merge(df_prev_melt, df_conso[['Ref_PF', 'Code_MP', 'Conso_U_Unitaire']], on='Ref_PF', how='inner')
    df_besoin_mp['Besoin_MP_KG'] = df_besoin_mp['Qte_PF_Prévue'] * df_besoin_mp['Conso_U_Unitaire']
    df_besoin_jour = df_besoin_mp.groupby(['Code_MP', 'Date'])['Besoin_MP_KG'].sum().reset_index()

    # --- D. Construction du DataFrame MRP Final ---
    # On part de Param qui est le master des MP
    df_mrp = df_param[['Code_MP', 'Désignation', 'Délai', 'MOQ', 'Stock_Sécu']].copy()

    # Ajout Stock Actuel depuis Conso
    stock_actuel = df_conso.groupby('Code_MP')['Stock_Actuel_MP'].sum().reset_index().rename(columns={'Stock_Actuel_MP': 'Stock'})
    df_mrp = pd.merge(df_mrp, stock_actuel, on='Code_MP', how='left')

    # Ajout Infos Fournisseurs + KPIs
    df_mrp = pd.merge(df_mrp, df_fournis, on='Code_MP', how='left')

    # Calcul Consommation Journalière Moyenne sur les 30 prochains jours basée sur le prévisionnel
    date_fin_30j = datetime.now() + timedelta(days=30)
    conso_30j = df_besoin_jour[df_besoin_jour['Date'] <= date_fin_30j].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
    conso_30j['Consommation_J'] = conso_30j['Besoin_MP_KG'] / 30
    df_mrp = pd.merge(df_mrp, conso_30j[['Code_MP', 'Consommation_J']], on='Code_MP', how='left')

    # --- E. Calculs Finaux & Nettoyage ---
    df_mrp['Stock'] = df_mrp['Stock'].fillna(0)
    df_mrp['Consommation_J'] = df_mrp['Consommation_J'].fillna(0.1) # Évite division par zéro
    df_mrp['Stock_Sécu'] = df_mrp['Stock_Sécu'].fillna(0)
    df_mrp['Prix_EUR'] = df_mrp['Prix_EUR'].fillna(0)

    df_mrp['Couverture_J'] = df_mrp['Stock'] / df_mrp['Consommation_J']
    df_mrp['Écart'] = df_mrp['Stock'] - df_mrp['Stock_Sécu']
    df_mrp['Valeur_Risque_EUR'] = df_mrp['Écart'].clip(upper=0).abs() * df_mrp['Prix_EUR']

    return df_mrp, df_besoin_jour

# ==================== 2. INTERFACE STREAMLIT ====================
st.title("🏭 MRP Analyse Pro - Pilotage Fournisseurs & Stock")

# Chargement
fichier_data = "Matière_première_et_PF_consommation_journaliere.xlsx"
try:
    df_mrp, df_besoin_jour = load_and_process_data(fichier_data)
except Exception as e:
    st.error(f"Erreur de chargement du fichier Excel : {e}")
    st.stop()

# Création des onglets
tab1, tab2, tab3 = st.tabs(["📊 Vue Globale MRP", "⚠️ Alertes & Ruptures", "🏢 Fournisseur 360"])

with tab1:
    st.header("Vue Globale de toutes les Matières Premières")
    st.dataframe(df_mrp[[
        'Code_MP', 'Désignation', 'Fournisseur', 'Stock', 'Consommation_J',
        'Couverture_J', 'Stock_Sécu', 'Écart', 'Délai', 'Valeur_Risque_EUR'
    ]].style.format({
        'Stock': '{:,.0f}', 'Consommation_J': '{:,.1f}', 'Couverture_J': '{:.1f}',
        'Stock_Sécu': '{:,.0f}', 'Écart': '{:,.0f}', 'Valeur_Risque_EUR': '€ {:,.0f}'
    }), use_container_width=True, height=600)

with tab2:
    st.header("Matières en Risque de Rupture")
    seuil_alerte = st.slider("Afficher les MP avec couverture inférieure à (jours) :", 0, 60, 15)
    df_alertes = df_mrp[df_mrp['Couverture_J'] <= seuil_alerte].sort_values('Couverture_J')
    st.dataframe(df_alertes[['Code_MP', 'Désignation', 'Fournisseur', 'Stock', 'Couverture_J', 'Délai']], use_container_width=True)

    if not df_alertes.empty:
        st.subheader("Projection de Stock pour MP en Alerte")
        mp_select_alerte = st.selectbox("Choisir une MP à visualiser:", df_alertes['Code_MP'])

        stock_initial = df_alertes[df_alertes['Code_MP'] == mp_select_alerte]['Stock'].iloc[0]
        besoin_mp = df_besoin_jour[df_besoin_jour['Code_MP'] == mp_select_alerte].copy()

        if not besoin_mp.empty:
            besoin_mp = besoin_mp.sort_values('Date')
            besoin_mp['Stock_Projeté'] = stock_initial - besoin_mp['Besoin_MP_KG'].cumsum()

            fig = px.line(besoin_mp, x='Date', y='Stock_Projeté', title=f"Projection de Stock pour {mp_select_alerte}")
            fig.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="RUPTURE")
            st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.header("🏢 Fournisseur 360 - Analyse Détaillée")
    fournisseurs_list = sorted(df_mrp['Fournisseur'].dropna().unique())
    fourni_select = st.selectbox("Sélectionner un fournisseur", fournisseurs_list)

    if fourni_select:
        df_fourni_mps = df_mrp[df_mrp['Fournisseur'] == fourni_select]
        df_fourni_kpi = df_fournis[df_fournis['Fournisseur'] == fourni_select].iloc[0]

        st.subheader(f"KPIs pour {fourni_select}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Taux de Service", f"{df_fourni_kpi['taux_service_%']:.0f}%")
        col2.metric("Fiabilité", f"{df_fourni_kpi['fiabilite_%']:.0f}%")
        col3.metric("Lead Time", f"{df_fourni_kpi['lead_time_j']:.0f} j")
        col4.metric("Note Qualité", f"{df_fourni_kpi['note_qualite_5']}/5")

        st.subheader(f"Matières Premières gérées par {fourni_select}")
        st.dataframe(df_fourni_mps[[
            'Code_MP', 'Désignation', 'Stock', 'Couverture_J', 'Écart', 'Valeur_Risque_EUR'
        ]].style.format({
            'Stock': '{:,.0f}', 'Couverture_J': '{:.1f}', 'Écart': '{:,.0f}', 'Valeur_Risque_EUR': '€ {:,.0f}'
        }), use_container_width=True)

        st.subheader("Besoin consolidé (30 prochains jours)")
        besoin_fourni_30j = df_besoin_jour[
            (df_besoin_jour['Code_MP'].isin(df_fourni_mps['Code_MP'])) &
            (df_besoin_jour['Date'] <= datetime.now() + timedelta(days=30))
        ]
        if not besoin_fourni_30j.empty:
            fig_besoin = px.bar(besoin_fourni_30j, x='Date', y='Besoin_MP_KG', color='Code_MP', title="Besoin Journalier Total (KG)")
            st.plotly_chart(fig_besoin, use_container_width=True)
        else:
            st.info("Pas de besoin prévu pour ce fournisseur dans les 30 prochains jours.")
