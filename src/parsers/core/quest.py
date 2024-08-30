import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import pytz
from app.schemas.common import Region
from app.schemas.gameenums import (
    QUEST_CONSUME_TYPE_NAME,
    NiceGiftType,
    NiceQuestAfterClearType,
    NiceQuestFlag,
    NiceQuestType,
)
from app.schemas.nice import NiceGift, NiceQuest, NiceQuestPhase
from app.schemas.raw import MstQuestPhase, MstQuestPhaseDetail

from ...config import PayloadSetting, settings
from ...schemas.common import NEVER_CLOSED_TIMESTAMP, MstQuestPhaseBasic
from ...schemas.data import GUARANTEED_RARE_COPY_ENEMY_WARS, RANDOM_ENEMY_QUESTS
from ...schemas.drop_data import DropData, QuestDropData
from ...schemas.gamedata import MasterData
from ...utils import SECS_PER_DAY, AtlasApi
from ...utils.helper import parse_json_file_as, sort_dict
from ...utils.log import logger
from ...utils.worker import Worker
from ...wiki.wiki_tool import KnownTimeZone
from ..helper import is_quest_in_expired_wars


@dataclass
class _QuestParser:
    jp_data: MasterData
    payload: PayloadSetting
    prev_data: DropData | None

    def parse(self):
        logger.info("processing quest data")
        self._now = int(time.time())
        self.used_prev: set[int] = set()

        worker = Worker("quest")

        for war in self.jp_data.nice_war:
            # if war.id == 9999:  # Chaldea Gate
            #     for spot in war.spots:
            #         spot.quests = [
            #             q
            #             for q in spot.quests
            #             if q.id in self.jp_data.remainedQuestIds
            #             or q.closedAt > self._now
            #         ]
            if war.id == 1002:  # 曜日クエスト
                # remove closed quests
                for spot in war.spots:
                    spot.quests = [
                        q
                        for q in spot.quests
                        if (
                            q.closedAt > NEVER_CLOSED_TIMESTAMP
                            and q.afterClear == NiceQuestAfterClearType.repeatLast
                        )
                    ]
            for _quest in [q for spot in war.spots for q in spot.quests]:
                if not _quest.phases:
                    continue
                # main story free quests
                if (
                    _quest.type == NiceQuestType.free
                    and _quest.warId < 1000
                    and _quest.afterClear == NiceQuestAfterClearType.repeatLast
                    and NiceQuestFlag.forceToNoDrop not in _quest.flags
                    and NiceQuestFlag.dropFirstTimeOnly not in _quest.flags
                ):
                    worker.add(self._save_main_free, _quest)
                    # continue
                # 宝物庫の扉を開け 初級&極級
                if _quest.warId == 1002:
                    if _quest.id in (94061636, 94061640):
                        worker.add(self._save_main_free, _quest)
                    continue
                # free drop : event free + hunting free
                # fixed drop: one-off quests, event/main story, high-diff
                add_fixed: bool = (
                    _quest.afterClear
                    in (
                        NiceQuestAfterClearType.close,
                        NiceQuestAfterClearType.resetInterval,
                        NiceQuestAfterClearType.closeDisp,
                    )
                    or NiceQuestFlag.dropFirstTimeOnly in _quest.flags
                )
                add_free: bool = (
                    not add_fixed
                    and _quest.afterClear == NiceQuestAfterClearType.repeatLast
                )
                has_enemy = _quest if _quest.phasesWithEnemies else None
                if not has_enemy:
                    _quest_na = self.jp_data.all_quests_na.get(_quest.id)
                    has_enemy = (
                        _quest_na if _quest_na and _quest_na.phasesWithEnemies else None
                    )
                if not has_enemy:
                    continue
                if add_fixed:
                    worker.add(self._save_fixed_drops, _quest)
                if add_free:
                    worker.add(self._save_free_drops, _quest)

        worker.wait()
        logger.debug(
            f"used {len(self.used_prev)} quest phases' fixed drop from previous build"
        )
        logger.info("finished checking quests")

    def _save_main_free(self, quest: NiceQuest):
        phase = quest.phases[-1]
        phase_data = AtlasApi.quest_phase(
            quest.id,
            phase,
            # enemyHash=MAIN_FREE_ENEMY_HASH.get(quest.id),
            # filter_fn=_check_quest_phase_in_recent,
            expire_after=self._get_expire(quest, self.payload.main_story_quest_expire),
        )
        assert phase_data
        self.jp_data.cachedQuestPhases[quest.id * 100 + phase] = phase_data

    def _save_fixed_drops(self, quest: NiceQuest):
        """always pass jp quest to here"""
        quest_na = self.jp_data.all_quests_na.get(quest.id)
        close_at_limit = int(self._now - 3 * SECS_PER_DAY)
        open_at_limit = int(self._now - self.payload.recent_quest_expire * SECS_PER_DAY)

        def _check(closed_at: int, opened_at: int) -> bool:
            if closed_at > NEVER_CLOSED_TIMESTAMP:
                closed_at = opened_at + 30 * SECS_PER_DAY
            return closed_at > close_at_limit or opened_at > open_at_limit

        retry_jp = _check(quest.closedAt, quest.openedAt)
        retry_na = quest_na and _check(quest_na.closedAt, quest_na.openedAt)
        retry_na = False  # useless for now
        retry = (
            is_quest_in_expired_wars(quest, self.payload.expired_wars)
            or retry_jp
            or retry_na
        )

        for phase in quest.phases:
            phase_key = quest.id * 100 + phase
            prev_fixed = (
                self.prev_data.fixedDrops.get(phase_key) if self.prev_data else None
            )
            if prev_fixed and not retry:
                self.jp_data.dropData.fixedDrops[phase_key] = prev_fixed
                self.used_prev.add(phase_key)
                continue
            phase_data = None
            if phase in quest.phasesWithEnemies:
                phase_data = AtlasApi.quest_phase(
                    quest.id,
                    phase,
                    region=Region.JP,
                    expire_after=self._get_expire(quest),
                )
            elif quest_na and phase in quest_na.phasesWithEnemies:
                phase_data = AtlasApi.quest_phase(
                    quest_na.id,
                    phase,
                    region=Region.NA,
                    expire_after=self._get_expire(quest),
                )
            if not phase_data:
                continue
            phase_drops: dict[int, int] = {}
            runs = phase_data.drops[0].runs if phase_data.drops else 0
            for drop in [
                _drop
                for stage in phase_data.stages
                for enemy in stage.enemies
                for _drop in enemy.drops
            ]:
                if drop.runs < 5:
                    continue
                drop_prob = drop.dropCount / drop.runs
                if 0.95 < drop_prob < 1:
                    drop_prob = 1
                if drop.type == NiceGiftType.item and drop_prob >= 1:
                    phase_drops[drop.objectId] = (
                        phase_drops.get(drop.objectId, 0) + int(drop_prob) * drop.num
                    )
            # always add even if there is nothing dropped
            self.jp_data.dropData.fixedDrops[phase_key] = QuestDropData(
                runs=runs, items=sort_dict(phase_drops)
            )

    def _save_free_drops(self, quest: NiceQuest):
        if not quest.phases:
            return
        quest_na = self.jp_data.all_quests_na.get(quest.id)
        close_at_limit = int(self._now - 3 * SECS_PER_DAY)
        open_at_limit = int(self._now - self.payload.recent_quest_expire * SECS_PER_DAY)
        # 关闭未过3天或20天内开放
        retry_jp = quest.closedAt > close_at_limit or quest.openedAt > open_at_limit
        retry_na = quest_na and (
            quest_na.closedAt > close_at_limit or quest_na.openedAt > open_at_limit
        )
        retry = (
            is_quest_in_expired_wars(quest, self.payload.expired_wars)
            or retry_jp
            or retry_na
        )

        phase = quest.phases[-1]
        phase_key = quest.id * 100 + phase
        prev_free = self.prev_data.freeDrops.get(phase_key) if self.prev_data else None
        if prev_free and not retry:
            self.jp_data.dropData.freeDrops[phase_key] = prev_free
            self.used_prev.add(phase_key)
            return
        phase_data = None
        if phase in quest.phasesWithEnemies:
            phase_data = get_quest_phase_check_rare_enemy(
                quest, phase, Region.JP, self._get_expire(quest)
            )
        elif quest_na and phase in quest_na.phasesWithEnemies:
            phase_data = get_quest_phase_check_rare_enemy(
                quest_na, phase, Region.NA, self._get_expire(quest_na)
            )

        if not phase_data:
            return
        phase_drops: dict[int, int] = {}
        drop_groups: dict[int, int] = {}
        runs = phase_data.drops[0].runs if phase_data.drops else 0
        for drop in phase_data.drops:
            if (
                drop.runs < 5
                or not (6500 < drop.objectId < 6600 or drop.objectId // 1000000 == 94)
                or drop.type != NiceGiftType.item
            ):
                continue
            phase_drops[drop.objectId] = (
                phase_drops.get(drop.objectId, 0) + drop.num * drop.dropCount
            )
            drop_groups[drop.objectId] = (
                drop_groups.get(drop.objectId, 0) + drop.dropCount
            )
        # always add even if there is nothing dropped
        self.jp_data.dropData.freeDrops[phase_key] = QuestDropData(
            runs=runs, items=sort_dict(phase_drops), groups=sort_dict(drop_groups)
        )

    def _get_expire(
        self, quest: NiceQuest, cache_days: int | None = None
    ) -> int | None:
        if is_quest_in_expired_wars(quest, self.payload.expired_wars):
            return 0
        close_limit = self._now - 3 * SECS_PER_DAY
        if close_limit < quest.closedAt < NEVER_CLOSED_TIMESTAMP:
            return 0
        recent_expire = self.payload.recent_quest_expire
        if quest.id in RANDOM_ENEMY_QUESTS:
            recent_expire = recent_expire // 3
        open_limit = self._now - recent_expire * SECS_PER_DAY
        if quest.openedAt > open_limit:
            return 0
        if cache_days is not None:
            return cache_days * SECS_PER_DAY
        return None


def parse_quest_drops(jp_data: MasterData, payload: PayloadSetting):
    """
    1. add main story's free quests + QP quest(初级+极级)' phase data to game_data.questPhases
    2. count each war's one-off questPhase's fixed drop
    3. count event free quests' normal item drop
    """
    if payload.skip_quests and settings.is_debug:
        logger.warning("[debug] skip checking quests data")
        return
    fp = settings.output_dist / "dropData.json"
    if payload.use_prev_drops and fp.exists():
        prev_data = parse_json_file_as(DropData, fp)
    else:
        prev_data = None

    parser = _QuestParser(jp_data, payload, prev_data)
    parser.parse()


def get_quest_phase_check_rare_enemy(
    quest: NiceQuest,
    phase: int,
    region: Region,
    expire_after,
) -> NiceQuestPhase | None:
    phase_data = AtlasApi.quest_phase(
        quest.id,
        phase,
        region=region,
        expire_after=expire_after,
    )
    if phase_data and has_guaranteed_rare_enemy(phase_data):
        phase_data2 = AtlasApi.quest_phase(
            quest.id,
            phase,
            region=region,
            enemyHash=phase_data.availableEnemyHashes[-1],
            expire_after=expire_after,
        )
        if (
            phase_data2
            and phase_data2.drops
            and phase_data.drops
            and phase_data.drops[0].runs / phase_data2.drops[0].runs < 3
        ):
            phase_data = phase_data2
    return phase_data


def has_guaranteed_rare_enemy(quest: NiceQuestPhase) -> bool:
    if quest.warId not in GUARANTEED_RARE_COPY_ENEMY_WARS:
        return False
    if quest.drops and 1 < len(quest.availableEnemyHashes) < 20:
        for stage in quest.stages:
            for enemy in stage.enemies:
                if enemy.infoScript.isAddition or enemy.enemyScript.probability_type:
                    return True
    return False


def get_quest_phase_basic(
    quests: dict[int, NiceQuest],
    quest_phase_list: list[MstQuestPhase],
    phase_detail_list: list[MstQuestPhaseDetail],
) -> list[list[MstQuestPhaseBasic]]:
    detail_dict = {
        detail.questId * 100 + detail.phase: detail for detail in phase_detail_list
    }

    def _get_basic(
        quest_phase: MstQuestPhase,
        quest: NiceQuest,
        detail: MstQuestPhaseDetail | None,
    ):
        return MstQuestPhaseBasic(
            questId=quest_phase.questId,
            phase=quest_phase.phase,
            classIds=quest_phase.classIds,
            qp=quest_phase.qp,
            exp=quest_phase.playerExp,
            bond=quest_phase.friendshipExp,
            giftId=quest_phase.giftId,
            gifts=(
                []
                if quest_phase.giftId in (0, 448)
                else AtlasApi.api_model(
                    f"/nice/gift/{quest_phase.giftId}", list[NiceGift]
                )
                or []
            ),
            spotId=(
                detail.spotId if detail and detail.spotId != quest.spotId else None
            ),
            consumeType=(
                detail.consumeType
                if detail
                and QUEST_CONSUME_TYPE_NAME[detail.consumeType] != quest.consumeType
                else None
            ),
            actConsume=(
                detail.actConsume
                if detail and detail.actConsume != quest.consume
                else None
            ),
            recommendLv=(
                detail.recommendLv
                if detail and detail.recommendLv != quest.recommendLv
                else None
            ),
        )

    groups: dict[int, list[MstQuestPhaseBasic]] = defaultdict(list)
    quest_phase_list = [v for v in quest_phase_list if v.questId in quests]
    quest_phase_list.sort(key=lambda v: quests[v.questId].openedAt)
    for quest_phase in quest_phase_list:
        quest = quests[quest_phase.questId]
        openAt = datetime.fromtimestamp(
            quest.openedAt, pytz.timezone(KnownTimeZone.jst)
        )
        # 2015-2018, 2019-2022, 2023-2026
        group_key = (openAt.year + 1) // 4
        groups[group_key].append(
            _get_basic(
                quest_phase,
                quest,
                detail_dict.get(quest_phase.questId * 100 + quest_phase.phase),
            )
        )
    return list(groups.values())
