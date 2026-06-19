#!/usr/bin/env python3
"""문서 구조 분석기 — 파이썬 표준 라이브러리만 사용.

지원: .txt .md .markdown .csv .json .docx
사용법:
    python analyze.py <파일경로>          # 사람이 읽기 좋은 리포트
    python analyze.py <파일경로> --json   # JSON 출력
"""
import sys
import os
import re
import csv
import json
import zipfile
import argparse
from xml.etree import ElementTree as ET


def analyze_text(text):
    lines = text.splitlines()
    words = re.findall(r"\S+", text)
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    return {
        "lines": len(lines),
        "words": len(words),
        "chars": len(text),
        "paragraphs": len(paras),
    }


def analyze_markdown(text):
    info = analyze_text(text)
    headings = []
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            headings.append({"level": len(m.group(1)), "text": m.group(2).strip()})
    info["headings"] = headings
    info["code_blocks"] = text.count("```") // 2
    info["links"] = len(re.findall(r"\[[^\]]+\]\([^)]+\)", text))
    info["table_rows"] = sum(
        1 for ln in text.splitlines() if re.match(r"^\s*\|.*\|\s*$", ln)
    )
    return info


def analyze_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        return {"rows": 0, "columns": 0, "header": []}
    header = rows[0]
    return {
        "rows": max(0, len(rows) - 1),
        "columns": len(header),
        "header": header,
    }


def _shape(obj, depth=0):
    if depth > 6:
        return "…"
    if isinstance(obj, dict):
        return {k: _shape(v, depth + 1) for k, v in list(obj.items())[:50]}
    if isinstance(obj, list):
        return [_shape(obj[0], depth + 1)] if obj else []
    return type(obj).__name__


def analyze_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {"top_type": type(data).__name__, "structure": _shape(data)}


_W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def analyze_docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    texts = []
    for p in root.findall(".//w:p", _W_NS):
        run = "".join(t.text or "" for t in p.findall(".//w:t", _W_NS))
        if run.strip():
            texts.append(run)
    tables = root.findall(".//w:tbl", _W_NS)
    info = analyze_text("\n".join(texts))
    info["docx_paragraphs"] = len(texts)
    info["tables"] = len(tables)
    return info


DISPATCH = {
    ".txt": lambda p: analyze_text(_read(p)),
    ".md": lambda p: analyze_markdown(_read(p)),
    ".markdown": lambda p: analyze_markdown(_read(p)),
    ".csv": analyze_csv,
    ".json": analyze_json,
    ".docx": analyze_docx,
}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def render_report(path, ext, data):
    out = []
    out.append(f"문서 분석: {os.path.basename(path)}  ({ext})")
    out.append("=" * 48)
    order = ["lines", "words", "chars", "paragraphs", "docx_paragraphs",
             "rows", "columns", "code_blocks", "links", "table_rows", "tables"]
    labels = {
        "lines": "줄 수", "words": "단어 수", "chars": "글자 수",
        "paragraphs": "문단 수", "docx_paragraphs": "본문 문단",
        "rows": "데이터 행", "columns": "열(컬럼)", "code_blocks": "코드블록",
        "links": "링크", "table_rows": "표 행", "tables": "표",
    }
    for k in order:
        if k in data:
            out.append(f"  {labels[k]:<10} : {data[k]}")
    if data.get("header"):
        out.append("  컬럼명     : " + ", ".join(map(str, data["header"])))
    if data.get("headings"):
        out.append("\n  목차 (헤딩 트리)")
        for h in data["headings"]:
            out.append("    " + "  " * (h["level"] - 1) + f"- {h['text']}")
    if "structure" in data:
        out.append("\n  스키마")
        out.append("    top: " + data["top_type"])
        out.append("    " + json.dumps(data["structure"], ensure_ascii=False)[:600])
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="문서 구조 분석기 (표준 라이브러리)")
    ap.add_argument("path", help="분석할 파일 경로")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.path):
        print(f"파일을 찾을 수 없습니다: {args.path}", file=sys.stderr)
        return 2
    ext = os.path.splitext(args.path)[1].lower()
    handler = DISPATCH.get(ext)
    if handler is None:
        print(f"지원하지 않는 형식: {ext}  (지원: {', '.join(DISPATCH)})",
              file=sys.stderr)
        return 2
    try:
        data = handler(args.path)
    except Exception as e:  # noqa: BLE001
        print(f"분석 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"file": args.path, "ext": ext, **data},
                         ensure_ascii=False, indent=2))
    else:
        print(render_report(args.path, ext, data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
