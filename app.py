import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="MRP Pro Dashboard V4.8 - PRO MAX", page_icon="🚀", layout="wide")

# ==================== CONFIG & STYLE ====================
st.markdown("""
<style>
.main { background-color: #f5f7fa; }
div[data-testid="metric-container"] { background-color: #fff; border: 1px solid #e6e6e6; padding: 15px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 MRP Pro Dashboard V4.8 - PRO MAX")
st.caption("Rolling 12M + Toast Alerts + PDF Export + Gantt + Search Global")

# ==================== 1. FONCTION DE CHARGEMENT MODIFIÉE ====================
@st.cache_data
def load_and_process_data(fichier):
    try:
        # --- A. Chargement des 4 sheets ---
        df_param = pd.read_excel(fichier, sheet_name="Param")
        df_conso = pd.read_excel(fichier, sheet_name="Conso", skiprows=1) # Skip header fusionné
        df_fournis = pd.read_excel(fichier, sheet_name="Fournisseurs")
        df_prev_pf = pd.read_excel(fichier, sheet_name="MRP")

        # --- B. Nettoyage & Renommage ---
        df_param = df_param.rename(columns={'code_mp': 'Code_MP', 'designation': 'Désignation', 'lead_time_j': 'Délai', 'moq_kg': 'MOQ', 'stock_secu_actuel': 'Stock_Sécu'})

        df_conso = df_conso.rename(columns={
            'Ref produit finis': 'Ref_PF', 'CODE matière': 'Code_MP',
            'conso journaliere MP en KG': 'Conso_U_Unitaire', 'Couverture : 2 semaine NBR OCTABIN': 'Couverture_Octab'
        })
        df_conso = df_conso.dropna(subset=['Code_MP', 'Ref_PF'])
        df_conso['Stock_Actuel_MP'] = df_conso['Couverture_Octab'] * df_conso['Conso_U_Unitaire']

        df_fournis = df_fournis.rename(columns={'code_mp': 'Code_MP', 'nom_fournisseur': 'Fournisseur', 'prix_unitaire_eur': 'Prix_EUR'})
        df_prev_pf = df_prev_pf.rename(columns={'Ref produit finis': 'Ref_PF'})

        # --- C. Explosion Prévisionnel PF -> Besoin MP Journalier ---
        df_prev_melt = df_prev_pf.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
        df_prev_melt = df_prev_melt.dropna(subset=['Qte_PF_Prévue'])
        df_prev_melt['Date'] = pd.to_datetime(df_prev_melt['Date'], dayfirst=True, errors='coerce')
        df_prev_melt = df_prev_melt.dropna(subset=['Date'])

        df_besoin_mp = pd.merge(df_prev_melt, df_conso[['Ref_PF', 'Code_MP', 'Conso_U_Unitaire']], on='Ref_PF', how='inner')
        df_besoin_mp['Besoin_MP_KG'] = df_besoin_mp['Qte_PF_Prévue'] * df_besoin_mp['Conso_U_Unitaire']
        df_besoin_jour = df_besoin_mp.groupby(['Code_MP', 'Date'])['Besoin_MP_KG'].sum().reset_index()

        # --- D. Construction du DF_MRP Final ---
        df_mrp = df_param[['Code_MP', 'Désignation', 'Délai', 'MOQ', 'Stock_Sécu']].copy()

        stock_actuel = df_conso.groupby('Code_MP')['Stock_Actuel_MP'].sum().reset_index().rename(columns={'Stock_Actuel_MP': 'Stock'})
        df_mrp = pd.merge(df_mrp, stock_actuel, on='Code_MP', how='left')
        df_mrp = pd.merge(df_mrp, df_fournis, on='Code_MP', how='left')

        date_fin_30j = datetime.now() + timedelta(days=30)
        conso_30j = df_besoin_jour[df_besoin_jour['Date'] <= date_fin_30j].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
        conso_30j['Consommation_J'] = conso_30j['Besoin_MP_KG'] / 30
        df_mrp = pd.merge(df_mrp, conso_30j[['Code_MP', 'Consommation_J']], on='Code_MP', how='left')

        # --- E. Calculs Finaux ---
        df_mrp['Stock'] = df_mrp['Stock'].fillna(0)
        df_mrp['Consommation_J'] = df_mrp['Consommation_J'].fillna(0.1)
        df_mrp['Stock_Sécu'] = df_mrp['Stock_Sécu'].fillna(0)
        df_mrp['Prix_EUR'] = df_mrp['Prix_EUR'].fillna(0)

        df_mrp['Couverture_J'] = df_mrp['Stock'] / df_mrp['Consommation_J']
        df_mrp['Écart'] = df_mrp['Stock'] - df_mrp['Stock_Sécu']
        df_mrp['Valeur_Risque_EUR'] = df_mrp['Écart'].clip(upper=0).abs() * df_mrp['Prix_EUR']

        # Ajouter colonnes li kanو f V4.8 9dima bach ma ycrashich
        df_mrp['Statut'] = pd.cut(df_mrp['Couverture_J'], bins=[-1, 0, 7, 15, 9999], labels=['Rupture', 'Critique', 'Alerte', 'OK'])

        return df_mrp, df_besoin_jour

    except Exception as e:
        st.error(f"Erreur f chargement: {e}")
        return None, None

# ==================== 2. CHARGEMENT DES DONNÉES ====================
fichier_data = "Matière_première_et_PF_consommation_journaliere.xlsx"
df_mrp, df_besoin_jour = load_and_process_data(fichier_data)

if df_mrp is None:
    st.stop()

# ==================== 3. INTERFACE V4.8 DYALK KAMLA ====================
# Hna khlli l interface dyalk kamla kif ma hiya
# Ana ghadi n7t ghi exemple dyal tab, nta dir l code dyalk kamlo li kayn f V4.8

tab1, tab2, tab3 = st.tabs(["📊 Vue Globale", "⚠️ Alertes", "🏢 Fourni 360"])

with tab1:
    st.header("Vue Globale MRP - Données Réelles")

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nb MP", df_mrp['Code_MP'].nunique())
    col2.metric("Valeur Stock Total", f"€ {df_mrp['Stock'].sum() * df_mrp['Prix_EUR'].mean():,.0f}")
    col3.metric("Nb Ruptures", df_mrp[df_mrp['Statut'] == 'Rupture'].shape[0])
    col4.metric("Valeur Risque", f"€ {df_mrp['Valeur_Risque_EUR'].sum():,.0f}")

    st.dataframe(df_mrp, use_container_width=True, height=600)

with tab2:
    st.header("Alertes & Ruptures")
    df_alertes = df_mrp[df_mrp['Statut'].isin(['Rupture', 'Critique', 'Alerte'])]
    st.dataframe(df_alertes, use_container_width=True)

    if not df_alertes.empty:
        mp_select = st.selectbox("Choisir MP pour voir projection:", df_alertes['Code_MP'])
        stock_initial = df_alertes[df_alertes['Code_MP'] == mp_select]['Stock'].iloc[0]
        besoin_mp = df_besoin_jour[df_besoin_jour['Code_MP'] == mp_select].copy().sort_values('Date')

        if not besoin_mp.empty:
            besoin_mp['Stock_Projeté'] = stock_initial - besoin_mp['Besoin_MP_KG'].cumsum()
            fig = px.line(besoin_mp, x='Date', y='Stock_Projeté', title=f"Projection Stock {mp_select}")
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.header("Fournisseur 360")
    # Dir hna l code dyal Fourni 360 dyalk mn V4.8
    fourni_select = st.selectbox("Fournisseur", sorted(df_mrp['Fournisseur'].dropna().unique()))
    if fourni_select:
        df_f = df_mrp[df_mrp['Fournisseur'] == fourni_select]
        st.dataframe(df_f)

# Zid hna ga3 les features lakhrin dyal V4.8: Rolling 12M, Toast Alerts, PDF Export, Gantt, Search Global...
# L mohim howa 'df_mrp' w 'df_besoin_jour' db fihom data s7i7a 100%
