"""Replace episode 71's repeated-text gap with locally cross-checked dialogue."""

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("align-episodes.py")
SPEC = importlib.util.spec_from_file_location("align_episodes", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

VIDEO = next(MODULE.EPISODES.glob("071 - *.webm"))
SOURCE = MODULE.OUTPUT
DESTINATION = MODULE.OUTPUT.parent / "episode-071-repair"

# These lines cover 49:51 to 50:27, where the original ASR repeated "çat"
# and omitted several turns. Turbo and Stable-ts agree on the later dialogue.
REPLACEMENT = [
    (2991.39, 2995.00, "E yeter be, ne oluyor böyle çat çat?", "Enough! What's with all that banging?"),
    (2995.00, 3000.32, "Uyutmadınız adamı.", "You wouldn't let a man sleep."),
    (3001.05, 3005.70, "Dede! Dede, yardım et! Oho, siz ne yapıyorsunuz orada ya?", "Grandpa, help! Hey, what are you doing over there?"),
    (3006.11, 3008.58, "Boşuna uğraşıyorsunuz. Ben onda oyun oynayamam.", "You're wasting your time. I can't play games on it."),
    (3008.64, 3009.70, "Tetris bile oynayamıyorum.", "I can't even play Tetris."),
    (3010.01, 3012.96, "Oradaki verileri NASA'ya göndereceklermiş.", "They said they'd send the data to NASA."),
    (3013.20, 3014.68, "Delileri Manisa'ya mı göndereceklermiş?", "Send the lunatics to Manisa?"),
    (3014.68, 3017.32, "Öyle gibi yani. Neticede öyle bir şey olacak.", "Something like that. That's what'll happen."),
    (3017.38, 3018.56, "Ben gerçekten anlamadım, dede.", "I really didn't get it, Grandpa."),
    (3018.58, 3019.46, "Ne demek istedin orada?", "What did you mean?"),
    (3019.48, 3021.78, "Orada verilerin varmış senin. Ne verdiysen oraya.", "Your data is there, whatever you put in."),
    (3021.94, 3023.74, "İşte onları NASA'ya gönderecekler.", "They're sending it to NASA."),
    (3024.40, 3025.98, "Ha, okey, tamam, eyvallah.", "Oh, okay. Thanks."),
    (3026.12, 3027.20, "Ben bir şey rica edebilir miyim?", "Can I ask a favor?"),
]


def repair() -> None:
    # 1. Read the aligned candidates and check the exact source interval.

    turkish = MODULE.read_srt(SOURCE / f"{VIDEO.stem}.tr.srt")
    english = MODULE.read_srt(SOURCE / f"{VIDEO.stem}.en.srt")
    if len(turkish) != len(english):
        raise ValueError("Episode 71 candidate languages have different cue counts")

    if "çat çat çat" not in turkish[890]["text"] or "çat çat çat" not in turkish[891]["text"]:
        raise ValueError("Episode 71 repeated-text cues have changed")

    if turkish[892]["start"] < REPLACEMENT[-1][1]:
        raise ValueError("Replacement overlaps the following cue")

    # 2. Replace only the two corrupt cues and keep both languages paired.

    for language, cues, text_index in (
        ("tr", turkish, 2),
        ("en", english, 3),
    ):
        inserted = [
            {"id": 0, "start": line[0], "end": line[1], "text": line[text_index]}
            for line in REPLACEMENT
        ]
        repaired = cues[:890] + inserted + cues[892:]
        for number, cue in enumerate(repaired, start=1):
            cue["id"] = number

        if any(first["end"] > second["start"] for first, second in zip(inserted, inserted[1:])):
            raise ValueError("Replacement cues overlap")

        DESTINATION.mkdir(parents=True, exist_ok=True)
        MODULE.write_srt(DESTINATION / f"{VIDEO.stem}.{language}.srt", repaired)


if __name__ == "__main__":
    repair()
