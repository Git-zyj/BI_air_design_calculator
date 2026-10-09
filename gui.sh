#!/usr/bin/env bash
# 启动 BI_SOV 图形界面。
#
# 必须用 bisov 环境：base 环境的 Tk 没链接 libXft，中文会退回 WSLg 的仿宋位图。
# 详见 PLAN.md §11。
#
#   bash tools/bi_sov/gui.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BISOV_PY="${BISOV_PY:-$HOME/miniconda3/envs/bisov/bin/python}"

if [ ! -x "$BISOV_PY" ]; then
  cat >&2 <<'EOF'
找不到 bisov 环境的 python。请先创建（只需一次，无需 sudo）：

  conda create -y -n bisov -c conda-forge --override-channels \
    python=3.12 "tk=8.6.13=xft_*" openpyxl

另外确保 ~/.config/fontconfig/fonts.conf 里加入了 <dir>/mnt/c/Windows/Fonts</dir>
并在之后执行过 fc-cache -f（详见 tools/bi_sov/PLAN.md §11）。
EOF
  exit 1
fi

cd "$HERE"
exec "$BISOV_PY" gui.py "$@"
