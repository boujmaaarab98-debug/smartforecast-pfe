import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

# ==================== CONFIG ====================
st.set_page_config(
    page_title="Dashboard Planification MP",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Dashboard Planification & Optimisation Matières Premières")

# ==================== SIDEBAR ====================
st.sidebar.header("⚙️ Configuration")

seuil_securite = st.sidebar.number_input(
    "Seuil Sécurité (%)",
    min_value=0,
    max_value=100,
    value=20,
    help="Seuil d'alerte stock en %"
)

seuil_critique = st.sidebar.number_input(
    "Seuil Critique (%)",
    min_value=0,
    max_value=100,
    value=10,
    help="Seuil critique stock en %"
)

# ==================== UPLOAD FICHIERS ====================
st.sidebar.header("📂 Upload Fichiers")

uploaded_param = st.sidebar.file_uploader(
    "1. Fichier Paramètres MP",
    type=['xlsx', 'xls']
)

uploaded_conso = st.sidebar.file_uploader(
    "2. Historique Consommation",
    type=['xlsx', 'xls']
)

uploaded_fournisseur = st.sidebar.file_uploader(
    "3. Fichier Fournisseurs",
    type=['xlsx', 'xls']
)

# ==================== FONCTIONS ====================
def trouver_colonne(df, noms_possibles):
    """Trouve la première colonne qui match dans la liste"""
    for nom in noms_possibles:
        if nom in df.columns:
            return nom
        # Check case insensitive
        for col in df.columns:
            if col.lower().strip() == nom.lower().strip():
                return col
    return None

def calculer_score_fournisseur(row):
    """Calcul score fournisseur: Prix 40%, Lead Time 30%, Fiabilité 20%, Qualité 10%"""
    score_prix = 10 - (row['prix_unitaire_eur'] / 10)
    score_lead = 10 - (row['lead_time_j'] / 3)
    score_fiab = row['fiabilite_%'] / 10
    score_qual = row['note_qualite_5'] * 2
    score_total = (score_prix * 0.4) + (score_lead * 0.3) + (score_fiab * 0.2) + (score_qual * 0.1)
    return round(max(0, min(10, score_total)), 2)

def determiner_statut_rotation(taux):
    """Détermine statut selon taux rotation"""
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

# ==================== MAIN LOGIC ====================
if uploaded_param and uploaded_conso:

    # Charger fichiers
    df_param = pd.read_excel(uploaded_param)
    df_conso = pd.read_excel(uploaded_conso)

    if uploaded_fournisseur:
        df_fournisseurs = pd.read_excel(uploaded_fournisseur)
    else:
        df_fournisseurs = None

    # Nettoyer colonnes - supprime espaces
    df_param.columns = df_param.columns.str.strip()
    df_conso.columns = df_conso.columns.str.strip()
    if df_fournisseurs is not None:
        df_fournisseurs.columns = df_fournisseurs.columns.str.strip()

    # ==================== DÉTECTION COLONNES PARAM ====================
    col_code_mp = trouver_colonne(df_param, ['code_mp', 'Code_MP', 'code', 'Code', 'MP'])
    col_designation = trouver_colonne(df_param, ['designation', 'Designation', 'Nom', 'nom'])
    col_stock = trouver_colonne(df_param, ['stock_secu_actuel', 'Stock_Actuel', 'stock_actuel', 'Stock'])
    col_lead = trouver_colonne(df_param, ['lead_time_j', 'Lead_Time_J', 'lead_time', 'Delai'])
    col_cout = trouver_colonne(df_param, ['cout_unitaire', 'Cout_Unitaire', 'prix', 'Prix'])
    col_moq = trouver_colonne(df_param, ['moq_kg', 'MOQ_kg', 'MOQ', 'moq'])

    # Vérification
    if not col_code_mp or not col_stock:
        st.error("❌ **Fichier Param invalide** - Colonnes manquantes: code_mp, stock_secu_actuel")
        st.write("**Colonnes trouvées:**", list(df_param.columns))
        st.stop()

    # ==================== DÉTECTION COLONNES CONSO ====================
    col_date = trouver_colonne(df_conso, ['Date', 'date', 'DATE', 'Date_Conso', 'Jour'])
    col_code_mp_conso = trouver_colonne(df_conso, ['Code_MP', 'code_mp', 'Code', 'code', 'MP'])
    col_qte = trouver_colonne(df_conso, ['Qte_Consommee', 'qte_consommee', 'Quantite', 'quantite', 'Qte', 'Consommation'])

    # Vérification
    if not col_date or not col_code_mp_conso or not col_qte:
        st.error("❌ **Fichier Conso invalide** - Colonnes manquantes")
        st.write("**Colonnes trouvées:**", list(df_conso.columns))
        st.write("**Colonnes requises:** Date, Code_MP, Qte_Consommee")
        st.stop()

    # Renommer pour standardiser
    df_conso = df_conso.rename(columns={
        col_date: 'Date',
        col_code_mp_conso: 'Code_MP',
        col_qte: 'Qte_Consommee'
    })

    # ==================== CALCULS ====================
    st.header("📊 Analyse Matières Premières")

    # Calcul consommation annuelle
    df_conso['Date'] = pd.to_datetime(df_conso['Date'], errors='coerce')
    df_conso = df_conso.dropna(subset=['Date']) # Supprime lignes sans date

    if len(df_conso) == 0:
        st.error("❌ **Aucune date valide dans fichier Consommation**")
        st.stop()

    nb_jours = (df_conso['Date'].max() - df_conso['Date'].min()).days
    if nb_jours == 0:
        nb_jours = 365

    conso_annuelle = df_conso.groupby('Code_MP')['Qte_Consommee'].sum().reset_index()
    conso_annuelle.columns = ['Code_MP', 'Conso_Totale']
    conso_annuelle['Conso_Annuelle'] = (conso_annuelle['Conso_Totale'] / nb_jours) * 365
    conso_annuelle['Conso_Jour'] = conso_annuelle['Conso_Annuelle'] / 365

    # Merger avec paramètres
    df_plan = df_param.merge(conso_annuelle, left_on=col_code_mp, right_on='Code_MP', how='left')
    df_plan['Conso_Annuelle'] = df_plan['Conso_Annuelle'].fillna(0)
    df_plan['Conso_Jour'] = df_plan['Conso_Jour'].fillna(0)

    # Calcul Taux Rotation - SANS PLAFOND
    df_plan['Stock_Actuel'] = df_plan[col_stock]
    df_plan['Rotation'] = np.where(
        df_plan['Stock_Actuel'] <= 1,
        0,
        df_plan['Conso_Annuelle'] / df_plan['Stock_Actuel']
    )
    df_plan['Taux_Rotation_%'] = df_plan['Rotation'] * 100

    # Statut
    df_plan[['Statut_Rotation', 'Couleur']] = df_plan['Taux_Rotation_%'].apply(
        lambda x: pd.Series(determiner_statut_rotation(x))
    )

    # Stock Sécurité Théorique
    df_plan['Stock_Secu_Theorique'] = df_plan['Conso_Jour'] * df_plan[col_lead] * 1.5

    # Ecart Stock
    df_plan['Ecart_Stock'] = df_plan['Stock_Actuel'] - df_plan['Stock_Secu_Theorique']
    df_plan['Ecart_%'] = (df_plan['Ecart_Stock'] / df_plan['Stock_Secu_Theorique'] * 100).fillna(0)

    # ==================== FOURNISSEURS ====================
    if df_fournisseurs is not None:
        # Détection colonnes fournisseur
        col_f_code_mp = trouver_colonne(df_fournisseurs, ['code_mp', 'Code_MP', 'code', 'MP'])

        if col_f_code_mp:
            df_fournisseurs = df_fournisseurs.rename(columns={col_f_code_mp: 'code_mp'})
            df_fournisseurs['Score'] = df_fournisseurs.apply(calculer_score_fournisseur, axis=1)

            def get_best_fournisseur(code_mp):
                df_f_mp = df_fournisseurs[df_fournisseurs['code_mp'] == code_mp]
                if len(df_f_mp) == 0:
                    return "Standard", 0, 0, 0, 0
                best = df_f_mp.loc[df_f_mp['Score'].idxmax()]
                return best['nom_fournisseur'], best['prix_unitaire_eur'], best['lead_time_j'], best['Score'], best['moq_kg']

            df_plan[['Fournisseur', 'Prix_EUR', 'Lead_Time_j', 'Score_F', 'MOQ']] = df_plan[col_code_mp].apply(
                lambda x: pd.Series(get_best_fournisseur(x))
            )
        else:
            df_plan['Fournisseur'] = 'Standard'
            df_plan['Prix_EUR'] = df_plan[col_cout] if col_cout else 0
            df_plan['Lead_Time_j'] = df_plan[col_lead]
            df_plan['Score_F'] = 5.0
            df_plan['MOQ'] = df_plan[col_moq] if col_moq else 0
    else:
        df_plan['Fournisseur'] = 'Standard'
        df_plan['Prix_EUR'] = df_plan[col_cout] if col_cout else 0
        df_plan['Lead_Time_j'] = df_plan[col_lead]
        df_plan['Score_F'] = 5.0
        df_plan['MOQ'] = df_plan[col_moq] if col_moq else 0

    # Commande Recommandée
    df_plan['Commande_Recommandee'] = np.where(
        df_plan['Ecart_Stock'] < 0,
        np.ceil(-df_plan['Ecart_Stock'] / df_plan['MOQ']) * df_plan['MOQ'],
        0
    )
    df_plan['Cout_Commande'] = df_plan['Commande_Recommandee'] * df_plan['Prix_EUR']

    # ==================== AFFICHAGE ====================
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Vue Générale", "⚠️ Alertes", "🏭 Fournisseurs", "📈 Détails"])

    with tab1:
        st.subheader("📊 KPIs Globaux")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Nb Matières Premières", len(df_plan))
        with col2:
            st.metric("Rotation Moyenne", f"{df_plan['Taux_Rotation_%'].mean():.0f}%")
        with col3:
            st.metric("Stock Total", f"{df_plan['Stock_Actuel'].sum():,.0f} kg")
        with col4:
            st.metric("Coût Commandes", f"{df_plan['Cout_Commande'].sum():,.0f} €")

        st.divider()
        st.subheader("📈 Taux Rotation par MP")
        fig_rot = px.bar(
            df_plan.sort_values('Taux_Rotation_%', ascending=False),
            x=col_code_mp,
            y='Taux_Rotation_%',
            color='Statut_Rotation',
            text='Taux_Rotation_%',
            title="Taux Rotation Stock (%)"
        )
        fig_rot.update_traces(texttemplate='%{text:.0f}%', textposition='outside')
        fig_rot.add_hline(y=150, line_dash="dash", line_color="green", annotation_text="Min Normal (150%)")
        fig_rot.add_hline(y=400, line_dash="dash", line_color="orange", annotation_text="Max Normal (400%)")
        st.plotly_chart(fig_rot, use_container_width=True)

        st.subheader("📋 Tableau Détaillé")
        df_display = df_plan[[
            col_code_mp, col_designation, 'Stock_Actuel', 'Conso_Annuelle',
            'Taux_Rotation_%', 'Statut_Rotation', 'Stock_Secu_Theorique',
            'Ecart_Stock', 'Commande_Recommandee', 'Fournisseur'
        ]].copy()
        df_display['Taux_Rotation_%'] = df_display['Taux_Rotation_%'].round(0)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("⚠️ Alertes Stock")
        df_critique = df_plan[df_plan['Ecart_Stock'] < 0]
        if len(df_critique) > 0:
            st.error(f"🔴 **{len(df_critique)} MPs en rupture ou sous seuil**")
            st.dataframe(df_critique[[col_code_mp, col_designation, 'Stock_Actuel', 'Commande_Recommandee']], hide_index=True)
        else:
            st.success("✅ Aucune rupture de stock")

        df_rotation_faible = df_plan[df_plan['Taux_Rotation_%'] < 150]
        if len(df_rotation_faible) > 0:
            st.warning(f"🟡 **{len(df_rotation_faible)} MPs avec rotation faible (<150%)**")
            st.dataframe(df_rotation_faible[[col_code_mp, col_designation, 'Taux_Rotation_%']], hide_index=True)

    with tab3:
        st.subheader("🏭 Analyse Fournisseurs")
        df_f_count = df_plan['Fournisseur'].value_counts().reset_index()
        df_f_count.columns = ['Fournisseur', 'Nb_MP']

        col1, col2 = st.columns([1, 1])
        with col1:
            fig_pie = px.pie(df_f_count, values='Nb_MP', names='Fournisseur', title="Répartition MPs", hole=0.3)
            st.plotly_chart(fig_pie, use_container_width=True)
        with col2:
            st.markdown("**Détail par MP:**")
            st.dataframe(df_plan[[col_code_mp, col_designation, 'Fournisseur', 'Prix_EUR', 'Score_F']], hide_index=True)

        st.divider()
        mps_sans_fournisseur = []
        if df_fournisseurs is not None and col_f_code_mp:
            for code_mp in df_param[col_code_mp].unique():
                if code_mp not in df_fournisseurs['code_mp'].values:
                    mps_sans_fournisseur.append(code_mp)

        if mps_sans_fournisseur:
            st.error(f"⚠️ **{len(mps_sans_fournisseur)} MPs sans fournisseur:** {', '.join(mps_sans_fournisseur)}")
        else:
            st.success("✅ **Tous les MPs ont un fournisseur assigné**")

    with tab4:
        st.subheader("📈 Analyse Détaillée")
        mp_selected = st.selectbox("Sélectionner MP:", df_plan[col_code_mp].unique())
        df_mp = df_plan[df_plan[col_code_mp] == mp_selected].iloc[0]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Stock Actuel", f"{df_mp['Stock_Actuel']:,.0f} kg")
            st.metric("Conso Annuelle", f"{df_mp['Conso_Annuelle']:,.0f} kg")
        with col2:
            st.metric("Taux Rotation", f"{df_mp['Taux_Rotation_%']:.0f}%")
            st.metric("Statut", df_mp['Statut_Rotation'])
        with col3:
            st.metric("Commande", f"{df_mp['Commande_Recommandee']:,.0f} kg")
            st.metric("Coût", f"{df_mp['Cout_Commande']:,.0f} €")

else:
    st.info("👆 **Upload les fichiers dans la sidebar pour commencer**")
