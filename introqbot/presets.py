import json
import logging
from pathlib import Path
from typing import ClassVar, get_args

from discord import OptionChoice
from pycord.localizer import Locale

logger = logging.getLogger(__name__)


class PlaylistPresets:
	"""プレイリストのプリセット"""

	PRESET_LIST: ClassVar[dict]

	@classmethod
	def load(cls) -> None:
		logger.info("プレイリストプリセットファイルを読み込み")
		with Path("./introqbot/resources/presets.json").open(encoding="utf-8") as presets_file:
			cls.PRESET_LIST = json.loads(presets_file.read())["presets"]

	@classmethod
	def get_presets(cls) -> list[OptionChoice]:
		"""プレイリストのプリセットをDiscordのコマンドオプションの選択肢として取得する"""
		presets = []
		for url, info in cls.PRESET_LIST.items():
			title = ""
			desc = ""
			name_loc = {}
			for lang_code in get_args(Locale):
				if info.get("title_" + lang_code) is not None and info.get("description_" + lang_code) is not None:
					name_loc[lang_code] = f"{info.get('title_' + lang_code)} | {info.get('description_' + lang_code)}"
					# title = info.get("title_" + lang_code)
					# desc = info.get("description_" + lang_code)
				title = info.get("title_" + "en_GB")
				desc = info.get("description_" + "en_GB")
			presets.append(OptionChoice(name=f"{title} | {desc}", value=url, name_localizations=name_loc))
		return presets


if __name__ == "__main__":
	logging.basicConfig(level=logging.DEBUG)
