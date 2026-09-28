#!/usr/bin/env python3
"""Light SRT pass. Timestamps never leave this script."""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

MODEL = "deepseek-flash"
BATCH = 40
URL = "https://api.deepseek.com/chat/completions"

NAMES = [
    "Mecnun", "Mecnun Çınar", "Leyla", "Leyla Yılmaz", "İskender", "Pakize",
    "İsmail", "İsmail Abi", "Yavuz", "Erdal", "Erdal Bakkal", "Metin", "Sevim",
    "Arda", "Kamil", "Yedek Kamil", "Zeynep", "Sabiha", "Ak Sakallı Dede",
    "Az Sakallı Dede", "Karabasan", "Şirin", "Sedef", "Kireçburnu", "İzmit",
]

PROMPT = """You are correcting a Turkish subtitle file for the comedy series Leyla ile Mecnun. Make a light pass only.

You receive JSON: {"cues":[{"id":1,"text":"..."}]}.
Return JSON only: {"cues":[{"id":1,"text":"..."}]}.
Return every id once, in the same order. Do not add ids.

You may:
- add or fix punctuation, capitalization, and spacing
- replace a word only when it is an obvious misspelling of a name or place on the list

You may not:
- add, delete, merge, or split cues
- translate, summarize, or improve a joke
- replace a word because it sounds odd, ungrammatical, or incomplete
- turn slang, repetition, rhyme, or insults into standard Turkish
- add a name that is not already almost present
- fill in words you think the speaker meant

If you are not sure, leave the word unchanged.

Names and places:
""" + ", ".join(NAMES)


def tr_lower(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def squash(s):
    return re.sub(r"[^a-zçğıöşü0-9]", "", tr_lower(s))


def words(s):
    return re.findall(r"[0-9A-Za-zÇĞİÖŞÜçğıöşüÂâÎîÛû']+", s)


def levenshtein(a, b):
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def near_name(old, new):
    """New text must be exactly a listed name. Old text must be a close misspelling."""
    got = squash(new)
    if not got:
        return False
    for name in NAMES:
        if squash(name) != got:
            continue
        old_s = squash(old)
        dist = levenshtein(old_s, got)
        limit = 1 if len(got) <= 5 else 2
        return dist <= limit and dist / len(got) <= 0.34
    return False


def name_suffix_fix(old, new):
    """Same letters, apostrophe added to a listed name plus a short Turkish ending."""
    if squash(old) != squash(new):
        return False
    bare = squash(new)
    for name in NAMES:
        stem = squash(name)
        extra = len(bare) - len(stem)
        if bare.startswith(stem) and 0 <= extra <= 5:
            return True
    return False


def acceptable(old, new):
    if old == new:
        return True
    ow, nw = words(old), words(new)
    if [tr_lower(w) for w in ow] == [tr_lower(w) for w in nw]:
        return True
    ops = SequenceMatcher(a=ow, b=nw, autojunk=False).get_opcodes()
    i = 0
    while i < len(ops):
        if ops[i][0] == "equal":
            i += 1
            continue
        k = i
        while k < len(ops) and ops[k][0] != "equal":
            k += 1
        old_span = " ".join(ow[ops[i][1]:ops[k - 1][2]])
        new_span = " ".join(nw[ops[i][3]:ops[k - 1][4]])
        if not (near_name(old_span, new_span) or name_suffix_fix(old_span, new_span)):
            return False
        i = k
    return True


def parse_srt(text):
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        if len(lines) < 2 or "-->" not in lines[1]:
            raise SystemExit(f"bad cue:\n{block[:200]}")
        cues.append({"id": len(cues) + 1, "time": lines[1], "text": "\n".join(lines[2:])})
    return cues


def write_srt(cues, path):
    parts = [f"{c['id']}\n{c['time']}\n{c['text']}" for c in cues]
    Path(path).write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def call(cues, key):
    body = {
        "model": MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps({"cues": cues}, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as res:
                payload = json.loads(res.read().decode())
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
            got = {item["id"]: item["text"] for item in data["cues"]}
            if set(got) != {c["id"] for c in cues}:
                raise ValueError("cue ids mismatch")
            return got
        except (json.JSONDecodeError, ValueError, OSError) as err:
            last = err
    raise last


def pass_file(src, dst, key):
    cues = parse_srt(Path(src).read_text(encoding="utf-8"))
    kept = rejected = 0
    for start in range(0, len(cues), BATCH):
        batch = cues[start : start + BATCH]
        got = call([{"id": c["id"], "text": c["text"]} for c in batch], key)
        for cue in batch:
            new = got[cue["id"]].strip()
            if acceptable(cue["text"], new):
                if new != cue["text"]:
                    kept += 1
                cue["text"] = new
            else:
                rejected += 1
                print(f"reject {src} cue {cue['id']}", file=sys.stderr)
    write_srt(cues, dst)
    print(f"{src}: {len(cues)} cues, {kept} changed, {rejected} rejected")


def demo():
    assert acceptable("ben de taksideyim", "Ben de taksideyim.")
    assert acceptable("Akize geldi", "Pakize geldi")
    assert not acceptable("doktor noktor", "doktor doktor")
    assert not acceptable("Denekman geldi", "Mecnun geldi")
    assert not acceptable("greve mi gitsek", "grev mi gitsek")
    assert not acceptable("ben de taksideyim", "Eben de taksideyim")
    assert acceptable("Mecnuna dön.", "Mecnun'a dön.")
    assert acceptable("Karabasandır oğlum o be.", "Karabasan'dır oğlum o be.")
    assert acceptable("Aksakallı dedenin mucizesi.", "Ak Sakallı Dede'nin mucizesi.")
    assert not acceptable("çayrak altınımı takarım", "çeyrek altınımı takarım")
    assert not acceptable("Kököteni terk mi ettin?", "Yoksa seni terk mi ettin?")
    print("check ok")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        demo()
        return
    if len(sys.argv) != 3:
        raise SystemExit("usage: light-pass.py INPUT.srt OUTPUT.srt")
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SystemExit("set DEEPSEEK_API_KEY")
    pass_file(sys.argv[1], sys.argv[2], key)


if __name__ == "__main__":
    main()
