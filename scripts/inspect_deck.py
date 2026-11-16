"""Inspect a .pptx: list parts and dump per-slide text (paragraph + run breakdown)."""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def para_text(p):
    return "".join(t.text or "" for t in p.iter(A + "t"))


def main(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    slides = sorted(
        (n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)),
    )
    print(f"FILE: {path}")
    print(f"parts={len(names)} slides={len(slides)}")
    print("--- non-slide parts of interest ---")
    for n in names:
        if n.startswith("[Content_Types]") or n.startswith("ppt/slideLayouts/slideLayout") or n.startswith("ppt/notesSlides/"):
            print("  ", n)
    for s in slides:
        root = ET.fromstring(z.read(s))
        print("=" * 100)
        print(f"## {s}")
        for sp in root.iter(P + "sp"):
            nv = sp.find(".//" + P + "nvSpPr/" + P + "cNvPr")
            sid = nv.get("id") if nv is not None else "?"
            nm = nv.get("name") if nv is not None else "?"
            paras = [p for p in sp.iter(A + "p")]
            texts = [para_text(p) for p in paras]
            if not any(t.strip() for t in texts):
                continue
            print(f"  [shape id={sid} name={nm!r}]")
            for t in texts:
                print(f"      | {t}")
        # graphicFrame tables
        for gf in root.iter(P + "graphicFrame"):
            tbl = gf.find(".//" + A + "tbl")
            if tbl is None:
                continue
            nv = gf.find(".//" + P + "nvGraphicFramePr/" + P + "cNvPr")
            print(f"  [table name={nv.get('name') if nv is not None else '?'}]")
            for tr in tbl.findall(A + "tr"):
                cells = ["".join(para_text(p) for p in tc.iter(A + "p")) for tc in tr.findall(A + "tc")]
                print("      || " + " | ".join(cells))


if __name__ == "__main__":
    main(sys.argv[1])
