import pytest

from kaxanuk.data_curator.data_providers import FinancialModelingPrep
from kaxanuk.data_curator.exceptions import DataProviderPaymentError


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(FinancialModelingPrep, '_is_paid_account_plan', None)
    return FinancialModelingPrep(api_key='test-key')


def _install_fake_request_data(monkeypatch, fake):
    monkeypatch.setattr(FinancialModelingPrep, '_request_data', classmethod(fake))


class TestRequestDataWithAccountPlanFallback:
    def test_payment_error_downgrades_plan_and_retries_with_free_limit(self, monkeypatch, provider):
        limits_requested = []

        def fake(cls, endpoint_id, endpoint_url, main_identifier, params):
            limits_requested.append(params['limit'])
            if params['limit'] == cls.MAX_RECORDS_DOWNLOAD_LIMIT:
                msg = 'payment required'
                raise DataProviderPaymentError(msg)
            return '[]'

        _install_fake_request_data(monkeypatch, fake)
        result = provider._request_data_with_account_plan_fallback(
            'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {'apikey': 'x'},
        )
        assert result == '[]'
        assert limits_requested == [
            FinancialModelingPrep.MAX_RECORDS_DOWNLOAD_LIMIT,
            FinancialModelingPrep.MAX_FREE_ACCOUNT_RECORDS_DOWNLOAD_LIMIT,
        ]
        assert FinancialModelingPrep._is_paid_account_plan is False

    def test_race_loser_retries_instead_of_failing(self, monkeypatch, provider):
        """A worker whose paid-limit request was in flight when another worker downgraded the plan must retry."""

        def fake(cls, endpoint_id, endpoint_url, main_identifier, params):
            if params['limit'] == cls.MAX_RECORDS_DOWNLOAD_LIMIT:
                # simulate a concurrent worker downgrading the plan while this request was in flight
                cls._is_paid_account_plan = False
                msg = 'payment required'
                raise DataProviderPaymentError(msg)
            return '[]'

        _install_fake_request_data(monkeypatch, fake)
        result = provider._request_data_with_account_plan_fallback(
            'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {'apikey': 'x'},
        )
        assert result == '[]'
        assert FinancialModelingPrep._is_paid_account_plan is False

    def test_payment_error_on_free_limit_propagates(self, monkeypatch, provider):
        monkeypatch.setattr(FinancialModelingPrep, '_is_paid_account_plan', False)

        def fake(cls, endpoint_id, endpoint_url, main_identifier, params):
            msg = 'payment required'
            raise DataProviderPaymentError(msg)

        _install_fake_request_data(monkeypatch, fake)
        with pytest.raises(DataProviderPaymentError):
            provider._request_data_with_account_plan_fallback(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {'apikey': 'x'},
            )

    def test_no_fallback_request_when_first_request_succeeds(self, monkeypatch, provider):
        calls = []

        def fake(cls, endpoint_id, endpoint_url, main_identifier, params):
            calls.append(params['limit'])
            return '[{"date": "2024-01-02"}]'

        _install_fake_request_data(monkeypatch, fake)
        result = provider._request_data_with_account_plan_fallback(
            'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {'apikey': 'x'},
        )
        assert result == '[{"date": "2024-01-02"}]'
        assert calls == [FinancialModelingPrep.MAX_RECORDS_DOWNLOAD_LIMIT]
        assert FinancialModelingPrep._is_paid_account_plan is None
