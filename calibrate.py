#!/usr/bin/env python3
"""用一次游戏内观测反推事故年损失系数 f。

模型（wiki 结构）：每机场每小时损失 = RATE × (1 − 可靠度) 的「一个联队」，
其中 RATE = f / 8760（年损失率 f 折成每小时）。

用法：
    python calibrate.py --planes 50 --wings 8 --losses 3,2,1,0,1,3,0,1 \
        --start 1941-02-16 --end 1941-04-03 --reliability 0.65 --airbases 8
"""

import argparse
import datetime
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REFERENCE = {  # 两种口径下的年损失率（供对照）
    "口径A 不计 BALANCE": 1.314,
    "口径B 计 BALANCE": 0.9855,
    "原版 wiki 锚点": 6.132,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--planes", type=int, required=True, help="每个联队的飞机数")
    ap.add_argument("--wings", type=int, required=True, help="联队数")
    ap.add_argument("--losses", required=True, help="各联队损失，逗号分隔")
    ap.add_argument("--start", required=True, help="起始日期 YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    ap.add_argument("--reliability", type=float, required=True, help="可靠度（0.65 表示 65%）")
    ap.add_argument("--airbases", type=int, default=None,
                    help="这些联队分布在几个机场（默认=联队数，即每队一个机场）")
    args = ap.parse_args()

    losses = [int(x) for x in args.losses.split(",")]
    total_lost = sum(losses)
    total_planes = args.planes * args.wings
    airbases = args.airbases or args.wings
    start = datetime.date.fromisoformat(args.start)
    end = datetime.date.fromisoformat(args.end)
    days = (end - start).days
    hours = days * 24
    wings_lost = total_lost / args.planes

    print("观测：%d 队 × %d 架 = %d 架；损失 %d 架（%.3f 个联队）；%d 天 / %d 小时；可靠度 %.2f"
          % (args.wings, args.planes, total_planes, total_lost, wings_lost, days, hours, args.reliability))
    print("      机场数按 %d 计" % airbases)
    print()
    print("按【每个机场每小时】口径反推：")
    rate = wings_lost / hours / airbases
    f_implied = rate * 8760 / (1 - args.reliability)
    print("  每机场每小时损失 = %.6f 个联队 → 隐含年损失率 f = %.4f" % (rate, f_implied))
    print()
    print("对照：")
    for name, f in REFERENCE.items():
        pred_wings = f / 8760 * (1 - args.reliability) * hours * airbases
        print("  %-20s f=%-7.4f  预测损失 %6.2f 架（观测 %d 架，比 %.2f）"
              % (name, f, pred_wings * args.planes, total_lost, pred_wings * args.planes / total_lost))
    print()
    print("注：样本只有 %d 次损失事件，泊松噪声约 ±%.0f%%；天气/演习/ veterancy 会额外偏移。"
          % (total_lost, 100 / max(total_lost, 1) ** 0.5))


if __name__ == "__main__":
    main()
