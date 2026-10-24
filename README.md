# Open Imagine gallery

Images made with [Open Imagine](https://github.com/CJHwong/open-imagine), each with the exact prompt
and settings it was made with, so you can make it yourself.

**See it:** https://cjhwong.github.io/open-imagine-gallery/

The page is static: `index.html`, `app.js` and `style.css` read `catalog.json` and show the WebP
files in `img/` and `thumb/`.

## Rebuild

`build.py` builds the catalog and the images from a folder of studio outputs, where each PNG has a
JSON record of its request beside it. `names.json` gives images their titles and categories. It
needs [uv](https://docs.astral.sh/uv/) and `cwebp`.

```sh
uv run build.py <folder of studio outputs>
```
