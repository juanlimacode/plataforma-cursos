"""Parser and validator for Markdown course definitions (.md)."""

import re
from typing import Any


SAFE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

VALID_TROPHY_TYPES = {
    "unidades_concluidas",
    "modulos_concluidos",
    "modulos_especificos_concluidos",
    "xp_total",
    "percentual_conclusao",
}
VALID_OPERATORS = {">=", ">", "==", "<=", "<"}


def _unquote(val: str) -> str:
    val = val.strip()
    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
        return val[1:-1]
    return val


def _parse_value(raw: str) -> Any:
    val = raw.strip()
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_unquote(item) for item in inner.split(",") if item.strip()]
    unquoted = _unquote(val)
    if raw.strip() == unquoted and re.fullmatch(r"-?\d+", unquoted):
        return int(unquoted)
    return unquoted


def _parse_kv_line(line: str) -> tuple[str, Any] | None:
    m = re.match(r"^-\s+([a-zA-Z0-9_]+)\s*:\s*(.*)$", line.strip())
    if not m:
        return None
    return m.group(1).lower(), _parse_value(m.group(2))


def parse_course_markdown(md_text: str) -> dict[str, Any]:
    """Parse a course Markdown string into a structured dict with errors/warnings."""
    errors: list[str] = []
    warnings: list[str] = []

    if not md_text or not md_text.strip():
        return {"valid": False, "errors": ["O arquivo Markdown está vazio."], "warnings": [], "course": None}

    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    idx = 0
    meta: dict[str, Any] = {}

    # Parse optional YAML-like frontmatter
    if lines[0].strip() == "---":
        idx = 1
        while idx < len(lines) and lines[idx].strip() != "---":
            line = lines[idx].strip()
            if line and ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = _parse_value(v)
            idx += 1
        if idx >= len(lines):
            errors.append("Frontmatter '---' não foi fechado.")
        else:
            idx += 1

    paths: list[dict[str, Any]] = []
    trophies: list[dict[str, Any]] = []

    mode = "idle"  # idle | trilha | modulo | unidade | conquistas | conquista | ignored
    current_path: dict[str, Any] | None = None
    current_module: dict[str, Any] | None = None
    current_unit: dict[str, Any] | None = None
    current_trophy: dict[str, Any] | None = None

    for line_no in range(idx, len(lines)):
        raw_line = lines[line_no]
        line = raw_line.strip()
        if not line or line == "---" or line.startswith(">"):
            continue

        if line.startswith("# ") and not meta.get("titulo"):
            meta["titulo"] = line[2:].strip()
            continue

        if line.startswith("## "):
            heading = line[3:].strip()
            if heading.lower().startswith("trilha:"):
                title = heading.split(":", 1)[1].strip()
                current_path = {"id": "", "title": title, "description": "", "courses": []}
                paths.append(current_path)
                current_module = None
                current_unit = None
                mode = "trilha"
            elif heading.lower() == "conquistas":
                mode = "conquistas"
                current_trophy = None
                current_path = None
                current_module = None
                current_unit = None
            else:
                # Non-course sections like "Instruções do formato" or "Regras de implementação"
                mode = "ignored"
            continue

        if mode == "ignored":
            continue

        if line.startswith("### "):
            heading = line[4:].strip()
            if heading.lower().startswith("módulo:") or heading.lower().startswith("modulo:"):
                if current_path is None:
                    errors.append(f"Linha {line_no + 1}: Módulo '{heading}' encontrado fora de uma Trilha.")
                    continue
                title = heading.split(":", 1)[1].strip()
                current_module = {
                    "id": "",
                    "title": title,
                    "url": "",
                    "tag": "",
                    "xp": 0,
                    "description": "",
                    "units": [],
                }
                current_path["courses"].append(current_module)
                current_unit = None
                mode = "modulo"
            elif heading.lower().startswith("conquista:"):
                title = heading.split(":", 1)[1].strip()
                current_trophy = {
                    "id": "",
                    "title": title,
                    "desc": "",
                    "icon": "fa-solid fa-award",
                    "type": "unidades_concluidas",
                    "operator": ">=",
                    "meta": 1,
                    "modules": [],
                }
                trophies.append(current_trophy)
                mode = "conquista"
            continue

        if line.startswith("#### "):
            heading = line[5:].strip()
            if heading.lower().startswith("unidade:"):
                if current_module is None:
                    errors.append(f"Linha {line_no + 1}: Unidade '{heading}' encontrada fora de um Módulo.")
                    continue
                title = heading.split(":", 1)[1].strip()
                current_unit = {"id": "", "title": title, "time": ""}
                current_module["units"].append(current_unit)
                mode = "unidade"
            continue

        kv = _parse_kv_line(line)
        if kv:
            k, v = kv
            if mode == "trilha" and current_path is not None:
                if k == "id":
                    current_path["id"] = str(v)
                elif k in ("descricao", "description"):
                    current_path["description"] = str(v)
            elif mode == "modulo" and current_module is not None:
                if k == "id":
                    current_module["id"] = str(v)
                elif k in ("link", "url"):
                    current_module["url"] = str(v)
                elif k in ("etiqueta", "tag"):
                    current_module["tag"] = str(v)
                elif k == "xp":
                    if isinstance(v, int):
                        current_module["xp"] = v
                    else:
                        errors.append(f"Módulo '{current_module['title']}': xp inválido '{v}'.")
                elif k in ("descricao", "description"):
                    current_module["description"] = str(v)
            elif mode == "unidade" and current_unit is not None:
                if k == "id":
                    current_unit["id"] = str(v)
                elif k in ("duracao", "time"):
                    current_unit["time"] = str(v)
            elif mode == "conquista" and current_trophy is not None:
                if k == "id":
                    current_trophy["id"] = str(v)
                elif k in ("descricao", "desc"):
                    current_trophy["desc"] = str(v)
                elif k in ("icone", "icon"):
                    current_trophy["icon"] = str(v)
                elif k in ("tipo", "type"):
                    current_trophy["type"] = str(v)
                elif k in ("operador", "operator"):
                    current_trophy["operator"] = str(v)
                elif k == "meta":
                    if isinstance(v, int):
                        current_trophy["meta"] = v
                    else:
                        errors.append(f"Conquista '{current_trophy['title']}': meta inválida '{v}'.")
                elif k in ("modulos", "modules"):
                    current_trophy["modules"] = v if isinstance(v, list) else [str(v)]

    # Structural validation
    course_id = str(meta.get("id", "")).strip()
    course_title = str(meta.get("titulo", "")).strip()
    if not course_id:
        errors.append("O campo 'id' do curso no frontmatter é obrigatório.")
    elif not ID_RE.match(course_id):
        errors.append(f"ID do curso inválido: '{course_id}'. Use apenas letras, números, '-' ou '_'.")

    if not course_title:
        errors.append("O campo 'titulo' do curso é obrigatório.")

    if not paths:
        errors.append("O curso deve possuir ao menos uma trilha ('## Trilha: ...').")

    seen_path_ids: set[str] = set()
    seen_module_ids: set[str] = set()
    seen_unit_ids: set[str] = set()
    seen_trophy_ids: set[str] = set()
    total_units = 0
    total_xp = 0

    for p in paths:
        if not p["id"]:
            errors.append(f"Trilha '{p['title']}' sem 'id'.")
        elif p["id"] in seen_path_ids:
            errors.append(f"ID de trilha duplicado: '{p['id']}'.")
        seen_path_ids.add(p["id"])

        if not p["courses"]:
            errors.append(f"Trilha '{p['title']}' não possui nenhum módulo.")

        for m in p["courses"]:
            if not m["id"]:
                errors.append(f"Módulo '{m['title']}' sem 'id'.")
            elif m["id"] in seen_module_ids:
                errors.append(f"ID de módulo duplicado: '{m['id']}'.")
            seen_module_ids.add(m["id"])

            if m["xp"] < 0:
                errors.append(f"Módulo '{m['title']}' possui XP negativo.")
            total_xp += m["xp"]

            if m["url"] and not SAFE_URL_RE.match(m["url"]):
                errors.append(f"Módulo '{m['title']}': link inválido ou protocolo não permitido ('{m['url']}'). Use http:// ou https://.")

            if not m["units"]:
                errors.append(f"Módulo '{m['title']}' não possui nenhuma unidade.")

            for u in m["units"]:
                if not u["id"]:
                    errors.append(f"Unidade '{u['title']}' (módulo '{m['title']}') sem 'id'.")
                elif u["id"] in seen_unit_ids:
                    errors.append(f"ID de unidade duplicado: '{u['id']}'.")
                seen_unit_ids.add(u["id"])
                total_units += 1

    for t in trophies:
        if not t["id"]:
            errors.append(f"Conquista '{t['title']}' sem 'id'.")
        elif t["id"] in seen_trophy_ids:
            errors.append(f"ID de conquista duplicado: '{t['id']}'.")
        seen_trophy_ids.add(t["id"])

        if t["type"] not in VALID_TROPHY_TYPES:
            errors.append(f"Conquista '{t['title']}': tipo inválido '{t['type']}'.")
        if t["operator"] not in VALID_OPERATORS:
            errors.append(f"Conquista '{t['title']}': operador inválido '{t['operator']}'.")
        if t["type"] == "modulos_especificos_concluidos" and not t["modules"]:
            warnings.append(f"Conquista '{t['title']}' não lista módulos em 'modulos: [...]'.")

    course_obj = {
        "id": course_id,
        "version": meta.get("versao", 1),
        "title": course_title,
        "description": str(meta.get("descricao", "")).strip(),
        "category": str(meta.get("categoria", "Geral")).strip(),
        "source": str(meta.get("fonte", "")).strip(),
        "xp_level_interval": int(meta.get("xp_nivel_intervalo", 600) or 600),
        "paths": paths,
        "trophies": trophies,
        "stats": {
            "paths_count": len(paths),
            "modules_count": len(seen_module_ids),
            "units_count": total_units,
            "trophies_count": len(trophies),
            "total_xp": total_xp,
        },
    }

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "course": course_obj,
    }
