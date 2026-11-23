import re

import pytest
from django.test import override_settings

from apps.lots.choices import LotStatus
from apps.lots.qr_rules import can_have_qr, new_qr_token, public_traceability_url

WITH_QR = {LotStatus.CLASSIFIED, LotStatus.IN_WAREHOUSE}


@pytest.mark.parametrize("status", list(LotStatus))
def test_only_classified_and_stored_lots_can_have_a_qr_code(status):
    assert can_have_qr(status) is (status in WITH_QR)


def test_the_token_has_sixteen_url_safe_characters():
    token = new_qr_token()

    assert re.fullmatch(r"[A-Za-z0-9_-]{16}", token)


def test_two_tokens_are_different():
    assert len({new_qr_token() for _ in range(50)}) == 50


@pytest.mark.parametrize("base", ["https://app.example.com", "https://app.example.com/"])
def test_the_public_url_joins_the_frontend_and_the_token(base):
    with override_settings(FRONTEND_URL=base):
        url = public_traceability_url("Xq3k9Lm2Pz7tRw1a")

    assert url == "https://app.example.com/trazabilidad/Xq3k9Lm2Pz7tRw1a"
