# _template

스와이프형 카드뉴스 재사용 스캐폴드. `dynamic-duo-album-1/`을 주제 중립으로
일반화한 것 — 색·폰트·문구가 전부 `content.json`에서 나오므로 어떤 주제든
이 파일 하나만 채우면 된다.

## 새 카드뉴스 만들기

```bash
cp -r _template <새-프로젝트-이름>
cd <새-프로젝트-이름>
```

1. **`content.json` 편집** — `meta`(제목/slug), `theme`(색 4~6쌍), `brand`,
   `cover`, `cards[]`, `closing`. 기본값은 이 템플릿 자체 사용법을 설명하는
   3장짜리 데모다 — 구조 참고용으로 먼저 빌드해서 확인해도 된다.
2. **이미지 필요하면** `assets/media/<stem>.jpg`(또는 png/webp)로 넣고
   해당 카드에 `"media": {"image": "<stem>", "href": "...", "cta": "..."}`.
   파일이 없으면 번호 플레이스홀더로 자동 대체된다 (에러 없음).
3. **폰트 바꾸려면** `assets/fonts/display.woff2`, `text.woff2`를 교체
   (파일명 고정). 기본값은 Big Shoulders Stencil/Text.
4. **빌드**
   ```bash
   python3 build.py
   ```
5. **검증**
   ```bash
   python3 test_build.py
   ```
6. **발행** — Claude Code 세션에서 `dist/<slug>.html`을 Artifact 툴로 발행.
   기존 링크를 유지하려면 이전 발행 URL을 `url` 파라미터로 넘긴다.

## content.json 필드

| 블록 | 필드 | 설명 |
|---|---|---|
| `meta` | `title`, `slug` | `<title>`, 출력 파일명 |
| `theme` | `bg`,`bg2`,`paper`,`paper2`,`ink`,`ink_dim`,`accent`,`accent_strong`,`glow`,`accent2`,`line`,`chip_bg`,`seg_off` + `bg_light`,`bg2_light`,`accent2_light` | CSS 변수로 직접 주입. `_light` 접미사는 라이트 테마일 때만 덮어쓰는 값 |
| `brand` | — | 좌상단 라벨 |
| `cover` | `eyebrow`,`mark[]`,`meta[]`,`hint` | 첫 슬라이드. `mark`는 줄바꿈 배열 |
| `cards[]` | `num`,`chip`,`title`,`subtitle`,`chips_label`,`chips[]`,`body`,`quote`,`media`,`link` | `chip.emphasis`: `null`\|`"primary"`\|`"secondary"`. `media`/`link`는 없으면 `null` |
| `closing` | `eyebrow`,`mark_lines[]`,`rows[[k,v]]`,`stamp`,`restart`,`sources[]` | 마지막 슬라이드. `mark_lines`의 마지막 줄만 강조색 |

## 알려진 한계

- 외부 host로의 요청(iframe, 외부 이미지 URL)은 Claude 아티팩트 CSP가 막는다.
  이미지는 반드시 `assets/media/`에 넣어 base64로 내장해야 한다.
- 원본(`dynamic-duo-album-1/`)의 유튜브 전용 로직(검색 링크 자동 생성 등)은
  빠졌다 — `link` 필드로 카드마다 직접 지정한다.
