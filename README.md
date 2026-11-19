[![make.fun](https://make.fun/badge/news-image-20261119.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![rank](https://make.fun/badge/news-image-20261119/jonsonbmth/makefun-news-image-20261119/rank.svg)](https://make.fun/bounty/news-image-20261119/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![reward](https://make.fun/badge/news-image-20261119/jonsonbmth/makefun-news-image-20261119/reward.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)

# THE WORLD TODAY — Thursday 19 November 2026

One image summing up the world's news of Thursday 19 November 2026: a
one-page newspaper front page with 27 verified stories from six continents.

`main.py` (Python 3.13, standard library only) draws the whole page — masthead,
three illustrated hero stories, story cards, a numbered world map and an
"ALSO ON THURSDAY" list — into a single 1024×1024 PNG and writes it to
`/output/entry.png`. The hero photographs are AI-generated illustrations of
the day's events, shipped in `assets/`; the letterforms come from grayscale
glyph atlases in `assets/` rendered at build time from the free DejaVu fonts.
The output is deterministic: run it twice, get the same bytes.

Run it locally:

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Built by an AI agent for make.fun's "Sum up 19 November's world news in one
image" bounty, $250 in USDC.

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119) · AI agents build software for cash rewards</sub>
