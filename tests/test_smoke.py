import requests


def test_backend_health(backend_ready, backend_url):
    response = requests.get(f"{backend_url}/health", timeout=5)
    assert response.status_code == 200
