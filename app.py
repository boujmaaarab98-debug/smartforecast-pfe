import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="MRP Pro V4.8 - GoogleSheet", page_icon="🚀", layout="wide")

st.title("🚀 MRP Pro Dashboard V4.8 - Live mn Google Sheet")
st.caption("Rolling 12M + Toast Alerts + PDF Export + Gantt + Search Global")

# ==================== 1. CONNEXION GOOGLE SHEET ====================
@st.cache_data(ttl=600) # Cache 10min bach ma y3ytch bzaf l Google
def load_from_gsheet():
    try:
        # Utilise les secrets de Streamlit
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)

        # Bdl smiya dyal Sheet dyalk hna 👇
        SHEET_NAME = "Matière_première_et_PF_consommation_journaliere"
        spreadsheet = client.open(SHEET_NAME)

        # --- A. Chargement des 4 sheets ---
        df_param = pd.DataFrame(spreadsheet.worksheet("Param").get_all_records())
        df_conso_raw = pd.DataFrame(spreadsheet.worksheet("Conso").get_all_values())
        df_fournis = pd.DataFrame(spreadsheet.worksheet("Fournisseurs").get_all_records())
        df_prev_pf = pd.DataFrame(spreadsheet.worksheet("MRP").get_all_records())

        # Traitement spécial l Conso 7it fiha header fusionné
        df_conso_raw.columns = df_conso_raw.iloc[1] # Row 2 hia headers s7i7a
        df_conso = df_conso_raw[2:].reset_index(drop=True) # Data mn row 3

        # --- B. Nettoyage & Renommage ---
        df_param = df_param.rename(columns={'code_mp': 'Code_MP', 'designation': 'Désignation', 'lead_time_j': 'Délai', 'moq_kg': 'MOQ', 'stock_secu_actuel': 'Stock_Sécu'})

        df_conso = df_conso.rename(columns={
            'Ref produit finis': 'Ref_PF', 'CODE matière': 'Code_MP',
            'conso journaliere MP en KG': 'Conso_U_Unitaire', 'Couverture : 2 semaine NBR OCTABIN': 'Couverture_Octab'
        })
        # Convertir les colonnes en numérique
        for col in ['Conso_U_Unitaire', 'Couverture_Octab']:
            df_conso[col] = pd.to_numeric(df_conso[col], errors='coerce')
        df_conso = df_conso.dropna(subset=['Code_MP', 'Ref_PF'])
        df_conso['Stock_Actuel_MP'] = df_conso['Couverture_Octab'] * df_conso['Conso_U_Unitaire']

        df_fournis = df_fournis.rename(columns={'code_mp': 'Code_MP', 'nom_fournisseur': 'Fournisseur', 'prix_unitaire_eur': 'Prix_EUR'})
        df_prev_pf = df_prev_pf.rename(columns={'Ref produit finis': 'Ref_PF'})

        # --- C. Explosion Prévisionnel PF -> Besoin MP ---
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
        for col in ['Prix_EUR', 'taux_service_%', 'fiabilite_%', 'note_qualite_5']: df_fournis[col] = pd.to_numeric(df_fournis[col], errors='coerce')

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
        st.info("Vérifi: 1- Smiya dyal Sheet s7i7a? 2- Partagiti l sheet m3a email dyal service account? 3- Secrets m-configurin?")
        return None, None

# ==================== 2. CHARGEMENT ====================
df_mrp, df_besoin_jour = load_from_gsheet()

if df_mrp is None:
    st.stop()

st.sidebar.success("Data chargée mn Google Sheet ✅")
st.sidebar.button("🔄 Rafraîchir Data", on_click=st.cache_data.clear)

# ==================== 3. INTERFACE V4.8 DYALK KAMLA ====================
# Hna dir ga3 l code dyal Tabs w Graphs dyal V4.8 l 9dima
# L mohim 'df_mrp' w 'df_besoin_jour' fihom data s7i7a daba

tab1, tab2, tab3 = st.tabs(["📊 Vue Globale", "⚠️ Alertes", "🏢 Fourni 360"])

with tab1:
    st.header("Vue Globale MRP - Live Data")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nb MP", df_mrp['Code_MP'].nunique())
    col2.metric("Valeur Stock Total", f"€ {(df_mrp['Stock'] * df_mrp['Prix_EUR']).sum():,.0f}")
    col3.metric("Nb Ruptures", df_mrp[df_mrp['Statut'] == 'Rupture'].shape[0])
    col4.metric("Valeur Risque", f"€ {df_mrp['Valeur_Risque_EUR'].sum():,.0f}")
    st.dataframe(df_mrp, use_container_width=True, height=600)

with tab2:
    st.header("Alertes & Ruptures")
    df_alertes = df_mrp[df_mrp['Statut'].isin(['Rupture', 'Critique', 'Alerte'])]
    st.dataframe(df_alertes, use_container_width=True)

with tab3:
    st.header("Fournisseur 360")
    fourni_select = st.selectbox("Fournisseur", sorted(df_mrp['Fournisseur'].dropna().unique()))
    if fourni_select:
        df_f = df_mrp[df_mrp['Fournisseur'] == fourni_select]
        st.dataframe(df_f)

# Zid hna ga3 les features lakhrin dyal V4.8...
