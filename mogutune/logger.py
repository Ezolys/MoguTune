import logging
import logging.handlers
from pathlib import Path


def setup_logging(console_level: int = logging.INFO, file_level: int = logging.DEBUG) -> None:
	"""アプリケーション全体のロガーを設定する関数"""
	# 1. ログ出力先のディレクトリを作成
	log_dir = Path("./logs")
	log_dir.mkdir(exist_ok=True)

	# 2. フォーマッタを定義
	# ログの出力形式をここで統一できる
	log_formatter = logging.Formatter(
		# [日時.ミリ秒] [ログレベル(左寄せ8文字)] [ロガー名] メッセージ
		fmt="[%(asctime)s.%(msecs)03d] [%(levelname)-8s] [%(name)s] %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S",
	)

	# 3. ルートロガーを取得
	# logging.getLogger() でルートロガーが取得できる
	root_logger = logging.getLogger()
	# ハンドラが処理するログの最低レベルをDEBUGに設定
	# これにより、各ハンドラがそれぞれのレベルでログをフィルタリングできる
	root_logger.setLevel(logging.DEBUG)

	# 4. コンソール出力用のハンドラ (StreamHandler)
	stream_handler = logging.StreamHandler()
	stream_handler.setLevel(console_level)  # コンソールにはINFO以上を表示
	stream_handler.setFormatter(log_formatter)
	root_logger.addHandler(stream_handler)

	# 5. ファイル出力用のハンドラ (RotatingFileHandler)
	# ファイルが一定サイズに達すると新しいファイルに切り替わる
	log_file_path = log_dir / "app.log"
	rotating_handler = logging.handlers.RotatingFileHandler(
		log_file_path,
		mode="a",
		maxBytes=1024 * 1024 * 5,  # 5MB
		backupCount=5,
		encoding="utf-8",
	)
	rotating_handler.setLevel(file_level)  # ファイルにはDEBUG以上の全てを記録
	rotating_handler.setFormatter(log_formatter)
	root_logger.addHandler(rotating_handler)

	# 6. ライブラリごとのログレベルを設定
	# Pycordのログは非常に多いので、重要なエラーのみに絞る
	logging.getLogger("discord").setLevel(logging.ERROR)
	# 必要に応じて他のライブラリのログレベルも設定できる
	# logging.getLogger("urllib3").setLevel(logging.INFO)

	logging.info("ロガーの設定が完了しました。")
