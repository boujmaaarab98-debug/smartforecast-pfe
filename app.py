import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="MRP Pro V4.8 - Live", page_icon="🚀", layout="wide")

st.markdown("""
<style>
.main { background-color: #f5f7fa; }
div[data-testid="metric-container"] { background-color: #fff; border: 1px solid #e6e6e6; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
</style>
""", unsafe_allow_html=True)

st.title("🚀 MRP Pro Dashboard V4.8 - Live Google Sheet")
st.caption("Rolling 12M + Toast Alerts + PDF Export + Gantt + Search Global")

# ==================== 1. CONFIG LINKS - BDLHOM B DYAWLK ====================
# File > Share > Publish to web > Choisir sheet > Publish > Copier lien CSV
URL_PARAM = "PASTE_LINK_PARAM_HERE"
URL_CONSO = "PASTE_LINK_CONSO_HERE"
URL_FOURNIS = "PASTE_LINK_FOURNISSEURS_HERE"
URL_MRP = "PASTE_LINK_MRP_HERE"

# ==================== 2. FONCTION DE CHARGEMENT ====================
@st.cache_data(ttl=600)
def load_from_gsheet_public():
    try:
        # --- A. Chargement des 4 sheets mn links ---
        df_param = pd.read_csv(URL_PARAM)

        # Conso fiha header fusionné donc traitement spécial
        df_conso_raw = pd.read_csv(URL_CONSO, header=None)
        df_conso_raw.columns = df_conso_raw.iloc[1] # Row 2 hia headers s7i7a
        df_conso = df_conso_raw[2:].reset_index(drop=True) # Data mn row 3

        df_fournis = pd.read_csv(URL_FOURNIS)
        df_prev_pf = pd.read_csv(URL_MRP)

        # --- B. Nettoyage & Renommage ---
        df_param = df_param.rename(columns={'code_mp': 'Code_MP', 'designation': 'Désignation', 'lead_time_j': 'Délai', 'moq_kg': 'MOQ', 'stock_secu_actuel': 'Stock_Sécu'})

        df_conso = df_conso.rename(columns={
            'Ref produit finis': 'Ref_PF', 'CODE matière': 'Code_MP',
            'conso journaliere MP en KG': 'Conso_U_Unitaire', 'Couverture : 2 semaine NBR OCTABIN': 'Couverture_Octab'
        })
        # Convertir en numérique
        for col in ['Conso_U_Unitaire', 'Couverture_Octab']:
            df_conso[col] = pd.to_numeric(df_conso[col], errors='coerce')
        df_conso = df_conso.dropna(subset=['Code_MP', 'Ref_PF'])
        df_conso['Stock_Actuel_MP'] = df_conso['Couverture_Octab'] * df_conso['Conso_U_Unitaire']

        df_fournis = df_fournis.rename(columns={'code_mp': 'Code_MP', 'nom_fournisseur': 'Fournisseur', 'prix_unitaire_eur': 'Prix_EUR'})
        df_prev_pf = df_prev_pf.rename(columns={'Ref produit finis': 'Ref_PF'})

        # --- C. Explosion Prévisionnel PF -> Besoin MP Journalier ---
        df_prev_melt = df_prev_pf.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
        df_prev_melt['Qte_PF_Prévue'] = pd.to_numeric(df_prev_melt['Qte_PF_Prévue'], errors='coerce')
        df_prev_melt = df_prev_melt.dropna(subset=['Qte_PF_Prévue'])
        df_prev_melt['Date'] = pd.to_datetime(df_prev_melt['Date'], dayfirst=True, errors='coerce')
        df_prev_melt = df_prev_melt.dropna(subset=['Date'])

        df_besoin_mp = pd.merge(df_prev_melt, df_conso[['Ref_PF', 'Code_MP', 'Conso_U_Unitaire']], on='Ref_PF', how='inner')
        df_besoin_mp['Besoin_MP_KG'] = df_besoin_mp['Qte_PF_Prévue'] * df_besoin_mp['Conso_U_Unitaire']
        df_besoin_jour = df_besoin_mp.groupby(['Code_MP', 'Date'])['Besoin_MP_KG'].sum().reset_index()

        # --- D. Construction DF_MRP Final ---
        for col in ['Délai', 'MOQ', 'Stock_Sécu']: df_param[col] = pd.to_numeric(df_param[col], errors='coerce')
        for col in ['Prix_EUR', 'taux_service_%', 'fiabilite_%', 'note_qualite_5', 'lead_time_j', 'moq_kg']:
            if col in df_fournis.columns: df_fournis[col] = pd.to_numeric(df_fournis[col], errors='coerce')

        df_mrp = df_param[['Code_MP', 'Désignation', 'Délai', 'MOQ', 'Stock_Sécu']].copy()
        stock_actuel = df_conso.groupby('Code_MP')['Stock_Actuel_MP'].sum().reset_index().rename(columns={'Stock_Actuel_MP': 'Stock'})
        df_mrp = pd.merge(df_mrp, stock_actuel, on='Code_MP', how='left')
        df_mrp = pd.merge(df_mrp, df_fournis, on='Code_MP', how='left')

        date_fin_30j = datetime.now() + timedelta(days=30)
        conso_30j = df_besoin_jour[df_besoin_jour['Date'] <= date_fin_30j].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
        conso_30j['Consommation_J'] = conso_30j['Besoin_MP_KG'] / 30
        df_mrp = pd.merge(df_mrp, conso_30j[['Code_MP', 'Consommation_J']], on='Code_MP', how='left')

        # --- E. Calculs Finaux ---
        df_mrp = df_mrp.fillna(0)
        df_mrp['Consommation_J'] = df_mrp['Consommation_J'].replace(0, 0.1)
        df_mrp['Couverture_J'] = df_mrp['Stock'] / df_mrp['Consommation_J']
        df_mrp['Écart'] = df_mrp['Stock'] - df_mrp['Stock_Sécu']
        df_mrp['Valeur_Risque_EUR'] = df_mrp['Écart'].clip(upper=0).abs() * df_mrp['Prix_EUR']
        df_mrp['Statut'] = pd.cut(df_mrp['Couverture_J'], bins=[-1, 0, 7, 15, 9999], labels=['Rupture', 'Critique', 'Alerte', 'OK'])

        return df_mrp, df_besoin_jour

    except Exception as e:
        st.error(f"Erreur f chargement mn Google Sheet: {e}")
        st.info("Vérifi: Wach 'Publish to web' mdir l kola sheet? Wach links s7a7?")
        return None, None

# ==================== 3. CHARGEMENT ====================
if "PASTE_LINK" in URL_PARAM:
    st.warning("⚠️ Mazal ma bdltich l links dyal Google Sheet f l code")
    st.info("1. Sir l Google Sheet > File > Share > Publish to web\n2. Choisir 'Param' > Publish > Copier lien CSV > 7tto f URL_PARAM\n3. 3awd nafs l3amal l 'Conso', 'Fournisseurs', 'MRP'")
    st.stop()

df_mrp, df_besoin_jour = load_from_gsheet_public()

if df_mrp is None:
    st.stop()

st.sidebar.success("Data Live mn Google Sheet ✅")
if st.sidebar.button("🔄 Rafraîchir Data"):
    st.cache_data.clear()
    st.rerun()

# ==================== 4. INTERFACE V4.8 DYALK ====================
tab1, tab2, tab3 = st.tabs(["📊 Vue Globale", "⚠️ Alertes & Projection", "🏢 Fourni 360"])

with tab1:
    st.header("Vue Globale MRP - Données Réelles Live")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nb MP", df_mrp['Code_MP'].nunique())
    col2.metric("Valeur Stock Total", f"€ {(df_mrp['Stock'] * df_mrp['Prix_EUR']).sum():,.0f}")
    col3.metric("Nb Ruptures", df_mrp[df_mrp['Statut'] == 'Rupture'].shape[0])
    col4.metric("Valeur Risque", f"€ {df_mrp['Valeur_Risque_EUR'].sum():,.0f}")

    st.dataframe(df_mrp.style.format({
        'Stock': '{:,.0f}', 'Consommation_J': '{:,.1f}', 'Couverture_J': '{:.1f}',
        'Stock_Sécu': '{:,.0f}', 'Écart': '{:,.0f}', 'Valeur_Risque_EUR': '€ {:,.0f}', 'Prix_EUR': '€ {:.2f}'
    }), use_container_width=True, height=600)

with tab2:
    st.header("Alertes & Projection de Rupture")
    df_alertes = df_mrp[df_mrp['Statut'].isin(['Rupture', 'Critique', 'Alerte'])].sort_values('Couverture_J')
    st.dataframe(df_alertes[['Code_MP', 'Désignation', 'Fournisseur', 'Stock', 'Couverture_J', 'Délai']], use_container_width=True)

    if not df_alertes.empty:
        st.subheader("Projection de Stock")
        mp_select = st.selectbox("Choisir MP:", df_alertes['Code_MP'])
        stock_initial = df_alertes[df_alertes['Code_MP'] == mp_select]['Stock'].iloc[0]
        besoin_mp = df_besoin_jour[df_besoin_jour['Code_MP'] == mp_select].copy().sort_values('Date')
        if not besoin_mp.empty:
            besoin_mp['Stock_Projeté'] = stock_initial - besoin_mp['Besoin_MP_KG'].cumsum()
            fig = px.line(besoin_mp, x='Date', y='Stock_Projeté', title=f"Projection Stock {mp_select}")
            fig.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="RUPTURE")
            st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.header("🏢 Fournisseur 360")
    fourni_select = st.selectbox("Choisir Fournisseur", sorted(df_mrp['Fournisseur'].dropna().unique()))
    if fourni_select:
        df_f = df_mrp[df_mrp['Fournisseur'] == fourni_select]
        df_kpi = df_fournis[df_fournis['Fournisseur'] == fourni_select].iloc[0] if not df_fournis[df_fournis['Fournisseur'] == fourni_select].empty else {}

        st.subheader(f"KPIs pour {fourni_select}")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Taux Service", f"{df_kpi.get('taux_service_%', 0):.0f}%")
        kpi2.metric("Fiabilité", f"{df_kpi.get('fiabilite_%', 0):.0f}%")
        kpi3.metric("Lead Time", f"{df_kpi.get('lead_time_j', 0):.0f} j")
        kpi4.metric("Note Qualité", f"{df_kpi.get('note_qualite_5', 0)}/5")

        st.subheader("Matières Premières Gérées")
        st.dataframe(df_f[['Code_MP', 'Désignation', 'Stock', 'Couverture_J', 'Écart', 'Valeur_Risque_EUR']], use_container_width=True)
