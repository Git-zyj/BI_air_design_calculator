# BI Air Design Calculator

给 **BIX（BlackICE 子模组）** 用的飞机选型计算器：输入年份、国家、用途、军工组织与已解锁的前置，
输出「该造哪一型飞机、怎么改装、为什么」。

## 快速开始

```
双击 gui.bat            （Windows，推荐）
python gui.py           （同上，命令行）
bash gui.sh             （WSL；需要 bisov 环境，见 PLAN.md §11）
```

界面上方是输入（① 用途 ② 年份 + 国家/对手 ③ 前置科技 ④ 军工组织 ⑤ 国家精神 ⑥ 总体累计），
下方 ⑦ 是结果表 + 帕累托散点图。**「计算」**只出结果，**「导出 Excel」**才写文件
（默认写到 `output/BI_SOV_选型输出.xlsx`）。

## 目录结构

```
gui.py / gui.sh / gui.bat      图形界面与启动器
engine.py                      评分口径（空战比值、事故折损、改装求值、MIO 穷举）
run.py                         读输入 → 计算 → 写工作簿
extract_game_data.py           从游戏/模组文件抽取数据（机身、改装、MIO、方针、特殊工程、科技年份…）
extract_loc_zh.py              抽取汉化名（机型/MIO/特质/改装/科技/修正名）
data/*.json                    抽取结果（重跑抽取脚本即可同步游戏版本）
BI_SOV.xlsx                    最初的手工试算表（只作 golden 参照，已被新口径覆盖）
output/                        导出的工作簿
PLAN.md                        完整设计文档与变更记录（**优先看这个**）
```

## 数据来源与复现

数据全部从游戏与模组文件抽取，不手写：

```
python extract_game_data.py --game-dir "<BIX 模组目录>"    # BIX/子模组目录
python extract_loc_zh.py                                   # 汉化（含原版简中）
```

抽取结果带 `data/manifest.json`（sha256 指纹），游戏版本更新后重跑即可。
数值口径、公式推导、踩过的坑都记在 `PLAN.md`。

## 验收

```
python run.py --anchor     # 对空 + 距离 900：Yak-9U@1944 = 15540.543552
```

## 依赖

- Python 3.8+，`openpyxl`（导出 Excel 用）
- 图形界面用 Tkinter；Windows 原生即可，字体不受限

## 说明

这是一个**工具模组**，本身不包含游戏内容；`descriptor.mod` 里把 BIX 标为依赖只是为了记录它服务于哪个模组。
