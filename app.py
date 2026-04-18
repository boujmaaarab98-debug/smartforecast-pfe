import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
from io import BytesIO

st.set_page_config(page_title="MRP Pro V4.13 - Full KPIs", page_icon="🚀", layout="wide")

st.title("🚀 MRP Pro Dashboard V4.13 - KPIs Professionnels Complets")
st.caption("Rouge: 4j | Orange: 6j | Stock Min: 12j | Saisonnalité + Forecast + Export")

# ==================== 1. SEUILS PROFESSIONNELS ====================
SEUIL_ROUGE = 4
SEUIL_ORANGE = 6
SEUIL_SECURITE = 12
SEUIL_VOLATILITE = 50 # CV% > 50 = Volatile

st.sidebar.info(f"""
**🔴 Rouge:** < {SEUIL_ROUGE} jours
**🟠 Orange:** < {SEUIL_ORANGE} jours
**🟢 Stock Min:** {SEUIL_SECURITE} jours
**⚠️ Volatilité:** CV > {SEUIL_VOLATILITE}%
""")

# ==================== 2. CONFIG LINKS ====================
URL_PARAM = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=0&single=true&output=csv"
URL_CONSO = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=326309876&single=true&output=csv"
URL_FOURNIS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=1581263595&single=true&output=csv"
URL_MRP = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSNFTes3pBz0_uPvWuOAmHiaSuux6KR72VvUGqN6W6cATE7jJmCdU__MuQHH-ejq1zLygGk5ZCYrrKn/pub?gid=418845709&single=true&output=csv"

# ==================== 3. FONCTIONS UTILES ====================
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

def to_excel(df_dict):
    """Export multiple dataframes l Excel"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in df_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output

# ==================== 4. FONCTION DE CHARGEMENT ====================
@st.cache_data(ttl=600)
def load_full_data():
    try:
        # --- Param ---
        df_param = pd.read_csv(URL_PARAM)
        df_param = df_param.rename(columns={
            'code_mp': 'Code_MP',
            'designation': 'Désignation',
            'lead_time_j': 'Délai_Param',
            'moq_kg': 'MOQ_Param',
            'stock_secu_actuel': 'Stock_Sécu_Sheet'
        })
        for col in ['Délai_Param', 'MOQ_Param', 'Stock_Sécu_Sheet']:
            if col in df_param.columns:
                df_param[col] = clean_numeric(df_param[col])

        # --- Conso ---
        df_conso = pd.read_csv(URL_CONSO)
        df_conso = df_conso.rename(columns={
            'Ref produit finis': 'Ref_PF',
            'CODE matière': 'Code_MP',
            'conso journaliere MP en KG': 'Conso_U_Unitaire',
            'Couverture : 2 semaine NBR OCTABIN': 'Couverture_Octab',
            'Projet': 'Projet' # N7afdo 3lih l correlation
        })
        df_conso['Conso_U_Unitaire'] = clean_numeric(df_conso['Conso_U_Unitaire'])
        df_conso['Couverture_Octab'] = clean_numeric(df_conso['Couverture_Octab'])
        df_conso['Stock_Actuel_MP'] = df_conso['Couverture_Octab'] * df_conso['Conso_U_Unitaire']
        df_conso = df_conso.dropna(subset=['Code_MP', 'Ref_PF'])

        # --- Fournisseurs ---
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

        # --- MRP Prévisionnel ---
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

        # --- Construction DF_MRP Final ---
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
        df_mrp['Stock_Sécu'] = df_mrp['Consommation_J'] * SEUIL_SECURITE
        df_mrp['Écart'] = df_mrp['Stock'] - df_mrp['Stock_Sécu']
        df_mrp['Valeur_Risque_EUR'] = df_mrp['Écart'].clip(upper=0).abs() * df_mrp['Prix_EUR']

        conditions = [
            (df_mrp['Couverture_J'] < SEUIL_ROUGE),
            (df_mrp['Couverture_J'] < SEUIL_ORANGE),
            (df_mrp['Couverture_J'] < SEUIL_SECURITE),
        ]
        choices = ['Rouge', 'Orange', 'Alerte']
        df_mrp['Statut'] = np.select(conditions, choices, default='OK')

        return df_mrp, df_besoin_jour, df_conso, df_prev_pf, df_besoin_mp

    except Exception as e:
        st.error(f"Erreur f chargement: {e}")
        return None, None, None

# ==================== 5. CHARGEMENT ====================
df_mrp, df_besoin_jour, df_conso, df_prev_pf, df_besoin_mp = load_full_data()

if df_mrp is None:
    st.stop()

st.sidebar.success("Data Full mn Google Sheet ✅")

if st.sidebar.button("🔄 Rafraîchir Data"):
    st.cache_data.clear()
    st.rerun()

# ==================== 6. INTERFACE V4.13 ====================
tab1, tab2, tab3, tab4 = st.tabs(["📊 MRP Complet", "📈 KPIs Conso & Prévision PRO", "⚠️ Alertes", "🏢 Fournisseurs"])

with tab1:
    st.header("MRP Complet - Seuils Professionnels")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔴 Rouge <4j", df_mrp[df_mrp['Statut'] == 'Rouge'].shape[0])
    col2.metric("🟠 Orange <6j", df_mrp[df_mrp['Statut'] == 'Orange'].shape[0])
    col3.metric("🟡 Alerte <12j", df_mrp[df_mrp['Statut'] == 'Alerte'].shape[0])
    col4.metric("🟢 OK >12j", df_mrp[df_mrp['Statut'] == 'OK'].shape[0])
    st.dataframe(df_mrp, use_container_width=True, height=600)

with tab2:
    st.header("📈 KPIs Consommation & Prévision - Niveau Professionnel")

    # ===== KPI 1: Consommation Moyenne =====
    st.subheader("1️⃣ Consommation Moyenne + Volatilité")
    conso_moy = df_conso.groupby('Code_MP')['Conso_U_Unitaire'].agg(['mean', 'std', 'count']).reset_index()
    conso_moy.columns = ['Code_MP', 'Conso_Moy_KG', 'Volatilité_StdDev', 'Nb_PF_Utilisateurs']
    conso_moy['CV_%'] = (conso_moy['Volatilité_StdDev'] / conso_moy['Conso_Moy_KG'] * 100).round(1)
    conso_moy = conso_moy.fillna(0)

    # Alerte Volatilité
    volatile = conso_moy[conso_moy['CV_%'] > SEUIL_VOLATILITE]
    if not volatile.empty:
        st.warning(f"⚠️ {len(volatile)} MP 3ndha volatilité > {SEUIL_VOLATILITE}%: {', '.join(volatile['Code_MP'].head(5).tolist())}...")

    col1, col2, col3 = st.columns(3)
    col1.metric("Conso Moyenne", f"{conso_moy['Conso_Moy_KG'].mean():.1f} KG/j")
    col2.metric("MP Volatile", f"{len(volatile)}")
    col3.metric("CV% Moyen", f"{conso_moy['CV_%'].mean():.1f}%")
    st.dataframe(conso_moy.sort_values('Conso_Moy_KG', ascending=False), use_container_width=True, height=250)

    # ===== KPI 2: Top 10 + Pareto 80/20 =====
    st.subheader("2️⃣ Top 10 MP Consommés + Pareto 80/20")
    top10 = conso_moy.sort_values('Conso_Moy_KG', ascending=False).head(10)
    top10['Cumul_%'] = (top10['Conso_Moy_KG'].cumsum() / conso_moy['Conso_Moy_KG'].sum() * 100).round(1)

    fig_pareto = go.Figure()
    fig_pareto.add_trace(go.Bar(x=top10['Code_MP'], y=top10['Conso_Moy_KG'], name='Conso Moyenne', marker_color='steelblue'))
    fig_pareto.add_trace(go.Scatter(x=top10['Code_MP'], y=top10['Cumul_%'], name='Cumul %', yaxis='y2', marker_color='red'))
    fig_pareto.update_layout(yaxis2=dict(overlaying='y', side='right', title='Cumul %'), title="Pareto: 80% dyal consommation jaya mn ache mn MP")
    st.plotly_chart(fig_pareto, use_container_width=True)

    # ===== KPI 3: Saisonnalité Heatmap =====
    st.subheader("3️⃣ Saisonnalité Consommation - Heatmap")
    df_besoin_jour['Mois'] = df_besoin_jour['Date'].dt.month_name()
    saison = df_besoin_jour.groupby(['Code_MP', 'Mois'])['Besoin_MP_KG'].sum().reset_index()
    saison_pivot = saison.pivot(index='Code_MP', columns='Mois', values='Besoin_MP_KG').fillna(0)

    if not saison_pivot.empty:
        fig_heat = px.imshow(saison_pivot, aspect='auto', title="Saisonnalité: Ch7al katstahlk f kol chhr", color_continuous_scale='YlOrRd')
        st.plotly_chart(fig_heat, use_container_width=True)

    # ===== KPI 4: Corrélation PF-MP =====
    st.subheader("4️⃣ Corrélation PF → MP")
    correl = df_conso.groupby(['Ref_PF', 'Code_MP', 'Projet'])['Conso_U_Unitaire'].sum().reset_index()
    correl = correl.sort_values('Conso_U_Unitaire', ascending=False)
    st.dataframe(correl.head(20), use_container_width=True, height=250)

    # ===== KPI 5: Forecast 6 Mois =====
    st.subheader("5️⃣ Forecast Consommation 6 Mois Jiyin")
    conso_mensuelle = df_besoin_jour.copy()
    conso_mensuelle['Mois'] = conso_mensuelle['Date'].dt.to_period('M')
    conso_mensuelle_sum = conso_mensuelle.groupby('Mois')['Besoin_MP_KG'].sum().reset_index()
    conso_mensuelle_sum['Mois'] = conso_mensuelle_sum['Mois'].astype(str)

    # Tendance linéaire simple
    if len(conso_mensuelle_sum) > 2:
        x = np.arange(len(conso_mensuelle_sum))
        y = conso_mensuelle_sum['Besoin_MP_KG'].values
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        forecast_x = np.arange(len(x), len(x) + 6)
        forecast_y = p(forecast_x)

        fig_forecast = go.Figure()
        fig_forecast.add_trace(go.Scatter(x=conso_mensuelle_sum['Mois'], y=y, mode='lines+markers', name='Historique'))
        future_months = pd.date_range(start=conso_mensuelle_sum['Mois'].iloc[-1], periods=7, freq='M')[1:]
        fig_forecast.add_trace(go.Scatter(x=future_months, y=forecast_y, mode='lines+markers', name='Forecast', line=dict(dash='dash')))
        fig_forecast.update_layout(title="Forecast 6 Mois - Tendance Linéaire")
        st.plotly_chart(fig_forecast, use_container_width=True)

    # ===== KPI 6: Stockout Simulé =====
    st.subheader("6️⃣ Date Prévue dyal Rupture Stock")
    df_rupture = df_mrp[df_mrp['Consommation_J'] > 0].copy()
    df_rupture['Jours_Ba9i'] = (df_rupture['Stock'] / df_rupture['Consommation_J']).round(0)
    df_rupture['Date_Rupture_Prévue'] = pd.to_datetime(datetime.now()) + pd.to_timedelta(df_rupture['Jours_Ba9i'], unit='D')
    df_rupture = df_rupture[df_rupture['Jours_Ba9i'] < 60].sort_values('Jours_Ba9i')
    st.dataframe(df_rupture[['Code_MP', 'Désignation', 'Stock', 'Consommation_J', 'Jours_Ba9i', 'Date_Rupture_Prévue', 'Statut']], use_container_width=True, height=250)

    # ===== KPI 7: MOQ Optimal =====
    st.subheader("7️⃣ Suggestion MOQ Optimal")
    besoin_30j = df_besoin_jour[df_besoin_jour['Date'] <= datetime.now() + timedelta(days=30)].groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
    besoin_30j.columns = ['Code_MP', 'Besoin_30j_KG']
    df_moq_opt = pd.merge(df_mrp[['Code_MP', 'MOQ_Param', 'Consommation_J']], besoin_30j, on='Code_MP', how='left').fillna(0)
    df_moq_opt['MOQ_Suggéré'] = (df_moq_opt['Consommation_J'] * 30).round(0) # 1 mois conso
    df_moq_opt['Économie'] = (df_moq_opt['MOQ_Param'] - df_moq_opt['MOQ_Suggéré']).clip(lower=0)
    df_moq_opt = df_moq_opt[df_moq_opt['Économie'] > 0].sort_values('Économie', ascending=False)
    st.dataframe(df_moq_opt[['Code_MP', 'MOQ_Param', 'MOQ_Suggéré', 'Économie']], use_container_width=True, height=250)

    # ===== EXPORT EXCEL =====
    st.subheader("📥 Export Excel Professionnel")
    excel_data = to_excel({
        'KPIs_Conso': conso_moy,
        'Pareto_Top10': top10,
        'Saisonnalité': saison,
        'Correlation_PF_MP': correl,
        'Forecast': conso_mensuelle_sum,
        'Stockout_Prévu': df_rupture,
        'MOQ_Optimal': df_moq_opt
    })
    st.download_button(
        label="⬇️ Télécharger Rapport KPIs Excel",
        data=excel_data,
        file_name=f"KPIs_Conso_Prevision_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

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
