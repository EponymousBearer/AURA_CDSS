from app.services.predictor import PredictionService


def test_predictor_loads():
    service = PredictionService()

    assert service is not None
    assert isinstance(service.antibiotic_list, list)


def test_predict_returns_dict():
    service = PredictionService()

    predictions = service.predict(
        organism='E. coli',
        age=65,
        gender='F',
        kidney_function='normal',
        severity='medium',
    )

    assert isinstance(predictions, dict)
    assert len(predictions) >= 5


def test_rank_antibiotics():
    service = PredictionService()
    predictions = {
        'Ceftriaxone': 0.91,
        'Ciprofloxacin': 0.88,
        'Meropenem': 0.84,
        'Vancomycin': 0.40,
        'Linezolid': 0.35,
    }

    ranked = service.rank_antibiotics(predictions, organism='E. coli', top_k=3)

    assert isinstance(ranked, list)
    assert len(ranked) == 3
    assert all(isinstance(item, tuple) and len(item) == 2 for item in ranked)


def test_organism_compatibility():
    service = PredictionService()

    good_score = service._organism_compatibility('E. coli', 'Ceftriaxone')
    bad_score = service._organism_compatibility('E. coli', 'Vancomycin')

    assert good_score == 1.0
    assert bad_score < 1.0