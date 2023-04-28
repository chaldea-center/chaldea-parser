from pydantic import BaseModel


class DropRateSheet(BaseModel):
    itemIds: list[int] = []
    questIds: list[int] = []
    apCosts: list[int] = []
    runs: list[int] = []
    bonds: list[int] = []
    exps: list[int] = []
    # <item, <quest, v>>
    sparseMatrix: dict[int, dict[int, float]] = {}

    def add_quest(self, quest_id: int, ap: int, run: int, bond: int, exp: int):
        self.questIds.append(quest_id)
        self.apCosts.append(ap)
        self.runs.append(run)
        self.bonds.append(bond)
        self.exps.append(exp)


class DomusAureaData(BaseModel):
    updatedAt: int
    newData: DropRateSheet
    legacyData: DropRateSheet


class QuestDropData(BaseModel):
    runs: int
    items: dict[int, int]
    groups: dict[int, int] = {}


class DropData(BaseModel):
    domusVer: int = 0
    domusAurea: DropRateSheet = DropRateSheet()
    freeDrops: dict[int, QuestDropData] = {}  # questId*100+phase: normal items
    fixedDrops: dict[int, QuestDropData] = {}  # questId*100+phase: normal items
