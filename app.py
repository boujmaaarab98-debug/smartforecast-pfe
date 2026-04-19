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
SHEET_ID = "1DNmM76FfZRtucCMEB-If0t1EEV-lPRn70pl9yP2ooeM" # FIX NameError
st.set_page_config(page_title="MRP Pro Dashboard V5.2", layout="wide", page_icon="🚀")

st.markdown("""
<style>
.kpi-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 20px;
    border-radius: 15px;
    color: white;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
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
# FONCTIONS UTILITAIRES
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
        # PARAM
        param = pd.read_csv(base_url + "Param")
        param.columns = param.columns.str.strip()
        param = param.rename(columns={'code_mp': 'Code_MP', 'designation': 'Désignation', 'lead_time_j': 'Lead_Time', 'moq_kg': 'MOQ', 'stock_actuel': 'Stock'})
        for col in ['Lead_Time', 'MOQ', 'Stock']:
            if col in param.columns: param[col] = clean_numeric_smart(param[col])

        # CONSOM - FIX: Poids_Piece
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

def analyser_mrp_appro(param, conso, mrp, fournis):
    # 1. Explosion MRP: PF × Dates → MP - FIX: Poids_Piece
    df_mrp_melt = mrp.melt(id_vars=['Ref_PF'], var_name='Date', value_name='Qte_PF_Prévue')
    df_mrp_melt['Qte_PF_Prévue'] = clean_numeric_smart(df_mrp_melt['Qte_PF_Prévue'])
    df_mrp_melt = df_mrp_melt.dropna(subset=['Qte_PF_Prévue'])
    df_mrp_melt['Date'] = pd.to_datetime(df_mrp_melt['Date'], dayfirst=True, errors='coerce')
    df_mrp_melt = df_mrp_melt.dropna(subset=['Date'])

    # FIX: Jointure × Poids_Piece machi Conso_U_Unitaire
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

    # Calculs MRP
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

# ========================================
# INTERFACE
# ========================================
st.title("🚀 MRP Pro V5.2 - Kolchi Raj3")
st.caption("Rolling 12M + Toast + PDF + Gantt + Chat IA + Fix Conso/J")

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
    if len(urgents) > 3:
        codes += f" + {len(urgents)-3} autres"
    st.toast(f"🔴 URGENT: {codes} - Commander lyoum!", icon='🔥')

# SIDEBAR
st.sidebar.header("⚙️ Configuration")
st.sidebar.info(f"📅 {datetime.now().strftime('%d/%m/%Y')}")
search = st.sidebar.text_input("🔍 Search Global", placeholder="Code MP, Désignation...")
if search:
    mask = df_result.apply(lambda row: search.lower() in str(row).lower(), axis=1)
    df_result = df_result[mask]
    st.sidebar.success(f"✅ {len(df_result)} résultats")
if st.sidebar.button("🔄 Actualiser", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Dashboard", "🤖 Plan Appro IA", "📅 Prévisions", "🏭 Fournisseurs", "🎯 Simulateur", "💬 Chat IA"])

with tab1:
    st.subheader("📊 KPIs Globaux")
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(kpi_card_html("Total MPs", len(df_result), "↑ Actif", "📦", ""), unsafe_allow_html=True)
    c2.markdown(kpi_card_html("Critiques", len(df_result[df_result['Statut'].str.contains('CRITIQUE')]), "⚠️", "🔴", "kpi-card-red"), unsafe_allow_html=True)
    c3.markdown(kpi_card_html("Urgents IA", len(df_result[df_result['Statut_IA'].str.contains('Urgent')]), "🔥", "🤖", "kpi-card-orange"), unsafe_allow_html=True)
    c4.markdown(kpi_card_html("Valeur Risque", f"{df_result['Valeur_Risque'].sum():,.0f}", "EUR", "💰", "kpi-card-green"), unsafe_allow_html=True)
    st.divider()
    st.dataframe(df_result[[
        'Code_MP', 'Désignation', 'Classe', 'Stock', 'Consommation_J', 'Couverture_J',
        'Statut_IA', 'Date_Cmd_Optimale', 'Action'
    ]], use_container_width=True, height=500, column_config={
        "Stock": st.column_config.NumberColumn(format="%.0f kg"),
        "Consommation_J": st.column_config.NumberColumn("Conso/J", format="%.1f kg"),
        "Couverture_J": st.column_config.NumberColumn("Couv. J", format="%.0f j"),
        "Date_Cmd_Optimale": st.column_config.DateColumn("Cmd Avant", format="DD/MM/YYYY"),
    })

with tab2:
    st.subheader("🤖 Plan d'Approvisionnement IA")
    df_ia = df_result[df_result['Date_Cmd_Optimale'].notna()].copy().sort_values('Date_Cmd_Optimale')
    if st.button("📄 Export PDF", key="pdf"):
        pdf_buffer = generer_pdf_plan_appro(df_ia)
        st.download_button("⬇️ Télécharger", pdf_buffer, f"Plan_Appro_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf")
    if len(df_ia) == 0:
        st.success("✅ Kolchi sécurisé!")
    else:
        st.dataframe(df_ia[['Code_MP', 'Désignation', 'Statut_IA', 'Date_Rupture', 'Date_Cmd_Optimale', 'Qté_Suggérée_IA', 'Fournisseur', 'Risque_%']], use_container_width=True, height=400)
        st.subheader("📊 Gantt Chart - 90 Jours")
        df_gantt = df_ia[df_ia['Date_Cmd_Optimale'] <= datetime.now().date() + timedelta(days=90)].copy()
        if len(df_gantt) > 0:
            gantt_data = []
            for _, row in df_gantt.iterrows():
                start_date = row['Date_Cmd_Optimale']
                end_date = start_date + timedelta(days=row['Lead_Time'])
                gantt_data.append(dict(Task=row['Code_MP'], Start=start_date, Finish=end_date, Resource=row['Statut_IA']))
            fig_gantt = ff.create_gantt(gantt_data, colors={'🔴 Urgent': 'rgb(245, 87, 108)', '🟠 À Planifier': 'rgb(255, 165, 0)', '🟡 Surveiller': 'rgb(78, 205, 196)'}, index_col='Resource', show_colorbar=True, group_tasks=True)
            st.plotly_chart(fig_gantt, use_container_width=True)

with tab3:
    st.subheader("📅 Prévisions 3 Mois")
    df_prev = df_result[['Code_MP', 'Désignation', 'Prév_M+1', 'Prév_M+2', 'Prév_M+3']].copy()
    mois1 = (datetime.now() + relativedelta(months=1)).strftime('%b %Y')
    mois2 = (datetime.now() + relativedelta(months=2)).strftime('%b %Y')
    mois3 = (datetime.now() + relativedelta(months=3)).strftime('%b %Y')
    df_prev = df_prev.rename(columns={'Prév_M+1': f'Prév {mois1}', 'Prév_M+2': f'Prév {mois2}', 'Prév_M+3': f'Prév {mois3}'})
    st.dataframe(df_prev, use_container_width=True, height=400)

with tab4:
    st.subheader("🏭 Analyse Fournisseurs")
    fournis['Score'] = (fournis['Taux_Service'].fillna(0) * 0.4 + fournis['Fiabilite'].fillna(0) * 0.3 + fournis['Note_Qualite'].fillna(0) * 20 * 0.3).round(1)
    df_score = fournis.groupby('Fournisseur').agg({'Score': 'mean', 'Prix_EUR': 'mean', 'Delai_Fournis': 'mean', 'Code_MP': 'count'}).round(1).reset_index().rename(columns={'Code_MP': 'Nb_MP'})
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(df_score.sort_values('Score', ascending=False), x='Fournisseur', y='Score', color='Score', color_continuous_scale='RdYlGn', text='Nb_MP'), use_container_width=True)
    c2.plotly_chart(px.scatter(df_score, x='Prix_EUR', y='Score', size='Nb_MP', hover_name='Fournisseur'), use_container_width=True)
    st.dataframe(fournis, use_container_width=True)

with tab5:
    st.subheader("🎯 Simulateur What-If")
    c1, c2 = st.columns(2)
    mp_sim = c1.selectbox("MP à simuler", df_result['Code_MP'].unique(), key="sim_mp")
    qte_sim = c2.number_input("Quantité à commander (kg)", min_value=0, value=10000, step=1000, key="sim_qte")
    mp_data = df_result[df_result['Code_MP'] == mp_sim].iloc[0].copy()
    nouveau_stock = mp_data['Stock'] + qte_sim
    nouveau_ecart = nouveau_stock - (mp_data['Besoin_MRP'] + mp_data['Conso_30j'])
    nouvelle_couv = nouveau_stock / mp_data['Conso_Moy_J']
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nouveau Stock", f"{nouveau_stock:,.0f} kg", f"+{qte_sim:,.0f}")
    c2.metric("Nouvel Écart", f"{nouveau_ecart:,.0f} kg")
    c3.metric("Nouvelle Couv.", f"{nouvelle_couv:.0f} jours")
    c4.metric("Coût Cmd", f"{qte_sim * mp_data['Prix_EUR']:,.0f} EUR")
    if nouveau_ecart >= 0:
        st.success(f"✅ **ALIGNÉ** → {mp_sim} ywlli VERT!")
    elif nouveau_ecart >= -mp_data['EOQ']:
        st.warning(f"🟠 **TENSION** → {mp_sim} ba9i ORANGE.")
    else:
        st.error(f"🔴 **CRITIQUE** → {mp_sim} ba9i ROUGE.")

with tab6:
    st.subheader("💬 Chat IA Pro")
    st.caption("Swwl 3la: plan, prevision, risque, abc, fournisseur")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if prompt := st.chat_input("Swwl hna..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        p = prompt.lower()
        if "plan" in p or "commande" in p:
            df_c = df_result[df_result['Date_Cmd_Optimale'].notna()].sort_values('Date_Cmd_Optimale')
            if len(df_c) > 0:
                lines = [f"📅 **Plan Commande IA - {len(df_c)} MPs:**\n"]
                for _, row in df_c.head(10).iterrows():
                    d = row['Date_Cmd_Optimale'].strftime('%d/%m')
                    lines.append(f"**{d}**: {row['Code_MP']} - {row['Qté_Suggérée_IA']:,.0f} kg - {row['Statut_IA']}")
                lines.append(f"\n💰 **Total:** {(df_c['Qté_Suggérée_IA'] * df_c['Prix_EUR']).sum():,.0f} EUR")
                r = "\n".join(lines)
            else:
                r = "✅ **Kolchi sécurisé!** Ma kayn 7ta commande."
        elif "prevision" in p or "prev" in p:
            lines = ["📊 **Prévisions 3 Mois:**\n"]
            for _, row in df_result.iterrows():
                lines.append(f"**{row['Code_MP']}**: {row['Prév_M+1']:,.0f} / {row['Prév_M+2']:,.0f} / {row['Prév_M+3']:,.0f} kg")
            r = "\n".join(lines)
        elif "risque" in p:
            crit = df_result[df_result['Risque_%'] > 50]
            if len(crit) > 0:
                lines = [f"⚠️ **{len(crit)} MPs à Risque > 50%:**\n"]
                for _, row in crit.head(10).iterrows():
                    lines.append(f"**{row['Code_MP']}**: {row['Risque_%']:.0f}% - {row['Statut_IA']}")
                r = "\n".join(lines)
            else:
                r = "✅ Aucun MP à risque élevé."
        elif "abc" in p:
            abc_counts = df_result['Classe'].value_counts()
            r = f"📊 **Classification ABC:**\n\n**A**: {abc_counts.get('A', 0)} MPs\n**B**: {abc_counts.get('B', 0)} MPs\n**C**: {abc_counts.get('C', 0)} MPs"
        elif "fournisseur" in p:
            df_f = df_result[df_result['Fournisseur']!= 'N/A'].groupby('Fournisseur').agg({'Score_Fourni': 'mean', 'Code_MP': 'count'}).reset_index().sort_values('Score_Fourni', ascending=False)
            lines = ["🏭 **Top Fournisseurs:**\n"]
            for _, row in df_f.head(5).iterrows():
                lines.append(f"**{row['Fournisseur']}**: Score {row['Score_Fourni']:.1f} - {row['Code_MP']} MPs")
            r = "\n".join(lines)
        else:
            r = "Swwl 3la: `plan`, `prevision`, `risque`, `abc`, `fournisseur`"
        st.session_state.messages.append({"role": "assistant", "content": r})
        with st.chat_message("assistant"):
            st.markdown(r)
