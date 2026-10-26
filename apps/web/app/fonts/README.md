# Dashboard font

`dashboard-font.woff2` is the real dashboard font: **Cairo** (variable),
self-hosted. It covers Arabic and Latin, with a variable weight range of
200–1000 (plus a slant axis, unused here).

- Font: Cairo (variable), Arabic + Latin coverage
- File: `dashboard-font.woff2` (~173 kB), converted from the source TTF with
  fontTools (`flavor: woff2`, variable axes kept)
- Source: <https://github.com/google/fonts> — `ofl/cairo/Cairo[slnt,wght].ttf`,
  downloaded from `main` at commit a2c83daed9bc723922de8d0a9512990bd3d91df4
  (2026-06-02); font internal version 3.130
- Licence: SIL Open Font License 1.1 — full text beside this file in `OFL.txt`

To replace it: download the variable TTF again (same source), convert it to
WOFF2 keeping the variable axes, overwrite `dashboard-font.woff2` (same name,
same folder), and update this README. If the weight range changes, edit
`weight` in `../fonts.ts` and re-run `npm run typecheck`, `lint` and
`next build` in `apps/web`. The app never requests a font from the web.
