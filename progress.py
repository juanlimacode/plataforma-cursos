"""Server-side calculation for XP, levels, module completion, and reversible achievements."""

from typing import Any


def _compare(value: int | float, operator: str, target: int | float) -> bool:
    if operator == ">=":
        return value >= target
    if operator == ">":
        return value > target
    if operator == "==":
        return value == target
    if operator == "<=":
        return value <= target
    if operator == "<":
        return value < target
    return False


def compute_course_stats(course_data: dict[str, Any], completed_units: list[str]) -> dict[str, Any]:
    """Compute XP, level, module/unit counts, and reversible trophies for a course."""
    completed_set = set(completed_units)
    valid_unit_ids: set[str] = set()

    total_xp_float = 0.0
    total_possible_xp = 0
    total_units_count = 0
    completed_units_count = 0
    total_modules_count = 0
    completed_modules_count = 0
    completed_module_ids: list[str] = []

    for path in course_data.get("paths", []):
        for module in path.get("courses", []):
            total_modules_count += 1
            units = module.get("units", [])
            unit_count = len(units)
            module_xp = int(module.get("xp", 0))
            total_possible_xp += module_xp

            if unit_count == 0:
                continue

            xp_per_unit = module_xp / unit_count
            done_in_module = 0

            for u in units:
                uid = u["id"]
                valid_unit_ids.add(uid)
                total_units_count += 1
                if uid in completed_set:
                    completed_units_count += 1
                    done_in_module += 1
                    total_xp_float += xp_per_unit

            if done_in_module == unit_count:
                completed_modules_count += 1
                completed_module_ids.append(module["id"])

    total_xp = round(total_xp_float)
    level_interval = int(course_data.get("xp_level_interval", 600) or 600)
    level = max(1, (total_xp // level_interval) + 1)
    percent = round((completed_units_count / total_units_count) * 100) if total_units_count > 0 else 0

    trophies_status: list[dict[str, Any]] = []
    unlocked_trophy_ids: list[str] = []

    for trophy in course_data.get("trophies", []):
        t_type = trophy.get("type", "unidades_concluidas")
        op = trophy.get("operator", ">=")
        meta = int(trophy.get("meta", 1))

        if t_type == "unidades_concluidas":
            unlocked = _compare(completed_units_count, op, meta)
        elif t_type == "modulos_concluidos":
            unlocked = _compare(completed_modules_count, op, meta)
        elif t_type == "modulos_especificos_concluidos":
            req_modules = trophy.get("modules", [])
            unlocked = bool(req_modules) and all(mid in completed_module_ids for mid in req_modules)
        elif t_type == "xp_total":
            unlocked = _compare(total_xp, op, meta)
        elif t_type == "percentual_conclusao":
            unlocked = _compare(percent, op, meta)
        else:
            unlocked = False

        if unlocked:
            unlocked_trophy_ids.append(trophy["id"])

        trophies_status.append({**trophy, "unlocked": unlocked})

    # Keep only valid unit IDs in deterministic order
    clean_completed = [uid for uid in completed_units if uid in valid_unit_ids]

    return {
        "completedUnits": clean_completed,
        "totalXp": total_xp,
        "totalPossibleXp": total_possible_xp,
        "level": level,
        "percent": percent,
        "completedUnitsCount": completed_units_count,
        "totalUnitsCount": total_units_count,
        "completedModulesCount": completed_modules_count,
        "totalModulesCount": total_modules_count,
        "completedModuleIds": completed_module_ids,
        "unlockedTrophies": unlocked_trophy_ids,
        "trophies": trophies_status,
    }
