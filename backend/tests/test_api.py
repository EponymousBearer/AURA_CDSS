from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'healthy', 'service': 'antibiotic-ai-cdss'}


def test_recommend_valid_request():
    payload = {
        'organism': 'E. coli',
        'age': 65,
        'gender': 'F',
        'kidney_function': 'normal',
        'severity': 'medium',
    }

    response = client.post('/api/v1/recommend', json=payload)

    assert response.status_code == 200
    body = response.json()
    assert 'recommendations' in body
    assert len(body['recommendations']) == 3
    assert 'all_predictions' in body
    assert len(body['all_predictions']) >= 5


def test_recommend_invalid_organism():
    payload = {
        'organism': 'unknown',
        'age': 65,
        'gender': 'F',
        'kidney_function': 'normal',
        'severity': 'medium',
    }

    response = client.post('/api/v1/recommend', json=payload)

    assert response.status_code == 422


def test_recommend_invalid_age():
    payload = {
        'organism': 'E. coli',
        'age': 200,
        'gender': 'F',
        'kidney_function': 'normal',
        'severity': 'medium',
    }

    response = client.post('/api/v1/recommend', json=payload)

    assert response.status_code in {400, 422}


def test_organisms_endpoint():
    response = client.get('/api/v1/organisms')

    assert response.status_code == 200
    body = response.json()
    assert 'organisms' in body
    assert isinstance(body['organisms'], list)
    assert len(body['organisms']) > 0