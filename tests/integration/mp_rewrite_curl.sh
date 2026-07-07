#!/usr/bin/env bash

# 公众号文章改写接口 curl 调用示例（集成测试 shell 版）
#
# 特色：演示如何用 `content_path` 传本地文件路径，避免把大段原文塞进 JSON body，
# 从而显著减少客户端 → 服务端的传输 token 与请求体大小。
#
# 用法（在项目根目录执行）：
#   chmod +x tests/integration/mp_rewrite_curl.sh
#   APP_API_KEY=your-key ./tests/integration/mp_rewrite_curl.sh
#
# 可选环境变量：
#   MP_BASE_URL   默认 http://127.0.0.1:8072
#   APP_API_KEY   作为 X-API-Key 发送到服务端
#   MP_ARTICLE_1  第一篇原文的本地文件路径（默认自动生成一份示例文本）
#   MP_ARTICLE_2  第二篇原文的本地文件路径（可选）
#
# 服务端安全提示：
#   若配置了 APP_MP_ARTICLE_READ_ROOT，则 content_path 必须位于该目录之下，
#   否则服务端会拒绝读取，防止目录穿越攻击。

set -euo pipefail

BASE_URL="${MP_BASE_URL:-http://127.0.0.1:8072}"
API_KEY="${APP_API_KEY:-test-key}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 若未指定第一篇原文路径，则自动生成一份示例文件
DEFAULT_ARTICLE_1="${SCRIPT_DIR}/mp_sample_article_1.txt"
if [[ -z "${MP_ARTICLE_1:-}" ]]; then
  if [[ ! -f "$DEFAULT_ARTICLE_1" ]]; then
    cat > "$DEFAULT_ARTICLE_1" <<'EOF'
标题：地中海饮食为什么能长期坚持

正文：
最近越来越多的营养学研究指向同一个结论——地中海饮食不仅有助于减脂，
更重要的是它足够"日常"，不需要精确称重，也不需要极端戒断某类食物。

核心结构大致是：全谷物 + 蔬菜水果 + 优质蛋白（鱼、豆类为主）+ 橄榄油，
再配合适量的坚果与发酵乳制品。它并不是一种"食谱"，而是一种可以长期
维持的生活方式。
EOF
    echo "ℹ 已自动生成示例原文: $DEFAULT_ARTICLE_1"
  fi
  MP_ARTICLE_1="$DEFAULT_ARTICLE_1"
fi

if [[ ! -f "$MP_ARTICLE_1" ]]; then
  echo "❌ 找不到原文文件: $MP_ARTICLE_1" >&2
  exit 1
fi

# 组装 source_articles 数组（支持可选的第二篇）
if [[ -n "${MP_ARTICLE_2:-}" ]]; then
  if [[ ! -f "$MP_ARTICLE_2" ]]; then
    echo "❌ 找不到原文文件: $MP_ARTICLE_2" >&2
    exit 1
  fi
  SOURCE_ARTICLES=$(cat <<EOF
[
  {"title": "示例原文一", "content_path": "${MP_ARTICLE_1}"},
  {"title": "示例原文二", "content_path": "${MP_ARTICLE_2}"}
]
EOF
)
else
  SOURCE_ARTICLES=$(cat <<EOF
[
  {"title": "示例原文一", "content_path": "${MP_ARTICLE_1}"}
]
EOF
)
fi

REWRITE_INTENT="面向普通人，把这些素材改写成一篇轻松易读、能引导读者收藏转发的公众号推文"
TARGET_STYLE="生活化、生动比喻，避免生硬说教，语言正向积极，实事求是"

PAYLOAD=$(cat <<EOF
{
  "rewrite_intent": "${REWRITE_INTENT}",
  "target_style": "${TARGET_STYLE}",
  "source_articles": ${SOURCE_ARTICLES}
}
EOF
)

echo "➡ 调用 ${BASE_URL}/api/v1/mp/articles/rewrite ..."
echo "   使用 content_path（本地文件路径）传原文，节省请求体 token"

curl -v \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  "${BASE_URL}/api/v1/mp/articles/rewrite"

echo
