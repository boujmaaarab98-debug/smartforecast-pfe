import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="MRP Pro V4.10 - Full Data", page_icon="🚀", layout="wide")

st.title("🚀 MRP Pro Dashboard V4.10 - Full Google Sheet Data")
st.caption("Kolchi m7foud + KPIs + Rolling 12M + Toast Alerts + PDF Export")

# ==================== 1. CONFIG LINKS ====================
URL_PARAM = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=0&single=true&output=csv"
URL_CONSO = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=326309876&single=true&output=csv"
URL_FOURNIS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=1581263595&single=true&output=csv"
URL_MRP = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=418845709&single=true&output=csv"

# ==================== 2. FONCTION DE CHARGEMENT - KOLCHI M7FOUD ====================
@st.cache_data(ttl=600)
def load_full_data():
    try:
        # --- 1. Param: nakhdo KOLCHI ---
        df_param = pd.read_csv(URL_PARAM)
        # N-renammiw ghi li m7tajin l calcul, lakhrin yb9aw
        df_param = df_param.rename(columns={
            'code_mp': 'Code_MP',
            'designation': 'Désignation',
            'lead_time_j': 'Délai',
            'moq_kg': 'MOQ',
            'stock_secu_actuel': 'Stock_Sécu'
        })

        # --- 2. Conso: nakhdo KOLCHI ---
        df_conso = pd.read_csv(URL_CONSO)
        df_conso = df_conso.rename(columns={
            'Ref produit finis': 'Ref_PF',
            'CODE matière': 'Code_MP',
            'conso journaliere MP en KG': 'Conso_U_Unitaire',
            'Couverture : 2 semaine NBR OCTABIN': 'Couverture_Octab'
        })

        # Vérification colonnes essentielles
        required = ['Ref_PF', 'Code_MP', 'Conso_U_Unitaire', 'Couverture_Octab']
        missing = [c for c in required if c not in df_conso.columns]
        if missing:
            st.error(f"Colonnes manquantes f Conso: {missing}")
            st.info(f"Colonnes disponibles: {df_conso.columns.tolist()}")
            return None, None, None, None

        # Calcul Stock - nzidouh f colonne jdida bla ma nmshou lakhrin
        df_conso['Conso_U_Unitaire'] = pd.to_numeric(df_conso['Conso_U_Unitaire'], errors='coerce')
        df_conso['Couverture_Octab'] = pd.to_numeric(df_conso['Couverture_Octab'], errors='coerce')
        df_conso['Stock_Actuel_MP'] = df_conso['Couverture_Octab'] * df_conso['Conso_U_Unitaire']

        # --- 3. Fournisseurs: nakhdo KOLCHI ---
        df_fournis = pd.read_csv(URL_FOURNIS)
        df_fournis = df_fournis.rename(columns={
            'code_mp': 'Code_MP',
            'nom_fournisseur': 'Fournisseur',
            'prix_unitaire_eur': 'Prix_EUR'
        })

        # --- 4. MRP Prévisionnel: nakhdo KOLCHI ---
        df_prev_pf = pd.read_csv(URL_MRP)
        df_prev_pf = df_prev_pf.rename(columns={'Ref produit finis': 'Ref_PF'})

        # --- 5. Explosion Prévisionnel ---
        df_prev_melt = df_prev_pf.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
        df_prev_melt['Qte_PF_Prévue'] = pd.to_numeric(df_prev_melt['Qte_PF_Prévue'], errors='coerce')
        df_prev_melt = df_prev_melt.dropna(subset=['Qte_PF_Prévue'])
        df_prev_melt['Date'] = pd.to_datetime(df_prev_melt['Date'], dayfirst=True, errors='coerce')
        df_prev_melt = df_prev_melt.dropna(subset=['Date'])

        df_besoin_mp = pd.merge(df_prev_melt, df_conso[['Ref_PF', 'Code_MP', 'Conso_U_Unitaire']], on='Ref_PF', how='inner')
        df_besoin_mp['Besoin_MP_KG'] = df_besoin_mp['Qte_PF_Prévue'] * df_besoin_mp['Conso_U_Unitaire']
        df_besoin_jour = df_besoin_mp.groupby(['Code_MP', 'Date'])['Besoin_MP_KG'].sum().reset_index()

        # --- 6. Construction DF_MRP Final - N7AFDO 3LA KOLCHI ---
        # Convert numeric
        for col in ['Délai', 'MOQ', 'Stock_Sécu']:
            if col in df_param.columns:
                df_param[col] = pd.to_numeric(df_param[col], errors='coerce')
        for col in ['Prix_EUR', 'taux_service_%', 'fiabilite_%', 'note_qualite_5', 'lead_time_j', 'moq_kg']:
            if col in df_fournis.columns:
                df_fournis[col] = pd.to_numeric(df_fournis[col], errors='coerce')

        # Merge KOLCHI mn Param
        df_mrp = df_param.copy() # KOLCHI m7foud

        # Stock actuel mn Conso
        stock_actuel = df_conso.groupby('Code_MP')['Stock_Actuel_MP'].sum().reset_index().rename(columns={'Stock_Actuel_MP': 'Stock'})
        df_mrp = pd.merge(df_mrp, stock_actuel, on='Code_MP', how='left')

        # Merge KOLCHI mn Fournisseurs - hna fin kayt7afdo kolchi
        df_mrp = pd.merge(df_mrp, df_fournis, on='Code_MP', how='left', suffixes=('', '_fournis'))

        # Consommation 30j
        date_fin_30j = datetime.now() + timedelta(days=30)
        conso_30j = df_besoin_jour[df_besoin_jour['Date'] <= date_fin_30j].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
        conso_30j['Consommation_J'] = conso_30j['Besoin_MP_KG'] / 30
        df_mrp = pd.merge(df_mrp, conso_30j[['Code_MP', 'Consommation_J']], on='Code_MP', how='left')

        # --- 7. Calculs MRP ---
        df_mrp = df_mrp.fillna(0)
        df_mrp['Consommation_J'] = df_mrp['Consommation_J'].replace(0, 0.1)
        df_mrp['Couverture_J'] = df_mrp['Stock'] / df_mrp['Consommation_J']
        df_mrp['Écart'] = df_mrp['Stock'] - df_mrp['Stock_Sécu']
        df_mrp['Valeur_Risque_EUR'] = df_mrp['Écart'].clip(upper=0).abs() * df_mrp['Prix_EUR']
        df_mrp['Statut'] = pd.cut(df_mrp['Couverture_J'], bins=[-1, 0, 7, 15, 9999], labels=['Rupture', 'Critique', 'Alerte', 'OK'])

        return df_mrp, df_besoin_jour, df_conso, df_prev_pf

    except Exception as e:
        st.error(f"Erreur f chargement: {e}")
        return None, None, None, None

# ==================== 3. CHARGEMENT ====================
df_mrp, df_besoin_jour, df_conso, df_prev_pf = load_full_data()

if df_mrp is None:
    st.stop()

st.sidebar.success("Data Full mn Google Sheet ✅")
st.sidebar.info(f"Colonnes MRP: {len(df_mrp.columns)}")
st.sidebar.info(f"Colonnes Conso: {len(df_conso.columns)}")

if st.sidebar.button("🔄 Rafraîchir Data"):
    st.cache_data.clear()
    st.rerun()

# ==================== 4. INTERFACE V4.10 ====================
tab1, tab2, tab3, tab4 = st.tabs(["📊 MRP Complet", "⚠️ Alertes", "🏢 Fournisseurs", "📈 Data Brute"])

with tab1:
    st.header("MRP Complet - Kolchi M7foud")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nb MP", df_mrp['Code_MP'].nunique())
    col2.metric("Valeur Stock", f"€ {(df_mrp['Stock'] * df_mrp['Prix_EUR']).sum():,.0f}")
    col3.metric("Nb Ruptures", df_mrp[df_mrp['Statut'] == 'Rupture'].shape[0])
    col4.metric("Valeur Risque", f"€ {df_mrp['Valeur_Risque_EUR'].sum():,.0f}")

    st.subheader("Tableau MRP + Kolchi les Colonnes")
    st.info("👇 Scroller l'imin w l'iser bach tchouf kolchi - Kolchi mn les 4 sheets m7foud")
    st.dataframe(df_mrp, use_container_width=True, height=600)

with tab2:
    st.header("Alertes & Projection")
    df_alertes = df_mrp[df_mrp['Statut'].isin(['Rupture', 'Critique', 'Alerte'])].sort_values('Couverture_J')
    st.dataframe(df_alertes, use_container_width=True)

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
    st.header("Fournisseurs - Data Complète")
    fourni_select = st.selectbox("Choisir Fournisseur", sorted(df_mrp['Fournisseur'].dropna().unique()))
    if fourni_select:
        df_f = df_mrp[df_mrp['Fournisseur'] == fourni_select]
        st.dataframe(df_f, use_container_width=True) # Kolchi kayban

with tab4:
    st.header("📈 Data Brute - Pour KPIs")
    st.subheader("Conso Sheet Complet")
    st.dataframe(df_conso, use_container_width=True)
    st.subheader("Prévisions PF Complet")
    st.dataframe(df_prev_pf, use_container_width=True)
