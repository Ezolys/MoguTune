try:
	from dotenv import load_dotenv

	load_dotenv()
except ImportError:
	pass

from mogutune.client import run


def main() -> None:
	run()


if __name__ == "__main__":
	main()
