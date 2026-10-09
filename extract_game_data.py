#!/usr/bin/env python3
"""BI_SOV 数据抽取（B1）

从 BlackICE 游戏文件抽取飞机选型计算所需的原始数据，固化成 tools/bi_sov/data/*.json。
抽取只依赖游戏目录本身；输出带来源指纹（路径/大小/sha256），便于复现与版本更新后重跑。

用法：
    python extract_game_data.py                     # 默认读取 BICE 测试版
    python extract_game_data.py --game-dir <路径>   # 指定正式版/其他版本
    python extract_game_data.py --check-sheet       # 额外与 BI_SOV.xlsx 的机型表逐格核对
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_GAME_DIR = r"D:\Steam\steamapps\workshop\content\394360\1851181613"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

# 表列 → 游戏字段（已用 SOV战斗机数据 逐行验证）
AIRFRAME_FIELDS = {
    "range": "air_range",
    "defence": "air_defence",
    "attack": "air_attack",
    "agility": "air_agility",
    "ground_attack": "air_ground_attack",
    "speed": "maximum_speed",
    "reliability": "reliability",
    "cost": "build_cost_ic",
    "year": "year",
    # 对海用的自身属性（以前漏抽，对海分数只能用改装乘子凑，见 PLAN §15）
    "naval_strike_attack": "naval_strike_attack",
    "naval_strike_targetting": "naval_strike_targetting",
}
# 这几项允许缺失（战斗机没有对海攻击、早期 CAS 没有对地攻击等）
OPTIONAL_AIRFRAME_FIELDS = ("ground_attack", "naval_strike_attack", "naval_strike_targetting")

# 机种：表内分类 → 文件 + archetype
AIRFRAME_SOURCES = [
    ("light_fighter", "_airframe_fighter_alt.txt", "fighter_alt_equipment"),
    ("fighter", "_airframe_fighter.txt", "fighter_equipment"),
    ("interceptor", "_airframe_interceptor.txt", "interceptor_equipment"),
    ("multi_role", "_airframe_multi_role.txt", "mr_fighter_equipment"),
    ("jet_fighter", "_airframe_jet_fighter.txt", "jet_fighter_equipment"),
]


def archetype_of_file(path):
    """文件里标了 `is_archetype = yes` 的那个块名，就是该文件的 archetype。"""
    for name, block in parse_blocks(read_text(path)):
        if name.endswith("_equipment") and scalar(block, "is_archetype"):
            return name
    return None


def discover_airframe_sources(game_dir):
    """扫描 common/units/equipment 下**全部** _airframe_*.txt → [(category, file, archetype)]。

    表内那 5 个战斗机文件保留原有 category 名（airframes.json 与验收锚点不受影响）；
    其余文件的 category = archetype 去掉 _equipment 后缀（小写）。
    """
    base = os.path.join(game_dir, "common", "units", "equipment")
    known = {fn: (cat, arch) for cat, fn, arch in AIRFRAME_SOURCES}
    out = []
    for filename in sorted(os.listdir(base)):
        if not (filename.startswith("_airframe_") and filename.endswith(".txt")):
            continue
        if filename in known:
            cat, arch = known[filename]
        else:
            arch = archetype_of_file(os.path.join(base, filename))
            if not arch:
                continue
            cat = (arch[:-len("_equipment")] if arch.endswith("_equipment") else arch).lower()
        out.append((cat, filename, arch))
    return out

SOV_LOCALISATION = os.path.join("localisation", "english", "equipment_l_english_SOV.yml")
UPGRADES_FILE = os.path.join("common", "units", "equipment", "upgrades", "air_upgrades.txt")
DEFINES_FILE = os.path.join("common", "defines", "00_defines.lua")
# 需要抽取的 NAir（飞机）常量
AIR_DEFINE_KEYS = (
    "ACCIDENT_CHANCE_BASE",
    "ACCIDENT_CHANCE_CARRIER_MULT",
    "ACCIDENT_CHANCE_BALANCE_MULT",
    "ACCIDENT_CHANCE_RELIABILITY_MULT",
    "ACCIDENT_EFFECT_MULT",
    "COMBAT_BETTER_AGILITY_DAMAGE_REDUCTION",
    "COMBAT_BETTER_SPEED_DAMAGE_INCREASE",
    "BIGGEST_AGILITY_FACTOR_DIFF",
    "BIGGEST_SPEED_FACTOR_DIFF",
)
IDEAS_DIR = os.path.join("common", "ideas")
# idea 的 equipment_bonus 里与飞机相关的类别关键字
AIR_CATEGORY_HINTS = ("fighter", "interceptor", "cas", "bomber", "plane", "air_", "mr_")
MIO_DIR = os.path.join("common", "military_industrial_organization", "organizations")
# 需要抽取的 MIO 来源；None = 自动发现 organizations 目录下全部 *_organization 文件
MIO_FILES = None
AIR_ARCHETYPES = ("fighter_equipment", "fighter_alt_equipment", "interceptor_equipment",
                  "mr_fighter_equipment", "jet_fighter_equipment", "heavy_fighter_equipment")


def strip_comments(text):
    return re.sub(r"#.*", "", text)


def parse_blocks(text):
    """把 `name = { ... }` 逐层扫出来，返回 [(name, depth, block_text, start_offset)]。"""
    text = strip_comments(text)
    blocks = []
    # (?<![\w:]) 用来排除 "mio:XXX = { ... }" 这类**引用**（效果里的 add_mio_funds 等），
    # 它们不是定义，之前会被误当成同名组织，导致 SOV_gaz_organization 出现两次。
    for m in re.finditer(r"(?<![\w:])([A-Za-z_0-9]+)\s*=\s*\{", text):
        name = m.group(1)
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        blocks.append((name, text[start:i - 1]))
    return blocks


def scalar(block, key):
    m = re.search(r"(?<![\w.])%s\s*=\s*([^\{}\n]+)" % re.escape(key), block)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw


def nested(block, parent, key):
    m = re.search(r"(?<![\w.])%s\s*=\s*\{" % re.escape(parent), block)
    if not m:
        return None
    depth = 1
    i = m.end()
    start = i
    while i < len(block) and depth > 0:
        if block[i] == "{":
            depth += 1
        elif block[i] == "}":
            depth -= 1
        i += 1
    return scalar(block[start:i - 1], key)


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_sov_names(game_dir):
    """SOV 本地化里的 `key:0 "Display Name"` → {key: display}"""
    path = os.path.join(game_dir, SOV_LOCALISATION)
    names = {}
    for line in read_text(path).splitlines():
        m = re.match(r'^\s*([A-Za-z_0-9]+):\d*\s+"([^"]+)"', line)
        if m and m.group(1).endswith(("_equipment_1", "_equipment_2", "_equipment_3",
                                      "_equipment_4", "_equipment_5", "_equipment_6")):
            names[m.group(1)] = m.group(2)
    return names


def parse_airframes(game_dir, sov_names):
    out = []
    for category, filename, archetype in AIRFRAME_SOURCES:
        path = os.path.join(game_dir, "common", "units", "equipment", filename)
        text = read_text(path)
        for name, block in parse_blocks(text):
            if scalar(block, "archetype") != archetype:
                continue
            if name not in sov_names:
                continue
            entry = {
                "key": name,
                "name": sov_names[name],
                "category": category,
                "archetype": archetype,
                "source": {"file": os.path.relpath(path, game_dir).replace("\\", "/")},
            }
            ok = True
            for field, game_key in AIRFRAME_FIELDS.items():
                value = scalar(block, game_key)
                if value is None and field in OPTIONAL_AIRFRAME_FIELDS:
                    value = 0
                if value is None:
                    ok = False
                    value = 0
                entry[field] = value
            entry["air_production"] = nested(block, "resources", "air_production") or 0
            entry["engine_production"] = nested(block, "resources", "engine_production") or 0
            entry["incomplete"] = not ok
            out.append(entry)
    out.sort(key=lambda e: (e["year"], e["category"], e["name"]))
    return out


def parse_upgrades(game_dir):
    path = os.path.join(game_dir, UPGRADES_FILE)
    text = read_text(path)
    out = []
    for name, block in parse_blocks(text):
        if not name.endswith("_upgrade"):
            continue
        adds = {}
        m = re.search(r"add_stats\s*=\s*\{([^}]*)\}", block)
        if m:
            for key, value in re.findall(r"([A-Za-z_0-9]+)\s*=\s*([-\d.]+)", m.group(1)):
                try:
                    adds[key] = float(value)
                except ValueError:
                    pass
        mod_block = re.sub(r"add_stats\s*=\s*\{[^}]*\}", "", block)
        fields = {}
        requires = {"techs": [], "flags": []}
        for key, value in re.findall(r"(?<![\w.])([A-Za-z_0-9]+)\s*=\s*([^\{}\n]+)", mod_block):
            key, value = key.strip(), value.strip()
            if key == "has_tech":
                requires["techs"].append(value)
                continue
            if key in ("has_country_flag", "has_global_flag"):
                requires["flags"].append(value)
                continue
            if key in ("max_level", "cost") or key.startswith("has_"):
                continue
            try:
                fields[key] = float(value) if "." in value else int(value)
            except ValueError:
                continue
        out.append({
            "key": name,
            "max_level": int(scalar(block, "max_level") or 1),
            "modifiers": fields,
            "add_stats": adds,
            "requires": requires,
        })
    return out


def parse_air_defines(game_dir):
    """从 common/defines/00_defines.lua 的 NAir 段抽取飞机相关常量。

    以前这些值是硬编码在 engine.py 里的；现在抽出来存 data/defines.json，
    模组更新后重跑一次就能同步（例如 ACCIDENT_CHANCE_CARRIER_MULT = 1.25）。
    """
    path = os.path.join(game_dir, DEFINES_FILE)
    text = read_text(path)
    m = re.search(r"(?<![\w.])NAir\s*=\s*\{", text)
    if not m:
        return {}
    depth, i = 1, m.end()
    start = i
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    body = text[start:i - 1]
    out = {}
    for key in AIR_DEFINE_KEYS:
        mm = re.search(r"(?<![\w.])%s\s*=\s*([-\d.eE]+)" % re.escape(key), body)
        if mm:
            out[key] = float(mm.group(1))
    return out


POLICY_DIR = os.path.join("common", "military_industrial_organization", "policies")
PROJECT_DIR = os.path.join("common", "special_projects", "projects")
TECH_DIR = os.path.join("common", "technologies")


def parse_tech_years(game_dir):
    """科技 → 起始年份（`start_year`／`year`）。用于"默认已完成到某年"的勾选。"""
    base = os.path.join(game_dir, TECH_DIR)
    out = {}
    if not os.path.isdir(base):
        return out
    for filename in sorted(os.listdir(base)):
        if not filename.endswith(".txt"):
            continue
        for name, block in parse_blocks(read_text(os.path.join(base, filename))):
            year = scalar(block, "start_year")
            if year is None:
                year = scalar(block, "year")
            if isinstance(year, int) and name not in out:
                out[name] = year
    return out


def parse_special_projects(game_dir):
    """特殊工程：只记录"会授予国家标识"的那些（改装里用的 flags 就来自这里）。

    例：sp_air_anti_air_rocket 需要 rocket_artillery4 + advanced_machine_tools，
    完成后 set_country_flag = unlock_plane_anti_air_rocket_upgrade（解锁空对空火箭改装）。
    """
    base = os.path.join(game_dir, PROJECT_DIR)
    out = []
    if not os.path.isdir(base):
        return out
    for filename in sorted(os.listdir(base)):
        if not filename.endswith(".txt"):
            continue
        text = read_text(os.path.join(base, filename))
        for name, block in parse_blocks(text):
            if not name.startswith("sp_"):
                continue
            flags = re.findall(r"set_country_flag\s*=\s*([A-Za-z_0-9]+)", block)
            if not flags:
                continue
            avail = re.search(r"(?<![\w.])available\s*=\s*\{", block)
            techs = []
            if avail:
                depth, j = 1, avail.end()
                while j < len(block) and depth:
                    if block[j] == "{":
                        depth += 1
                    elif block[j] == "}":
                        depth -= 1
                    j += 1
                techs = re.findall(r"has_tech\s*=\s*([A-Za-z_0-9]+)", block[avail.end():j - 1])
            out.append({
                "project": name,
                "file": os.path.relpath(os.path.join(base, filename), game_dir).replace("\\", "/"),
                "flags": flags,
                "requires_techs": techs,
            })
    return out


def _pairs(block):
    """块里的 `key = 数值` 直接子项 → dict。"""
    return {k: float(v) for k, v in
            re.findall(r"(?<![\w.])([a-z_0-9]+)\s*=\s*(-?[\d.]+)", block)}


def parse_policies(game_dir):
    """MIO 方针（policies/*.txt）。

    结构：
        mio_policy_xxx = {
            allowed   = { has_mio_equipment_type = ... }        # 适用装备类型
            available = { has_mio_size > 5  owner = { has_tech = X } }   # 6 级起 + 一项科技
            equipment_bonus = { same_as_mio = { 修正… } }
            organization_modifier = { 研究加成/资金… }          # 不是装备修正
        }
    """
    base = os.path.join(game_dir, POLICY_DIR)
    out = []
    if not os.path.isdir(base):
        return out
    for filename in sorted(os.listdir(base)):
        if not filename.endswith(".txt"):
            continue
        text = read_text(os.path.join(base, filename))
        for name, block in parse_blocks(text):
            if not name.startswith("mio_policy_"):
                continue
            subs = {}
            for sub_name, sub_body in parse_blocks(block):
                subs.setdefault(sub_name, sub_body)
            equip = {}
            if "same_as_mio" in dict(parse_blocks(subs.get("equipment_bonus", ""))):
                equip = _pairs(dict(parse_blocks(subs["equipment_bonus"]))["same_as_mio"])
            size = re.search(r"has_mio_size\s*>\s*(\d+)", subs.get("available", ""))
            allowed_body = subs.get("allowed", "")
            out.append({
                "token": name,
                "file": os.path.relpath(os.path.join(base, filename), game_dir).replace("\\", "/"),
                "equipment_types": re.findall(r"has_mio_equipment_type\s*=\s*([A-Za-z_0-9]+)",
                                              allowed_body),
                # allowed = { always = yes } → 所有军工组织通用；
                # allowed 里只有空的 OR（条件全被注释掉）→ 实际上谁都选不了
                "allowed_all": bool(re.search(r"always\s*=\s*yes", allowed_body)),
                "min_size": (int(size.group(1)) + 1) if size else 0,
                "requires_techs": re.findall(r"has_tech\s*=\s*([A-Za-z_0-9]+)",
                                             subs.get("available", "")),
                "equipment_bonus": equip,
                "organization_modifier": _pairs(subs.get("organization_modifier", "")),
            })
    return out


def parse_archetype_upgrades(game_dir):
    """每种机身原型（archetype）允许的改装轨列表。"""
    out = []
    for category, filename, archetype in discover_airframe_sources(game_dir):
        path = os.path.join(game_dir, "common", "units", "equipment", filename)
        if not os.path.exists(path):
            continue
        for name, block in parse_blocks(read_text(path)):
            if name != archetype:
                continue
            m = re.search(r"upgrades\s*=\s*\{([^}]*)\}", block)
            upgrades = m.group(1).split() if m else []
            out.append({"archetype": archetype, "category": category, "upgrades": upgrades})
            break
    return out


def parse_national_ideas(game_dir):
    """记录 ideas 目录下与飞机相关的国家精神及其修正，供输入侧匹配/选择。"""
    directory = os.path.join(game_dir, IDEAS_DIR)
    out = []
    if not os.path.isdir(directory):
        return out
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".txt"):
            continue
        path = os.path.join(directory, filename)
        for idea, block in parse_blocks(read_text(path)):
            m = re.search(r"(?<![\w.])equipment_bonus\s*=\s*\{", block)
            if not m:
                continue
            depth, i, start = 1, m.end(), m.end()
            while i < len(block) and depth:
                if block[i] == "{":
                    depth += 1
                elif block[i] == "}":
                    depth -= 1
                i += 1
            for category, cat_block in parse_blocks(block[start:i - 1]):
                if not any(hint in category for hint in AIR_CATEGORY_HINTS):
                    continue
                mods = {}
                for key, value in re.findall(r"([A-Za-z_0-9]+)\s*=\s*([-\d.]+)", cat_block):
                    if key == "instant":
                        continue
                    mods[key] = float(value)
                if mods:
                    out.append({
                        "file": os.path.relpath(path, game_dir).replace("\\", "/"),
                        "idea": idea,
                        "category": category,
                        "modifiers": mods,
                    })
    return out


def check_sheet(airframes):
    return _check_sheet(airframes)


def parse_country_names(game_dir):
    """所有 equipment_l_english_*.yml → {key: (国家TAG, 显示名)}"""
    base = os.path.join(game_dir, "localisation", "english")
    out = {}
    if not os.path.isdir(base):
        return out
    for filename in sorted(os.listdir(base)):
        m = re.match(r"equipment_l_english_([A-Za-z0-9_]+)\.yml$", filename)
        if not m:
            continue
        tag = m.group(1)
        for line in read_text(os.path.join(base, filename)).splitlines():
            mm = re.match(r'^\s*([A-Za-z_0-9]+):\d*\s+"([^"]+)"', line)
            if mm and "_equipment_" in mm.group(1):
                out.setdefault(mm.group(1), (tag, mm.group(2)))
    return out


def parse_all_airframes(game_dir, country_names):
    """所有国家的全部机型（含 priority 与 archetype），供候选池、对手选取与手动指定。"""
    out = []
    for category, filename, archetype in discover_airframe_sources(game_dir):
        path = os.path.join(game_dir, "common", "units", "equipment", filename)
        if not os.path.exists(path):
            continue
        for name, block in parse_blocks(read_text(path)):
            if scalar(block, "archetype") != archetype:
                continue
            if name == "equipments":
                continue        # 解析产物的外层包裹块，不是机型
            country, display = country_names.get(name, (None, name))
            entry = {
                "key": name,
                "name": display,
                "country": country,
                "category": category,
                "archetype": archetype,
                "priority": scalar(block, "priority"),
            }
            for field, game_key in AIRFRAME_FIELDS.items():
                value = scalar(block, game_key)
                entry[field] = 0 if value is None else value
            entry["air_production"] = nested(block, "resources", "air_production") or 0
            entry["engine_production"] = nested(block, "resources", "engine_production") or 0
            out.append(entry)
    return out


def parse_mio(game_dir):
    """抽取 MIO 组织与其特质（含 ai_will_do、前置、互斥、适用装备）。"""
    out = []
    directory = os.path.join(game_dir, MIO_DIR)
    if MIO_FILES:
        filenames = list(MIO_FILES)
    else:
        filenames = sorted(f for f in os.listdir(directory) if f.endswith("_organization.txt"))
    for filename in filenames:
        path = os.path.join(directory, filename)
        if not os.path.exists(path):
            continue
        for org, block in parse_blocks(read_text(path)):
            # 名字不一定以 _organization 结尾：如 SOV_gaz_organization_mot、SOV_kirov_organization_mio
            if "_organization" not in org:
                continue
            organization = {
                "organization": org,
                "file": os.path.relpath(path, game_dir).replace("\\", "/"),
                "includes": [m.group(1) for m in re.finditer(r"include\s*=\s*([A-Za-z_0-9]+)", block)],
                "equipment_types": [],
                "traits": [],
            }
            for key, value in re.findall(r"([A-Za-z_0-9]+)\s*=\s*([^\{}\n]+)", block):
                pass
            m = re.search(r"equipment_type\s*=\s*\{([^}]*)\}", block)
            if m:
                organization["equipment_types"] = m.group(1).split()
            initial = re.search(r"initial_trait\s*=\s*\{", block)
            if initial:
                segment = block[initial.end():]
                organization["initial_trait"] = _trait_payload(segment)
            # 有些国家 MIO 用 add_trait 定义特质（例如 GER_arado_flugzeugwerke_organization）
            for trait_block in re.finditer(r"(?<![\w.])(?:add_)?trait\s*=\s*\{", block):
                payload = _trait_payload(block[trait_block.end():])
                if payload:
                    organization["traits"].append(payload)
            # 不要过滤"没有自身特质"的组织：设计局类 MIO 常写成纯 include 通用模板
            out.append(organization)
    # 同名重复定义：游戏里后定义的覆盖先定义的（如 SOV_gaz_organization 在文件里出现两次）
    dedup = {}
    for org in out:
        if org["organization"] in dedup:
            print("  注意：%s 重复定义，按游戏规则保留后一处" % org["organization"])
        dedup[org["organization"]] = org
    out = list(dedup.values())
    # 合并 include 的通用组织：游戏里国家 MIO 的特质树 = 自身特质 + 模板特质
    by_name = {o["organization"]: o for o in out}
    for org in out:
        for inc in org.get("includes", []):
            src = by_name.get(inc)
            if not src:
                continue
            have = {t.get("token") for t in org["traits"]}
            for trait in src.get("traits", []):
                if trait.get("token") not in have:
                    org["traits"].append(trait)
            if not org.get("initial_trait") and src.get("initial_trait"):
                org["initial_trait"] = src["initial_trait"]
    return out


def _trait_payload(segment):
    """从 '{...}' 之后的文本里抓取第一个 trait 的字段（用花括号配对截断）。"""
    depth, i = 1, 0
    while i < len(segment) and depth:
        if segment[i] == "{":
            depth += 1
        elif segment[i] == "}":
            depth -= 1
        i += 1
    body = segment[:i - 1]
    token = scalar(body, "token") or scalar(body, "name")
    bonuses = {}
    m = re.search(r"equipment_bonus\s*=\s*\{([^}]*)\}", body)
    if m:
        for key, value in re.findall(r"([A-Za-z_0-9]+)\s*=\s*([-\d.]+)", m.group(1)):
            bonuses[key] = float(value)
    m = re.search(r"ai_will_do\s*=\s*\{([^}]*)\}", body)
    ai_base = None
    if m:
        ai_base = scalar(m.group(1), "base")
    parents = []
    for kind in ("all_parents", "any_parent"):
        m = re.search(r"%s\s*=\s*\{([^}]*)\}" % kind, body)
        if m:
            parents.append((kind, m.group(1).split()))
    limits = []
    m = re.search(r"limit_to_equipment_type\s*=\s*\{([^}]*)\}", body)
    if m:
        limits = m.group(1).split()
    excl = []
    m = re.search(r"mutually_exclusive\s*=\s*\{([^}]*)\}", body)
    if m:
        excl = m.group(1).split()
    # 特质自身的科技门槛：available = { FROM = { has_tech = X } }（BICE 里只有少数特质有）
    avail = re.search(r"(?<![\w.])available\s*=\s*\{", body)
    requires_techs = []
    if avail:
        depth2, j = 1, avail.end()
        while j < len(body) and depth2:
            if body[j] == "{":
                depth2 += 1
            elif body[j] == "}":
                depth2 -= 1
            j += 1
        requires_techs = re.findall(r"has_tech\s*=\s*([A-Za-z_0-9]+)", body[avail.end():j - 1])
    if not token:
        return None
    return {
        "token": token,
        "bonuses": bonuses,
        "ai_will_do": ai_base,
        "parents": parents,
        "limit_to_equipment_type": limits,
        "mutually_exclusive": excl,
        "requires_techs": requires_techs,
    }


def _check_sheet(airframes):
    import openpyxl

    sheet_path = os.path.join(HERE, "..", "BI_SOV.xlsx")
    wb = openpyxl.load_workbook(sheet_path, data_only=True, read_only=True)
    ws = wb["SOV战斗机数据"]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        rows.append(row)
    wb.close()

    by_name = {a["name"]: a for a in airframes}
    cols = ["range", "defence", "attack", "agility", "ground_attack",
            "speed", "reliability", "cost"]
    matched, problems = 0, []
    for row in rows:
        name = row[0]
        entry = by_name.get(name)
        if entry is None:
            problems.append("机型表里有、游戏数据里没找到：%s" % name)
            continue
        matched += 1
        for idx, field in enumerate(cols):
            sheet_value = row[1 + idx]
            game_value = entry[field]
            if sheet_value is None:
                continue
            if abs(float(sheet_value) - float(game_value)) > 1e-9:
                problems.append("%s.%s: 表=%s 游戏=%s" % (name, field, sheet_value, game_value))
        if row[9] is not None and int(row[9]) != int(entry["year"]):
            problems.append("%s.year: 表=%s 游戏=%s" % (name, row[9], entry["year"]))
        if row[10] is not None and int(row[10]) != int(entry["air_production"]):
            problems.append("%s.air_production: 表=%s 游戏=%s" % (name, row[10], entry["air_production"]))
        if row[11] is not None and int(row[11]) != int(entry["engine_production"]):
            problems.append("%s.engine_production: 表=%s 游戏=%s" % (name, row[11], entry["engine_production"]))
    extra = [a["name"] for a in airframes if a["name"] not in {r[0] for r in rows}]
    print("机型核对：表内 %d 行，命中 %d 行" % (len(rows), matched))
    if extra:
        print("  游戏数据里多出未进表的：%s" % ", ".join(extra))
    if problems:
        print("  差异 %d 处：" % len(problems))
        for p in problems[:40]:
            print("    " + p)
    else:
        print("  全部一致 ✓")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    ap.add_argument("--check-sheet", action="store_true")
    args = ap.parse_args()

    game_dir = args.game_dir
    if not os.path.isdir(game_dir):
        raise SystemExit("游戏目录不存在：%s" % game_dir)

    sov_names = parse_sov_names(game_dir)
    frame_sources = discover_airframe_sources(game_dir)
    airframes = parse_airframes(game_dir, sov_names)
    upgrades = parse_upgrades(game_dir)
    ideas = parse_national_ideas(game_dir)
    country_names = parse_country_names(game_dir)
    all_airframes = parse_all_airframes(game_dir, country_names)
    mio = parse_mio(game_dir)
    archetypes = parse_archetype_upgrades(game_dir)
    air_defines = parse_air_defines(game_dir)
    policies = parse_policies(game_dir)
    projects = parse_special_projects(game_dir)
    tech_years = parse_tech_years(game_dir)

    os.makedirs(DATA_DIR, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "game_dir": game_dir,
        "sources": [],
    }
    for rel in [SOV_LOCALISATION, UPGRADES_FILE, DEFINES_FILE] + [
        os.path.join("common", "units", "equipment", f) for _, f, _ in frame_sources
    ]:
        path = os.path.join(game_dir, rel)
        manifest["sources"].append({
            "file": rel.replace("\\", "/"),
            "size": os.path.getsize(path),
            "sha256": sha256(path),
        })

    with open(os.path.join(DATA_DIR, "airframes.json"), "w", encoding="utf-8") as fh:
        json.dump(airframes, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "upgrades.json"), "w", encoding="utf-8") as fh:
        json.dump(upgrades, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "national_ideas.json"), "w", encoding="utf-8") as fh:
        json.dump(ideas, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "airframes_all.json"), "w", encoding="utf-8") as fh:
        json.dump(all_airframes, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "mio.json"), "w", encoding="utf-8") as fh:
        json.dump(mio, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "archetypes.json"), "w", encoding="utf-8") as fh:
        json.dump(archetypes, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "defines.json"), "w", encoding="utf-8") as fh:
        json.dump(air_defines, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "policies.json"), "w", encoding="utf-8") as fh:
        json.dump(policies, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "special_projects.json"), "w", encoding="utf-8") as fh:
        json.dump(projects, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "tech_years.json"), "w", encoding="utf-8") as fh:
        json.dump(tech_years, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)

    print("机身：%d 型" % len(airframes))
    for category, _, _ in AIRFRAME_SOURCES:
        n = sum(1 for a in airframes if a["category"] == category)
        print("   %-12s %d" % (category, n))
    print("扫描到的机身文件：%d 个（全部机种）" % len(frame_sources))
    for category, _, arch in frame_sources:
        n = sum(1 for a in all_airframes if a["category"] == category)
        print("   %-22s %-32s %d 型（含他国）" % (category, arch, n))
    print("改装：%d 项（含 cv_ 变体）" % len(upgrades))
    print("国家精神（飞机相关）：%d 条" % len(ideas))
    print("全部机型（含他国）：%d 型；MIO 组织：%d 个" % (len(all_airframes), len(mio)))
    print("机身原型的改装轨：%s" % ", ".join("%s=%d" % (a["category"], len(a["upgrades"])) for a in archetypes))
    print("NAir 常量：%s" % json.dumps(air_defines, ensure_ascii=False))
    print("MIO 方针：%d 条" % len(policies))
    print("特殊工程（会授予国家标识的）：%d 条" % len(projects))
    print("科技年份：%d 项" % len(tech_years))
    for p in projects:
        print("   %-42s → %s｜前置 %s"
              % (p["project"], ",".join(p["flags"]), ",".join(p["requires_techs"]) or "-"))
    for p in policies:
        print("   %-44s 装备类型 %d｜%d 级起｜科技 %s｜修正 %s"
              % (p["token"], len(p["equipment_types"]), p["min_size"],
                 ",".join(p["requires_techs"]) or "-", json.dumps(p["equipment_bonus"], ensure_ascii=False)))
    print("输出：%s" % DATA_DIR)

    if args.check_sheet:
        print()
        check_sheet(airframes)


if __name__ == "__main__":
    main()
