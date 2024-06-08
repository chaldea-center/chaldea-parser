from pathlib import Path
import requests
import re
import pyperclip


def convert_varname(name: str) -> str:
    words = name.split("_")
    out = words.pop(0).lower()
    for word in words:
        out += word.lower().title()
    if re.match(r"^\d", out):
        out = "k" + out
    assert re.match(r"^[a-zA-Z][0-9a-zA-Z_]*$", out), (name, out)
    return out


def main():
    url = "https://api.atlasacademy.io/export/JP/NiceConstant.json"
    const_ints: dict[str, int] = requests.get(url).json()
    const_ints = {convert_varname(k): const_ints[k] for k in sorted(const_ints.keys())}
    code = """
@JsonSerializable()
class GameConstants {"""
    for k, v in const_ints.items():
        code += f"\n  final int {k}; // {v}"
    code += "\n\n  const GameConstants({"
    for k, v in const_ints.items():
        code += f"\n    this.{k} = {v},"
    code += "\n  });\n"
    pyperclip.copy(code)
    print(f"copied {len(const_ints)} int vals to clipboard")


if __name__ == "__main__":
    main()
