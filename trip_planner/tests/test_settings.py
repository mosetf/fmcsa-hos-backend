from core.settings import _parse_cors_allowed_origins


def test_parse_cors_allowed_origins_keeps_only_valid_origins():
    value = "http://localhost:3000,localhost,127.0.0.1,testserver,https://example.com"

    assert _parse_cors_allowed_origins(value) == [
        "http://localhost:3000",
        "https://example.com",
    ]
