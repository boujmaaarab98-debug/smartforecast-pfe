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
st.set_page_config(page_title="MRP Pro Dashboard V4.8", layout="wide", page_icon="🚀")

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

def to_numeric_safe(series):
    return pd.to_numeric(series, errors='coerce').fillna(0)

@st.cache_data(ttl=300)
def charger_donnees_google():
    base_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
    try:
        param = pd.read_csv(base_url + "Param")
        conso = pd.read_csv(base_url + "Conso")
        mrp = pd.read_csv(base_url + "MRP")
        fournis = pd.read_csv(base_url + "Fournisseurs")
        for df in [param, conso, mrp, fournis]:
            df.columns = df.columns.str.strip()
            for col in df.columns:
                if any(x in col.lower() for x in ['qte', 'stock', 'cout', 'moq', 'lead', 'taux', 'fiabilite', 'note']):
                    df[col] = to_numeric_safe(df[col])
        conso['date'] = pd.to_datetime(conso[trouver_colonne(conso, ['date'])], errors='coerce')
        mrp['date_besoin'] = pd.to_datetime(mrp[trouver_colonne(mrp, ['date_besoin'])], errors='coerce')
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
    total_val = (df_ia['Qté_Suggérée_IA'] * df_ia['Cout_Unit']).sum()
    elements.append(Paragraph(f"<br/><b>Valeur Totale: {total_val:,.0f} MAD</b>", styles['Normal']))
    doc.build(elements)
    buffer.seek(0)
    return buffer

def kpi_card_html(label, value, trend, icon, color_class=""):
    return f"""<div class="kpi-card {color_class}"><div class="kpi-label">{icon} {label}</div><div class="kpi-value">{value}</div><div class="kpi-trend">{trend}</div></div>"""

def analyser_mrp_appro(param, conso, mrp, fournis):
    col_mp_param = trouver_colonne(param, ['code_mp'])
    col_mp_conso = trouver_colonne(conso, ['code_mp'])
    col_qte_conso = trouver_colonne(conso, ['qte_consommee_kg', 'qte_consommee'])
    col_mp_mrp = trouver_colonne(mrp, ['code_mp'])
    col_qte_mrp = trouver_colonne(mrp, ['qte_besoin_kg', 'qte_besoin'])
    col_mp_fournis = trouver_colonne(fournis, ['code_mp'])
    resultats = []
    forecasts_dict = {}
    date_actuelle = datetime.now().date()
    date_12_mois = date_actuelle - relativedelta(months=12)
    for _, mp_row in param.iterrows():
        code = mp_row[col_mp_param]
        stock_secu = mp_row.get('stock_secu_actuel', 0)
        lead_time = mp_row.get('lead_time_j', 14)
        moq = mp_row.get('moq_kg', 1000)
        cout_unit = mp_row.get('cout_unitaire', 0)
        designation = mp_row.get('designation', 'N/A')
        cout_commande = mp_row.get('cout_commande', 500)
        taux_stockage = mp_row.get('taux_stockage', 0.2)
        hist_total = conso[conso[col_mp_conso] == code].copy()
        hist_total = hist_total.dropna(subset=['date', col_qte_conso])
        hist_12m = hist_total[hist_total['date'].dt.date >= date_12_mois].copy()
        hist = hist_12m if len(hist_12m) >= 10 else hist_total
        conso_prevue_30j = 0
        conso_moy_j = 0
        demande_annuelle = 0
        has_forecast = False
        date_rupture = None
        risque_pct = 0
        prevision_m1 = 0
        prevision_m2 = 0
        prevision_m3 = 0
        if len(hist) >= 3:
            df_prophet = hist.groupby('date')[col_qte_conso].sum().reset_index()
            df_prophet.columns = ['ds', 'y']
            df_prophet = df_prophet.dropna()
            if len(df_prophet) >= 3:
                try:
                    m = Prophet(yearly_seasonality=len(df_prophet)>60, weekly_seasonality=True, daily_seasonality=False)
                    m.fit(df_prophet)
                    future = m.make_future_dataframe(periods=90)
                    forecast = m.predict(future)
                    fc_future = forecast[forecast['ds'].dt.date > date_actuelle].copy()
                    if len(fc_future) >= 30:
                        prevision_m1 = max(0, fc_future.head(30)['yhat'].sum())
                        prevision_m2 = max(0, fc_future.iloc[30:60]['yhat'].sum()) if len(fc_future) >= 60 else 0
                        prevision_m3 = max(0, fc_future.iloc[60:90]['yhat'].sum()) if len(fc_future) >= 90 else 0
                        conso_prevue_30j = prevision_m1
                    else:
                        conso_prevue_30j = max(0, fc_future['yhat'].sum())
                        prevision_m1 = conso_prevue_30j
                        prevision_m2 = conso_prevue_30j
                        prevision_m3 = conso_prevue_30j
                    conso_moy_j = df_prophet['y'].mean()
                    demande_annuelle = conso_moy_j * 365
                    forecasts_dict[code] = forecast
                    has_forecast = True
                    if stock_secu <= 0:
                        date_rupture = date_actuelle
                        risque_pct = 100
                    else:
                        stock_simule = stock_secu
                        for idx, row in forecast.iterrows():
                            if row['ds'].date() <= date_actuelle:
                                continue
                            stock_simule -= max(0, row['yhat'])
                            if stock_simule <= 0:
                                date_rupture = row['ds'].date()
                                jours_restants = (date_rupture - date_actuelle).days
                                risque_pct = max(0, min(100, 100 - (jours_restants / lead_time * 100)))
                                break
                except:
                    conso_moy_j = df_prophet['y'].mean() if len(df_prophet) > 0 else 0
                    conso_prevue_30j = conso_moy_j * 30
                    prevision_m1 = conso_prevue_30j
                    prevision_m2 = conso_prevue_30j
                    prevision_m3 = conso_prevue_30j
                    demande_annuelle = conso_moy_j * 365
        if conso_moy_j == 0:
            conso_moy_j = 0.1
        besoin_mrp = mrp[mrp[col_mp_mrp] == code][col_qte_mrp].sum()
        besoin_mrp = 0 if pd.isna(besoin_mrp) else besoin_mrp
        couverture_j = stock_secu / conso_moy_j if conso_moy_j > 0 else 999
        besoin_total = besoin_mrp + conso_prevue_30j
        ecart = stock_secu - besoin_total
        valeur_risque = abs(ecart) * cout_unit if ecart < 0 else 0
        cout_stockage_unit = cout_unit * taux_stockage
        eoq = calcul_eoq(demande_annuelle, cout_commande, cout_stockage_unit, cout_unit)
        point_commande = conso_moy_j * lead_time
        date_cmd_optimale = None
        qte_suggeree_ia = 0
        statut_ia = "✅ Sécurisé"
        if ecart < 0:
            qte_suggeree_ia = max(abs(ecart), eoq, moq)
            statut_ia = "🔴 Urgent"
            risque_pct = 100
            date_rupture = date_actuelle
            date_cmd_optimale = date_actuelle
        else:
            if date_rupture:
                date_cmd_optimale = date_rupture - timedelta(days=lead_time)
                jours_avant_cmd = (date_cmd_optimale - date_actuelle).days
                qte_suggeree_ia = max(eoq, moq)
                if jours_avant_cmd <= 0:
                    statut_ia = "🔴 Urgent"
                    date_cmd_optimale = date_actuelle
                elif jours_avant_cmd <= 7:
                    statut_ia = "🟠 À Planifier"
                else:
                    statut_ia = "🟡 Surveiller"
        if len(hist) == 0:
            statut = "⚪ PAS DE DONNÉES"
            action = "Vérifier historique conso"
        elif ecart < -moq:
            statut = "🔴 CRITIQUE"
            action = f"Commander {max(abs(ecart), eoq):,.0f} kg"
        elif ecart < 0:
            statut = "🟠 TENSION"
            action = f"Commander {max(moq, eoq):,.0f} kg"
        else:
            statut = "🟢 ALIGNÉ"
            action = "Pas d'action"
        fournis_mp = fournis[fournis[col_mp_fournis] == code].copy()
        if len(fournis_mp) > 0:
            fournis_mp['score'] = (fournis_mp['taux_service_%'].fillna(0) * 0.4 + fournis_mp['fiabilite_%'].fillna(0) * 0.3 + fournis_mp['note_qualite_5'].fillna(0) * 20 * 0.3)
            best = fournis_mp.nlargest(1, 'score').iloc[0]
            fournisseur = best['nom_fournisseur']
            delai = best['lead_time_j']
            score_fourni = best['score']
        else:
            fournisseur = "N/A"
            delai = lead_time
            score_fourni = 0
        resultats.append({'Code_MP': code, 'Désignation': designation, 'Stock': stock_secu, 'Besoin_MRP': besoin_mrp, 'Conso_30j': conso_prevue_30j, 'Écart': ecart, 'Couverture_J': couverture_j, 'Valeur_Risque': valeur_risque, 'EOQ': eoq, 'Point_Cmd': point_commande, 'Statut': statut, 'Action': action, 'Fournisseur': fournisseur, 'Délai': delai, 'Score_Fourni': score_fourni, 'Conso_Moy_J': conso_moy_j, 'Has_Forecast': has_forecast, 'Cout_Unit': cout_unit, 'Date_Rupture_Prévue': date_rupture, 'Date_Cmd_Optimale': date_cmd_optimale, 'Qté_Suggérée_IA': qte_suggeree_ia, 'Risque_%': risque_pct, 'Statut_IA': statut_ia, 'Prév_M+1': prevision_m1, 'Prév_M+2': prevision_m2, 'Prév_M+3': prevision_m3})
    df_result = pd.DataFrame(resultats)
    df_result = classification_abc(df_result)
    return df_result, forecasts_dict, fournis

# ========================================
# INTERFACE
# ========================================
st.title("🚀 MRP Pro Dashboard V4.8 - PRO MAX")
st.caption("Rolling 12M + Toast Alerts + PDF Export + Gantt + Search Global")

param, conso, mrp, fournis = charger_donnees_google()
if param is None:
    st.stop()

df_result, forecasts, df_fournis_all = analyser_mrp_appro(param, conso, mrp, fournis)
if len(df_result) == 0:
    st.warning("Aucun MP dans Param")
    st.stop()

# TOAST NOTIFICATIONS
urgents = df_result[df_result['Statut_IA'].str.contains('Urgent')]
if len(urgents) > 0:
    codes_urgents = ", ".join(urgents['Code_MP'].head(3).tolist())
    if len(urgents) > 3:
        codes_urgents += f" + {len(urgents)-3} autres"
    st.toast(f"🔴 URGENT: {codes_urgents} - Commander lyoum!", icon='🔥')

# SIDEBAR + SEARCH
st.sidebar.header("⚙️ Configuration")
st.sidebar.info(f"📅 Date: {datetime.now().strftime('%d/%m/%Y')}\n\n🔄 Rolling: Akhr 12 chehar")
search_query = st.sidebar.text_input("🔍 Search Global", placeholder="Code MP, Désignation, Fournisseur...")
if search_query:
    mask = df_result.apply(lambda row: search_query.lower() in str(row).lower(), axis=1)
    df_result = df_result[mask]
    st.sidebar.success(f"✅ {len(df_result)} résultats")
if st.sidebar.button("🔄 Actualiser Données", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 Dashboard", "🤖 Plan Appro IA", "📅 Prévisions", "🏭 Fournisseurs", "🎯 Simulateur", "🏆 Fourni 360","💬 Chat IA"])

with tab1:
    st.subheader("📊 KPIs Globaux - Version Pro")
    col1, col2, col3, col4 = st.columns(4)
    total_mp = len(df_result)
    critiques = len(df_result[df_result['Statut'].str.contains('CRITIQUE')])
    urgents_ia = len(df_result[df_result['Statut_IA'].str.contains('Urgent')])
    valeur_risque_tot = df_result['Valeur_Risque'].sum()
    with col1:
        st.markdown(kpi_card_html("Total MPs", total_mp, "↑ Actif", "📦", ""), unsafe_allow_html=True)
    with col2:
        st.markdown(kpi_card_html("Critiques", critiques, "⚠️ Attention", "🔴", "kpi-card-red"), unsafe_allow_html=True)
    with col3:
        st.markdown(kpi_card_html("Urgents IA", urgents_ia, "🔥 Action", "🤖", "kpi-card-orange"), unsafe_allow_html=True)
    with col4:
        st.markdown(kpi_card_html("Valeur Risque", f"{valeur_risque_tot:,.0f}", "MAD", "💰", "kpi-card-green"), unsafe_allow_html=True)
    st.divider()
    st.subheader(f"📋 Détail par MP - {total_mp} MPs")
    colf1, colf2, colf3 = st.columns(3)
    statut_filter = colf1.multiselect("Statut", df_result['Statut'].unique(), default=df_result['Statut'].unique())
    classe_filter = colf2.multiselect("Classe ABC", ['A', 'B', 'C'], default=['A', 'B', 'C'])
    df_filtre = df_result[df_result['Statut'].isin(statut_filter) & df_result['Classe'].isin(classe_filter)]
    st.dataframe(df_filtre[['Code_MP', 'Désignation', 'Classe', 'Stock', 'Écart', 'Couverture_J', 'Statut_IA', 'Date_Cmd_Optimale', 'Action']], use_container_width=True, height=400, column_config={"Couverture_J": st.column_config.NumberColumn("Couv. J", format="%.0f j"), "Écart": st.column_config.NumberColumn(format="%d kg"), "Date_Cmd_Optimale": st.column_config.DateColumn("Date Cmd IA", format="DD/MM/YYYY")})

with tab2:
    st.subheader("🤖 Plan d'Approvisionnement IA")
    col_btn1, col_btn2 = st.columns([3, 1])
    df_ia = df_result[df_result['Date_Cmd_Optimale'].notna()].copy()
    df_ia = df_ia.sort_values('Date_Cmd_Optimale')
    with col_btn2:
        if len(df_ia) > 0:
            pdf_buffer = generer_pdf_plan_appro(df_ia)
            st.download_button("📄 Export PDF", pdf_buffer, f"Plan_Appro_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf")
    st.info("💡 **Logique V4.7:** Ila `Statut_IA = Urgent`, `Commander Avant = Aujourd'hui`")
    if len(df_ia) == 0:
        st.success("✅ Aucune commande à planifier. Kolchi sécurisé!")
    else:
        col1, col2, col3, col4 = st.columns(4)
        urgents = len(df_ia[df_ia['Statut_IA'].str.contains('Urgent')])
        a_planifier = len(df_ia[df_ia['Statut_IA'].str.contains('À Planifier')])
        surveiller = len(df_ia[df_ia['Statut_IA'].str.contains('Surveiller')])
        valeur_cmd_tot = (df_ia['Qté_Suggérée_IA'] * df_ia['Cout_Unit']).sum()
        col1.metric("🔴 Urgents", urgents)
        col2.metric("🟠 À Planifier", a_planifier)
        col3.metric("🟡 Surveiller", surveiller)
        col4.metric("💰 Valeur Cmd Total", f"{valeur_cmd_tot:,.0f} MAD")
        st.divider()
        st.dataframe(df_ia[['Code_MP', 'Désignation', 'Statut_IA', 'Date_Rupture_Prévue', 'Date_Cmd_Optimale', 'Qté_Suggérée_IA', 'Fournisseur', 'Risque_%']], use_container_width=True, height=400, column_config={"Date_Rupture_Prévue": st.column_config.DateColumn("Rupture Prévue", format="DD/MM/YYYY"), "Date_Cmd_Optimale": st.column_config.DateColumn("Commander Avant", format="DD/MM/YYYY"), "Qté_Suggérée_IA": st.column_config.NumberColumn("Qté IA (kg)", format="%.0f"), "Risque_%": st.column_config.ProgressColumn("Risque", min_value=0, max_value=100, format="%.0f%%")})
        st.subheader("📊 Gantt Chart - Commandes 90 Jours")
        df_gantt = df_ia[df_ia['Date_Cmd_Optimale'] <= datetime.now().date() + timedelta(days=90)].copy()
        if len(df_gantt) > 0:
            gantt_data = []
            for _, row in df_gantt.iterrows():
                start_date = row['Date_Cmd_Optimale']
                end_date = start_date + timedelta(days=row['Délai'])
                gantt_data.append(dict(Task=row['Code_MP'], Start=start_date, Finish=end_date, Resource=row['Statut_IA']))
            fig_gantt = ff.create_gantt(gantt_data, colors={'🔴 Urgent': 'rgb(245, 87, 108)', '🟠 À Planifier': 'rgb(255, 165, 0)', '🟡 Surveiller': 'rgb(78, 205, 196)'}, index_col='Resource', show_colorbar=True, group_tasks=True, title='Timeline Commandes avec Lead Time')
            fig_gantt.update_layout(height=400)
            st.plotly_chart(fig_gantt, use_container_width=True)

with tab3:
    st.subheader("📅 Prévisions Mensuelles - Rolling 12 Mois")
    df_prev = df_result[['Code_MP', 'Désignation', 'Prév_M+1', 'Prév_M+2', 'Prév_M+3', 'Conso_Moy_J']].copy()
    mois1 = (datetime.now() + relativedelta(months=1)).strftime('%b %Y')
    mois2 = (datetime.now() + relativedelta(months=2)).strftime('%b %Y')
    mois3 = (datetime.now() + relativedelta(months=3)).strftime('%b %Y')
    df_prev = df_prev.rename(columns={'Prév_M+1': f'Prév {mois1}', 'Prév_M+2': f'Prév {mois2}', 'Prév_M+3': f'Prév {mois3}', 'Conso_Moy_J': 'Moy/J (kg)'})
    st.dataframe(df_prev, use_container_width=True, height=400)

with tab4:
    st.subheader("🏭 Analyse Fournisseurs")
    df_fourni_score = df_result[df_result['Fournisseur']!= 'N/A'].groupby('Fournisseur').agg({'Score_Fourni': 'mean', 'Code_MP': 'count', 'Valeur_Risque': 'sum'}).reset_index().rename(columns={'Code_MP': 'Nb_MPs'}).sort_values('Score_Fourni', ascending=False)
    col1, col2 = st.columns(2)
    with col1:
        if len(df_fourni_score) > 0:
            fig = px.bar(df_fourni_score, x='Fournisseur', y='Score_Fourni', title="Score Moyen", color='Score_Fourni', color_continuous_scale='RdYlGn', text='Nb_MPs')
            st.plotly_chart(fig, use_container_width=True)
    with col2:
        if df_fourni_score['Valeur_Risque'].sum() > 0:
            fig2 = px.pie(df_fourni_score, values='Valeur_Risque', names='Fournisseur', title="Valeur à Risque")
            st.plotly_chart(fig2, use_container_width=True)
    st.dataframe(df_fournis_all, use_container_width=True)

with tab5:
    st.subheader("🎯 Simulateur What-If - VERSION VISUELLE")
    col1, col2, col3 = st.columns(3)
    mp_sim = col1.selectbox("MP à simuler", df_result['Code_MP'].unique(), key="sim_mp_v8")
    qte_sim = col2.number_input("Quantité à commander (kg)", min_value=0, value=10000, step=1000, key="sim_qte_v8")
    mp_data_sim = df_result[df_result['Code_MP'] == mp_sim].iloc[0].copy()
    for col in ['Stock', 'Écart', 'Couverture_J', 'Conso_Moy_J']:
        if pd.isna(mp_data_sim[col]):
            mp_data_sim[col] = 0
    nouveau_stock = mp_data_sim['Stock'] + qte_sim
    nouveau_ecart = nouveau_stock - (mp_data_sim['Besoin_MRP'] + mp_data_sim['Conso_30j'])
    nouvelle_couv = nouveau_stock / mp_data_sim['Conso_Moy_J'] if mp_data_sim['Conso_Moy_J'] > 0 else 999
    st.divider()
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        fig_stock = go.Figure()
        fig_stock.add_trace(go.Bar(x=['Stock Actuel', 'Après Commande'], y=[mp_data_sim['Stock'], nouveau_stock], marker_color=['#FF6B6B', '#4ECDC4'], text=[f"{mp_data_sim['Stock']:,.0f}", f"{nouveau_stock:,.0f}"], textposition='auto'))
        fig_stock.update_layout(title="📦 Stock (kg)", yaxis_title="Kg", showlegend=False, height=300)
        st.plotly_chart(fig_stock, use_container_width=True)
    with col_g2:
        color_avant = '#FF6B6B' if mp_data_sim['Écart'] < 0 else '#4ECDC4'
        color_apres = '#FF6B6B' if nouveau_ecart < 0 else '#4ECDC4'
        fig_ecart = go.Figure()
        fig_ecart.add_trace(go.Bar(x=['Écart Actuel', 'Après Commande'], y=[mp_data_sim['Écart'], nouveau_ecart], marker_color=[color_avant, color_apres], text=[f"{mp_data_sim['Écart']:,.0f}", f"{nouveau_ecart:,.0f}"], textposition='auto'))
        fig_ecart.add_hline(y=0, line_dash="dash", line_color="black", annotation_text="Seuil 0")
        fig_ecart.update_layout(title="⚖️ Écart (kg)", yaxis_title="Kg", showlegend=False, height=300)
        st.plotly_chart(fig_ecart, use_container_width=True)
    with col_g3:
        color_couv_avant = '#FF6B6B' if mp_data_sim['Couverture_J'] < 7 else '#FFA500' if mp_data_sim['Couverture_J'] < 14 else '#4ECDC4'
        color_couv_apres = '#FF6B6B' if nouvelle_couv < 7 else '#FFA500' if nouvelle_couv < 14 else '#4ECDC4'
        fig_couv = go.Figure()
        fig_couv.add_trace(go.Bar(x=['Couv. Actuelle', 'Après Commande'], y=[mp_data_sim['Couverture_J'], nouvelle_couv], marker_color=[color_couv_avant, color_couv_apres], text=[f"{mp_data_sim['Couverture_J']:.0f}j", f"{nouvelle_couv:.0f}j"], textposition='auto'))
        fig_couv.add_hline(y=7, line_dash="dash", line_color="red", annotation_text="Critique")
        fig_couv.add_hline(y=14, line_dash="dash", line_color="orange", annotation_text="Tension")
        fig_couv.update_layout(title="📅 Couverture (jours)", yaxis_title="Jours", showlegend=False, height=300)
        st.plotly_chart(fig_couv, use_container_width=True)
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nouveau Stock", f"{nouveau_stock:,.0f} kg", f"+{qte_sim:,.0f}")
    col2.metric("Nouvel Écart", f"{nouveau_ecart:,.0f} kg", f"{nouveau_ecart - mp_data_sim['Écart']:,.0f}")
    col3.metric("Nouvelle Couverture", f"{nouvelle_couv:.0f} jours", f"{nouvelle_couv - mp_data_sim['Couverture_J']:.0f}")
    col4.metric("Coût Commande", f"{qte_sim * mp_data_sim['Cout_Unit']:,.0f} MAD")
    if nouveau_ecart >= 0:
        st.success(f"✅ **VERDICT: ALIGNÉ** → Avec {qte_sim:,.0f} kg, **{mp_sim} ywlli VERT**!")
    elif nouveau_ecart >= -mp_data_sim['EOQ']:
        st.warning(f"🟠 **VERDICT: TENSION** → **{mp_sim} ba9i ORANGE**. Khass {abs(nouveau_ecart):,.0f} kg zayda.")
    else:
        st.error(f"🔴 **VERDICT: CRITIQUE** → **{mp_sim} ba9i ROUGE**. Khass {abs(nouveau_ecart):,.0f} kg zayda.")

with tab6:
    st.subheader("Chat IA Pro - Version Stable")
    st.caption("Version bla syntax errors")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Swwl 3la: plan, prevision, risque, abc, fournisseur"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        p = prompt.lower()
        r = "Ma fhmtech. Swwl 3la: plan, prevision, risque, abc, fournisseur"

        if "plan" in p or "commande" in p:
            df_c = df_result[df_result['Date_Cmd_Optimale'].notna()].sort_values('Date_Cmd_Optimale')
            if len(df_c) > 0:
                lines = []
                lines.append("Plan Commande IA - " + str(len(df_c)) + " MPs:")
                lines.append("")
                for _, row in df_c.head(10).iterrows():
                    d = row['Date_Cmd_Optimale'].strftime('%d/%m')
                    qte = f"{row['Qté_Suggérée_IA']:,.0f}"
                    lines.append(d + ": " + row['Code_MP'] + " - " + qte + " kg - " + row['Statut_IA'])
                total = (df_c['Qté_Suggérée_IA'] * df_c['Cout_Unit']).sum()
                lines.append("")
                lines.append("Total: " + f"{total:,.0f}" + " MAD")
                r = "\n".join(lines)
            else:
                r = "Kolchi sécurisé! Ma kayn 7ta commande."

        elif "prevision" in p or "prev" in p:
            lines = []
            lines.append("Prévisions 3 Mois:")
            lines.append("")
            for _, row in df_result.iterrows():
                p1 = f"{row['Prév_M+1']:,.0f}"
                p2 = f"{row['Prév_M+2']:,.0f}"
                p3 = f"{row['Prév_M+3']:,.0f}"
                lines.append(row['Code_MP'] + ": " + p1 + " / " + p2 + " / " + p3 + " kg")
            r = "\n".join(lines)

        elif "risque" in p:
            crit = df_result[df_result['Risque_%'] > 50]
            if len(crit) > 0:
                lines = []
                lines.append(str(len(crit)) + " MPs f Risque:")
                lines.append("")
                for _, row in crit.iterrows():
                    lines.append(row['Code_MP'] + ": " + str(int(row['Risque_%'])) + "% - " + row['Action'])
                r = "\n".join(lines)
            else:
                r = "Ma kayn 7ta risque!"

        elif "abc" in p or "classe" in p:
            ca = df_result[df_result['Classe'] == 'A']
            lines = []
            lines.append("Classe A - " + str(len(ca)) + " MPs:")
            lines.append("")
            for _, row in ca.iterrows():
                val = f"{row['Valeur_Risque']:,.0f}"
                lines.append(row['Code_MP'] + ": " + val + " MAD")
            r = "\n".join(lines)

        elif "fournisseur" in p:
            df_f = df_result[df_result['Fournisseur'] != 'N/A'].groupby('Fournisseur')['Valeur_Risque'].sum()
            if df_f.sum() > 0:
                lines = []
                lines.append("Valeur à Risque:")
                lines.append("")
                for f, v in df_f.items():
                    if v > 0:
                        lines.append(f + ": " + f"{v:,.0f}" + " MAD")
                r = "\n".join(lines)
            else:
                r = "Ma kayn 7ta risque!"

        st.session_state.messages.append({"role": "assistant", "content": r})
        with st.chat_message("assistant"):
            st.markdown(r)

with tab6:
    st.subheader("💬 Chat IA Pro - Version Stable")
    ... # code dyal tab6 kamlo
    # akhr ster dyal tab6 hna

# W HNA BDDA TAB7
with tab7:
    st.subheader("🏆 Fournisseur 360 - Dashboard Individuel")
    st.caption("Profil kamil dyal kola fournisseur b KPIs w historique")

    # SELECTEUR FOURNISSEUR
    if df_fournis_all is None or len(df_fournis_all) == 0:
        st.warning("Ma kaynch données fournisseurs f sheet 'Fournisseurs'")
        st.stop()
    
    liste_fournis = sorted(df_fournis_all['nom_fournisseur'].dropna().unique().tolist())
    
    if len(liste_fournis) == 0:
        st.warning("Ma l9itch smiyat fournisseurs f l sheet")
        st.stop()
    
    fourni_select = st.selectbox("🎯 Khtar Fournisseur", liste_fournis)

    if fourni_select:
        # FILTRAGE DATA
        df_fourni_data = df_fournis_all[df_fournis_all['nom_fournisseur'] == fourni_select].copy()
        df_mps_fourni = df_result[df_result['Fournisseur'] == fourni_select].copy()
        
        # ==================== KPIs HEADER ====================
        col1, col2, col3, col4, col5 = st.columns(5)
        
        nb_mps = len(df_mps_fourni)
        urgents = len(df_mps_fourni[df_mps_fourni['Statut_IA'].str.contains('Urgent', na=False)])
        pct_urgent = (urgents / nb_mps * 100) if nb_mps > 0 else 0
        delai_moy = df_fourni_data['lead_time_j'].mean() if len(df_fourni_data) > 0 else 0
        taux_service = df_fourni_data['taux_service_%'].mean() if len(df_fourni_data) > 0 else 0
        fiabilite = df_fourni_data['fiabilite_%'].mean() if len(df_fourni_data) > 0 else 0
        note_qualite = df_fourni_data['note_qualite_5'].mean() if len(df_fourni_data) > 0 else 0
        valeur_risque = df_mps_fourni['Valeur_Risque'].sum()
        
        # Score Global
        score_global = (taux_service * 0.4 + fiabilite * 0.3 + note_qualite * 20 * 0.3)
        
        with col1:
            st.markdown(kpi_card_html("MPs Fournis", nb_mps, f"{urgents} urgents", "📦", ""), unsafe_allow_html=True)
        with col2:
            color = "kpi-card-red" if pct_urgent > 30 else "kpi-card-orange" if pct_urgent > 10 else "kpi-card-green"
            st.markdown(kpi_card_html("% Urgents", f"{pct_urgent:.0f}%", "Stress Level", "🔴", color), unsafe_allow_html=True)
        with col3:
            st.markdown(kpi_card_html("Délai Moyen", f"{delai_moy:.0f}j", "Lead Time", "⏱️", ""), unsafe_allow_html=True)
        with col4:
            color = "kpi-card-green" if taux_service >= 95 else "kpi-card-orange" if taux_service >= 85 else "kpi-card-red"
            st.markdown(kpi_card_html("Taux Service", f"{taux_service:.0f}%", "On-Time", "📊", color), unsafe_allow_html=True)
        with col5:
            color = "kpi-card-green" if score_global >= 90 else "kpi-card-orange" if score_global >= 75 else "kpi-card-red"
            st.markdown(kpi_card_html("Score Global", f"{score_global:.0f}/100", "⭐ Note", "🏆", color), unsafe_allow_html=True)
        
        st.divider()
        
        # ==================== GRAPHIQUES ====================
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("📊 Répartition Statuts MPs")
            if len(df_mps_fourni) > 0:
                statut_count = df_mps_fourni['Statut_IA'].value_counts()
                fig_statut = px.pie(
                    values=statut_count.values, 
                    names=statut_count.index, 
                    hole=0.4,
                    color_discrete_map={'🔴 Urgent': '#FF6B6B', '🟠 À Planifier': '#FFA500', '🟡 Surveiller': '#4ECDC4', '✅ Sécurisé': '#51CF66'}
                )
                fig_statut.update_layout(height=300, showlegend=True)
                st.plotly_chart(fig_statut, use_container_width=True)
            else:
                st.info("Ma kaynch MPs m3a had fournisseur f MRP")
        
        with col_g2:
            st.subheader("💎 KPIs Qualité")
            kpi_data = pd.DataFrame({
                'Métrique': ['Taux Service', 'Fiabilité', 'Qualité'],
                'Valeur': [taux_service, fiabilite, note_qualite * 20],
                'Objectif': [95, 90, 90]
            })
            fig_kpi = go.Figure()
            fig_kpi.add_trace(go.Bar(x=kpi_data['Métrique'], y=kpi_data['Valeur'], name='Réel', marker_color='#667eea'))
            fig_kpi.add_trace(go.Scatter(x=kpi_data['Métrique'], y=kpi_data['Objectif'], name='Objectif', mode='lines+markers', line=dict(color='red', dash='dash')))
            fig_kpi.update_layout(height=300, yaxis_title="%", yaxis_range=[0,100])
            st.plotly_chart(fig_kpi, use_container_width=True)
        
        st.divider()
        
        # ==================== TABLEAU MPs ====================
        st.subheader(f"📦 MPs Fournis par {fourni_select} - {len(df_mps_fourni)} articles")
        
        if len(df_mps_fourni) > 0:
            st.dataframe(
                df_mps_fourni[['Code_MP', 'Désignation', 'Stock', 'Écart', 'Couverture_J', 'Statut_IA', 'Date_Cmd_Optimale', 'Qté_Suggérée_IA', 'Valeur_Risque']],
                use_container_width=True,
                height=350,
                column_config={
                    "Couverture_J": st.column_config.NumberColumn("Couv. J", format="%.0f j"),
                    "Écart": st.column_config.NumberColumn(format="%d kg"),
                    "Date_Cmd_Optimale": st.column_config.DateColumn("Cmd Avant", format="DD/MM/YYYY"),
                    "Qté_Suggérée_IA": st.column_config.NumberColumn("Qté (kg)", format="%.0f"),
                    "Valeur_Risque": st.column_config.NumberColumn("Risque MAD", format="%.0f")
                }
            )
            
            # EXPORT EXCEL PAR FOURNISSEUR
            excel_buf = BytesIO()
            df_mps_fourni.to_excel(excel_buf, index=False, engine='openpyxl')
            excel_buf.seek(0)
            st.download_button(
                f"📊 Export Excel {fourni_select}",
                excel_buf,
                f"Fourni_{fourni_select}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning(f"Ma kayn 7ta MP m3a {fourni_select} f MRP dyalk")
        
        st.divider()
        
        # ==================== ALERTES ====================
        st.subheader("🚨 Alertes & Recommandations")
        
        alerts = []
        if pct_urgent > 30:
            alerts.append(f"🔴 **RISQUE ÉLEVÉ**: {pct_urgent:.0f}% dyal MPs urgents. Khassk tswl {fourni_select} 3lach.")
        if taux_service < 85:
            alerts.append(f"⚠️ **Taux Service Faible**: {taux_service:.0f}%. Chof fournisseur alternatif.")
        if fiabilite < 80:
            alerts.append(f"⚠️ **Fiabilité Faible**: {fiabilite:.0f}%. Problèmes qualité fréquents.")
        if delai_moy > df_result['Délai'].mean() * 1.3:
            alerts.append(f"⏱️ **Délai Long**: {delai_moy:.0f}j vs {df_result['Délai'].mean():.0f}j moyenne. Impact stock sécurité.")
        if valeur_risque > 100000:
            alerts.append(f"💰 **Valeur à Risque Élevée**: {valeur_risque:,.0f} MAD. Diversifie fournisseurs.")
        
        if alerts:
            for alert in alerts:
                st.warning(alert)
        else:
            st.success(f"✅ **{fourni_select} fournisseur fiable!** Kolchi KPIs f lkhdar.")
