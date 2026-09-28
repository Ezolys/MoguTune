# Copyright (c) 2026 Milkeyyy

"""クイズ結果表示の整形 (文字数制限・ページネーション)"""

EMBED_DESCRIPTION_MAX = 4096
"""埋め込み description の最大文字数 (Discord 制限)"""

USERNAME_MAX = 32
"""Discord のユーザー名・表示名の最大文字数"""

USER_LINE_OVERHEAD = 4
"""ユーザー1行あたりの装飾文字数の目安 ("  - " や順位アイコンなど)"""

USER_LINE_MIN_WIDTH = USERNAME_MAX + USER_LINE_OVERHEAD
"""ユーザー行の見積り幅 (メンションが表示名として展開された場合の最大幅)"""

MARGIN = 64
"""埋め込みの上限に達しないための安全マージン"""

LIST_MAX_CHARS = 1024
"""ランキング・リーダーボードなど一覧表示の最大文字数"""

RANK_ICONS = {1: "🥇", 2: "🥈", 3: "🥉"}
"""上位3位までの順位アイコン"""


def rank_icon(rank: int) -> str:
	"""順位に応じたアイコンを返す (4位以降は順位の数値)"""
	return RANK_ICONS.get(rank, f"**{rank}**")


def truncate_lines(lines: list[str], max_chars: int, *, min_line_width: int = 0) -> tuple[list[str], int]:
	"""先頭から max_chars に収まる行だけを残し、(採用した行, 除外した行数) を返す

	ユーザー行は min_line_width に USER_LINE_MIN_WIDTH を渡すことで、メンションが展開された
	表示名 (最大32文字) を基準に見積もる (人数ではなく文字数基準で表示数を制限する)
	"""
	kept: list[str] = []
	used = 0
	for i, line in enumerate(lines):
		cost = max(len(line), min_line_width)
		required = cost if not kept else used + 1 + cost
		if required > max_chars:
			return kept, len(lines) - i
		kept.append(line)
		used = required
	return kept, 0


def paginate_lines(lines: list[str], max_chars: int) -> list[str]:
	"""行を改行で結合しつつ max_chars 以内のページに分割する (1行が上限を超える場合は切り詰める)"""
	pages: list[str] = []
	current: list[str] = []
	used = 0
	for raw_line in lines:
		line = raw_line[:max_chars]
		required = len(line) if not current else used + 1 + len(line)
		if current and required > max_chars:
			pages.append("\n".join(current))
			current = [line]
			used = len(line)
			continue
		current.append(line)
		used = required
	if current:
		pages.append("\n".join(current))
	return pages


if __name__ == "__main__":
	# truncate_lines の自己チェック
	assert truncate_lines([], 100) == ([], 0)  # noqa: S101
	# 10文字の行は "10 + 1 + 10 + 1 + 10 = 32" まで3行、4行目は 43 で超過
	_kept, _omitted = truncate_lines(["a" * 10] * 10, 35)
	assert (_kept, _omitted) == (["a" * 10] * 3, 7)  # noqa: S101
	# メンション行は USER_LINE_MIN_WIDTH (36) として見積もる
	_kept, _omitted = truncate_lines(["<@1>", "<@2>", "<@3>"], 73, min_line_width=USER_LINE_MIN_WIDTH)
	assert (_kept, _omitted) == (["<@1>", "<@2>"], 1)  # noqa: S101
	# 1行目が上限を超える場合は0行
	assert truncate_lines(["x" * 10], 5) == ([], 1)  # noqa: S101

	# paginate_lines の自己チェック
	assert paginate_lines([], 10) == []  # noqa: S101
	assert paginate_lines(["aaa", "bbb", "ccc"], 7) == ["aaa\nbbb", "ccc"]  # noqa: S101
	assert paginate_lines(["x" * 12], 10) == ["x" * 10]  # noqa: S101
	print("results self-check passed")  # noqa: T201
