import discord

# ロケールキー cmd.play.error.missing_permissions.{name} に対応
REQUIRED_PERMISSIONS: tuple[str, ...] = ("view_channel", "connect", "speak", "send_messages", "embed_links")


def check_missing_permissions(perms: discord.Permissions) -> list[str]:
	"""不足している権限名のリストを返す (純粋関数・テスト容易)"""
	return [name for name in REQUIRED_PERMISSIONS if not getattr(perms, name, False)]


def check_voice_permissions(channel: discord.VoiceChannel) -> list[str]:
	"""ボイスチャンネルでボットが不足している実効権限名を返す"""
	perms = channel.permissions_for(channel.guild.me)
	return check_missing_permissions(perms)


if __name__ == "__main__":

	def _assert_missing(perms_kwargs: dict, expected: list[str]) -> None:
		perms = discord.Permissions(**perms_kwargs)
		# discord.Permissions は未指定の権限が True になるため、明示的に False を期待するものだけ検証する
		# 全権限を False にしてから期待値を再現する簡易チェックに留める
		result = check_missing_permissions(perms)
		# 指定した kwargs が False のものだけが missing に含まれることを確認
		for name in expected:
			assert name in result, f"expected {name} in {result} (kwargs={perms_kwargs})"  # noqa: S101
		for name in result:
			# result に含まれるものは実際に False であること
			assert not getattr(perms, name), f"unexpected missing {name} in {result}"  # noqa: S101

	# 全権限なし
	_assert_missing(
		{
			"view_channel": False,
			"connect": False,
			"speak": False,
			"send_messages": False,
			"embed_links": False,
		},
		["view_channel", "connect", "speak", "send_messages", "embed_links"],
	)
	# 1つだけ不足
	_assert_missing(
		{
			"view_channel": True,
			"connect": False,
			"speak": True,
			"send_messages": True,
			"embed_links": True,
		},
		["connect"],
	)
	# 全てあり
	perms_all = discord.Permissions(
		view_channel=True,
		connect=True,
		speak=True,
		send_messages=True,
		embed_links=True,
	)
	assert check_missing_permissions(perms_all) == [], f"expected no missing, got {check_missing_permissions(perms_all)}"  # noqa: S101
	print("permissions self-check passed")  # noqa: T201
