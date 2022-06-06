from pydantic import BaseModel, Field


class DropRateSheet(BaseModel):
    itemIds: list[int] = []
    questIds: list[int] = []
    apCosts: list[int] = []
    runs: list[int] = []
    bonds: list[int] = []
    exps: list[int] = []
    sparseMatrix: dict[int, dict[int, float]] = {}


class DropRateData(BaseModel):
    updatedAt: int
    newData: DropRateSheet
    legacyData: DropRateSheet
