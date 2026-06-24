from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = ("admin", "secret")


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_conversations():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/conversations"


def test_conversations_requires_auth():
    response = client.get("/conversations")
    assert response.status_code == 401


@patch("app.main.templates.TemplateResponse")
def test_conversations_with_auth(mock_template_response):
    from starlette.responses import HTMLResponse

    mock_template_response.return_value = HTMLResponse("<html>Conversations</html>")

    with patch("app.main.ChatSessionLocal") as mock_session_local:
        session = mock_session_local.return_value
        query = session.query.return_value
        query.count.return_value = 0
        query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        response = client.get("/conversations", auth=AUTH)
        assert response.status_code == 200
        assert "Conversations" in response.text


def test_api_conversations_requires_auth():
    response = client.get("/api/conversations")
    assert response.status_code == 401


def test_api_conversations_with_auth():
    with patch("app.main.ChatSessionLocal") as mock_session_local:
        session = mock_session_local.return_value
        query = session.query.return_value
        query.count.return_value = 0
        query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        response = client.get("/api/conversations", auth=AUTH)
        assert response.status_code == 200
        payload = response.json()
        assert payload["items"] == []
        assert payload["total"] == 0


@patch("app.main.send_message")
@patch("app.main.llm_sales_reply", return_value="Respuesta demo")
def test_message_text_flow(mock_llm, mock_send):
    with patch("app.main.ChatSessionLocal"), patch("app.main.CatalogSessionLocal"):
        response = client.post(
            "/message",
            data={"Body": "hola", "From": "whatsapp:+15550001111", "To": "whatsapp:+15550002222"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_llm.assert_called_once()
        mock_send.assert_called_once()


def test_message_rejects_large_body():
    large_body = "x" * (1_048_576 + 1)
    response = client.post(
        "/message",
        data={"Body": large_body, "From": "whatsapp:+1", "To": "whatsapp:+2"},
        headers={"Content-Length": str(len(large_body) + 50)},
    )
    assert response.status_code == 413