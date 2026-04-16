import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ========================================
# CONFIG
# ========================================
SHEET_ID = "1DNmM76FfZRtucCMEB-If0t1EEV-lPRn70pl9yP2ooeM"
st.set_page_config(page_title="MRP Pro Dashboard", layout="wide", page_icon="🎯")

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

        # Nettoyage colonnes
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

def analyser_mrp_appro(param, conso, mrp, fournis):
    col_mp_param = trouver_colonne(param, ['code_mp'])
    col_mp_conso = trouver_colonne(conso, ['code_mp'])
    col_qte_conso = trouver_colonne(conso, ['qte_consommee_kg', 'qte_consommee'])
    col_mp_mrp = trouver_colonne(mrp, ['code_mp'])
    col_qte_mrp = trouver_colonne(mrp, ['qte_besoin_kg', 'qte_besoin'])
    col_mp_fournis = trouver_colonne(fournis, ['code_mp'])

    resultats = []
    forecasts_dict = {}

    # 🔥 IMPORTANT: Ndwzo 3la KOL MP f Param, wakha ma 3ndoch conso
    for _, mp_row in param.iterrows():
        code = mp_row[col_mp_param]
        stock_secu = mp_row.get('stock_secu_actuel', 0)
        lead_time = mp_row.get('lead_time_j', 14)
        moq = mp_row.get('moq_kg', 1000)
        cout_unit = mp_row.get('cout_unitaire', 0)
        designation = mp_row.get('designation', 'N/A')

        # Conso historique - wakha ma kaynach
        hist = conso[conso[col_mp_conso] == code].copy()
        hist = hist.dropna(subset=['date', col_qte_conso])

        conso_prevue_30j = 0
        conso_moy_j = 0
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
                    forecasts_dict[code] = forecast
                    has_forecast = True
                except:
                    conso_moy_j = df_prophet['y'].mean() if len(df_prophet) > 0 else 0
                    conso_prevue_30j = conso_moy_j * 30

        # MRP
        besoin_mrp = mrp[mrp[col_mp_mrp] == code][col_qte_mrp].sum()
        besoin_mrp = 0 if pd.isna(besoin_mrp) else besoin_mrp

        # Calculs
        couverture_j = stock_secu / conso_moy_j if conso_moy_j > 0 else 999
        besoin_total = besoin_mrp + conso_prevue_30j
        ecart = stock_secu - besoin_total
        valeur_risque = abs(ecart) * cout_unit if ecart < 0 else 0

        # Statut
        if len(hist) == 0:
            statut = "⚪ PAS DE DONNÉES"
            action = "Vérifier historique conso"
        elif ecart < -moq:
            statut = "🔴 CRITIQUE"
            action = f"Commander {abs(ecart):,.0f} kg"
        elif ecart < 0:
            statut = "🟠 TENSION"
            action = f"Commander {moq:,.0f} kg"
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
            'Statut': statut,
            'Action': action,
            'Fournisseur': fournisseur,
            'Délai': delai,
            'Score_Fourni': score_fourni,
            'Conso_Moy_J': conso_moy_j,
            'Has_Forecast': has_forecast
        })

    return pd.DataFrame(resultats), forecasts_dict, fournis

# ========================================
# INTERFACE
# ========================================
st.title("🎯 MRP vs Approvisionnement - Dashboard Pro")
st.caption("Analyse prédictive + KPIs Fournisseurs + Chat IA")

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
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🏭 Fournisseurs", "📈 Graphiques", "💬 Chat IA"])

with tab1:
    st.subheader("📊 KPIs Globaux")
    col1, col2, col3, col4, col5 = st.columns(5)

    total_mp = len(df_result)
    critiques = len(df_result[df_result['Statut'].str.contains('CRITIQUE')])
    tensions = len(df_result[df_result['Statut'].str.contains('TENSION')])
    sans_donnees = len(df_result[df_result['Statut'].str.contains('PAS DE DONNÉES')])
    valeur_risque_tot = df_result['Valeur_Risque'].sum()

    col1.metric("📦 Total MPs", total_mp)
    col2.metric("🔴 Critiques", critiques, f"{critiques/total_mp*100:.0f}%")
    col3.metric("🟠 Tensions", tensions)
    col4.metric("⚪ Sans Données", sans_donnees)
    col5.metric("💰 Valeur à Risque", f"{valeur_risque_tot:,.0f} MAD")

    st.divider()
    st.subheader(f"📋 Détail par MP - {total_mp} MPs trouvés")

    # Filtres
    colf1, colf2 = st.columns(2)
    statut_filter = colf1.multiselect("Filtrer par Statut", df_result['Statut'].unique(), default=df_result['Statut'].unique())
    df_filtre = df_result[df_result['Statut'].isin(statut_filter)]

    st.dataframe(
        df_filtre[['Code_MP', 'Désignation', 'Stock', 'Besoin_MRP', 'Conso_30j', 'Écart', 'Couverture_J', 'Statut', 'Action', 'Fournisseur']],
        use_container_width=True, height=400,
        column_config={
            "Couverture_J": st.column_config.NumberColumn("Couv. Jours", format="%.0f j"),
            "Écart": st.column_config.NumberColumn(format="%d kg"),
            "Stock": st.column_config.NumberColumn(format="%d kg"),
            "Besoin_MRP": st.column_config.NumberColumn(format="%d kg"),
            "Conso_30j": st.column_config.NumberColumn("Conso 30j", format="%d kg")
        }
    )

    csv = df_filtre.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 Télécharger CSV", csv, f"MRP_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

with tab2:
    st.subheader("🏭 Analyse Fournisseurs - TOUS les fournisseurs")

    # 🔥 IMPORTANT: Afficher TOUS les fournisseurs, wakha ma 3ndhomch MP actif
    st.write(f"**Total fournisseurs dans la base:** {len(df_fournis_all)}")

    # Score par fournisseur
    df_fourni_score = df_result[df_result['Fournisseur']!= 'N/A'].groupby('Fournisseur').agg({
        'Score_Fourni': 'mean',
        'Code_MP': 'count',
        'Valeur_Risque': 'sum'
    }).reset_index().rename(columns={'Code_MP': 'Nb_MPs'})

    # Ajouter fournisseurs sans MP
    fournisseurs_sans_mp = df_fournis_all[~df_fournis_all['nom_fournisseur'].isin(df_fourni_score['Fournisseur'])]
    if len(fournisseurs_sans_mp) > 0:
        st.warning(f"⚠️ {len(fournisseurs_sans_mp)} fournisseurs sans MP associé:")
        st.dataframe(fournisseurs_sans_mp[['nom_fournisseur', 'code_mp']], use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        if len(df_fourni_score) > 0:
            fig = px.bar(df_fourni_score, x='Fournisseur', y='Score_Fourni', title="Score Moyen par Fournisseur",
                         color='Score_Fourni', color_continuous_scale='RdYlGn', text='Nb_MPs')
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        if df_fourni_score['Valeur_Risque'].sum() > 0:
            fig2 = px.pie(df_fourni_score, values='Valeur_Risque', names='Fournisseur',
                          title="Répartition Valeur à Risque")
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📋 Détail Tous les Fournisseurs")
    st.dataframe(df_fournis_all, use_container_width=True)

with tab3:
    st.subheader("📈 Graphiques Analytiques")
    mp_select = st.selectbox("Choisir MP pour détail", df_result['Code_MP'].unique())
    mp_data = df_result[df_result['Code_MP'] == mp_select].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        fig.add_trace(go.Bar(name='Stock', x=['Stock'], y=[mp_data['Stock']], marker_color='blue'))
        fig.add_trace(go.Bar(name='Besoin Total', x=['Besoin'], y=[mp_data['Besoin_MRP'] + mp_data['Conso_30j']], marker_color='red'))
        fig.update_layout(title=f"Écart {mp_select}: {mp_data['Écart']:,.0f} kg", barmode='group')
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        if mp_select in forecasts and forecasts[mp_select] is not None:
            fc = forecasts[mp_select]
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=fc['ds'], y=fc['yhat'], name='Prévision', line=dict(color='orange')))
            fig2.add_trace(go.Scatter(x=fc['ds'], y=fc['yhat_upper'], fill=None, line=dict(color='lightgray'), showlegend=False))
            fig2.add_trace(go.Scatter(x=fc['ds'], y=fc['yhat_lower'], fill='tonexty', line=dict(color='lightgray'), name='Intervalle'))
            fig2.update_layout(title=f"Prévision Conso {mp_select} - 60j")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info(f"Pas assez de données pour forecast {mp_select}")

with tab4:
    st.subheader("💬 Chat IA - Pose tes questions")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Sowlni 3la data dyalk..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        prompt_lower = prompt.lower()
        response = ""

        if any(x in prompt_lower for x in ["combien", "ch7al", "khssni"]):
            for mp in df_result['Code_MP'].unique():
                if mp.lower() in prompt_lower:
                    row = df_result[df_result['Code_MP'] == mp].iloc[0]
                    response = f"**{mp}**: Stock = {row['Stock']:,.0f} kg | Besoin Total = {row['Besoin_MRP']+row['Conso_30j']:,.0f} kg | **Écart = {row['Écart']:,.0f} kg** | Statut: {row['Statut']}\n\n**Action:** {row['Action']}"
                    break
            if not response:
                response = "**MPs disponibles:** " + ", ".join(df_result['Code_MP'].tolist())

        elif "fournisseur" in prompt_lower or "a7ssan" in prompt_lower:
            if len(df_result[df_result['Score_Fourni'] > 0]) > 0:
                top_fourni = df_result.nlargest(1, 'Score_Fourni').iloc[0]
                response = f"**A7ssan fournisseur:** {top_fourni['Fournisseur']} | Score: {top_fourni['Score_Fourni']:.1f}/100\n\n**Top 3:**\n"
                for i, row in df_result.nlargest(3, 'Score_Fourni').iterrows():
                    response += f"{i+1}. {row['Fournisseur']} - {row['Code_MP']} - Score {row['Score_Fourni']:.1f}\n"
            else:
                response = "Ma kaynach data fournisseurs mziana. Vérifier feuille Fournisseurs."

        elif "risque" in prompt_lower or "rupture" in prompt_lower:
            critiques = df_result[df_result['Statut'].str.contains('CRITIQUE')]
            if len(critiques) > 0:
                response = f"⚠️ **{len(critiques)} MPs en RUPTURE CRITIQUE:**\n\n"
                for _, row in critiques.iterrows():
                    response += f"- **{row['Code_MP']}**: Écart {row['Écart']:,.0f} kg | Couv {row['Couverture_J']:.0f}j | {row['Action']}\n"
            else:
                response = "✅ 7ta risque de rupture critique daba!"

        else:
            response = f"**Jrb:**\n- 'Ch7al khssni mn MP_PP?'\n- 'Chkon a7ssan fournisseur?'\n- 'Wach kayn risque?'\n\n**MPs:** {', '.join(df_result['Code_MP'].tolist())}"

        with st.chat_message("assistant"):
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
