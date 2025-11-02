import json
import logging
from pathlib import Path
from typing import get_args

from discord import Bot
from pycord.localizer import I18n, Locale

logger = logging.getLogger(__name__)


class Localization:
	client: Bot
	i18n: I18n | None
	LOCALE_DATA: dict
	EXISTS_LOCALE_LIST: dict

	def __init__(self, client: Bot) -> None:
		self.client = client

	def load_locale_data(self) -> None:
		# 言語一覧
		self.LOCALE_DATA = {}
		self.EXISTS_LOCALE_LIST = {}

		# 言語ファイルを読み込む
		logger.info("言語ファイルを読み込み")
		for lang_code in get_args(Locale):
			# 言語ファイルのフォルダー
			lang_file_base_path = "./introqbot/locales"
			# - を _ へ置き換える
			lang = lang_code.replace("-", "_")
			# 言語ファイルのパス
			lang_file_path = Path(lang_file_base_path) / (lang + ".json")
			# 対象の言語ファイルが存在するかチェック
			if not Path(lang_file_path).exists():
				# ファイルが存在しない場合は英語 (en_GB) のファイルを読み込むようにする (フォールバック)
				logger.info("- %s -> en_GB (フォールバック)", lang)
				lang_file_path = Path(lang_file_base_path) / "en_GB.json"
			else:
				logger.info("- %s", lang)
				# 有効な言語一覧へ追加
				self.EXISTS_LOCALE_LIST[lang] = lang

			# 翻訳データを読み込む
			with Path(lang_file_path).open(encoding="utf-8") as lang_file:
				self.LOCALE_DATA[lang] = json.loads(lang_file.read())

			# 有効な言語一覧の名称を設定する
			if lang in self.EXISTS_LOCALE_LIST:
				self.EXISTS_LOCALE_LIST[lang] = self.LOCALE_DATA[lang]["strings"]["name"]

		# Pycord の多言語対応用クラスのインスタンスを生成
		self.i18n = I18n(self.client, consider_user_locale=True, **self.LOCALE_DATA)

	def localize_commands(self) -> None:
		logger.info("コマンドの多言語化実行")
		if self.i18n is not None:
			self.i18n.localize_commands()
			logger.info("- 完了")
		else:
			logger.error("- エラー: i18n is None")

	def translate(self, text: str, values: list | None = None, lang: str = "en_GB") -> str:
		if values is None:
			values = []

		try:
			if self.LOCALE_DATA is not None:
				return self.LOCALE_DATA[lang]["strings"][text].format(*values)
		except KeyError as e:
			logger.error("Translate Error - KeyError: %s", str(e))
			return text

		logger.error("Translate Error - LOCALE_DATA is None")
		return text
