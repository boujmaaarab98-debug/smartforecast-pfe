import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import plotly.express as px
import plotly.graph_objects as go
import plotly.figure_factory as ff
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch

st.set_page_config(page_title="MRP Pro V5.1 - Fix Conso", layout="wide", page_icon="🚀")
st.title("🚀 MRP Pro V5.1 - Conso/J S7i7a")
st.caption("Rouge: 4j | Orange: 6j | Stock Min: 12j | Fix: Poids Pièce")

# ==================== 1. SEUILS ====================
SEUIL_ROUGE, SEUIL_ORANGE, SEUIL_SECURITE = 4, 6, 12
st.sidebar.info(f"🔴 <{SEUIL_ROUGE}j | 🟠 <{SEUIL_ORANGE}j | 🟡 <{SEUIL_SECURITE}j")

# ==================== 2. LIENS ====================
URL_PARAM = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=0&single=true&output=csv"
URL_CONSO = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=326309876&single=true&output=csv"
URL_FOURNIS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=1581263595&single=true&output=csv"
URL_MRP = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=418845709&single=true&output=csv"

# ==================== 3. CLEAN NUMERIC ====================
def clean_numeric_smart(series):
    def convert_one(val):
        if pd.isna(val): return np.nan
        s = str(val).strip().replace(' ', '').replace('€', '').replace('KG', '').replace('kg', '').replace('%', '')
        if '.' in s and ',' in s:
            s = s.replace('.', '').replace(',', '.')
            return pd.to_numeric(s, errors='coerce')
        if ',' in s:
            parts = s.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                s = s.replace(',', '.')
            else:
                s = s.replace(',', '')
            return pd.to_numeric(s, errors='coerce')
        return pd.to_numeric(s, errors='coerce')
    return series.apply(convert_one)

# ==================== 4. LOAD DATA - FIX ====================
@st.cache_data(ttl=300)
def charger_donnees_google():
    base_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
    try:
        # PARAM
        param = pd.read_csv(base_url + "Param")
        param.columns = param.columns.str.strip()
        param = param.rename(columns={'code_mp': 'Code_MP', 'designation': 'Désignation', 'lead_time_j': 'Lead_Time', 'moq_kg': 'MOQ', 'stock_actuel': 'Stock'})
        for col in ['Lead_Time', 'MOQ', 'Stock']:
            if col in param.columns: param[col] = clean_numeric_smart(param[col])

        # CONSOM - FIX: Nakhdo Poids_Piece
        conso = pd.read_csv(base_url + "Conso")
        conso.columns = conso.columns.str.strip()
        conso = conso.rename(columns={'Ref produit finis': 'Ref_PF', 'CODE matière': 'Code_MP', 'Poids pièce': 'Poids_Piece', 'Projet': 'Projet'})
        conso['Poids_Piece'] = clean_numeric_smart(conso['Poids_Piece'])
        conso = conso.dropna(subset=['Code_MP', 'Ref_PF', 'Poids_Piece'])

        # MRP
        mrp = pd.read_csv(base_url + "MRP")
        mrp.columns = mrp.columns.str.strip()
        mrp = mrp.rename(columns={'Ref produit finis': 'Ref_PF'})

        # FOURNISSEURS
        fournis = pd.read_csv(base_url + "Fournisseurs")
        fournis.columns = fournis.columns.str.strip()
        fournis = fournis.rename(columns={'code_mp': 'Code_MP', 'nom_fournisseur': 'Fournisseur', 'prix_unitaire_eur': 'Prix_EUR', 'lead_time_j': 'Delai_Fournis', 'moq_kg': 'MOQ_Fournis', 'fiabilite_%': 'Fiabilite', 'taux_service_%': 'Taux_Service', 'note_qualite_5': 'Note_Qualite'})
        for col in ['Prix_EUR', 'Delai_Fournis', 'MOQ_Fournis', 'Fiabilite', 'Taux_Service', 'Note_Qualite']:
            if col in fournis.columns: fournis[col] = clean_numeric_smart(fournis[col])

        return param, conso, mrp, fournis
    except Exception as e:
        st.error(f"❌ Erreur: {e}")
        return None, None, None, None

def calcul_eoq(demande_annuelle, cout_commande, cout_stockage_unit, cout_unitaire):
    if cout_stockage_unit <= 0 or demande_annuelle <= 0: return 0
    return np.sqrt((2 * demande_annuelle * cout_commande) / cout_stockage_unit)

def classification_abc(df):
    df = df.sort_values('Valeur_Risque', ascending=False).reset_index(drop=True)
    df['Cumul'] = df['Valeur_Risque'].cumsum()
    total = df['Valeur_Risque'].sum()
    df['Cumul_%'] = df['Cumul'] / total * 100 if total > 0 else 0
    df['Classe'] = df['Cumul_%'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))
    return df

# ==================== 5. ANALYSE MRP - FIX CONSO ====================
def analyser_mrp_appro(param, conso, mrp, fournis):
    # Explosion MRP: PF × Dates → MP
    df_mrp_melt = mrp.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
    df_mrp_melt['Qte_PF_Prévue'] = clean_numeric_smart(df_mrp_melt['Qte_PF_Prévue'])
    df_mrp_melt = df_mrp_melt.dropna(subset=['Qte_PF_Prévue'])
    df_mrp_melt['Date'] = pd.to_datetime(df_mrp_melt['Date'], dayfirst=True, errors='coerce')
    df_mrp_melt = df_mrp_melt.dropna(subset=['Date'])

    # FIX: Jointure × Poids_Piece machi Conso_U
    df_besoin = pd.merge(df_mrp_melt, conso[['Ref_PF', 'Code_MP', 'Poids_Piece']], on='Ref_PF', how='inner')
    df_besoin['Besoin_MP_KG'] = df_besoin['Qte_PF_Prévue'] * df_besoin['Poids_Piece']
    df_besoin_jour = df_besoin.groupby(['Code_MP', 'Date'])['Besoin_MP_KG'].sum().reset_index()

    # Consommation_J = Moyenne sur horizon
    conso_total = df_besoin_jour.groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
    nb_jours = (df_besoin_jour['Date'].max() - df_besoin_jour['Date'].min()).days + 1 if not df_besoin_jour.empty else 1
    conso_total['Consommation_J'] = conso_total['Besoin_MP_KG'] / nb_jours

    # MRP Final
    df_result = pd.merge(param, conso_total[['Code_MP', 'Consommation_J']], on='Code_MP', how='left')

    # Meilleur fournisseur
    fournis['Score'] = (fournis['Taux_Service'].fillna(0) * 0.4 + fournis['Fiabilite'].fillna(0) * 0.3 + fournis['Note_Qualite'].fillna(0) * 20 * 0.3)
    best_fournis = fournis.sort_values('Score', ascending=False).drop_duplicates('Code_MP')
    df_result = pd.merge(df_result, best_fournis[['Code_MP', 'Fournisseur', 'Prix_EUR', 'Delai_Fournis', 'Score']], on='Code_MP', how='left')

    # Calculs
    df_result = df_result.fillna(0)
    df_result['Consommation_J'] = df_result['Consommation_J'].replace(0, 0.1)
    df_result['Couverture_J'] = df_result['Stock'] / df_result['Consommation_J']
    df_result['Stock_Sécu'] = df_result['Consommation_J'] * 12
    df_result['Écart'] = df_result['Stock'] - df_result['Stock_Sécu']
    df_result['Valeur_Risque'] = df_result['Écart'].clip(upper=0).abs() * df_result['Prix_EUR']
    df_result['Date_Rupture'] = pd.to_datetime(datetime.now()) + pd.to_timedelta(df_result['Couverture_J'], unit='D')

    demande_annuelle = df_result['Consommation_J'] * 365
    cout_stockage = df_result['Prix_EUR'] * 0.2
    df_result['EOQ'] = np.sqrt((2 * demande_annuelle * 500) / cout_stockage.clip(lower=0.1))
    df_result['Point_Cmd'] = df_result['Consommation_J'] * df_result['Lead_Time'].fillna(14)
    df_result['Date_Cmd_Optimale'] = df_result['Date_Rupture'] - pd.to_timedelta(df_result['Lead_Time'].fillna(14), unit='D')
    df_result['Qté_Suggérée_IA'] = df_result.apply(lambda r: max(abs(r['Écart']), r['EOQ'], r['MOQ']) if r['Écart'] < 0 else max(r['EOQ'], r['MOQ']), axis=1)

    conditions = [(df_result['Écart'] < -df_result['MOQ']), (df_result['Écart'] < 0), (df_result['Couverture_J'] < 4)]
    df_result['Statut_IA'] = np.select(conditions, ['🔴 Urgent', '🟠 À Planifier', '🔴 Critique'], default='🟢 Sécurisé')

    conditions2 = [(df_result['Couverture_J'] < 4), (df_result['Couverture_J'] < 6), (df_result['Couverture_J'] < 12)]
    df_result['Statut'] = np.select(conditions2, ['🔴 CRITIQUE', '🟠 TENSION', '🟡 ALERTE'], default='🟢 ALIGNÉ')
    df_result['Action'] = df_result.apply(lambda r: f"Commander {r['Qté_Suggérée_IA']:,.0f} kg" if r['Écart'] < 0 else "Pas d'action", axis=1)
    df_result['Risque_%'] = np.where(df_result['Couverture_J'] <= 0, 100, np.maximum(0, np.minimum(100, 100 - (df_result['Couverture_J'] / df_result['Lead_Time'].fillna(14) * 100))))

    df_result = classification_abc(df_result)
    return df_result, df_besoin_jour

# ==================== 6. INTERFACE ====================
st.title("🚀 MRP Pro V5.1 - Fix Conso/J")
st.caption("Fix: Poids Pièce × Qté PF = Besoin MP S7i7")

param, conso, mrp, fournis = charger_donnees_google()
if param is None: st.stop()

df_result, df_besoin_jour = analyser_mrp_appro(param, conso, mrp, fournis)
if len(df_result) == 0: st.warning("Aucun MP"); st.stop()

# TOAST
urgents = df_result[df_result['Statut_IA'].str.contains('Urgent')]
if len(urgents) > 0:
    st.toast(f"🔴 URGENT: {', '.join(urgents['Code_MP'].head(3).tolist())}", icon='🔥')

# SIDEBAR
st.sidebar.header("⚙️ Config")
st.sidebar.info(f"📅 {datetime.now().strftime('%d/%m/%Y')}")
search = st.sidebar.text_input("🔍 Search", placeholder="Code MP...")
if search:
    mask = df_result.apply(lambda row: search.lower() in str(row).lower(), axis=1)
    df_result = df_result[mask]
if st.sidebar.button("🔄 Refresh", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

tab1, tab2, tab3 = st.tabs(["📊 MRP", "📈 KPIs Conso", "🏭 Fournisseurs"])

with tab1:
    st.subheader("📊 MRP Dashboard - Conso/J S7i7a")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total MPs", len(df_result))
    c2.metric("Critiques", len(df_result[df_result['Statut'].str.contains('CRITIQUE')]))
    c3.metric("Urgents IA", len(df_result[df_result['Statut_IA'].str.contains('Urgent')]))
    c4.metric("Valeur Risque", f"{df_result['Valeur_Risque'].sum():,.0f} EUR")

    st.divider()
    st.dataframe(df_result[[
        'Code_MP', 'Désignation', 'Classe', 'Stock', 'Consommation_J', 'Couverture_J',
        'Statut_IA', 'Date_Rupture', 'Date_Cmd_Optimale', 'Qté_Suggérée_IA', 'Action'
    ]], use_container_width=True, height=500, column_config={
        "Stock": st.column_config.NumberColumn(format="%.0f kg"),
        "Consommation_J": st.column_config.NumberColumn("Conso/J", format="%.1f kg"),
        "Couverture_J": st.column_config.NumberColumn("Couv. J", format="%.0f j"),
        "Date_Rupture": st.column_config.DateColumn("Rupture", format="DD/MM/YYYY"),
        "Date_Cmd_Optimale": st.column_config.DateColumn("Cmd Avant", format="DD/MM/YYYY"),
        "Qté_Suggérée_IA": st.column_config.NumberColumn("Qté IA", format="%.0f kg"),
    })

with tab2:
    st.subheader("📈 KPIs Consommation")
    conso_stats = conso.groupby('Code_MP')['Poids_Piece'].agg(['mean', 'std', 'count']).reset_index()
    conso_stats.columns = ['Code_MP', 'Poids_Moy', 'StdDev', 'Nb_PF']
    conso_stats['CV_%'] = (conso_stats['StdDev'] / conso_stats['Poids_Moy'] * 100).round(1)

    c1, c2 = st.columns(2)
    c1.metric("Poids Moyen/PF", f"{conso_stats['Poids_Moy'].mean():.2f} KG")
    c2.metric("MP Volatiles", conso_stats[conso_stats['CV_%'] > 50].shape[0])

    st.subheader("Pareto Poids Pièce")
    pareto = conso_stats.sort_values('Poids_Moy', ascending=False).head(10)
    st.plotly_chart(px.bar(pareto, x='Code_MP', y='Poids_Moy', title="Top 10 MP par Poids/PF"), use_container_width=True)

with tab3:
    st.subheader("🏭 Analyse Fournisseurs")
    fournis['Score'] = (fournis['Taux_Service'].fillna(0) * 0.4 + fournis['Fiabilite'].fillna(0) * 0.3 + fournis['Note_Qualite'].fillna(0) * 20 * 0.3).round(1)
    df_score = fournis.groupby('Fournisseur').agg({'Score': 'mean', 'Prix_EUR': 'mean', 'Delai_Fournis': 'mean', 'Code_MP': 'count'}).round(1).reset_index().rename(columns={'Code_MP': 'Nb_MP'})

    st.plotly_chart(px.scatter(df_score, x='Prix_EUR', y='Score', size='Nb_MP', hover_name='Fournisseur', title="Prix vs Score"), use_container_width=True)
    st.dataframe(fournis, use_container_width=True, height=400)
