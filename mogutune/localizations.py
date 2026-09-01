# Copyright (c) 2026 Milkeyyy

import json
import logging
from importlib import resources
from typing import get_args

from discord import Bot, SlashCommandGroup, utils
from pycord.localizer import I18n, Locale
from pycord.localizer.i18n.choice import ChoiceLocalizer
from pycord.localizer.utils import add_localization

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
			# 言語ファイルのフォルダー (インストール済み core パッケージ内)
			lang_files = resources.files("mogutune_core") / "locales"
			# - を _ へ置き換える
			lang = lang_code.replace("-", "_")
			# 言語ファイルのパス
			lang_file = lang_files / (lang + ".json")
			# 対象の言語ファイルが存在するかチェック
			if not lang_file.is_file():
				# ファイルが存在しない場合は英語 (en_GB) のファイルを読み込むようにする (フォールバック)
				logger.info("- %s -> en_GB (フォールバック)", lang)
				lang_file = lang_files / "en_GB.json"
			else:
				logger.info("- %s", lang)
				# 有効な言語一覧へ追加
				self.EXISTS_LOCALE_LIST[lang] = lang

			# 翻訳データを読み込む
			with lang_file.open(encoding="utf-8") as lang_file_handle:
				self.LOCALE_DATA[lang] = json.loads(lang_file_handle.read())

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

	def localize_command_groups(self) -> None:
		logger.info("コマンドグループの多言語化実行")
		if self.i18n is None:
			logger.error("- エラー: i18n is None")
			return

		# pycord-localizer はコマンドグループとサブコマンドをローカライズできないため、ここで補助する
		for lang in self.EXISTS_LOCALE_LIST:
			# Discord のロケール形式へ正規化する (en_GB -> en-GB)
			locale = lang.replace("_", "-")
			for key, data in self.LOCALE_DATA[lang].get("commands", {}).items():
				# キーに空白がないものはコマンドグループ (通常コマンドは localize_commands() が処理済み)
				if " " not in key:
					group = utils.get(self.client.pending_application_commands, qualified_name=key)
					if not isinstance(group, SlashCommandGroup):
						continue
					self._apply_name_description(group, locale, data)
					continue
				# キーに空白があるものはサブコマンド (ルート名 と サブ名 に分割)
				root_name, sub_name = key.split(" ", 1)
				group = utils.get(self.client.pending_application_commands, qualified_name=root_name)
				if group is None:
					continue
				sub = utils.get(group.subcommands, name=sub_name)
				if sub is None:
					continue
				self._apply_name_description(sub, locale, data)
				if options := data.get("options"):
					self._localize_options(sub, locale, options)

	@staticmethod
	def _apply_name_description(target: object, locale: str, data: dict) -> None:
		"""コマンド名と説明文のローカライズを適用する"""
		if name := data.get("name"):
			add_localization(target, "name", locale, name)
		if description := data.get("description"):
			add_localization(target, "description", locale, description)

	@staticmethod
	def _localize_options(command: object, locale: str, options: dict) -> None:
		"""オプションの name / description / choices をローカライズする (pycord-localizer と同様)"""
		for option_name, localization in options.items():
			option = utils.get(command.options, name=option_name)
			if option is None:
				continue
			if op_name := localization.get("name"):
				add_localization(option, "name", locale, op_name)
			if op_description := localization.get("description"):
				add_localization(option, "description", locale, op_description)
			if op_choices := localization.get("choices"):
				ChoiceLocalizer.localize_choices(option, locale, op_choices)

	def translate(self, text: str, values: list | None = None, lang: str = "en_GB") -> str:
		if values is None:
			values = []

		tr_text = text

		try:
			if self.LOCALE_DATA is not None:
				tr_text = self.LOCALE_DATA[lang]["strings"][text].format(*values)
		except KeyError as e:
			logger.debug("Translate Error - KeyError: %s", str(e))
			tr_text = self.LOCALE_DATA["en_GB"]["strings"][text].format(*values)
		return tr_text
