from app.rag.ollama_client import parse_chat_response, parse_embedding_response


def test_parse_embedding_response_primary_shape():
    payload = {"embedding": [0.1, 0.2, 0.3]}
    assert parse_embedding_response(payload) == [0.1, 0.2, 0.3]


def test_parse_embedding_response_openai_like_shape():
    payload = {"data": [{"embedding": [1, 2]}]}
    assert parse_embedding_response(payload) == [1.0, 2.0]


def test_parse_chat_response_ollama_shape():
    payload = {"message": {"role": "assistant", "content": "Answer"}}
    assert parse_chat_response(payload) == "Answer"


def test_parse_chat_response_response_shape():
    payload = {"response": "Answer from generate endpoint"}
    assert parse_chat_response(payload) == "Answer from generate endpoint"
