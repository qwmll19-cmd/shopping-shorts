#!/usr/bin/env python3
"""작업 폴더의 도구·문서를 공유 폴더(GitHub 저장소)로 복사한다.

작업 폴더와 공유 폴더를 손으로 맞추면 반드시 어긋난다.
실제로 프롬프트 템플릿이 한쪽만 갱신돼 서로 다른 내용이 된 적이 있다.

  python sync_share.py            # 무엇이 다른지 보여주기만 함
  python sync_share.py --apply    # 실제로 복사
"""
import filecmp, shutil, subprocess, sys
from pathlib import Path

SRC = Path(__file__).parent
DST = SRC.parent / "쇼츠_공유"
SKILL = Path.home() / ".claude" / "skills" / "shopping-shorts" / "SKILL.md"

FILES = ["make_remix.py", "check_render.py", "thumb.py", "prep_sources.py",
         "index_sources.py", "ref_sheet.py", "new_project.py", "tts.py",
         "tts_whole.py", "프롬프트_템플릿.md", "package.json",
         "src/Remix.jsx", "src/Root.jsx", "src/index.jsx"]


def main():
    apply = "--apply" in sys.argv
    if not DST.exists():
        sys.exit(f"{DST} 가 없습니다.")

    pairs = [(SRC / f, DST / f) for f in FILES]
    pairs.append((SKILL, DST / "SKILL.md"))      # 스킬 문서는 홈에서 가져온다

    diff = []
    for s, d in pairs:
        if not s.exists():
            print(f"  없음(원본): {s.name}"); continue
        if not d.exists() or not filecmp.cmp(s, d, shallow=False):
            diff.append((s, d))

    if not diff:
        print("전부 같습니다. 동기화할 것 없음.")
        return

    print(f"다른 파일 {len(diff)}개:")
    for s, d in diff:
        print(f"  {d.relative_to(DST)}")

    if not apply:
        print("\n실제로 복사하려면: python sync_share.py --apply")
        return

    for s, d in diff:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    print(f"\n{len(diff)}개 복사 완료. 이어서 커밋·푸시하세요:")
    print(f"  cd {DST}")
    print('  git add -A && git commit -m "설명" && git push')


if __name__ == "__main__":
    main()
