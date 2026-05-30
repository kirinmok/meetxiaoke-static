#!/usr/bin/env python3
"""
小可日記封面健康檢查 — 掃描所有文章，找出缺圖的並自動修復

用法：
  python3 scripts/check_covers.py           # 檢查 + 自動修復
  python3 scripts/check_covers.py --check   # 只檢查不修
  python3 scripts/check_covers.py --notify  # 檢查 + 有問題就通知 KIRIN
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = SITE_ROOT / "_posts"
COVERS_DIR = SITE_ROOT / "assets" / "covers"
IMAGES_DIR = SITE_ROOT / "assets" / "images"
IMAGE_DROP = Path.home() / "Desktop" / "小可日記" / "日記圖片"


def parse_frontmatter(filepath: Path) -> dict:
    """解析 Jekyll frontmatter"""
    text = filepath.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


def find_cover_file(day_num: int) -> Path | None:
    """在各種可能位置找封面圖"""
    patterns = [
        COVERS_DIR / f"小可日記_Day{day_num:02d}_*.jpg",
        COVERS_DIR / f"小可日記_Day{day_num}_*.jpg",
        IMAGES_DIR / f"day{day_num}-cover.jpg",
        IMAGES_DIR / f"day{day_num:02d}-cover.jpg",
    ]
    for pattern in patterns:
        matches = list(pattern.parent.glob(pattern.name))
        if matches:
            return matches[0]

    # 搜桌面日記圖片資料夾
    for f in IMAGE_DROP.glob(f"*Day{day_num}*"):
        return f
    for f in IMAGE_DROP.glob(f"*Day{day_num:02d}*"):
        return f

    return None


def fix_post(filepath: Path, day_num: int, title: str) -> tuple[bool, str]:
    """修復缺封面的文章，回傳 (是否修復成功, 訊息)"""
    cover = find_cover_file(day_num)

    if not cover:
        return False, f"Day {day_num}：找不到封面圖"

    # 確保圖在 covers/ 目錄
    dest_name = f"小可日記_Day{day_num}_{title}.jpg"
    dest = COVERS_DIR / dest_name

    if not dest.exists():
        if cover.suffix.lower() == ".png":
            try:
                from PIL import Image
                img = Image.open(cover).convert("RGB")
                img.save(str(dest), "JPEG", quality=82, optimize=True)
            except ImportError:
                subprocess.run(
                    ["sips", "-s", "format", "jpeg", str(cover), "--out", str(dest)],
                    capture_output=True,
                )
        else:
            import shutil
            shutil.copy2(cover, dest)

    if not dest.exists():
        return False, f"Day {day_num}：封面圖複製失敗"

    # 檢查大小
    size_kb = dest.stat().st_size / 1024
    if size_kb > 600:
        try:
            from PIL import Image
            img = Image.open(dest)
            img.save(str(dest), "JPEG", quality=75, optimize=True)
        except ImportError:
            pass

    # 修 frontmatter
    text = filepath.read_text(encoding="utf-8")
    image_line = f"image: /assets/covers/{dest_name}"

    if "image:" not in text:
        text = text.replace("---\n\n", f"{image_line}\n---\n\n", 1)
        if "image:" not in text:
            text = re.sub(
                r"(day:\s*\d+)\n---",
                rf"\1\n{image_line}\n---",
                text,
            )

    if "tags:" not in text:
        text = re.sub(
            r"(day:\s*\d+)",
            r"\1\ntags: [小可日記]",
            text,
        )

    filepath.write_text(text, encoding="utf-8")
    return True, f"Day {day_num}：✅ 封面修復完成"


def notify_kirin(problems: list[str]) -> None:
    """用 macOS 通知告知 KIRIN"""
    msg = f"小可日記封面檢查：{len(problems)} 篇有問題"
    subprocess.run(
        ["osascript", "-e",
         f'display notification "{msg}" with title "小可日記健康檢查"'],
        capture_output=True,
    )
    print(f"🔔 已通知 KIRIN：{msg}")


def main():
    parser = argparse.ArgumentParser(description="小可日記封面健康檢查")
    parser.add_argument("--check", action="store_true", help="只檢查不修")
    parser.add_argument("--notify", action="store_true", help="有問題就通知")
    args = parser.parse_args()

    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    posts = sorted(POSTS_DIR.glob("*xiaoke-diary*"))

    problems = []
    fixed = []

    for post in posts:
        fm = parse_frontmatter(post)
        day = fm.get("day", "")
        title = fm.get("title", "").split("｜")[-1].strip() if "｜" in fm.get("title", "") else ""

        if not day:
            continue

        day_num = int(day)
        has_image = bool(fm.get("image"))
        image_path = SITE_ROOT / fm.get("image", "").lstrip("/") if has_image else None
        image_exists = image_path and image_path.exists() if image_path else False

        if has_image and image_exists:
            continue

        if not has_image:
            issue = f"Day {day_num}：frontmatter 缺 image 欄位"
        else:
            issue = f"Day {day_num}：image 指向 {fm['image']} 但檔案不存在"

        print(f"❌ {issue}")

        if args.check:
            problems.append(issue)
            continue

        ok, msg = fix_post(post, day_num, title)
        if ok:
            fixed.append(msg)
            print(f"  → {msg}")
        else:
            problems.append(msg)
            print(f"  → ❌ {msg}")

    print(f"\n{'='*40}")
    print(f"總計 {len(posts)} 篇文章")
    print(f"✅ 正常：{len(posts) - len(problems) - len(fixed)} 篇")
    if fixed:
        print(f"🔧 自動修復：{len(fixed)} 篇")
    if problems:
        print(f"❌ 需要處理：{len(problems)} 篇")
        for p in problems:
            print(f"  - {p}")

    if args.notify and problems:
        notify_kirin(problems)

    return len(problems)


if __name__ == "__main__":
    exit(main())
