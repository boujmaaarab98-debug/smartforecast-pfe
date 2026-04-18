import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

st.set_page_config(page_title="MRP Pro V4.12 - Seuils Pro", page_icon="🚀", layout="wide")

st.title("🚀 MRP Pro Dashboard V4.12 - Seuils Professionnels")
st.caption("Rouge: 4j | Orange: 6j | Stock Min: 12j | KPIs Consommation & Prévision")

# ==================== 1. SEUILS PROFESSIONNELS ====================
SEUIL_ROUGE = 4 # Couverture d'alerte rouge
SEUIL_ORANGE = 6 # Couverture orange
SEUIL_SECURITE = 12 # Stock min 12 jours

st.sidebar.info(f"""
**🔴 Rouge:** < {SEUIL_ROUGE} jours
**🟠 Orange:** < {SEUIL_ORANGE} jours
**🟢 Stock Min:** {SEUIL_SECURITE} jours
""")

# ==================== 2. CONFIG LINKS ====================
URL_PARAM = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=0&single=true&output=csv"
URL_CONSO = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=326309876&single=true&output=csv"
URL_FOURNIS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=1581263595&single=true&output=csv"
URL_MRP = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=418845709&single=true&output=csv"

# ==================== 3. FONCTION NETTOYAGE NUMÉRIQUE ====================
def clean_numeric(series):
    return pd.to_numeric(
        series.astype(str)
      .str.replace(' ', '')
      .str.replace(',', '.')
      .str.replace('€', '')
      .str.replace('KG', '')
      .str.replace('kg', '')
      .str.strip(),
        errors='coerce'
    )

# ==================== 4. FONCTION DE CHARGEMENT ====================
@st.cache_data(ttl=600)
def load_full_data():
    try:
        # --- 1. Param ---
        df_param = pd.read_csv(URL_PARAM)
        df_param = df_param.rename(columns={
            'code_mp': 'Code_MP',
            'designation': 'Désignation',
            'lead_time_j': 'Délai_Param',
            'moq_kg': 'MOQ_Param',
            'stock_secu_actuel': 'Stock_Sécu_Sheet' # N7afdo 3liha mais ma nst3mloch
        })
        for col in ['Délai_Param', 'MOQ_Param', 'Stock_Sécu_Sheet']:
            if col in df_param.columns:
                df_param[col] = clean_numeric(df_param[col])

        # --- 2. Conso ---
        df_conso = pd.read_csv(URL_CONSO)
        df_conso = df_conso.rename(columns={
            'Ref produit finis': 'Ref_PF',
            'CODE matière': 'Code_MP',
            'conso journaliere MP en KG': 'Conso_U_Unitaire',
            'Couverture : 2 semaine NBR OCTABIN': 'Couverture_Octab'
        })
        df_conso['Conso_U_Unitaire'] = clean_numeric(df_conso['Conso_U_Unitaire'])
        df_conso['Couverture_Octab'] = clean_numeric(df_conso['Couverture_Octab'])
        df_conso['Stock_Actuel_MP'] = df_conso['Couverture_Octab'] * df_conso['Conso_U_Unitaire']
        df_conso = df_conso.dropna(subset=['Code_MP', 'Ref_PF'])

        # --- 3. Fournisseurs ---
        df_fournis = pd.read_csv(URL_FOURNIS)
        df_fournis = df_fournis.rename(columns={
            'code_mp': 'Code_MP',
            'nom_fournisseur': 'Fournisseur',
            'prix_unitaire_eur': 'Prix_EUR',
            'moq_kg': 'MOQ_Fournis',
            'lead_time_j': 'Délai_Fournis'
        })
        for col in ['Prix_EUR', 'MOQ_Fournis', 'Délai_Fournis', 'taux_service_%', 'fiabilite_%', 'note_qualite_5']:
            if col in df_fournis.columns:
                df_fournis[col] = clean_numeric(df_fournis[col])

        # --- 4. MRP Prévisionnel ---
        df_prev_pf = pd.read_csv(URL_MRP)
        df_prev_pf = df_prev_pf.rename(columns={'Ref produit finis': 'Ref_PF'})

        # Explosion Prévisionnel
        df_prev_melt = df_prev_pf.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
        df_prev_melt['Qte_PF_Prévue'] = clean_numeric(df_prev_melt['Qte_PF_Prévue'])
        df_prev_melt = df_prev_melt.dropna(subset=['Qte_PF_Prévue'])
        df_prev_melt['Date'] = pd.to_datetime(df_prev_melt['Date'], dayfirst=True, errors='coerce')
        df_prev_melt = df_prev_melt.dropna(subset=['Date'])

        df_besoin_mp = pd.merge(df_prev_melt, df_conso[['Ref_PF', 'Code_MP', 'Conso_U_Unitaire']], on='Ref_PF', how='inner')
        df_besoin_mp['Besoin_MP_KG'] = df_besoin_mp['Qte_PF_Prévue'] * df_besoin_mp['Conso_U_Unitaire']
        df_besoin_jour = df_besoin_mp.groupby(['Code_MP', 'Date'])['Besoin_MP_KG'].sum().reset_index()

        # --- 5. Construction DF_MRP Final ---
        df_mrp = df_param.copy()
        stock_actuel = df_conso.groupby('Code_MP')['Stock_Actuel_MP'].sum().reset_index().rename(columns={'Stock_Actuel_MP': 'Stock'})
        df_mrp = pd.merge(df_mrp, stock_actuel, on='Code_MP', how='left')
        df_mrp = pd.merge(df_mrp, df_fournis, on='Code_MP', how='left')

        date_fin_30j = datetime.now() + timedelta(days=30)
        conso_30j = df_besoin_jour[df_besoin_jour['Date'] <= date_fin_30j].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
        conso_30j['Consommation_J'] = conso_30j['Besoin_MP_KG'] / 30
        df_mrp = pd.merge(df_mrp, conso_30j[['Code_MP', 'Consommation_J']], on='Code_MP', how='left')

        df_mrp = df_mrp.fillna(0)
        df_mrp['Consommation_J'] = df_mrp['Consommation_J'].replace(0, 0.1)
        df_mrp['Couverture_J'] = df_mrp['Stock'] / df_mrp['Consommation_J']

        # ===== STOCK SÉCU = 12 JOURS AUTOMATIQUE =====
        df_mrp['Stock_Sécu'] = df_mrp['Consommation_J'] * SEUIL_SECURITE

        df_mrp['Écart'] = df_mrp['Stock'] - df_mrp['Stock_Sécu']
        df_mrp['Valeur_Risque_EUR'] = df_mrp['Écart'].clip(upper=0).abs() * df_mrp['Prix_EUR']

        # ===== STATUT AVEC TES SEUILS =====
        conditions = [
            (df_mrp['Couverture_J'] < SEUIL_ROUGE),
            (df_mrp['Couverture_J'] < SEUIL_ORANGE),
            (df_mrp['Couverture_J'] < SEUIL_SECURITE),
        ]
        choices = ['Rouge', 'Orange', 'Alerte']
        df_mrp['Statut'] = np.select(conditions, choices, default='OK')

        return df_mrp, df_besoin_jour, df_conso, df_prev_pf

    except Exception as e:
        st.error(f"Erreur f chargement: {e}")
        return None, None, None, None

# ==================== 5. CHARGEMENT ====================
df_mrp, df_besoin_jour, df_conso, df_prev_pf = load_full_data()

if df_mrp is None:
    st.stop()

st.sidebar.success("Data Full mn Google Sheet ✅")

if st.sidebar.button("🔄 Rafraîchir Data"):
    st.cache_data.clear()
    st.rerun()

# ==================== 6. INTERFACE V4.12 ====================
tab1, tab2, tab3, tab4 = st.tabs(["📊 MRP Complet", "📈 KPIs Conso & Prévision", "⚠️ Alertes", "🏢 Fournisseurs"])

with tab1:
    st.header("MRP Complet - Seuils Professionnels Appliqués")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Rouge <4j", df_mrp[df_mrp['Statut'] == 'Rouge'].shape[0])
    col2.metric("🟠 Orange <6j", df_mrp[df_mrp['Statut'] == 'Orange'].shape[0])
    col3.metric("🟡 Alerte <12j", df_mrp[df_mrp['Statut'] == 'Alerte'].shape[0])
    col4.metric("🟢 OK >12j", df_mrp[df_mrp['Statut'] == 'OK'].shape[0])

    # Coloration conditionnelle
    def highlight_statut(row):
        if row['Statut'] == 'Rouge':
            return ['background-color: #ffcccc'] * len(row)
        elif row['Statut'] == 'Orange':
            return ['background-color: #ffe4cc'] * len(row)
        elif row['Statut'] == 'Alerte':
            return ['background-color: #ffffcc'] * len(row)
        else:
            return ['background-color: #ccffcc'] * len(row)

    st.dataframe(df_mrp.style.apply(highlight_statut, axis=1).format({
        'Stock': '{:,.0f}', 'Consommation_J': '{:,.1f}', 'Couverture_J': '{:.1f}',
        'Stock_Sécu': '{:,.0f}', 'Écart': '{:,.0f}', 'Valeur_Risque_EUR': '€ {:,.0f}', 'Prix_EUR': '€ {:.2f}'
    }), use_container_width=True, height=600)

with tab2:
    st.header("📈 KPIs Consommation & Prévision")

    # ===== KPI 1: Consommation Moyenne =====
    st.subheader("1️⃣ Consommation Moyenne par MP")
    conso_moy = df_conso.groupby('Code_MP')['Conso_U_Unitaire'].agg(['mean', 'std', 'count']).reset_index()
    conso_moy.columns = ['Code_MP', 'Conso_Moy_KG', 'Volatilité_StdDev', 'Nb_PF_Utilisateurs']
    conso_moy['CV_%'] = (conso_moy['Volatilité_StdDev'] / conso_moy['Conso_Moy_KG'] * 100).round(1)
    conso_moy = conso_moy.fillna(0)

    col1, col2, col3 = st.columns(3)
    col1.metric("Conso Moyenne Globale", f"{conso_moy['Conso_Moy_KG'].mean():.1f} KG/j")
    if not conso_moy.empty:
        col2.metric("MP Plus Consommé", f"{conso_moy.loc[conso_moy['Conso_Moy_KG'].idxmax(), 'Code_MP']}")
    col3.metric("Volatilité Moyenne CV%", f"{conso_moy['CV_%'].mean():.1f}%")

    st.dataframe(conso_moy.sort_values('Conso_Moy_KG', ascending=False), use_container_width=True, height=300)

    # ===== KPI 2: Volatilité =====
    st.subheader("2️⃣ Volatilité Consommation")
    fig_vol = px.scatter(conso_moy, x='Conso_Moy_KG', y='CV_%', size='Nb_PF_Utilisateurs',
                         hover_data=['Code_MP'], title="Matrice Volatilité vs Volume")
    fig_vol.add_hline(y=20, line_dash="dash", line_color="orange", annotation_text="Stable <20%")
    fig_vol.add_hline(y=50, line_dash="dash", line_color="red", annotation_text="Volatile >50%")
    st.plotly_chart(fig_vol, use_container_width=True)

    # ===== KPI 3: Taux Utilisation MOQ =====
    st.subheader("3️⃣ Taux Utilisation MOQ")
    besoin_30j = df_besoin_jour[df_besoin_jour['Date'] <= datetime.now() + timedelta(days=30)].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
    besoin_30j.columns = ['Code_MP', 'Besoin_30j_KG']

    df_moq = pd.merge(df_mrp[['Code_MP', 'MOQ_Param']], besoin_30j, on='Code_MP', how='left').fillna(0)
    df_moq['Commande_Optimale'] = df_moq[['Besoin_30j_KG', 'MOQ_Param']].max(axis=1)
    df_moq['Taux_Utilisation_MOQ_%'] = np.where(df_moq['Commande_Optimale'] > 0,
                                                 (df_moq['Besoin_30j_KG'] / df_moq['Commande_Optimale'] * 100).round(1),
                                                 0)
    df_moq['Surstock_MOQ_KG'] = (df_moq['Commande_Optimale'] - df_moq['Besoin_30j_KG']).clip(lower=0)

    col1, col2, col3 = st.columns(3)
    col1.metric("Taux Utilisation MOQ Moyen", f"{df_moq['Taux_Utilisation_MOQ_%'].mean():.1f}%")
    col2.metric("Surstock dû au MOQ", f"{df_moq['Surstock_MOQ_KG'].sum():,.0f} KG")
    col3.metric("Nb MP b Surstock MOQ", f"{(df_moq['Surstock_MOQ_KG'] > 0).sum()}")

    st.dataframe(df_moq.sort_values('Surstock_MOQ_KG', ascending=False), use_container_width=True, height=300)

    # ===== KPI 4: Besoin 30/60/90J =====
    st.subheader("4️⃣ Besoin Prévisionnel 30/60/90 Jours")
    date_60j = datetime.now() + timedelta(days=60)
    date_90j = datetime.now() + timedelta(days=90)

    besoin_60j = df_besoin_jour[df_besoin_jour['Date'] <= date_60j].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
    besoin_90j = df_besoin_jour[df_besoin_jour['Date'] <= date_90j].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()

    df_besoin_comp = pd.merge(besoin_30j, besoin_60j, on='Code_MP', how='outer', suffixes=('_30j', '_60j'))
    df_besoin_comp = pd.merge(df_besoin_comp, besoin_90j, on='Code_MP', how='outer')
    df_besoin_comp.columns = ['Code_MP', 'Besoin_30j', 'Besoin_60j', 'Besoin_90j']
    df_besoin_comp = df_besoin_comp.fillna(0)
    df_besoin_comp = pd.merge(df_besoin_comp, df_mrp[['Code_MP', 'Stock', 'Prix_EUR']], on='Code_MP', how='left')
    df_besoin_comp['Manque_30j'] = (df_besoin_comp['Besoin_30j'] - df_besoin_comp['Stock']).clip(lower=0)
    df_besoin_comp['Valeur_Achat_30j'] = df_besoin_comp['Manque_30j'] * df_besoin_comp['Prix_EUR']

    col1, col2, col3 = st.columns(3)
    col1.metric("Besoin Total 30j", f"{df_besoin_comp['Besoin_30j'].sum():,.0f} KG")
    col2.metric("Besoin Total 90j", f"{df_besoin_comp['Besoin_90j'].sum():,.0f} KG")
    col3.metric("Valeur Achat 30j", f"€ {df_besoin_comp['Valeur_Achat_30j'].sum():,.0f}")

    st.dataframe(df_besoin_comp.sort_values('Valeur_Achat_30j', ascending=False), use_container_width=True, height=300)

with tab3:
    st.header("⚠️ Alertes Selon Tes Seuils")
    df_alertes = df_mrp[df_mrp['Statut'].isin(['Rouge', 'Orange', 'Alerte'])].sort_values('Couverture_J')
    st.dataframe(df_alertes, use_container_width=True)

with tab4:
    st.header("Fournisseurs - Data Complète")
    fourni_select = st.selectbox("Choisir Fournisseur", sorted(df_mrp['Fournisseur'].dropna().unique()))
    if fourni_select:
        df_f = df_mrp[df_mrp['Fournisseur'] == fourni_select]
        st.dataframe(df_f, use_container_width=True)
