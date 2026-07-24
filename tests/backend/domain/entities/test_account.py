import pytest
from pydantic import ValidationError

from src.backend.domain.entities.account import (
    AccountCreateRequest,
    AccountPatchRequest,
    Currency,
)


def make_create_request(number: str) -> AccountCreateRequest:
    return AccountCreateRequest(
        number=number,
        name="Jane Doe",
        type="TFSA",
        currency=Currency.CAD,
        tax_status="Registered",
        benchmark="SPY",
    )


@pytest.mark.parametrize("number", ["001", "ACC-001", "TFSA_2024", "a1-B2_c3"])
def test_create_request_accepts_valid_account_numbers(number):
    assert make_create_request(number).number == number


@pytest.mark.parametrize("number", ["", "ACC 001", "acc/001", "acc#1", "ACC.001"])
def test_create_request_rejects_invalid_account_numbers(number):
    with pytest.raises(ValidationError):
        make_create_request(number)


def test_patch_request_accepts_valid_number_and_none():
    assert AccountPatchRequest(number="ACC-001").number == "ACC-001"
    assert AccountPatchRequest().number is None


@pytest.mark.parametrize("number", ["", "ACC 001", "acc/001"])
def test_patch_request_rejects_invalid_account_numbers(number):
    with pytest.raises(ValidationError):
        AccountPatchRequest(number=number)
