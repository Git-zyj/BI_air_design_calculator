# -*- coding: utf-8 -*-
"""离线预计算"方针 × 特质路线"表（data/route_table.json）。

为什么要它：方针现在和特质一起穷举（每个方针各跑一次真实管线），单次约 0.5~2.5 秒；
把常用情境提前算好，界面命中即读，用时不再重算。表外的情境照样能算，并写进本机缓存
（route_cache.json），第二次打开就是秒开。

它**走界面同一套代码路径**（临时起一个隐藏的界面实例），所以键与结果和界面完全一致，
不会出现"离线表和界面算出来不一样"。

用法示例：
    python precompute_routes.py --countries SOV,GER --years 1939-1948 \
        --roles air_far --allocs split,balanced
    python precompute_routes.py --countries SOV,GER --years 1939-1948 --roles air_far \
        --allocs split,balanced --force        # 忽略已有条目，全部重算
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import engine  # noqa: E402
import gui  # noqa: E402
import run  # noqa: E402

if getattr(sys, "stdout", None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def parse_ints(spec, default):
    spec = (spec or "").strip()
    if not spec:
        return list(default)
    if "-" in spec and "," not in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="SOV,GER")
    ap.add_argument("--years", default="1939-1948", help="当前年份（决定对手）")
    ap.add_argument("--tech-years", default="", help="飞机科技年份；默认与 --years 相同")
    ap.add_argument("--roles", default="air_far", help="用途，逗号分隔")
    ap.add_argument("--allocs", default="split,balanced", help="配点口径：split/balanced")
    ap.add_argument("--out", default=run.PLAN_TABLE)
    ap.add_argument("--enemies", default="", help="对手国别（逗号分隔）；默认每个玩家国配默认对手")
    ap.add_argument("--force", action="store_true", help="忽略已有条目，全部重算")
    ap.add_argument("--progress", type=int, default=10, help="每多少组打印一次进度")
    args = ap.parse_args()

    countries = [c.strip() for c in args.countries.split(",") if c.strip()]
    years = parse_ints(args.years, range(1939, 1949))
    tech_years = parse_ints(args.tech_years, years) if args.tech_years else list(years)
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    allocs = [a.strip() for a in args.allocs.split(",") if a.strip()]
    alloc_label = dict(gui.ALLOC_MODES)

    table = {} if args.force else run._load_plan_file(args.out)
    print("已有条目 %d 个；本次目标 %d 国 × %d 科技年 × %d 当前年 × %d 用途 × %d 口径"
          % (len(table), len(countries), len(tech_years), len(years), len(roles), len(allocs)))

    gui.App._pop_to_front = lambda self: None
    app = gui.App()
    app.withdraw()
    if args.force:
        app._plan_table = {}
        app._plan_runtime = {}

    t_all = time.time()
    done = 0
    for country in countries:
        label = app._tag_labels.get(country, country)
        if label not in app._tag_labels.values():
            print("跳过 %s：机型数据里没有这个国家" % country)
            continue
        app.var_tag.set(label)
        app._refresh_country()
        # 默认对手：苏→德、德→苏，其余用德国
        enemies = ([e.strip() for e in args.enemies.split(",") if e.strip()]
                   if args.enemies else [("GER" if country != "GER" else "SOV")])
        for role in roles:
            for k, v in app.role_vars.items():
                v.set(k == role)
            app._on_roles_changed()
            for enemy in enemies:
                app.var_enemy_tag.set(app._tag_labels.get(enemy, enemy))
                app._on_enemy_change()
                for tech_year in tech_years:
                    app.var_tech.set(tech_year)
                app._on_tech_year_changed()
                for year in years:
                    app.var_year.set(year)
                    for alloc in allocs:
                        app.var_alloc_mode.set(alloc_label[alloc])
                        app._on_alloc_mode_change()
                        if getattr(app, "_plan_job", None):
                            app.after_cancel(app._plan_job)
                            app._plan_job = None
                        inputs = app.collect()
                        orgs = app._air_orgs()[0]
                        t0 = time.time()
                        for org in orgs:
                            app._org_plan(org, inputs)
                        done += 1
                        if args.progress and (done % max(1, args.progress) == 0):
                            print("  [%d] %-4s %-8s 科技%d 当前%d %-8s %.1fs（累计 %d 组，已用时 %.1f 分）"
                                  % (done, country, role, tech_year, year, alloc,
                                     time.time() - t0, done, (time.time() - t_all) / 60.0))
                            sys.stdout.flush()
            # 一个 (国家, 用途) 存一个分片（只挑属于本片的键），下次运行自动续算
            shard = {} if args.force else run._load_plan_file(run.plan_shard_path(country, role))
            for key, rec in app._plan_runtime.items():
                parts = key.split("|")
                if parts[3] == country and parts[6] == role:
                    shard[key] = rec
            run.save_plan_shard(country, role, shard)
            print("  分片 %s_%s：%d 条" % (country, role, len(shard)))
            sys.stdout.flush()

    print("\n完成：分片目录 %s，用时 %.1f 分钟" % (run.PLAN_TABLE_DIR, (time.time() - t_all) / 60.0))
    app.destroy()


if __name__ == "__main__":
    main()
