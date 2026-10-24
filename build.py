# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow"]
# ///
"""Build the gallery from a study folder: catalog.json plus a WebP and a thumbnail per image.

    uv run build.py <study folder>

Each study image has a JSON record beside it with the request it was sent and the result the
server returned. The catalog keeps only the inputs the model received. names.json gives each By
use image its title and category, and names a few others. Needs cwebp.
"""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SETUP = {
    "model": "Qwen-Image 2.1 Turbo",
    "machine": "an Apple M5 Pro laptop (64 GB)",
    "app": "Open Imagine",
    "app_url": "https://github.com/CJHwong/open-imagine",
}
DEFAULT_GUIDANCE = {"generate": 1.0, "edit": 1.0}
# Backends other than the one SETUP names, by the id the request sent, as the page shows them.
OTHER_MODELS = {"qwen21": "Qwen-Image 2.1"}

# The hero mosaic, in its order: the first fills a tall cell and the fifth a wide one.
FEATURED = [
    "1960s-psychedelic-poster",
    "zoom-burst-radial-streaks",
    "double-exposure-a-silhouette-filled-with-a-second-scene",
    "night-lights-turned-into-round-bokeh",
    "rinpa-gold-folding-screen",
    "infrared-film-pink-and-red-trees",
    "synthwave",
]
CACHE = HERE / ".cache"  # encoded files under the study's own names, so a rename skips encoding
# The page's topics in order, each in one of its three tabs. By use images take their topic from
# names.json; the other tabs take it from the study folder.
TOPICS = {
    "Showcase": "showcase",
    "Street and travel photography": "make",
    "Portraits": "make",
    "Product photography and ads": "make",
    "Graphic design and lettering": "make",
    "Character design, stickers and icons": "make",
    "Anime": "make",
    "Game and film concept art": "make",
    "Scientific and architectural illustration": "make",
    "Craft, print and fashion": "make",
    "Photo editing and retouching": "make",
    "From brief to final": "make",
    "Art movements and periods": "compare",
    "Lenses, film stock and lighting": "compare",
    "Animation styles": "compare",
    "Cinematic styles": "compare",
    "One prompt, three results": "compare",
}
FOLDER_TOPICS = {
    "19_showcase": "Showcase",
    "15_art_history": "Art movements and periods",
    "16_camera_lens_film": "Lenses, film stock and lighting",
    "13_animation_styles": "Animation styles",
    "14_director_visions": "Cinematic styles",
    "18_seed_recheck": "One prompt, three results",
}
MAKE_FOLDERS = {
    "01_prompt_wording",
    "03_text_and_layout",
    "04_illustration_and_characters",
    "05_games_and_film",
    "06_commerce_and_product",
    "07_learning_and_architecture",
    "08_craft_and_fashion",
    "09_edits",
    "11_street_and_candid",
    "12_anime",
    "17_guided_flow",
    "fill_rounds",
}
# Rounds made to fill thin By use topics. Each image's topic and title come from names.json.
FILL_ROUNDS = ("r15/", "r16/", "r19/", "r20/")
# Showcase rounds, in the order they lead the tab: full-model renders, then the masterpieces
# made on Turbo, then style combinations, then the first showcase round.
SHOWCASE_ROUNDS = ("r18/", "r14/", "r17/", "r13/")
# Masterpieces whose full-model render beat the Turbo image. The other renders came back the same
# or worse, so the page keeps their Turbo image.
FULL_MODEL_WINS = {"01_glass_whale", "03_dragon_mountains"}
# Study images that must not be published: a real person's likeness, a real mark, nudity, or a
# living artist's signature motif.
EXCLUDE = {"r12/out_g/g8_kahlo_name.png", "r13/out_s/s083.png", "r13/out_s/s099.png"}
# Round 1 made each brief twice: as written, and after Open Imagine's Rewrite. By use shows the
# rewritten one, except where the study judged the brief better (lost text, a recased brand name,
# a stylized look drifting to realism, a cropped figure).
REWRITE_LOST = {"07_logo", "11_infographic", "22_tattoo_flash", "23_avatar", "25_3d_render"}
REWRITE_NOTE = "Open Imagine's Rewrite wrote this prompt from a one-line request"


def collector(study: Path):
    spec = importlib.util.spec_from_file_location("collect", study / "harness" / "collect.py")
    module = importlib.util.module_from_spec(spec)
    sys.argv = [
        sys.argv[0],
        str(study),
        str(study / "unused"),
    ]  # collect.py reads its paths at import
    spec.loader.exec_module(module)
    return module


def showcase_rank(stem: str) -> int:
    """The position of a showcase image's round in SHOWCASE_ROUNDS; other images rank last."""
    rounds = [name.rstrip("/") for name in SHOWCASE_ROUNDS]
    return next((rank for rank, name in enumerate(rounds) if stem.startswith(name)), len(rounds))


def rerendered(png: Path, study: Path) -> bool:
    """One of a Turbo masterpiece and its full-model render, whichever looked worse: the page shows
    the other. The full model won only where FULL_MODEL_WINS says."""
    if png.parent == study / "r14" / "out_x":
        return png.stem[1:] in FULL_MODEL_WINS
    return png.parent.parent == study / "r18" and png.stem[1:] not in FULL_MODEL_WINS


def verdicts(study: Path) -> dict[str, list]:
    """name -> [look, verdict, watch for] from every verdict file in the index folder."""
    rows = {}
    for path in (study / "index").glob("verdicts_*.json"):
        for table in json.loads(path.read_text()).values():
            rows.update({name: row for name, row in table.items() if not name.startswith("_")})
    for showcase in study.glob("r1[3-9]/verdicts_*.json"):
            rows.update(json.loads(showcase.read_text()))
    return rows


def shared_fields(folder: Path) -> dict:
    """The fields a batch sent once for every item, from the folder's saved request."""
    for path in sorted(folder.glob("_batch*/batch.json")) + [folder / "_request.json"]:
        if path.exists():
            data = json.loads(path.read_text())
            return data.get(
                "defaults",
                {k: v for k, v in data.items() if k not in ("items", "client_id", "count")},
            )
    return {}


def inputs(png: Path, shared: dict) -> dict | None:
    """What the model received, as a reader would want to retype it."""
    record_path = png.with_suffix(".json")
    if not record_path.exists():
        return None
    record = json.loads(record_path.read_text())
    request, result = record.get("request", {}), record.get("result", {})
    sent = {**shared, **request}
    mode = result.get("mode") or sent.get("mode", "generate")
    fields = {
        "mode": mode,
        "prompt": result.get("prompt") or sent.get("prompt", ""),
        "negative": sent.get("negative") or "",
        "size": f"{result['width']} x {result['height']}"
        if result.get("width")
        else sent.get("size", ""),
        "seed": result.get("seed", sent.get("seed")),
        "steps": result.get("steps", 8),
    }
    knob = "guidance" if mode == "generate" else "cfg"
    fields[knob] = sent.get(knob, 2.5 if fields["negative"] else DEFAULT_GUIDANCE[mode])
    for key in ("strength", "resolution"):
        if key in sent:
            fields[key] = sent[key]
    if sent.get("backend") in OTHER_MODELS:
        fields["model"] = OTHER_MODELS[sent["backend"]]
    if sent.get("rewrite"):
        fields["note"] = "Open Imagine's Rewrite expanded a short request into this prompt"
    fields["seconds"] = result.get("elapsed")
    refs = record.get("refs") or request.get("ref_files") or []
    return {"inputs": fields, "refs": [str(Path(r).expanduser()) for r in refs]}


def encode(source: Path, stem: str) -> None:
    """A full-size WebP and a 480-pixel WebP thumbnail in the cache; skip files already built."""
    jobs = [
        (CACHE / "img" / f"{stem}.webp", ["-q", "88"]),
        (CACHE / "thumb" / f"{stem}.webp", ["-q", "75", "-resize", "480", "0"]),
    ]
    for target, options in jobs:
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        command = ["cwebp", "-quiet", *options, str(source), "-o", str(target)]
        subprocess.run(command, check=True, capture_output=True)


def publish(files: dict[str, str]) -> None:
    """Link each cached file under its page name, and remove page files no image uses any more."""
    for folder in ("img", "thumb"):
        (HERE / folder).mkdir(exist_ok=True)
        wanted = {f"{name}.webp" for name in files}
        for old in (HERE / folder).iterdir():
            if old.name not in wanted:
                old.unlink()
        for name, stem in files.items():
            target = HERE / folder / f"{name}.webp"
            if not target.exists():
                target.hardlink_to(CACHE / folder / f"{stem}.webp")


def fingerprint(stem: str) -> int:
    """A 64-bit difference hash of the thumbnail: near-identical images differ in a few bits."""
    from PIL import Image

    pixels = Image.open(CACHE / "thumb" / f"{stem}.webp").convert("L").resize((9, 8)).tobytes()
    return sum(
        1 << k for k in range(64) if pixels[k // 8 * 9 + k % 8] > pixels[k // 8 * 9 + k % 8 + 1]
    )


def look_alike(item: dict, other: dict) -> bool:
    """Near-identical thumbnails of related prompts. The prompt test keeps two unrelated grids on
    white apart: a sticker sheet and a lantern prop sheet differed in one bit of the hash."""
    close = (item["_hash"] ^ other["_hash"]).bit_count() <= 5
    return close and similar(item["prompt"], other["prompt"]) >= 0.3


def distinct(items: list[dict]) -> list[dict]:
    """One image per prompt (or a prompt with nine words in ten the same) and per look-alike
    group, so a visitor does not scroll past repeats.

    The study re-ran prompts at more seeds, A/B-tested wording that changed nothing visible, and
    chained edits that change one detail. An edit wins its group, since its detail view shows the
    image it came from. That holds for a repeated prompt too: a final made from a concept keeps
    the concept's prompt, so the image with a reference is met first.
    """
    groups: list[list[dict]] = []
    prompts: list[str] = []
    for item in sorted(items, key=lambda item: not item["refs"]):
        if any(similar(item["prompt"], prompt) >= 0.9 for prompt in prompts):
            continue
        prompts.append(item["prompt"])
        item["_hash"] = fingerprint(item["stem"])
        for group in groups:
            if any(look_alike(item, other) for other in group):
                group.append(item)
                break
        else:
            groups.append([item])
    kept = [next((i for i in group if i["refs"]), group[0]) for group in groups]
    for item in kept:
        del item["_hash"]
    return kept


def topic_for(relative: str, study: Path, collect) -> str | None:
    """The page topic of a study image, or None when the page leaves it out."""
    if relative.startswith(SHOWCASE_ROUNDS):
        return "19_showcase"
    if relative.startswith(FILL_ROUNDS):
        return "fill_rounds"
    name = Path(relative).name
    if relative.startswith("r1/rewritten"):
        return None if Path(name).stem in REWRITE_LOST else collect.topic_of(f"r1/brief/{name}")
    rewritten = any(
        (study / "r1" / folder / name).exists() for folder in ("rewritten", "rewritten30")
    )
    if relative.startswith("r1/brief/") and rewritten and Path(name).stem not in REWRITE_LOST:
        return None
    return collect.topic_of(relative)


def words(prompt: str, ignore: frozenset[str] = frozenset()) -> set[str]:
    return set(re.findall(r"\w+", prompt.lower())) - ignore


def similar(a: str, b: str, ignore: frozenset[str] = frozenset()) -> float:
    """Share of words two prompts have in common, leaving out the words in ignore."""
    words_a, words_b = words(a, ignore), words(b, ignore)
    return len(words_a & words_b) / max(1, len(words_a | words_b))


def grouped(items: list[dict]) -> list[dict]:
    """Keep the topic order, and inside a topic put prompts about the same subject together.

    A topic often repeats one style sentence in every prompt, so the words in more than a quarter
    of a topic's prompts do not count toward the match.
    """
    ordered = []
    for topic in TOPICS:
        members = [item for item in items if item["topic"] == topic]
        counts: dict[str, int] = {}
        for item in members:
            for word in words(item["prompt"]):
                counts[word] = counts.get(word, 0) + 1
        common = frozenset(word for word, n in counts.items() if n > max(2, len(members) / 4))
        groups: list[list[dict]] = []
        for item in members:
            score, match = max(
                ((similar(group[0]["prompt"], item["prompt"], common), group) for group in groups),
                key=lambda pair: pair[0],
                default=(0.0, None),
            )
            if match is not None and score >= 0.3:
                match.append(item)
            else:
                groups.append([item])
        ordered += [item for group in groups for item in group]
    return ordered


def stem_of(relative: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", relative.removesuffix(".png").lower()).strip("-")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def page_names(items: list[dict]) -> None:
    """Name each image after its title; a repeated title takes -2, -3 in page order."""
    taken: dict[str, int] = {}
    for item in items:
        base = slug(item["title"]) or "image"
        taken[base] = taken.get(base, 0) + 1
        item["id"] = base if taken[base] == 1 else f"{base}-{taken[base]}"


def ref_stem(path: str) -> str:
    """A reference's cache name, without the study's numbering."""
    return "ref-" + slug(re.sub(r"^[a-z]?\d+[a-z]?_", "", Path(path).stem))


def main() -> int:
    study = Path(sys.argv[1]).expanduser()
    collect = collector(study)
    names = json.loads((HERE / "names.json").read_text())
    looks = verdicts(study)
    items, skipped = [], []
    for png in sorted(study.glob("r*/**/*.png")):
        relative = png.relative_to(study).as_posix()
        if "/_" in relative or "/sheets/" in relative or relative in EXCLUDE:
            continue
        if rerendered(png, study):
            continue
        folder = topic_for(relative, study, collect)
        named = names.get(relative, {})
        topic = named.get("category") if folder in MAKE_FOLDERS else FOLDER_TOPICS.get(folder)
        record = inputs(png, shared_fields(png.parent)) if topic else None
        if record is None:
            skipped.append(relative)
            continue
        if relative.startswith("r1/rewritten"):
            record["inputs"]["note"] = REWRITE_NOTE
        stem = stem_of(relative)
        encode(png, stem)
        for ref in record["refs"]:
            encode(Path(ref), ref_stem(ref))
        look = looks.get(png.stem)
        items.append(
            {
                "stem": stem,
                "topic": topic,
                "group": TOPICS[topic],
                "refs": [ref_stem(ref) for ref in record["refs"]],
                "title": look[0] if look else named.get("title", topic),
                "verdict": look[1] if look else "",
                "watch": look[2] if look else "",
                **record["inputs"],
            }
        )
    uses = grouped(distinct([item for item in items if item["group"] == "make"]))
    repeats = sum(item["group"] == "make" for item in items) - len(uses)
    order = list(TOPICS)
    items = sorted(
        [item for item in items if item["group"] != "make"] + uses,
        key=lambda item: (order.index(item["topic"]), showcase_rank(item["stem"])),
    )
    page_names(items)
    files = {item["id"]: item.pop("stem") for item in items}
    files.update({ref: ref for item in items for ref in item["refs"]})
    publish(files)
    missing = [name for name in FEATURED if name not in files]
    if missing:
        sys.exit(f"featured images not in the catalog: {missing}")
    catalog = {"setup": SETUP, "topics": order, "featured": FEATURED, "items": items}
    (HERE / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    )
    print(
        f"{len(items)} images in the catalog; {repeats} repeats left out of By use; "
        f"{len(skipped)} skipped without a topic, a record or a By use name"
    )
    for relative in skipped:
        print(f"  skipped {relative}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
