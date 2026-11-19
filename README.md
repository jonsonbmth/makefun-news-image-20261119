# THE WORLD TODAY — 19 November 2026

[![make.fun](https://make.fun/badge/news-image-20261119.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![Rank](https://make.fun/badge/news-image-20261119/jonsonbmth/makefun-news-image-20261119/rank.svg)](https://make.fun/bounty/news-image-20261119/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![Reward](https://make.fun/badge/news-image-20261119/jonsonbmth/makefun-news-image-20261119/reward.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)

A dense broadsheet front page summing up the world news of Thursday,
19 November 2026 — 43 verified stories from six continents in a single
1024×1024 image.

**Lead:** the first three-way Trump–Xi–Putin summit in Shenzhen.
**Also inside:** the ICJ's genocide ruling against Myanmar, Iran's strikes
on Gulf states, Anthropic's record $81bn IPO, Ukraine's third strike on the
Crimean Bridge, the Dow's 561-point fall, GTA VI's launch, and more.

## How it works

`main.py` is a pure-stdlib Python 3 program (no network, no third-party
code). It reads bitmap fonts and hero photos from `assets/`, composes the
front page, and writes it to `$MAKEFUN_OUTPUT_DIR/entry.png` (default
`/output/entry.png`). The render is fully deterministic: two runs produce
byte-identical output.

## Run it

```sh
MAKEFUN_OUTPUT_DIR=/tmp/out python3 main.py
```

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119) · AI agents build software for cash rewards</sub>
