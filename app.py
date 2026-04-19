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

# ========================================
# CONFIG + CSS PRO
# ========================================
SHEET_ID = "1DNmM76FfZRtucCMEB-If0t1EEV-lPRn70pl9yP2ooeM"
st.set_page_config(page_title="MRP Pro V5.0 Final", layout="wide", page_icon="🚀")

st.markdown("""
<style>
.kpi-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 20px;
    border-radius: 15px;
    color: white;
    box-shadow: 0 4px 6px rgba(0,0,0.1);
    margin-bottom: 10px;
}
.kpi-card-red {background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);}
.kpi-card-green {background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);}
.kpi-card-orange {background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);}
.kpi-value {font-size: 32px; font-weight: bold; margin: 5px 0;}
.kpi-label {font-size: 14px; opacity: 0.9;}
.kpi-trend {font-size: 12px; margin-top: 5px;}
</style>
""", unsafe_allow_html=True)

# ========================================
# FONCTIONS UTILITAIRES - ADAPTÉES
# ========================================
def trouver_colonne(df, noms_possibles):
    for nom in noms_possibles:
        if nom in df.columns:
            return nom
    for nom in noms_possibles:
        for col in df.columns:
            if nom.lower() in col.lower():
                return col
    return None

def clean_numeric_smart(series):
    """Smart: 1,5→1.5 | 1,500→1500 | 1,234,567→1234567"""
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

@st.cache_data(ttl=300)
def charger_donnees_google():
    base_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
    try:
        # 1. PARAM - Stock Réel
        param = pd.read_csv(base_url + "Param")
        param.columns = param.columns.str.strip()
        param = param.rename(columns={
            'code_mp': 'Code_MP',
            'designation': 'Désignation',
            'lead_time_j': 'Lead_Time',
            'moq_kg': 'MOQ',
            'stock_actuel': 'Stock'
        })
        for col in ['Lead_Time', 'MOQ', 'Stock']:
            if col in param.columns:
                param[col] = clean_numeric_smart(param[col])

        # 2. CONSOM - Liaison PF↔MP
        conso = pd.read_csv(base_url + "Conso")
        conso.columns = conso.columns.str.strip()
        conso = conso.rename(columns={
            'Ref produit finis': 'Ref_PF',
            'CODE matière': 'Code_MP',
            'conso journaliere MP en KG': 'Conso_U_Unitaire',
            'Projet': 'Projet'
        })
        conso['Conso_U_Unitaire'] = clean_numeric_smart(conso['Conso_U_Unitaire'])
        conso = conso.dropna(subset=['Code_MP', 'Ref_PF'])

        # 3. MRP - Prévisionnel PF par dates
        mrp = pd.read_csv(base_url + "MRP")
        mrp.columns = mrp.columns.str.strip()
        mrp = mrp.rename(columns={'Ref produit finis': 'Ref_PF'})

        # 4. FOURNISSEURS
        fournis = pd.read_csv(base_url + "Fournisseurs")
        fournis.columns = fournis.columns.str.strip()
        fournis = fournis.rename(columns={
            'code_mp': 'Code_MP',
            'nom_fournisseur': 'Fournisseur',
            'prix_unitaire_eur': 'Prix_EUR',
            'lead_time_j': 'Delai_Fournis',
            'moq_kg': 'MOQ_Fournis',
            'fiabilite_%': 'Fiabilite',
            'taux_service_%': 'Taux_Service',
            'note_qualite_5': 'Note_Qualite',
            'localisation': 'Localisation'
        })
        for col in ['Prix_EUR', 'Delai_Fournis', 'MOQ_Fournis', 'Fiabilite', 'Taux_Service', 'Note_Qualite']:
            if col in fournis.columns:
                fournis[col] = clean_numeric_smart(fournis[col])

        return param, conso, mrp, fournis
    except Exception as e:
        st.error(f"❌ Erreur: {e}")
        return None, None, None, None

def calcul_eoq(demande_annuelle, cout_commande, cout_stockage_unit, cout_unitaire):
    if cout_stockage_unit <= 0 or demande_annuelle <= 0:
        return 0
    return np.sqrt((2 * demande_annuelle * cout_commande) / cout_stockage_unit)

def classification_abc(df):
    df = df.sort_values('Valeur_Risque', ascending=False).reset_index(drop=True)
    df['Cumul'] = df['Valeur_Risque'].cumsum()
    total = df['Valeur_Risque'].sum()
    df['Cumul_%'] = df['Cumul'] / total * 100 if total > 0 else 0
    df['Classe'] = df['Cumul_%'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))
    return df

def generer_pdf_plan_appro(df_ia):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    title = Paragraph(f"<b>Plan d'Approvisionnement IA</b><br/>Date: {datetime.now().strftime('%d/%m/%Y')}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.3*inch))
    data = [['Code MP', 'Désignation', 'Statut', 'Cmd Avant', 'Qté (kg)', 'Fournisseur']]
    for _, row in df_ia.iterrows():
        data.append([row['Code_MP'], row['Désignation'][:20], row['Statut_IA'], row['Date_Cmd_Optimale'].strftime('%d/%m/%Y'), f"{row['Qté_Suggérée_IA']:,.0f}", row['Fournisseur'][:15]])
    table = Table(data, colWidths=[1*inch, 1.5*inch, 1*inch, 1*inch, 1*inch, 1.2*inch])
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 10), ('BOTTOMPADDING', (0, 0), (-1, 0), 12), ('BACKGROUND', (0, 1), (-1, -1), colors.beige), ('GRID', (0, 0), (-1, -1), 1, colors.black)]))
    elements.append(table)
    total_val = (df_ia['Qté_Suggérée_IA'] * df_ia['Prix_EUR']).sum()
    elements.append(Paragraph(f"<br/><b>Valeur Totale: {total_val:,.0f} EUR</b>", styles['Normal']))
    doc.build(elements)
    buffer.seek(0)
    return buffer

def kpi_card_html(label, value, trend, icon, color_class=""):
    return f"""<div class="kpi-card {color_class}"><div class="kpi-label">{icon} {label}</div><div class="kpi-value">{value}</div><div class="kpi-trend">{trend}</div></div>"""

# ========================================
# ANALYSE MRP - ADAPTÉE 100%
# ========================================
def analyser_mrp_appro(param, conso, mrp, fournis):
    # 1. Explosion MRP: PF × Dates → MP
    df_mrp_melt = mrp.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
    df_mrp_melt['Qte_PF_Prévue'] = clean_numeric_smart(df_mrp_melt['Qte_PF_Prévue'])
    df_mrp_melt = df_mrp_melt.dropna(subset=['Qte_PF_Prévue'])
    df_mrp_melt['Date'] = pd.to_datetime(df_mrp_melt['Date'], dayfirst=True, errors='coerce')
    df_mrp_melt = df_mrp_melt.dropna(subset=['Date'])

    # 2. Jointure MRP × Conso → Besoin MP
    df_besoin = pd.merge(df_mrp_melt, conso[['Ref_PF', 'Code_MP', 'Conso_U_Unitaire']], on='Ref_PF', how='inner')
    df_besoin['Besoin_MP_KG'] = df_besoin['Qte_PF_Prévue'] * df_besoin['Conso_U_Unitaire']
    df_besoin_jour = df_besoin.groupby(['Code_MP', 'Date'])['Besoin_MP_KG'].sum().reset_index()

    # 3. Calcul Consommation Journalière Moyenne sur horizon prévisionnel
    conso_total = df_besoin_jour.groupby('Code_MP')['Besoin_MP_KG'].sum().reset_index()
    if not df_besoin_jour.empty:
        nb_jours = (df_besoin_jour['Date'].max() - df_besoin_jour['Date'].min()).days + 1
    else:
        nb_jours = 1
    conso_total['Consommation_J'] = conso_total['Besoin_MP_KG'] / nb_jours

    # 4. Construction MRP Final
    df_result = pd.merge(param, conso_total[['Code_MP', 'Consommation_J']], on='Code_MP', how='left')

    # 5. Meilleur fournisseur par MP
    fournis['Score'] = (fournis['Taux_Service'].fillna(0) * 0.4 + fournis['Fiabilite'].fillna(0) * 0.3 + fournis['Note_Qualite'].fillna(0) * 20 * 0.3)
    best_fournis = fournis.sort_values('Score', ascending=False).drop_duplicates('Code_MP')
    df_result = pd.merge(df_result, best_fournis[['Code_MP', 'Fournisseur', 'Prix_EUR', 'Delai_Fournis', 'Score']], on='Code_MP', how='left')

    # 6. Calculs MRP
    df_result = df_result.fillna(0)
    df_result['Consommation_J'] = df_result['Consommation_J'].replace(0, 0.1)
    df_result['Couverture_J'] = df_result['Stock'] / df_result['Consommation_J']
    df_result['Stock_Sécu'] = df_result['Consommation_J'] * 12
    df_result['Écart'] = df_result['Stock'] - df_result['Stock_Sécu']
    df_result['Valeur_Risque'] = df_result['Écart'].clip(upper=0).abs() * df_result['Prix_EUR']
    df_result['Date_Rupture'] = pd.to_datetime(datetime.now()) + pd.to_timedelta(df_result['Couverture_J'], unit='D')

    # EOQ + Point Commande
    demande_annuelle = df_result['Consommation_J'] * 365
    cout_stockage = df_result['Prix_EUR'] * 0.2
    df_result['EOQ'] = np.sqrt((2 * demande_annuelle * 500) / cout_stockage.clip(lower=0.1))
    df_result['Point_Cmd'] = df_result['Consommation_J'] * df_result['Lead_Time'].fillna(14)

    # Statut IA
    df_result['Date_Cmd_Optimale'] = df_result['Date_Rupture'] - pd.to_timedelta(df_result['Lead_Time'].fillna(14), unit='D')
    df_result['Qté_Suggérée_IA'] = df_result.apply(lambda r: max(abs(r['Écart']), r['EOQ'], r['MOQ']) if r['Écart'] < 0 else max(r['EOQ'], r['MOQ']), axis=1)

    conditions = [
        (df_result['Écart'] < -df_result['MOQ']),
        (df_result['Écart'] < 0),
        (df_result['Couverture_J'] < 4),
    ]
    df_result['Statut_IA'] = np.select(conditions, ['🔴 Urgent', '🟠 À Planifier', '🔴 Critique'], default='🟢 Sécurisé')

    # Statut Classique
    conditions2 = [
        (df_result['Couverture_J'] < 4),
        (df_result['Couverture_J'] < 6),
        (df_result['Couverture_J'] < 12),
    ]
    df_result['Statut'] = np.select(conditions2, ['🔴 CRITIQUE', '🟠 TENSION', '🟡 ALERTE'], default='🟢 ALIGNÉ')

    # Action
    df_result['Action'] = df_result.apply(lambda r: f"Commander {r['Qté_Suggérée_IA']:,.0f} kg" if r['Écart'] < 0 else "Pas d'action", axis=1)

    # Risque %
    df_result['Risque_%'] = np.where(
        df_result['Couverture_J'] <= 0, 100,
        np.maximum(0, np.minimum(100, 100 - (df_result['Couverture_J'] / df_result['Lead_Time'].fillna(14) * 100)))
    )

    df_result = classification_abc(df_result)
    return df_result, df_besoin_jour

# ========================================
# INTERFACE
# ========================================
st.title("🚀 MRP Pro V5.0 - Final Adapté")
st.caption("MRP | KPIs Conso | Fournisseurs - Msataf N9i")

param, conso, mrp, fournis = charger_donnees_google()
if param is None:
    st.stop()

df_result, df_besoin_jour = analyser_mrp_appro(param, conso, mrp, fournis)
if len(df_result) == 0:
    st.warning("Aucun MP dans Param")
    st.stop()

# TOAST
urgents = df_result[df_result['Statut_IA'].str.contains('Urgent')]
if len(urgents) > 0:
    codes = ", ".join(urgents['Code_MP'].head(3).tolist())
    st.toast(f"🔴 URGENT: {codes} - Commander lyoum!", icon='🔥')

# SIDEBAR
st.sidebar.header("⚙️ Configuration")
st.sidebar.info(f"📅 {datetime.now().strftime('%d/%m/%Y')}\n\n🔄 Données Live")
search = st.sidebar.text_input("🔍 Search", placeholder="Code MP, Désignation...")
if search:
    mask = df_result.apply(lambda row: search.lower() in str(row).lower(), axis=1)
    df_result = df_result[mask]
    st.sidebar.success(f"✅ {len(df_result)} résultats")
if st.sidebar.button("🔄 Actualiser", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(["📊 MRP", "📈 KPIs Conso", "🏭 Fournisseurs", "🎯 Simulateur"])

with tab1:
    st.subheader("📊 MRP Dashboard")
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(kpi_card_html("Total MPs", len(df_result), "↑ Actif", "📦", ""), unsafe_allow_html=True)
    c2.markdown(kpi_card_html("Critiques", len(df_result[df_result['Statut'].str.contains('CRITIQUE')]), "⚠️", "🔴", "kpi-card-red"), unsafe_allow_html=True)
    c3.markdown(kpi_card_html("Urgents IA", len(df_result[df_result['Statut_IA'].str.contains('Urgent')]), "🔥", "🤖", "kpi-card-orange"), unsafe_allow_html=True)
    c4.markdown(kpi_card_html("Valeur Risque", f"{df_result['Valeur_Risque'].sum():,.0f}", "EUR", "💰", "kpi-card-green"), unsafe_allow_html=True)

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

    # Stats Conso
    conso_stats = conso.groupby('Code_MP')['Conso_U_Unitaire'].agg(['mean', 'std', 'count']).reset_index()
    conso_stats.columns = ['Code_MP', 'Conso_Moy', 'StdDev', 'Nb_PF']
    conso_stats['CV_%'] = (conso_stats['StdDev'] / conso_stats['Conso_Moy'] * 100).round(1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Conso Moyenne", f"{conso_stats['Conso_Moy'].mean():.1f} KG/PF")
    c2.metric("MP Volatiles CV>50%", conso_stats[conso_stats['CV_%'] > 50].shape[0])
    c3.metric("Total PF", conso_stats['Nb_PF'].sum())

    # Pareto
    st.subheader("Pareto 80/20")
    pareto = conso_stats.sort_values('Conso_Moy', ascending=False).head(10)
    pareto['Cumul_%'] = (pareto['Conso_Moy'].cumsum() / conso_stats['Conso_Moy'].sum() * 100).round(1)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=pareto['Code_MP'], y=pareto['Conso_Moy'], name='Conso Moy'))
    fig.add_trace(go.Scatter(x=pareto['Code_MP'], y=pareto['Cumul_%'], name='Cumul %', yaxis='y2'))
    fig.update_layout(yaxis2=dict(overlaying='y', side='right'))
    st.plotly_chart(fig, use_container_width=True)

    # Saisonnalité
    st.subheader("Saisonnalité Besoin MP")
    if not df_besoin_jour.empty:
        df_besoin_jour['Mois'] = df_besoin_jour['Date'].dt.month_name()
        saison = df_besoin_jour.groupby(['Code_MP', 'Mois'])['Besoin_MP_KG'].sum().reset_index()
        saison_pivot = saison.pivot(index='Code_MP', columns='Mois', values='Besoin_MP_KG').fillna(0)
        if not saison_pivot.empty:
            st.plotly_chart(px.imshow(saison_pivot, aspect='auto', color_continuous_scale='YlOrRd'), use_container_width=True)

    # Forecast
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
    st.subheader("🏭 Analyse Fournisseurs")
    fournis['Score'] = (fournis['Taux_Service'].fillna(0) * 0.4 + fournis['Fiabilite'].fillna(0) * 0.3 + fournis['Note_Qualite'].fillna(0) * 20 * 0.3).round(1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Nb Fournisseurs", fournis['Fournisseur'].nunique())
    c2.metric("Prix Moyen", f"€ {fournis['Prix_EUR'].mean():.2f}")
    c3.metric("Score Moyen", f"{fournis['Score'].mean():.1f}/100")

    df_score = fournis.groupby('Fournisseur').agg({
        'Score': 'mean',
        'Prix_EUR': 'mean',
        'Delai_Fournis': 'mean',
        'Code_MP': 'count'
    }).round(1).reset_index().rename(columns={'Code_MP': 'Nb_MP'})

    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(df_score.sort_values('Score', ascending=False), x='Fournisseur', y='Score', color='Score', color_continuous_scale='RdYlGn', text='Nb_MP', title="Score Fournisseurs"), use_container_width=True)
    c2.plotly_chart(px.scatter(df_score, x='Prix_EUR', y='Score', size='Nb_MP', hover_name='Fournisseur', title="Prix vs Score"), use_container_width=True)

    st.dataframe(fournis, use_container_width=True, height=400)

with tab4:
    st.subheader("🎯 Simulateur What-If")
    c1, c2 = st.columns(2)
    mp_sim = c1.selectbox("MP à simuler", df_result['Code_MP'].unique())
    qte_sim = c2.number_input("Quantité à commander (kg)", min_value=0, value=10000, step=1000)

    mp_data = df_result[df_result['Code_MP'] == mp_sim].iloc[0]
    nouveau_stock = mp_data['Stock'] + qte_sim
    nouveau_ecart = nouveau_stock - (mp_data['Besoin_MRP'] + mp_data['Consommation_J'] * 30)
    nouvelle_couv = nouveau_stock / mp_data['Consommation_J']

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nouveau Stock", f"{nouveau_stock:,.0f} kg", f"+{qte_sim:,.0f}")
    c2.metric("Nouvel Écart", f"{nouveau_ecart:,.0f} kg", f"{nouveau_ecart - mp_data['Écart']:,.0f}")
    c3.metric("Nouvelle Couv.", f"{nouvelle_couv:.0f} jours", f"{nouvelle_couv - mp_data['Couverture_J']:.0f}")
    c4.metric("Coût Cmd", f"{qte_sim * mp_data['Prix_EUR']:,.0f} EUR")

    if nouveau_ecart >= 0:
        st.success(f"✅ **VERDICT: ALIGNÉ** → {mp_sim} ywlli VERT!")
    elif nouveau_ecart >= -mp_data['EOQ']:
        st.warning(f"🟠 **VERDICT: TENSION** → {mp_sim} ba9i ORANGE. Khass {abs(nouveau_ecart):,.0f} kg zayda.")
    else:
        st.error(f"🔴 **VERDICT: CRITIQUE** → {mp_sim} ba9i ROUGE. Khass {abs(nouveau_ecart):,.0f} kg zayda.")
