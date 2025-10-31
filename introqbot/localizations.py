from pathlib import Path
from typing import ClassVar

import ezcord
import yaml

from introqbot.client import client
from introqbot.logger import logger


class Localization:
	LOCAL_FILE_PATH: Path = Path("./locales")
	LOCALE_LIST: ClassVar[list[str]] = ["en", "ja"]
	i18n = None
	LOCALE_DATA: dict
	EXISTS_LOCALE_LIST: dict

	@classmethod
	def load_locale_data(cls) -> None:
		"""言語データを読み込む"""
		# 言語一覧
		cls.LOCALE_DATA = {}
		cls.EXISTS_LOCALE_LIST = {}

		# 言語ファイルを読み込む
		logger.info("言語ファイルを読み込み")
		for lang_code in cls.LOCALE_LIST:
			# - を _ へ置き換える
			lang = lang_code.replace("-", "_")
			# 言語ファイルのパス
			lang_file_path = cls.LOCAL_FILE_PATH / "strings" / (lang + ".yaml")
			# 対象の言語ファイルが存在するかチェック
			if not Path(lang_file_path).exists():
				# ファイルが存在しない場合は英語 (en_GB) のファイルを読み込むようにする (フォールバック
				logger.info("- %s -> en (フォールバック)", lang)
				lang_file_path = cls.LOCAL_FILE_PATH / "strings" / "en.yaml"
			else:
				logger.info("- %s", lang)
				# 有効な言語一覧へ追加
				cls.EXISTS_LOCALE_LIST[lang] = lang

			# 翻訳データを読み込む
			with Path(lang_file_path).open(encoding="utf-8") as lang_file:
				cls.LOCALE_DATA[lang] = yaml.safe_load(lang_file)

			# 有効な言語一覧の名称を設定する
			if lang in cls.EXISTS_LOCALE_LIST:
				cls.EXISTS_LOCALE_LIST[lang] = cls.LOCALE_DATA[lang]["info"]["name"]

		# EzCord のローカライズ機能初期化
		ezcord.i18n.I18N(cls.LOCALE_DATA)

		# Pycord の多言語対応用クラスのインスタンスを生成
		# cls.i18n = I18n(client, consider_user_locale=True, **cls.LOCALE_DATA)

	@classmethod
	def localize_commands(cls) -> None:
		try:
			logger.info("コマンドの多言語実行")
			with (cls.LOCAL_FILE_PATH / "commands.yaml").open(encoding="utf-8") as lang_file:
				client.localize_commands(yaml.safe_load(lang_file))
		except Exception:
			logger.error("- エラー", exc_info=True)
		else:
			logger.info("- 完了")

	@classmethod
	def translate(cls, text: str, values: list | None = None, lang: str = "en_GB") -> str:
		if values is None:
			values = []

		try:
			if cls.LOCALE_DATA is not None:
				return cls.LOCALE_DATA[lang]["strings"][text].format(*values)
		except KeyError as e:
			logger.error("Translate Error - KeyError: %s", str(e))
			return text

		logger.error("Translate Error - LOCALE_DATA is None")
		return text


def translate(text: str, values: list | None = None, lang: str = "en_GB") -> str:
	"""指定されたキーのテキストを取得する"""
	return Localization.translate(text, values, lang)


_ = translate
