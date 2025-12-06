import json


def load_json(path):
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def flatten_dict(d, parent_key="", sep="."):
	items = []
	for k, v in d.items():
		new_key = f"{parent_key}{sep}{k}" if parent_key else k
		if isinstance(v, dict):
			items.extend(flatten_dict(v, new_key, sep=sep).items())
		else:
			items.append((new_key, v))
	return dict(items)


ja = load_json("resources/locales/ja.json")
en = load_json("resources/locales/en_GB.json")

ja_flat = flatten_dict(ja)
en_flat = flatten_dict(en)

missing_keys = [k for k in ja_flat if k not in en_flat]
extra_keys = [k for k in en_flat if k not in ja_flat]

print("Missing keys in en_GB.json:")
for k in missing_keys:
	print(f"- {k}")

print("\nExtra keys in en_GB.json:")
for k in extra_keys:
	print(f"- {k}")
