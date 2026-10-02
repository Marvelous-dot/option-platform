#!/usr/bin/env bash
# P2 运维：源码/配置可恢复归档 + 一致性备份校验。
# v2 无 SQLite 持久化库（行情为实时抓取、内存快照），故备份=源码+前端构建+部署单元。
# 用法：./backup.sh [dest_dir]   默认 /root/option-platform-v2-backups
set -euo pipefail
SRC="/root/option-platform-v2"
DEST="${1:-/root/option-platform-v2-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${DEST}/${STAMP}"
mkdir -p "$OUT"

# 归档源码与构建产物（排除 node_modules、__pycache__、pytest_cache）
tar --exclude='node_modules' --exclude='__pycache__' --exclude='.pytest_cache' \
    -czf "$OUT/v2-source.tar.gz" -C "$(dirname "$SRC")" "$(basename "$SRC")"

# 生成清单 + sha256，供恢复校验
( cd "$OUT" && sha256sum v2-source.tar.gz > v2-source.sha256 )
echo "source-archived" > "$OUT/MANIFEST.txt"
echo "path=$OUT/v2-source.tar.gz" >> "$OUT/MANIFEST.txt"
cat "$OUT/v2-source.sha256" >> "$OUT/MANIFEST.txt"

# 容量控制：仅保留最近 5 份（非交互，显式 </dev/null 防止误读 stdin）
KEEP=5
mapfile -t OLD < <(ls -1d "$DEST"/[0-9]* 2>/dev/null | sort -r | tail -n +$((KEEP + 1)))
for d in "${OLD[@]:-}"; do
  [ -n "$d" ] && rm -rf "$d" </dev/null
done

# 一致性校验：解包到临时目录并核对哈希（sha256sum -c 须与哈希文件同目录运行）
TMP="$(mktemp -d)"
( cd "$OUT" && sha256sum -c v2-source.sha256 )
tar -xzf "$OUT/v2-source.tar.gz" -C "$TMP"
rm -rf "$TMP"
echo "[backup.sh] OK -> $OUT"
cat "$OUT/MANIFEST.txt"
