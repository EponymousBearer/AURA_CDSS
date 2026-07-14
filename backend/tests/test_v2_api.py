from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_v2_model_info_includes_current_model_inventory():
    response = client.get('/api/v2/model-info')

    assert response.status_code == 200
    body = response.json()

    assert body['model_type'] == 'RandomForest (ARMD)'
    assert body['n_antibiotics'] == 32
    # 4 categorical + 5 numeric (age + 4 labs) + binary flags
    assert body['n_features'] >= 44
    # threshold now chosen by the 'balanced' policy; sanity-check the range
    assert 0.0 < body['best_threshold'] < 1.0
    assert body['available'] is True
    assert len(body['antibiotics']) == 32
    assert 'meropenem' in body['antibiotics']
    assert 'recommendation' in body['models']
    assert 'dosage' in body['models']


def test_v2_model_info_exposes_test_results_and_features():
    response = client.get('/api/v2/model-info')

    assert response.status_code == 200
    body = response.json()

    tuned_result = next(
        row for row in body['test_summary']
        if row['threshold'] == body['best_threshold']
    )
    # Metrics depend on the retrained, patient-grouped model — assert sane ranges
    # rather than exact values so the suite isn't brittle to re-training.
    assert 0.6 < tuned_result['roc_auc'] <= 1.0
    assert 0.0 < tuned_result['recall_1'] <= 1.0
    assert 0.0 < tuned_result['f1_1'] <= 1.0

    top_features = body['top_feature_importances']
    feature_names = [f['feature'] for f in top_features]
    # 'antibiotic' remains a dominant signal (one-hot names look like '...antibiotic_meropenem')
    assert any('antibiotic' in f for f in feature_names)
    assert top_features[0]['importance'] > 0.0
    assert body['feature_groups']['categorical'] == [
        'culture_description',
        'organism',
        'antibiotic',
        'gender',
    ]
    # Labs are now active numeric features (fix: column-name mismatch corrected)
    numeric = set(body['feature_groups']['numeric'])
    assert {'age', 'wbc_median', 'cr_median', 'lactate_median', 'procalcitonin_median'}.issubset(numeric)


def test_v2_model_info_exposes_dosage_model_status():
    response = client.get('/api/v2/model-info')

    assert response.status_code == 200
    dosage = response.json()['dosage_model']

    # M5 reframe: dosage is a guideline reference, NOT validated dosing; ML tier retired.
    assert dosage['model_type'] == 'Guideline dose reference (lookup table + static defaults)'
    assert dosage['validated'] is False
    assert dosage['available'] is True
    assert dosage['lookup_entries'] > 0
    assert dosage['fallback_antibiotics'] >= 32  # expanded with Pakistan-locale agents
    assert 'disclaimer' in dosage and 'not' in dosage['disclaimer'].lower()


def test_v2_organisms_endpoint_filters_by_culture_site():
    response = client.get('/api/v2/organisms', params={'culture_description': 'urine'})

    assert response.status_code == 200
    body = response.json()
    assert body['culture_description'] == 'urine'
    assert 'urine' in body['culture_sites']
    assert 'escherichia coli' in body['organisms']
    assert 'other' in body['organisms']


def test_v2_locales_lists_us_and_pakistan():
    response = client.get('/api/v2/locales')

    assert response.status_code == 200
    body = response.json()
    assert body['default'] == 'us_armd'
    ids = {loc['id'] for loc in body['locales']}
    assert {'us_armd', 'pakistan'}.issubset(ids)

    pakistan = next(loc for loc in body['locales'] if loc['id'] == 'pakistan')
    assert pakistan['basis'] == 'antibiogram'
    by_name = {o['name']: o for o in pakistan['organisms']}
    # organisms with real cited data are usable; all-`unknown` ones are flagged pending
    assert by_name['salmonella typhi']['has_data'] is True
    assert by_name['escherichia coli']['has_data'] is True
    assert by_name['acinetobacter baumannii']['has_data'] is False


def test_v2_model_info_includes_evaluation_and_contrast():
    body = client.get('/api/v2/model-info').json()

    # M1 evaluation block surfaced for the dashboard
    ev = body['evaluation']
    assert ev['pooled']['rf_roc_auc'] > 0.6
    assert ev['within_cell']['median_rf_cell_auc'] > 0.5
    assert ev['calibration']['served_method'] == 'isotonic'
    assert any(f['file'] == 'organism_drug_auc_heatmap.png' for f in ev['figures'])

    # US-vs-PK contrast: XDR typhoid ceftriaxone must be gated for Pakistan
    rows = body['us_vs_pk_contrast']['rows']
    typhoid_cro = next(
        r for r in rows if r['organism'] == 'salmonella typhi' and r['drug'] == 'ceftriaxone'
    )
    assert typhoid_cro['pk_gated'] is True


def test_v2_recommend_pakistan_typhoid_gates_ceftriaxone():
    payload = {
        'culture_description': 'blood',
        'organism': 'salmonella typhi',
        'age': 25,
        'gender': 'male',
        'ward': 'general',
        'locale': 'pakistan',
    }
    body = client.post('/api/v2/recommend', json=payload).json()

    assert body['locale'] == 'pakistan'
    assert body['basis'] == 'antibiogram'
    picks = [r['antibiotic'] for r in body['recommendations']]
    assert 'ceftriaxone' not in picks
    assert 'azithromycin' in picks  # last reliable oral option locally
    assert body['excluded'].get('ceftriaxone') == 'gated_do_not_use'
    assert body['dose_disclaimer']
    # antibiogram picks carry provenance
    assert body['recommendations'][0]['basis'] == 'antibiogram'


def test_v2_recommend_rejects_invalid_culture_organism_pair():
    payload = {
        'culture_description': 'urine',
        'organism': 'not a listed organism',
        'age': 45,
        'gender': 'female',
        'wbc': None,
        'cr': None,
        'lactate': None,
        'procalcitonin': None,
        'ward': 'er',
    }

    response = client.post('/api/v2/recommend', json=payload)

    assert response.status_code == 422
    assert 'Select one of the listed organisms' in response.json()['detail']


# ── M3/T3.2: prior-history inputs (no longer zeroed at inference) ──────────────

def test_v2_model_info_exposes_prior_history_options():
    body = client.get('/api/v2/model-info').json()
    opts = body['prior_history_options']
    abx = {o['value'] for o in opts['antibiotic_classes']}
    orgs = {o['value'] for o in opts['organisms']}
    # values are model column suffixes; a few well-known ones must be present
    assert {'beta_lactam', 'fluoroquinolone', 'aminoglycoside'} <= abx
    assert {'escherichia', 'pseudomonas', 'klebsiella'} <= orgs
    # every option carries a display label
    assert all(o['label'] for o in opts['antibiotic_classes'] + opts['organisms'])


def _us_ecoli_payload(**extra):
    payload = {
        'culture_description': 'urine',
        'organism': 'escherichia coli',
        'age': 60,
        'gender': 'female',
        'ward': 'general',
        'locale': 'us_armd',
    }
    payload.update(extra)
    return payload


def test_v2_recommend_prior_history_changes_scores():
    """The core M3 acceptance: supplying prior history changes the model output."""
    base = client.post('/api/v2/recommend', json=_us_ecoli_payload()).json()
    hist = client.post('/api/v2/recommend', json=_us_ecoli_payload(
        prior_abx_classes=['beta_lactam', 'fluoroquinolone'],
        prior_organisms=['escherichia'],
    )).json()

    assert base['locale'] == 'us_armd' and base['basis'] == 'model'
    base_scores = {p['antibiotic']: p['probability'] for p in base['all_predictions']}
    hist_scores = {p['antibiotic']: p['probability'] for p in hist['all_predictions']}
    # at least one candidate's probability must move once history is supplied
    moved = [a for a in base_scores if abs(base_scores[a] - hist_scores.get(a, base_scores[a])) > 1e-6]
    assert moved, 'prior history did not change any prediction — feature not wired'
    # request echoes the supplied history back in patient_factors
    assert hist['patient_factors']['prior_abx_classes'] == ['beta_lactam', 'fluoroquinolone']


def test_v2_recommend_prior_history_is_optional_and_additive():
    """Omitting history keeps the original US contract (back-compat)."""
    body = client.post('/api/v2/recommend', json=_us_ecoli_payload()).json()
    assert body['patient_factors']['prior_abx_classes'] == []
    assert body['patient_factors']['prior_organisms'] == []
    assert len(body['recommendations']) == 3


def test_v2_recommend_prior_history_ignores_unknown_tokens():
    """Unknown history values are silently ignored (robust, never 500s)."""
    resp = client.post('/api/v2/recommend', json=_us_ecoli_payload(
        prior_abx_classes=['not_a_real_class'],
        prior_organisms=['not_a_real_org'],
    ))
    assert resp.status_code == 200


# ── M3/T3.1: per-prediction TreeSHAP explanations ─────────────────────────────

def test_v2_recommend_us_path_returns_explanations(monkeypatch):
    """US model path attaches per-drug TreeSHAP factors (best-effort; skip if shap absent)."""
    import importlib.util
    if importlib.util.find_spec('shap') is None:
        import pytest
        pytest.skip('shap not installed in this environment')
    monkeypatch.setenv('ENABLE_SHAP', '1')  # force-on regardless of ENVIRONMENT

    body = client.post('/api/v2/recommend', json=_us_ecoli_payload()).json()
    rec = body['recommendations'][0]
    factors = rec.get('explanation')
    assert factors, 'expected TreeSHAP explanation on the US model path'
    top = factors[0]
    assert {'feature', 'label', 'contribution', 'direction'} <= set(top)
    assert top['direction'] in ('increases', 'decreases')
    # factors ordered by |contribution| descending
    mags = [abs(f['contribution']) for f in factors]
    assert mags == sorted(mags, reverse=True)


def test_v2_recommend_pakistan_path_has_no_model_explanation():
    """Route A (antibiogram) carries provenance, not a model explanation."""
    payload = {
        'culture_description': 'blood', 'organism': 'salmonella typhi',
        'age': 25, 'gender': 'male', 'ward': 'general', 'locale': 'pakistan',
    }
    body = client.post('/api/v2/recommend', json=payload).json()
    assert body['recommendations'][0].get('explanation') is None
