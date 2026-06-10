import httpx
import pytest

from kaxanuk.data_curator.data_providers import DataProviderInterface, FinancialModelingPrep
from kaxanuk.data_curator.exceptions import (
    ApiEndpointError,
    DataProviderPaymentError,
    IdentifierNotFoundError,
)


@pytest.fixture
def _reset_http_client():
    DataProviderInterface._close_http_client()
    yield
    DataProviderInterface._close_http_client()


def _install_mock_client(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    DataProviderInterface._http_client = client
    return client


@pytest.mark.usefixtures('_reset_http_client')
class TestRequestData:
    def test_returns_response_body_on_success(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, text='[{"a": 1}]')

        _install_mock_client(handler)
        result = DataProviderInterface._request_data(
            'TEST_ENDPOINT',
            'https://example.com/endpoint',
            'AAPL',
            {'apikey': 'x', 'symbol': 'AAPL'},
        )
        assert result == '[{"a": 1}]'
        assert len(calls) == 1
        assert calls[0].url.params['symbol'] == 'AAPL'

    def test_retries_server_error_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(DataProviderInterface, '_REQUEST_RETRY_TIME', 0)
        responses = [httpx.Response(500), httpx.Response(200, text='data')]

        def handler(request):
            return responses.pop(0)

        _install_mock_client(handler)
        result = DataProviderInterface._request_data(
            'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
        )
        assert result == 'data'

    def test_exhausted_retries_raise_api_endpoint_error(self, monkeypatch):
        monkeypatch.setattr(DataProviderInterface, '_REQUEST_RETRY_TIME', 0)
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(500)

        _install_mock_client(handler)
        with pytest.raises(ApiEndpointError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
            )
        # existing behavior: raises on attempt _MAX_CONNECTION_RETRIES - 1
        assert len(calls) == DataProviderInterface._MAX_CONNECTION_RETRIES - 1

    def test_transport_errors_retried_then_raise(self, monkeypatch):
        monkeypatch.setattr(DataProviderInterface, '_REQUEST_RETRY_TIME', 0)

        def handler(request):
            error_message = 'connection refused'
            raise httpx.ConnectError(error_message, request=request)

        _install_mock_client(handler)
        with pytest.raises(ApiEndpointError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
            )

    def test_not_found_with_no_data_message_raises_identifier_not_found(self):
        def handler(request):
            return httpx.Response(404, text='No data found for this symbol')

        _install_mock_client(handler)
        with pytest.raises(IdentifierNotFoundError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'NOPE', {},
            )

    def test_not_found_without_no_data_message_raises_api_endpoint_error(self):
        def handler(request):
            return httpx.Response(404, text='gone')

        _install_mock_client(handler)
        with pytest.raises(ApiEndpointError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'NOPE', {},
            )

    def test_payment_required_raises_payment_error_with_body(self):
        def handler(request):
            return httpx.Response(402, text='please upgrade your plan')

        _install_mock_client(handler)
        with pytest.raises(DataProviderPaymentError, match='please upgrade your plan'):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
            )

    def test_client_error_raises_api_endpoint_error_without_retry(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(403, text='forbidden')

        _install_mock_client(handler)
        with pytest.raises(ApiEndpointError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
            )
        assert len(calls) == 1

    def test_http_client_is_shared_across_provider_classes(self):
        client_a = DataProviderInterface._get_http_client()
        client_b = FinancialModelingPrep._get_http_client()
        assert client_a is client_b
