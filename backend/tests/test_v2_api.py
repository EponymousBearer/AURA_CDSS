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

    assert dosage['model_type'] == 'Hybrid lookup + RandomForest fallback'
    assert dosage['available'] is True
    assert dosage['lookup_entries'] > 0
    assert dosage['fallback_antibiotics'] == 32


def test_v2_organisms_endpoint_filters_by_culture_site():
    response = client.get('/api/v2/organisms', params={'culture_description': 'urine'})

    assert response.status_code == 200
    body = response.json()
    assert body['culture_description'] == 'urine'
    assert 'urine' in body['culture_sites']
    assert 'escherichia coli' in body['organisms']
    assert 'other' in body['organisms']


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
