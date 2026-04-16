import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ========================================
# CONFIG - SHEET_ID DYALK
# ========================================
SHEET_ID = "1DNmM76FfZRtucCMEB-If0t1EEV-lPRn70pl9yP2ooeM"

# ========================================
# FUNCTIONS
# ========================================
def trouver_colonne(df, noms_possibles):
    """Tl9a smiya dyal colonne wakha tkoun mkhtalfa"""
    for nom in noms_possibles:
        if nom in df.columns:
            return nom
    for nom in noms_possibles:
        for col in df.columns:
            if nom.lower() in col.lower():
                return col
    return None

def to_numeric_safe(series):
    """7wl colonne l number - ila ma 9drch dir NaN"""
    return pd.to_numeric(series, errors='coerce')

@st.cache_data(ttl=300)
def charger_donnees_google():
    """9ra les 4 feuilles mn Google Sheets"""
    base_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
    try:
        param = pd.read_csv(base_url + "Param")
        conso = pd.read_csv(base_url + "Conso")
        mrp = pd.read_csv(base_url + "MRP")
        fournis = pd.read_csv(base_url + "Fournisseurs")
        return param, conso, mrp, fournis
    except Exception as e:
        st.error(f"❌ Erreur lecture Google Sheets: {e}")
        st.error("""
        **Vérifier:**
        1. **Partager** → General access → **Anyone with the link** → **Viewer** → Done
        2. Smiyat les onglets exact: **Param** **Conso** **MRP** **Fournisseurs**
        """)
        return None, None, None, None

def analyser_mrp_appro(param, conso, mrp, fournis):
    """Analyse MRP vs Appro + Prévision Prophet"""

    # Standardiser colonnes
    col_date_conso = trouver_colonne(conso, ['date', 'Date', 'DATE'])
    col_mp_conso = trouver_colonne(conso, ['code_mp', 'Code_MP', 'Code', 'MP'])
    col_qte_conso = trouver_colonne(conso, ['qte_consommee_kg', 'Qte_Consommee', 'Quantite', 'Qte'])

    col_date_mrp = trouver_colonne(mrp, ['date_besoin', 'Date_Besoin', 'Date'])
    col_mp_mrp = trouver_colonne(mrp, ['code_mp', 'Code_MP', 'Code', 'MP'])
    col_qte_mrp = trouver_colonne(mrp, ['qte_besoin_kg', 'Qte_Besoin', 'Besoin', 'Qte'])

    if not all([col_date_conso, col_mp_conso, col_qte_conso]):
        st.error("❌ Colonnes manquantes dans 'Conso'. Vérifier: date, code_mp, qte_consommee_kg")
        return pd.DataFrame()

    if not all([col_date_mrp, col_mp_mrp, col_qte_mrp]):
        st.error("❌ Colonnes manquantes dans 'MRP'. Vérifier: date_besoin, code_mp, qte_besoin_kg")
        return pd.DataFrame()

    conso = conso.rename(columns={col_date_conso: 'Date', col_mp_conso: 'Code_MP', col_qte_conso: 'Qte_Consommee'})
    mrp = mrp.rename(columns={col_date_mrp: 'Date_Besoin', col_mp_mrp: 'Code_MP', col_qte_mrp: 'Qte_Besoin'})

    # 🔥 MHM: 7WL KOLCHI L NUMÉRIQUE
    conso['Date'] = pd.to_datetime(conso['Date'], errors='coerce')
    conso['Qte_Consommee'] = to_numeric_safe(conso['Qte_Consommee'])

    mrp['Date_Besoin'] = pd.to_datetime(mrp['Date_Besoin'], errors='coerce')
    mrp['Qte_Besoin'] = to_numeric_safe(mrp['Qte_Besoin'])

    # Param aussi
    param['stock_secu_actuel'] = to_numeric_safe(param.get('stock_secu_actuel', 0))
    param['lead_time_j'] = to_numeric_safe(param.get('lead_time_j', 14))
    param['moq_kg'] = to_numeric_safe(param.get('moq_kg', 1000))
    param['cout_unitaire'] = to_numeric_safe(param.get('cout_unitaire', 0))

    # Fournisseurs
    fournis['taux_service_%'] = to_numeric_safe(fournis.get('taux_service_%', 0))
    fournis['fiabilite_%'] = to_numeric_safe(fournis.get('fiabilite_%', 0))
    fournis['note_qualite_5'] = to_numeric_safe(fournis.get('note_qualite_5', 0))
    fournis['lead_time_j'] = to_numeric_safe(fournis.get('lead_time_j', 14))

    resultats = []

    for _, mp_row in param.iterrows():
        code = mp_row['code_mp']
        stock_secu = mp_row.get('stock_secu_actuel', 0)
        lead_time = mp_row.get('lead_time_j', 14)
        moq = mp_row.get('moq_kg', 1000)

        # 1. Historique consommation
        hist = conso[conso['Code_MP'] == code].copy()
        hist = hist.dropna(subset=['Date', 'Qte_Consommee'])

        if len(hist) < 10:
            continue

        df_prophet = hist.groupby('Date')['Qte_Consommee'].sum().reset_index()
        df_prophet.columns = ['ds', 'y']
        df_prophet = df_prophet.dropna()

        if len(df_prophet) < 10:
            continue

        # 2. Prévision Prophet 30j
        try:
            m = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
            m.fit(df_prophet)
            future = m.make_future_dataframe(periods=30)
            forecast = m.predict(future)
            conso_prevue_30j = forecast[forecast['ds'] > df_prophet['ds'].max()]['yhat'].sum()
            conso_prevue_30j = max(0, conso_prevue_30j)
        except:
            conso_prevue_30j = df_prophet['y'].mean() * 30

        # 3. Besoin MRP
        besoin_mrp = mrp[mrp['Code_MP'] == code]['Qte_Besoin'].sum()
        besoin_mrp = 0 if pd.isna(besoin_mrp) else besoin_mrp

        # 4. Calcul écart
        besoin_total = besoin_mrp + conso_prevue_30j
        ecart = stock_secu - besoin_total

        if ecart < -moq:
            statut = "🔴 CRITIQUE"
            action = f"Commander {abs(ecart):,.0f} kg"
        elif ecart < 0:
            statut = "🟠 TENSION"
            action = f"Commander {moq:,.0f} kg"
        else:
            statut = "🟢 ALIGNÉ"
            action = "Pas d'action"

        # 5. Meilleur fournisseur
        fournis_mp = fournis[fournis['code_mp'] == code].copy()
        if len(fournis_mp) > 0:
            fournis_mp['score'] = (
                fournis_mp['taux_service_%'].fillna(0) * 0.4 +
                fournis_mp['fiabilite_%'].fillna(0) * 0.3 +
                fournis_mp['note_qualite_5'].fillna(0) * 20 * 0.3
            )
            best = fournis_mp.nlargest(1, 'score').iloc[0]
            fournisseur = best['nom_fournisseur']
            delai = best['lead_time_j']
        else:
            fournisseur = "N/A"
            delai = lead_time

        resultats.append({
            'Code MP': code,
            'Désignation': mp_row.get('designation', 'N/A'),
            'Stock Actuel': f"{stock_secu:,.0f}",
            'Besoin MRP': f"{besoin_mrp:,.0f}",
            'Conso Prévue 30j': f"{conso_prevue_30j:,.0f}",
            'Écart': f"{ecart:,.0f}",
            'Statut': statut,
            'Action': action,
            'Fournisseur Recommandé': fournisseur,
            'Délai': f"{delai:.0f}j" if not pd.isna(delai) else "N/A"
        })

    return pd.DataFrame(resultats)

# ========================================
# INTERFACE STREAMLIT
# ========================================
st.set_page_config(page_title="MRP vs Appro", layout="wide")
st.title("🎯 Analyse MRP vs Approvisionnement")
st.caption("Google Sheets: MRP_Analyse | 4 onglets: Param, Conso, MRP, Fournisseurs")

st.sidebar.header("⚙️ Configuration")
if st.sidebar.button("🔄 Actualiser Données Google Sheets"):
    st.cache_data.clear()
    st.rerun()

# Charger données
with st.spinner("Chargement depuis Google Sheets..."):
    param, conso, mrp, fournis = charger_donnees_google()

if param is not None and conso is not None and mrp is not None and fournis is not None:
    st.success(f"✅ {len(param)} MPs | {len(conso)} lignes conso | {len(mrp)} lignes MRP | {len(fournis)} fournisseurs")

    if st.button("🚀 Analyser MRP vs Appro", type="primary", use_container_width=True):
        with st.spinner("Analyse en cours... Prophet kay 7sseb..."):
            df_result = analyser_mrp_appro(param, conso, mrp, fournis)

        if len(df_result) > 0:
            st.subheader("📊 Résultats de l'Analyse")
            st.dataframe(df_result, use_container_width=True, height=400)

            # Stats
            col1, col2, col3, col4 = st.columns(4)
            critique = len(df_result[df_result['Statut'].str.contains('CRITIQUE')])
            tension = len(df_result[df_result['Statut'].str.contains('TENSION')])
            aligne = len(df_result[df_result['Statut'].str.contains('ALIGNÉ')])
            total = len(df_result)

            col1.metric("🔴 Critiques", critique, f"{critique/total*100:.0f}%" if total > 0 else "0%")
            col2.metric("🟠 Tensions", tension, f"{tension/total*100:.0f}%" if total > 0 else "0%")
            col3.metric("🟢 Alignés", aligne, f"{aligne/total*100:.0f}%" if total > 0 else "0%")
            col4.metric("📦 Total MPs", total)

            # Télécharger
            csv = df_result.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 Télécharger Résultats CSV",
                csv,
                f"MRP_Analyse_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True
            )
        else:
            st.warning("⚠️ Aucun résultat. Vérifier que les MPs dans Param existent dans Conso avec au moins 10 lignes d'historique.")
else:
    st.warning("⚠️ Impossible de charger les données.")
    st.info("""
    **ÉTAPES À VÉRIFIER:**

    1. **Ouvrir Google Sheet `MRP_Analyse`** → Click **Partager**
    2. **General access** → Changer l **Anyone with the link**
    3. **Viewer** → **Done**
    4. **Smiyat les onglets exact:** `Param` `Conso` `MRP` `Fournisseurs`
    5. **Refresh l'app** → Click "🔄 Actualiser"
    """)
