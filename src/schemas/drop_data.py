from pydantic import BaseModel, Field


class DropRateSheet(BaseModel):
    questIds: list[int] = Field(default_factory=list)
    itemIds: list[int] = Field(default_factory=list)
    apCosts: list[int] = Field(default_factory=list)
    runs: list[int] = Field(default_factory=list)
    sparseMatrix: dict[int, dict[int, float]] = Field(default_factory=dict)


class DropRateData(BaseModel):
    updatedAt: int
    newData: DropRateSheet
    legacyData: DropRateSheet
