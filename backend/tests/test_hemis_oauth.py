"""Tests for the defensive parsing in app/services/hemis_oauth.py.

The real HEMIS OAuth server cannot be reached from anywhere but the production domain, so
these lock in the tolerance for the response shapes it might plausibly return.
"""

import httpx
import pytest

from afu_shared.settings import settings
from app.services.hemis_oauth import _normalize_userinfo, _parse_token_body, build_authorize_url


def _response(text: str, content_type: str) -> httpx.Response:
    return httpx.Response(
        200, text=text, headers={"content-type": content_type}, request=httpx.Request("POST", "http://x")
    )


class TestParseTokenBody:
    def test_json(self):
        resp = _response('{"access_token": "abc", "token_type": "Bearer"}', "application/json")
        assert _parse_token_body(resp)["access_token"] == "abc"

    def test_form_encoded(self):
        # Some Yii2 OAuth2 servers answer form-encoded despite an Accept: application/json header.
        resp = _response("access_token=abc&token_type=Bearer", "application/x-www-form-urlencoded")
        assert _parse_token_body(resp)["access_token"] == "abc"

    def test_form_encoded_repeated_key_kept_as_list(self):
        resp = _response("scope=a&scope=b", "application/x-www-form-urlencoded")
        assert _parse_token_body(resp)["scope"] == ["a", "b"]

    def test_json_error_body_is_still_parsed(self):
        # OAuth error bodies are more informative than the status code, so they must survive parsing.
        resp = _response('{"error": "invalid_client"}', "application/json")
        assert _parse_token_body(resp) == {"error": "invalid_client"}

    def test_html_body_yields_empty(self):
        resp = _response("<html><body>Gateway Error</body></html>", "text/html")
        assert _parse_token_body(resp) == {}


class TestNormalizeUserinfo:
    def test_plain_payload(self):
        raw = {"id": 42, "name": "TEST"}
        assert _normalize_userinfo(raw) == raw

    def test_data_envelope(self):
        # The HEMIS REST API wraps everything in {"success":..., "data":...}; assume OAuth might too.
        inner = {"id": 42, "login": "123"}
        assert _normalize_userinfo({"success": True, "data": inner}) == inner

    def test_uuid_only_payload_accepted(self):
        raw = {"uuid": "abc-def"}
        assert _normalize_userinfo(raw) == raw

    def test_payload_without_identifier_rejected(self):
        assert _normalize_userinfo({"name": "no id here"}) is None

    def test_non_dict_rejected(self):
        assert _normalize_userinfo([1, 2, 3]) is None


class TestBuildAuthorizeUrl:
    def test_contains_required_params(self):
        url = build_authorize_url(state="STATE123")
        assert "response_type=code" in url
        assert "state=STATE123" in url
        assert f"client_id={settings.employee_client_id}" in url

    def test_redirect_uri_sent_verbatim(self):
        # A mismatch here is the classic cause of invalid_request, so it must never be
        # rebuilt from the incoming request.
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(build_authorize_url(state="s")).query)
        assert query["redirect_uri"] == [settings.employee_redirect_uri]

    def test_scope_omitted_when_unset(self, monkeypatch):
        monkeypatch.setattr(settings, "employee_oauth_scope", "")
        assert "scope=" not in build_authorize_url(state="s")

    def test_scope_included_when_set(self, monkeypatch):
        monkeypatch.setattr(settings, "employee_oauth_scope", "profile")
        assert "scope=profile" in build_authorize_url(state="s")
