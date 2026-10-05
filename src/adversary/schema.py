from typing import Literal

from pydantic import BaseModel, Field


class Challenge(BaseModel):
    claim: str = Field(..., description="What is wrong, stated as a falsifiable claim")
    evidence: str = Field(..., description="Exact quote from the input that the claim rests on")
    why_it_matters: str = Field(..., description="The concrete consequence if the claim is true")
    refutation_test: str = Field(..., description="A quick concrete check that would prove this claim wrong")
    severity: Literal["fatal", "serious", "worth-checking"]


class AdversaryReport(BaseModel):
    strongest_objection: str = Field(
        ..., description="The single argument that, if true, means this should not proceed as-is"
    )
    unexamined_assumption: str = Field(
        ..., description="The assumption the author seems not to have noticed they are making"
    )
    challenges: list[Challenge] = Field(..., description="At most 5, most severe first")
    better_alternative: str = Field(
        ...,
        description="What should have been built or proposed instead, or 'none -- approach holds' with one sentence of why",
    )


class Ruling(BaseModel):
    challenge: int = Field(..., description="1-based index of the challenge being ruled on")
    verdict: Literal["concede", "hold", "escalate"]
    reasoning: str = Field(
        ...,
        description="concede: what evidence convinced you. hold: what the response failed to address. escalate: the bigger problem the response revealed",
    )


class RebuttalReport(BaseModel):
    rulings: list[Ruling]
    remaining_objection: str = Field(
        ..., description="What still stands after the rebuttal, or 'nothing -- conceded' if every challenge fell"
    )
