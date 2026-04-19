import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
from io import BytesIO
import zipfile

st.set_page_config(page_title="MRP Pro V5.0 - Final", page_icon="🚀", layout="wide")
st.title("🚀 MRP Dashboard V5.0 - Msataf N9i")
st.caption("MRP | KPIs Conso | Fournisseurs - Kolchi bo7do")

# ==================== 1. SEUILS ====================
SEUIL_ROUGE, SEUIL_ORANGE, SEUIL_SECURITE = 4, 6, 12

st.sidebar.info(f"🔴 <{SEUIL_ROUGE}j | 🟠 <{SEUIL_ORANGE}j | 🟡 <{SEUIL_SECURITE}j")

# ==================== 2. LIENS ====================
URL_PARAM = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=0&single=true&output=csv"
URL_CONSO = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=326309876&single=true&output=csv"
URL_FOURNIS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=1581263595&single=true&output=csv"
URL_MRP = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=418845709&single=true&output=csv"

# ==================== 3. CLEAN NUMERIC SMART ====================
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

# ==================== 4. LOAD DATA ====================
@st.cache_data(ttl=600)
def load_data():
    # PARAM - Source dyal Stock
    df_param = pd.read_csv(URL_PARAM)
    df_param = df_param.rename(columns={
        'code_mp': 'Code_MP',
        'designation': 'Désignation',
        'lead_time_j': 'Délai_Param',
        'moq_kg': 'MOQ_Param',
        'stock_actuel': 'Stock'
    })
    for col in ['Délai_Param', 'MOQ_Param', 'Stock']:
        if col in df_param.columns:
            df_param[col] = clean_numeric_smart(df_param[col])

    # CONSOM - Liaison PF ↔ MP
    df_conso = pd.read_csv(URL_CONSO)
    df_conso = df_conso.rename(columns={
        'Ref produit finis': 'Ref_PF',
        'CODE matière': 'Code_MP',
        'conso journaliere MP en KG': 'Conso_U_Unitaire',
        'Projet': 'Projet',
        'Couverture : 2 semaine NBR OCTABIN': 'Couv_2sem_Octab'
    })
    df_conso['Conso_U_Unitaire'] = clean_numeric_smart(df_conso['Conso_U_Unitaire'])
    df_conso = df_conso.dropna(subset=['Code_MP', 'Ref_PF'])

    # FOURNISSEUR
    df_fournis = pd.read_csv(URL_FOURNIS)
    df_fournis = df_fournis.rename(columns={
        'code_mp': 'Code_MP',
        'nom_fournisseur': 'Fournisseur',
        'prix_unitaire_eur': 'Prix_EUR',
        'lead_time_j': 'Délai_Fournis',
        'moq_kg': 'MOQ_Fournis',
        'fiabilite_%': 'Fiabilite',
        'taux_service_%': 'Taux_Service',
        'note_qualite_5': 'Note_Qualite',
        'localisation': 'Localisation'
    })
    for col in ['Prix_EUR', 'Délai_Fournis', 'MOQ_Fournis', 'Fiabilite', 'Taux_Service', 'Note_Qualite']:
        if col in df_fournis.columns:
            df_fournis[col] = clean_numeric_smart(df_fournis[col])

    # MRP - Prévisionnel PF
    df_mrp = pd.read_csv(URL_MRP)
    df_mrp = df_mrp.rename(columns={'Ref produit finis': 'Ref_PF'})

    # Explosion: PF × Date → MP
    df_mrp_melt = df_mrp.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
    df_mrp_melt['Qte_PF_Prévue'] = clean_numeric_smart(df_mrp_melt['Qte_PF_Prévue'])
    df_mrp_melt = df_mrp_melt.dropna(subset=['Qte_PF_Prévue'])
    df_mrp_melt['Date'] = pd.to_datetime(df_mrp_melt['Date'], dayfirst=True, errors='coerce')
    df_mrp_melt = df_mrp_melt.dropna(subset=['Date'])

    # Jointure: Prévisionnel PF × Conso_U → Besoin MP
    df_besoin = pd.merge(df_mrp_melt, df_conso[['Ref_PF', 'Code_MP', 'Conso_U_Unitaire']], on='Ref_PF', how='inner')
    df_besoin['Besoin_MP_KG'] = df_besoin['Qte_PF_Prévue'] * df_besoin['Conso_U_Unitaire']
    df_besoin_jour = df_besoin.groupby(['Code_MP', 'Date'])['Besoin_MP_KG'].sum().reset_index()

    return df_param, df_conso, df_fournis, df_besoin_jour, df_besoin

df_param, df_conso, df_fournis, df_besoin_jour, df_besoin = load_data()

if df_param is None:
    st.stop()

st.sidebar.success("Data Loaded ✅")
if st.sidebar.button("🔄 Refresh"): st.cache_data.clear(); st.rerun()

# ==================== 5. CALCUL MRP ====================
# Consommation_J = Moyenne sur horizon prévisionnel
conso_total = df_besoin_jour.groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
nb_jours = (df_besoin_jour['Date'].max() - df_besoin_jour['Date'].min()).days + 1 if not df_besoin_jour.empty else 1
conso_total['Consommation_J'] = conso_total['Besoin_MP_KG'] / nb_jours

df_mrp_final = pd.merge(df_param, conso_total[['Code_MP', 'Consommation_J']], on='Code_MP', how='left')
df_mrp_final = pd.merge(df_mrp_final, df_fournis[['Code_MP', 'Fournisseur', 'Prix_EUR', 'Fiabilite']].drop_duplicates('Code_MP'), on='Code_MP', how='left')

df_mrp_final = df_mrp_final.fillna(0)
df_mrp_final['Consommation_J'] = df_mrp_final['Consommation_J'].replace(0, 0.1)
df_mrp_final['Couverture_J'] = df_mrp_final['Stock'] / df_mrp_final['Consommation_J']
df_mrp_final['Stock_Sécu'] = df_mrp_final['Consommation_J'] * SEUIL_SECURITE
df_mrp_final['Écart'] = df_mrp_final['Stock'] - df_mrp_final['Stock_Sécu']
df_mrp_final['Valeur_Risque_EUR'] = df_mrp_final['Écart'].clip(upper=0).abs() * df_mrp_final['Prix_EUR']
df_mrp_final['Date_Rupture'] = pd.to_datetime(datetime.now()) + pd.to_timedelta(df_mrp_final['Couverture_J'], unit='D')
df_mrp_final['Besoin_Commande'] = (df_mrp_final['Stock_Sécu'] - df_mrp_final['Stock']).clip(lower=0)

conditions = [
    (df_mrp_final['Couverture_J'] < SEUIL_ROUGE),
    (df_mrp_final['Couverture_J'] < SEUIL_ORANGE),
    (df_mrp_final['Couverture_J'] < SEUIL_SECURITE),
]
df_mrp_final['Statut'] = np.select(conditions, ['Rouge', 'Orange', 'Alerte'], default='OK')

# ==================== 6. INTERFACE ====================
tab1, tab2, tab3 = st.tabs(["📊 MRP", "📈 KPIs Conso", "🏢 Fournisseurs"])

with tab1:
    st.header("📊 MRP - Stock w Couverture")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Rouge", df_mrp_final[df_mrp_final['Statut'] == 'Rouge'].shape[0])
    c2.metric("🟠 Orange", df_mrp_final[df_mrp_final['Statut'] == 'Orange'].shape[0])
    c3.metric("🟡 Alerte", df_mrp_final[df_mrp_final['Statut'] == 'Alerte'].shape[0])
    c4.metric("🟢 OK", df_mrp_final[df_mrp_final['Statut'] == 'OK'].shape[0])

    st.dataframe(df_mrp_final[[
        'Code_MP', 'Désignation', 'Stock', 'Consommation_J', 'Couverture_J',
        'Statut', 'Date_Rupture', 'Besoin_Commande', 'Valeur_Risque_EUR', 'Fournisseur'
    ]].style.format({
        'Stock': '{:,.0f}', 'Consommation_J': '{:,.1f}', 'Couverture_J': '{:.1f}',
        'Besoin_Commande': '{:,.0f}', 'Valeur_Risque_EUR': '€ {:,.0f}'
    }), use_container_width=True, height=600)

with tab2:
    st.header("📈 KPIs Consommation")

    # KPI1: Conso Moyenne + Volatilité
    conso_stats = df_conso.groupby('Code_MP')['Conso_U_Unitaire'].agg(['mean', 'std']).reset_index()
    conso_stats.columns = ['Code_MP', 'Conso_Moy', 'StdDev']
    conso_stats['CV_%'] = (conso_stats['StdDev'] / conso_stats['Conso_Moy'] * 100).round(1)

    c1, c2 = st.columns(2)
    c1.metric("Conso Moyenne Globale", f"{conso_stats['Conso_Moy'].mean():.1f} KG/PF")
    c2.metric("MP Volatiles CV>50%", conso_stats[conso_stats['CV_%'] > 50].shape[0])

    # KPI2: Pareto
    st.subheader("Pareto 80/20 - Top Consommateurs")
    pareto = conso_stats.sort_values('Conso_Moy', ascending=False).head(10)
    pareto['Cumul_%'] = (pareto['Conso_Moy'].cumsum() / conso_stats['Conso_Moy'].sum() * 100).round(1)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=pareto['Code_MP'], y=pareto['Conso_Moy'], name='Conso Moy'))
    fig.add_trace(go.Scatter(x=pareto['Code_MP'], y=pareto['Cumul_%'], name='Cumul %', yaxis='y2'))
    fig.update_layout(yaxis2=dict(overlaying='y', side='right'))
    st.plotly_chart(fig, use_container_width=True)

    # KPI3: Saisonnalité
    st.subheader("Saisonnalité Besoin MP")
    df_besoin_jour['Mois'] = df_besoin_jour['Date'].dt.month_name()
    saison = df_besoin_jour.groupby(['Code_MP', 'Mois'])['Besoin_MP_KG'].sum().reset_index()
    saison_pivot = saison.pivot(index='Code_MP', columns='Mois', values='Besoin_MP_KG').fillna(0)
    if not saison_pivot.empty:
        st.plotly_chart(px.imshow(saison_pivot, aspect='auto', color_continuous_scale='YlOrRd'), use_container_width=True)

    # KPI4: Forecast
    st.subheader("Forecast 6 Mois")
    conso_mensuelle = df_besoin_jour.copy()
    conso_mensuelle['Mois'] = conso_mensuelle['Date'].dt.to_period('M')
    conso_sum = conso_mensuelle.groupby('Mois')['Besoin_MP_KG'].sum().reset_index()
    if len(conso_sum) > 2:
        x = np.arange(len(conso_sum))
        y = conso_sum['Besoin_MP_KG'].values
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        future_x = np.arange(len(x), len(x) + 6)
        future_y = p(future_x)
        fig_f = go.Figure()
        fig_f.add_trace(go.Scatter(x=conso_sum['Mois'].dt.to_timestamp(), y=y, mode='lines+markers', name='Histo'))
        last_date = conso_sum['Mois'].iloc[-1].to_timestamp()
        future_dates = pd.date_range(start=last_date, periods=7, freq='ME')[1:]
        fig_f.add_trace(go.Scatter(x=future_dates, y=future_y, mode='lines+markers', name='Forecast', line=dict(dash='dash')))
        st.plotly_chart(fig_f, use_container_width=True)

with tab3:
    st.header("🏢 Analyse Fournisseurs")

    # Score Fournisseur
    df_fournis['Score'] = (
        df_fournis['Fiabilite'].fillna(0) * 0.4 +
        df_fournis['Taux_Service'].fillna(0) * 0.3 +
        df_fournis['Note_Qualite'].fillna(0) * 20 * 0.3
    ).round(1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Nb Fournisseurs", df_fournis['Fournisseur'].nunique())
    c2.metric("Prix Moyen", f"€ {df_fournis['Prix_EUR'].mean():.2f}")
    c3.metric("Score Moyen", f"{df_fournis['Score'].mean():.1f}/100")

    st.subheader("Top/Bottom Fournisseurs")
    df_score = df_fournis.groupby('Fournisseur').agg({
        'Score': 'mean',
        'Prix_EUR': 'mean',
        'Délai_Fournis': 'mean',
        'Code_MP': 'count'
    }).round(1).reset_index().rename(columns={'Code_MP': 'Nb_MP'})

    c1, c2 = st.columns(2)
    c1.dataframe(df_score.sort_values('Score', ascending=False).head(), use_container_width=True)
    c2.dataframe(df_score.sort_values('Score', ascending=True).head(), use_container_width=True)

    st.subheader("Risque: MOQ vs Besoin")
    df_risk = pd.merge(df_mrp_final[['Code_MP', 'Consommation_J']], df_fournis[['Code_MP', 'MOQ_Fournis', 'Fournisseur']], on='Code_MP')
    df_risk['Besoin_30j'] = df_risk['Consommation_J'] * 30
    df_risk['Risque_Surstock'] = (df_risk['MOQ_Fournis'] - df_risk['Besoin_30j']).clip(lower=0)
    st.dataframe(df_risk[df_risk['Risque_Surstock'] > 0].sort_values('Risque_Surstock', ascending=False), use_container_width=True)
