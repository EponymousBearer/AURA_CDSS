from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_v2_model_info_includes_current_model_inventory():
    response = client.get('/api/v2/model-info')

    assert response.status_code == 200
    body = response.json()

    assert body['model_type'] == 'RandomForest (ARMD)'
    assert body['n_antibiotics'] == 32
    assert body['n_features'] >= 40
    assert body['best_threshold'] == 0.23
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
    assert tuned_result['roc_auc'] == 0.844789
    assert tuned_result['recall_1'] == 0.994838
    assert tuned_result['f1_1'] == 0.918071

    top_features = body['top_feature_importances']
    assert top_features[0]['feature'] == 'antibiotic'
    assert top_features[0]['importance'] > 0.5
    assert body['feature_groups']['categorical'] == [
        'culture_description',
        'organism',
        'antibiotic',
        'gender',
    ]


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
