import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# ========================================
# CONFIG
# ========================================
SHEET_ID = "1DNmM76FfZRtucCMEB-If0t1EEV-lPRn70pl9yP2ooeM"
st.set_page_config(page_title="MRP Pro Dashboard V4", layout="wide", page_icon="🎯")

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
    """Formule Wilson EOQ"""
    if cout_stockage_unit <= 0 or demande_annuelle <= 0:
        return 0
    eoq = np.sqrt((2 * demande_annuelle * cout_commande) / cout_stockage_unit)
    return eoq

def classification_abc(df):
    """Classification ABC Pareto 80/20"""
    df = df.sort_values('Valeur_Risque', ascending=False).reset_index(drop=True)
    df['Cumul'] = df['Valeur_Risque'].cumsum()
    df['Cumul_%'] = df['Cumul'] / df['Valeur_Risque'].sum() * 100
    df['Classe'] = df['Cumul_%'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))
    return df

def analyser_mrp_appro(param, conso, mrp, fournis):
    col_mp_param = trouver_colonne(param, ['code_mp'])
    col_mp_conso = trouver_colonne(conso, ['code_mp'])
    col_qte_conso = trouver_colonne(conso, ['qte_consommee_kg', 'qte_consommee'])
    col_mp_mrp = trouver_colonne(mrp, ['code_mp'])
    col_qte_mrp = trouver_colonne(mrp, ['qte_besoin_kg', 'qte_besoin'])
    col_mp_fournis = trouver_colonne(fournis, ['code_mp'])

    resultats = []
    forecasts_dict = {}

    for _, mp_row in param.iterrows():
        code = mp_row[col_mp_param]
        stock_secu = mp_row.get('stock_secu_actuel', 0)
        lead_time = mp_row.get('lead_time_j', 14)
        moq = mp_row.get('moq_kg', 1000)
        cout_unit = mp_row.get('cout_unitaire', 0)
        designation = mp_row.get('designation', 'N/A')
        cout_commande = mp_row.get('cout_commande', 500) # Coût de passation
        taux_stockage = mp_row.get('taux_stockage', 0.2) # 20% par an

        # Conso historique
        hist = conso[conso[col_mp_conso] == code].copy()
        hist = hist.dropna(subset=['date', col_qte_conso])

        conso_prevue_30j = 0
        conso_moy_j = 0
        demande_annuelle = 0
        has_forecast = False

        if len(hist) >= 10:
            df_prophet = hist.groupby('date')[col_qte_conso].sum().reset_index()
            df_prophet.columns = ['ds', 'y']
            df_prophet = df_prophet.dropna()

            if len(df_prophet) >= 10:
                try:
                    m = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
                    m.fit(df_prophet)
                    future = m.make_future_dataframe(periods=60)
                    forecast = m.predict(future)
                    conso_prevue_30j = forecast[forecast['ds'] > df_prophet['ds'].max()].head(30)['yhat'].sum()
                    conso_prevue_30j = max(0, conso_prevue_30j)
                    conso_moy_j = df_prophet['y'].mean()
                    demande_annuelle = conso_moy_j * 365
                    forecasts_dict[code] = forecast
                    has_forecast = True
                except:
                    conso_moy_j = df_prophet['y'].mean() if len(df_prophet) > 0 else 0
                    conso_prevue_30j = conso_moy_j * 30
                    demande_annuelle = conso_moy_j * 365

        # MRP
        besoin_mrp = mrp[mrp[col_mp_mrp] == code][col_qte_mrp].sum()
        besoin_mrp = 0 if pd.isna(besoin_mrp) else besoin_mrp

        # Calculs
        couverture_j = stock_secu / conso_moy_j if conso_moy_j > 0 else 999
        besoin_total = besoin_mrp + conso_prevue_30j
        ecart = stock_secu - besoin_total
        valeur_risque = abs(ecart) * cout_unit if ecart < 0 else 0

        # EOQ
        cout_stockage_unit = cout_unit * taux_stockage
        eoq = calcul_eoq(demande_annuelle, cout_commande, cout_stockage_unit, cout_unit)
        point_commande = conso_moy_j * lead_time

        # Statut
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

        # Fournisseur
        fournis_mp = fournis[fournis[col_mp_fournis] == code].copy()
        if len(fournis_mp) > 0:
            fournis_mp['score'] = (
                fournis_mp['taux_service_%'].fillna(0) * 0.4 +
                fournis_mp['fiabilite_%'].fillna(0) * 0.3 +
                fournis_mp['note_qualite_5'].fillna(0) * 20 * 0.3
            )
            best = fournis_mp.nlargest(1, 'score').iloc[0]
            fournisseur = best['nom_fournisseur']
            delai = best['lead_time_j']
            score_fourni = best['score']
        else:
            fournisseur = "N/A"
            delai = lead_time
            score_fourni = 0

        resultats.append({
            'Code_MP': code,
            'Désignation': designation,
            'Stock': stock_secu,
            'Besoin_MRP': besoin_mrp,
            'Conso_30j': conso_prevue_30j,
            'Écart': ecart,
            'Couverture_J': couverture_j,
            'Valeur_Risque': valeur_risque,
            'EOQ': eoq,
            'Point_Cmd': point_commande,
            'Statut': statut,
            'Action': action,
            'Fournisseur': fournisseur,
            'Délai': delai,
            'Score_Fourni': score_fourni,
            'Conso_Moy_J': conso_moy_j,
            'Has_Forecast': has_forecast,
            'Cout_Unit': cout_unit
        })

    df_result = pd.DataFrame(resultats)
    df_result = classification_abc(df_result)
    return df_result, forecasts_dict, fournis

def generer_pdf(df):
    """Génère rapport PDF"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    # Titre
    elements.append(Paragraph("Rapport MRP vs Approvisionnement", styles['Title']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Tableau
    data = [['Code MP', 'Désignation', 'Stock', 'Écart', 'Statut', 'Action']]
    for _, row in df.iterrows():
        data.append([
            row['Code_MP'],
            row['Désignation'][:20],
            f"{row['Stock']:,.0f}",
            f"{row['Écart']:,.0f}",
            row['Statut'],
            row['Action'][:30]
        ])

    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ========================================
# INTERFACE
# ========================================
st.title("🎯 MRP Pro Dashboard V4")
st.caption("Analyse Prédictive + EOQ + ABC + Simulateur What-If + PDF")

param, conso, mrp, fournis = charger_donnees_google()

if param is None:
    st.stop()

st.sidebar.header("⚙️ Configuration")
if st.sidebar.button("🔄 Actualiser Données"):
    st.cache_data.clear()
    st.rerun()

df_result, forecasts, df_fournis_all = analyser_mrp_appro(param, conso, mrp, fournis)

if len(df_result) == 0:
    st.warning("Aucun MP dans Param")
    st.stop()

# TABS
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "🏭 Fournisseurs", "📈 Graphiques", "🎯 Simulateur", "💬 Chat IA"])

with tab1:
    st.subheader("📊 KPIs Globaux")
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    total_mp = len(df_result)
    critiques = len(df_result[df_result['Statut'].str.contains('CRITIQUE')])
    classe_a = len(df_result[df_result['Classe'] == 'A'])
    valeur_risque_tot = df_result['Valeur_Risque'].sum()
    eoq_moy = df_result['EOQ'].mean()
    couverture_moy = df_result[df_result['Couverture_J'] < 999]['Couverture_J'].mean()

    col1.metric("📦 Total MPs", total_mp)
    col2.metric("🔴 Critiques", critiques)
    col3.metric("💎 Classe A", classe_a, "80% valeur")
    col4.metric("💰 Valeur Risque", f"{valeur_risque_tot:,.0f} MAD")
    col5.metric("📦 EOQ Moy", f"{eoq_moy:,.0f} kg")
    col6.metric("📅 Couv. Moy", f"{couverture_moy:.0f}j")

    st.divider()
    st.subheader(f"📋 Détail par MP - {total_mp} MPs | Classe ABC")

    colf1, colf2, colf3 = st.columns(3)
    statut_filter = colf1.multiselect("Statut", df_result['Statut'].unique(), default=df_result['Statut'].unique())
    classe_filter = colf2.multiselect("Classe ABC", ['A', 'B', 'C'], default=['A', 'B', 'C'])
    df_filtre = df_result[df_result['Statut'].isin(statut_filter) & df_result['Classe'].isin(classe_filter)]

    st.dataframe(
        df_filtre[['Code_MP', 'Désignation', 'Classe', 'Stock', 'Besoin_MRP', 'Conso_30j', 'Écart', 'Couverture_J', 'EOQ', 'Statut', 'Action']],
        use_container_width=True, height=400,
        column_config={
            "Couverture_J": st.column_config.NumberColumn("Couv. J", format="%.0f j"),
            "Écart": st.column_config.NumberColumn(format="%d kg"),
            "EOQ": st.column_config.NumberColumn(format="%.0f kg"),
            "Classe": st.column_config.TextColumn(help="A=80% valeur, B=15%, C=5%")
        }
    )

    col1, col2 = st.columns(2)
    csv = df_filtre.to_csv(index=False).encode('utf-8-sig')
    col1.download_button("📥 Télécharger CSV", csv, f"MRP_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

    pdf_buffer = generer_pdf(df_filtre)
    col2.download_button("📄 Télécharger PDF", pdf_buffer, f"Rapport_MRP_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf")

with tab2:
    st.subheader("🏭 Analyse Fournisseurs - TOUS les fournisseurs")
    st.write(f"**Total fournisseurs:** {len(df_fournis_all)} | **Actifs:** {len(df_result[df_result['Fournisseur']!= 'N/A']['Fournisseur'].unique())}")

    df_fourni_score = df_result[df_result['Fournisseur']!= 'N/A'].groupby('Fournisseur').agg({
        'Score_Fourni': 'mean',
        'Code_MP': 'count',
        'Valeur_Risque': 'sum'
    }).reset_index().rename(columns={'Code_MP': 'Nb_MPs'}).sort_values('Score_Fourni', ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        if len(df_fourni_score) > 0:
            fig = px.bar(df_fourni_score, x='Fournisseur', y='Score_Fourni', title="Score Moyen",
                         color='Score_Fourni', color_continuous_scale='RdYlGn', text='Nb_MPs')
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        if df_fourni_score['Valeur_Risque'].sum() > 0:
            fig2 = px.pie(df_fourni_score, values='Valeur_Risque', names='Fournisseur', title="Valeur à Risque")
            st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df_fournis_all, use_container_width=True)

with tab3:
    st.subheader("📈 Graphiques Analytiques")
    mp_select = st.selectbox("Choisir MP", df_result['Code_MP'].unique())
    mp_data = df_result[df_result['Code_MP'] == mp_select].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        fig.add_trace(go.Bar(name='Stock', x=['Stock'], y=[mp_data['Stock']], marker_color='blue'))
        fig.add_trace(go.Bar(name='Besoin Total', x=['Besoin'], y=[mp_data['Besoin_MRP'] + mp_data['Conso_30j']], marker_color='red'))
        fig.add_trace(go.Bar(name='EOQ', x=['EOQ'], y=[mp_data['EOQ']], marker_color='green'))
        fig.update_layout(title=f"{mp_select} | Écart: {mp_data['Écart']:,.0f} kg | Classe {mp_data['Classe']}", barmode='group')
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        if mp_select in forecasts and forecasts[mp_select] is not None:
            fc = forecasts[mp_select]
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=fc['ds'], y=fc['yhat'], name='Prévision', line=dict(color='orange')))
            fig2.add_trace(go.Scatter(x=fc['ds'], y=fc['yhat_upper'], fill=None, line=dict(color='lightgray'), showlegend=False))
            fig2.add_trace(go.Scatter(x=fc['ds'], y=fc['yhat_lower'], fill='tonexty', line=dict(color='lightgray'), name='Intervalle'))
            fig2.update_layout(title=f"Prévision {mp_select} - 60j")
            st.plotly_chart(fig2, use_container_width=True)

with tab4:
    st.subheader("🎯 Simulateur What-If")
    st.caption("Tester l'impact d'une commande avant de la passer")

    col1, col2, col3 = st.columns(3)
    mp_sim = col1.selectbox("MP à simuler", df_result['Code_MP'].unique())
    qte_sim = col2.number_input("Quantité à commander (kg)", min_value=0, value=10000, step=1000)

    mp_data_sim = df_result[df_result['Code_MP'] == mp_sim].iloc[0]
    nouveau_stock = mp_data_sim['Stock'] + qte_sim
    nouveau_ecart = nouveau_stock - (mp_data_sim['Besoin_MRP'] + mp_data_sim['Conso_30j'])
    nouvelle_couv = nouveau_stock / mp_data_sim['Conso_Moy_J'] if mp_data_sim['Conso_Moy_J'] > 0 else 999

    col3.metric("Nouveau Stock", f"{nouveau_stock:,.0f} kg", f"{qte_sim:,.0f}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Nouvel Écart", f"{nouveau_ecart:,.0f} kg", f"{nouveau_ecart - mp_data_sim['Écart']:,.0f}")
    col2.metric("Nouvelle Couverture", f"{nouvelle_couv:.0f} jours", f"{nouvelle_couv - mp_data_sim['Couverture_J']:.0f}")
    col3.metric("Coût Commande", f"{qte_sim * mp_data_sim['Cout_Unit']:,.0f} MAD")

    if nouveau_ecart >= 0:
        st.success(f"✅ Avec {qte_sim:,.0f} kg, **{mp_sim} passe en ALIGNÉ**. Plus de risque!")
    else:
        st.warning(f"⚠️ Avec {qte_sim:,.0f} kg, **{mp_sim} reste en TENSION**. Il faut {abs(nouveau_ecart):,.0f} kg de plus.")

with tab5:
    st.subheader("💬 Chat IA Pro")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ex: 'Ch7al EOQ dyal MP_PP?' 'Chno plan commande?'"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        prompt_lower = prompt.lower()
        response = ""

        if any(x in prompt_lower for x in ["eoq", "qte économique"]):
            for mp in df_result['Code_MP'].unique():
                if mp.lower() in prompt_lower:
                    row = df_result[df_result['Code_MP'] == mp].iloc[0]
                    response = f"**EOQ {mp}**: {row['EOQ']:,.0f} kg\n**Point Commande**: {row['Point_Cmd']:,.0f} kg\n**Stock Actuel**: {row['Stock']:,.0f} kg\n\n💡 **Recommandation**: Commander {row['EOQ']:,.0f} kg quand stock = {row['Point_Cmd']:,.0f} kg"
                    break
            if not response:
                response = "**EOQ par MP:**\n" + "\n".join([f"- {r['Code_MP']}: {r['EOQ']:,.0f} kg" for _, r in df_result.nlargest(5, 'EOQ').iterrows()])

        elif "plan" in prompt_lower or "commande" in prompt_lower:
            critiques = df_result[df_result['Statut'].str.contains('CRITIQUE') | df_result['Statut'].str.contains('TENSION')]
            if len(critiques) > 0:
                response = f"📅 **Plan de Commande Urgent - {len(critiques)} MPs:**\n\n"
                for _, row in critiques.sort_values('Couverture_J').iterrows():
                    date_cmd = datetime.now() + timedelta(days=max(0, row['Couverture_J'] - row['Délai']))
                    response += f"**{date_cmd.strftime('%d/%m')}**: Commander {row['Code_MP']} - {max(abs(row['Écart']), row['EOQ']):,.0f} kg chez {row['Fournisseur']}\n"
            else:
                response = "✅ Aucune commande urgente. Tous les MPs ALIGNÉS!"

        elif "abc" in prompt_lower or "pareto" in prompt_lower:
            classe_a = df_result[df_result['Classe'] == 'A']
            response = f"💎 **Classe A (80% valeur)**: {len(classe_a)} MPs\n\n"
            for _, row in classe_a.head(5).iterrows():
                response += f"- **{row['Code_MP']}**: {row['Valeur_Risque']:,.0f} MAD | {row['Statut']}\n"

        else:
            response = f"**Questions dispo:**\n- 'EOQ dyal MP_PP?'\n- 'Plan commande?'\n- 'Classification ABC?'\n- 'Ch7al khssni mn X?'\n\n**MPs:** {', '.join(df_result['Code_MP'].tolist())}"

        with st.chat_message("assistant"):
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
