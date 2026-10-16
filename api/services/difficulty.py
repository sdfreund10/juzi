from api.models import Learner

DIFFICULTY_LEVEL = Learner.ProficiencyLevel.values

DIFFICULTY_HSK_LEVEL_MAP: dict[str, tuple[int, ...]] = {
    Learner.ProficiencyLevel.NOVICE: (1, 2),
    Learner.ProficiencyLevel.INTERMEDIATE: (3, 4),
    Learner.ProficiencyLevel.ADVANCED: (5, 6),
    Learner.ProficiencyLevel.EXPERT: (7,),
}

KNOWN_DIFFICULTIES = frozenset(DIFFICULTY_LEVEL)


def hsk_levels_for_proficiency(proficiency: str) -> tuple[int, ...]:
    return DIFFICULTY_HSK_LEVEL_MAP[proficiency]


def hsk_levels_for_difficulties(difficulties: list[str]) -> set[int]:
    levels: set[int] = set()
    for key in difficulties:
        levels.update(hsk_levels_for_proficiency(key))
    return levels
