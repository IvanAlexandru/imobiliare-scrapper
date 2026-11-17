import httpx
import pytest
from apartment_scraper.email_sender import rejection_reason, send
from apartment_scraper.http import Client, AccessError
from apartment_scraper.config import load


@pytest.mark.parametrize('status,body,expected', [
    (403, {'name': 'validation_error', 'message': 'You can only send testing emails to your own email address private@example.org'}, 'test mode'),
    (403, {'name': 'validation_error', 'message': 'The sender domain is not verified'}, 'Verify the sender domain'),
    (401, {'name': 'invalid_api_key', 'message': 'secret-value'}, 'RESEND_API_KEY'),
    (429, {'name': 'rate_limit_exceeded'}, 'quota'),
    (422, {'name': 'validation_error'}, 'valid email'),
    (500, {'name': 'unexpected-private-value'}, 'dashboard'),
    (403, ['private@example.org'], 'key permissions'),
])
def test_safe_rejection(status, body, expected):
    reason = rejection_reason(httpx.Response(status, json=body))
    assert f'HTTP {status}' in reason and expected in reason
    assert 'private@example.org' not in reason and 'secret-value' not in reason
    assert 'unexpected-private-value' not in reason


def test_non_json_rejection():
    assert 'HTTP 502' in rejection_reason(httpx.Response(502, text='<html>error</html>'))


def test_invalid_success_and_whitespace(monkeypatch):
    for k in ('RESEND_API_KEY', 'REPORT_EMAIL_TO', 'REPORT_EMAIL_FROM'):
        monkeypatch.setenv(k, ' value ')
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json=[])
    monkeypatch.setattr('apartment_scraper.email_sender.httpx.post', post)
    with pytest.raises(RuntimeError, match='invalid success response'):
        send('subject', 'html', 'text')
    assert calls[0]['json']['to'] == ['value']
    assert len(calls) == 1


def test_redirect_diagnostic_redacts_credentials(monkeypatch):
    def handler(req):
        return httpx.Response(301, headers={'Location': 'https://user:password@www.storia.ro/ro/oferta/private-slug?token=secret#fragment'})
    original = httpx.Client
    monkeypatch.setattr('apartment_scraper.http.httpx.Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr('apartment_scraper.http.time.sleep', lambda _: None)
    c = Client('www.storia.ro', load()['http'])
    try:
        with pytest.raises(AccessError) as e:
            c.raw('https://www.storia.ro/ro/oferta/example')
        message = str(e.value)
        assert 'HTTP 301' in message and 'www.storia.ro/ro/oferta/[redacted]' in message
        assert all(word not in message for word in ('password', 'token', 'secret', 'private-slug'))
    finally:
        c.close()
