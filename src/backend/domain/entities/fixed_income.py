from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FixedIncomeType(StrEnum):
    GIC = "GIC"
    TERM_DEPOSIT = "Term Deposit"


class PaymentFrequency(StrEnum):
    AT_MATURITY = "At Maturity"
    ANNUAL = "Annual"
    SEMI_ANNUAL = "Semi-Annual"
    QUARTERLY = "Quarterly"
    MONTHLY = "Monthly"


class Compounding(StrEnum):
    SIMPLE = "Simple"
    ANNUAL = "Annual"


class FixedIncomeStatus(StrEnum):
    ACTIVE = "Active"
    MATURED = "Matured"


class InstrumentTerms(BaseModel):
    """Contract terms of a fixed-rate instrument; `annual_rate` is a decimal."""

    model_config = ConfigDict(use_enum_values=True, validate_default=True)

    type: FixedIncomeType = FixedIncomeType.GIC
    name: str = ""
    issue_date: date
    maturity_date: date
    annual_rate: float = Field(ge=0.0, le=1.0)
    payment_frequency: PaymentFrequency = PaymentFrequency.AT_MATURITY
    compounding: Compounding = Compounding.SIMPLE
    redeemable: bool = False

    @model_validator(mode="after")
    def _check_terms(self) -> "InstrumentTerms":
        if self.maturity_date <= self.issue_date:
            raise ValueError("Maturity date must be after the issue date")
        if (
            self.compounding == Compounding.ANNUAL
            and self.payment_frequency != PaymentFrequency.AT_MATURITY
        ):
            raise ValueError(
                "Compounding applies only when interest is paid at maturity"
            )
        return self
