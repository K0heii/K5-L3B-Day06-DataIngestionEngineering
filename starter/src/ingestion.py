"""Read and normalize source data for Day 06 Data Ingestion Engineering."""
from __future__ import annotations

import json
import re
import struct
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import olefile
from pypdf import PdfReader

from .models import DocumentPage

MIN_UNIT_CHARS = 1500


def normalize_text(text: str) -> str:
    """Normalize Unicode NFC and whitespace without discarding paragraph/section structure."""
    if not text:
        return ""
    txt = unicodedata.normalize("NFC", text)
    # Convert Word soft line breaks (\x0b) and carriage returns to newline
    txt = txt.replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n")
    # Remove Word field codes such as \x13 PAGE \x1433\x15
    txt = re.sub(r"\x13[^\x15]*\x15", "", txt)
    # Strip other control characters except newline and tab
    txt = "".join(ch for ch in txt if ch in ("\n", "\t") or ord(ch) >= 32)
    # Remove running Công báo headers/footers
    txt = re.sub(r"(?m)^\s*CÔNG BÁO/Số[^\n]*$", "", txt)
    # Collapse horizontal spaces per line while preserving line breaks
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in txt.split("\n")]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical PDF page; keep its page number and source.

    Detect and record pages with no text (e.g. scanned image PDFs).
    """
    reader = PdfReader(str(path))
    pages: list[DocumentPage] = []
    for idx, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        norm = normalize_text(raw)
        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=idx,
                text=norm,
                metadata={
                    "physical_page": idx,
                    "char_count": len(norm),
                    "is_empty_or_scan": len(norm) < 50,
                },
            )
        )
    return pages


def extract_ole_doc_text(path: Path) -> str:
    """Extract raw Unicode/CP1252 text from a Word 97-2003 binary .doc (OLE2) file."""
    with olefile.OleFileIO(str(path)) as ole:
        word_stream = ole.openstream("WordDocument").read()
        flags = struct.unpack("<H", word_stream[0x000A:0x000C])[0]
        f_which_tbl_stm = (flags >> 9) & 1
        table_name = f"{f_which_tbl_stm}Table"
        table_stream = ole.openstream(table_name).read()

        fc_clx, lcb_clx = struct.unpack("<II", word_stream[0x01A2:0x01AA])
        clx = table_stream[fc_clx : fc_clx + lcb_clx]

        pos = 0
        pieces: list[str] = []
        while pos < len(clx):
            clxt = clx[pos]
            if clxt == 1:
                cb_grpprl = struct.unpack("<h", clx[pos + 1 : pos + 3])[0]
                pos += 3 + cb_grpprl
            elif clxt == 2:
                lcb = struct.unpack("<I", clx[pos + 1 : pos + 5])[0]
                plc_pcd = clx[pos + 5 : pos + 5 + lcb]
                n = (lcb - 4) // 12
                cps = [struct.unpack("<I", plc_pcd[i * 4 : (i + 1) * 4])[0] for i in range(n + 1)]
                pcds_offset = (n + 1) * 4
                for i in range(n):
                    cp_start, cp_end = cps[i], cps[i + 1]
                    char_count = cp_end - cp_start
                    pcd = plc_pcd[pcds_offset + i * 8 : pcds_offset + (i + 1) * 8]
                    fc_raw = struct.unpack("<I", pcd[2:6])[0]
                    is_compressed = bool(fc_raw & 0x40000000)
                    fc = fc_raw & 0x3FFFFFFF
                    if is_compressed:
                        byte_offset = fc // 2
                        raw_bytes = word_stream[byte_offset : byte_offset + char_count]
                        pieces.append(raw_bytes.decode("cp1252", errors="replace"))
                    else:
                        byte_offset = fc
                        raw_bytes = word_stream[byte_offset : byte_offset + char_count * 2]
                        pieces.append(raw_bytes.decode("utf-16le", errors="replace"))
                break
            else:
                break
        return "".join(pieces)


def _split_chapters_and_sections(text: str, min_chars: int = MIN_UNIT_CHARS) -> list[dict[str, str]]:
    """Split normalized legal text into ordered structural units (Chương / Mục) >= min_chars."""
    chap_pattern = re.compile(r"(?m)^(Chương\s+[IVXLCDM]+)\s*\n([^\n]+)")
    matches = list(chap_pattern.finditer(text))
    raw_units: list[dict[str, str]] = []

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chap_code = m.group(1).strip()
        chap_title = m.group(2).strip()
        chap_text = text[start:end].strip()

        muc_pattern = re.compile(r"(?m)^(Mục\s+\d+)\s*\n([^\n]+)")
        muc_matches = list(muc_pattern.finditer(chap_text))
        if len(muc_matches) >= 2 and len(chap_text) >= 6000:
            for j, mm in enumerate(muc_matches):
                m_start = 0 if j == 0 else mm.start()
                m_end = muc_matches[j + 1].start() if j + 1 < len(muc_matches) else len(chap_text)
                sub_text = chap_text[m_start:m_end].strip()
                if j > 0:
                    sub_text = f"{chap_code} - {chap_title}\n{sub_text}"
                raw_units.append(
                    {
                        "chapter": chap_code,
                        "section": f"{chap_code} - {mm.group(1).strip()}: {mm.group(2).strip()}",
                        "text": sub_text,
                    }
                )
        else:
            raw_units.append(
                {
                    "chapter": chap_code,
                    "section": f"{chap_code}: {chap_title}",
                    "text": chap_text,
                }
            )

    merged: list[dict[str, str]] = []
    idx = 0
    while idx < len(raw_units):
        u = dict(raw_units[idx])
        if len(u["text"]) < min_chars and idx + 1 < len(raw_units):
            nxt = dict(raw_units[idx + 1])
            nxt["text"] = u["text"] + "\n\n" + nxt["text"]
            nxt["chapter"] = (
                f"{u['chapter']}+{nxt['chapter']}" if u["chapter"] != nxt["chapter"] else u["chapter"]
            )
            nxt["section"] = f"{u['section']} & {nxt['section']}"
            raw_units[idx + 1] = nxt
            idx += 1
        elif len(u["text"]) < min_chars and merged:
            merged[-1]["text"] += "\n\n" + u["text"]
            merged[-1]["section"] += f" & {u['section']}"
            idx += 1
        else:
            merged.append(u)
            idx += 1
    return merged


def load_corpus(raw_dir: Path) -> tuple[list[DocumentPage], dict[str, Any]]:
    """Load the full Vietnamese Labor Law corpus, recording scan errors and anomalies."""
    anomalies: list[dict[str, Any]] = []

    # 1. Inspect the two signed PDFs first and log that they are unextractable scans
    for pdf_name, doc_id in [
        ("blld-2019-45-qh14.pdf", "blld-2019-pdf-scan"),
        ("nd-145-2020.pdf", "nd-145-2020-pdf-scan"),
    ]:
        pdf_path = raw_dir / pdf_name
        if pdf_path.exists():
            pdf_pages = load_pdf(pdf_path, doc_id, f"data/raw/{pdf_name}")
            empty_pages = [p.page for p in pdf_pages if p.metadata.get("is_empty_or_scan")]
            anomalies.append(
                {
                    "file": f"data/raw/{pdf_name}",
                    "issue_type": "scanned_pdf_no_text_layer",
                    "total_physical_pages": len(pdf_pages),
                    "empty_or_scan_pages_count": len(empty_pages),
                    "action_taken": "Excluded from active indexing; replaced by official Công báo .doc text edition.",
                }
            )

    pages: list[DocumentPage] = []

    # 2. Load Bộ luật Lao động 45/2019/QH14 (.doc)
    blld_file = "2019_993 + 994_45-2019-QH14.doc"
    blld_path = raw_dir / blld_file
    blld_raw = extract_ole_doc_text(blld_path)
    blld_norm = normalize_text(blld_raw)
    blld_units = _split_chapters_and_sections(blld_norm, min_chars=MIN_UNIT_CHARS)

    for idx, u in enumerate(blld_units, start=1):
        pages.append(
            DocumentPage(
                document_id="blld-2019",
                source=f"data/raw/{blld_file}",
                page=idx,
                text=u["text"],
                metadata={
                    "unit_id": f"blld-2019-p{idx:02d}",
                    "document_type": "bo_luat",
                    "year": 2019,
                    "effective_date": "2021-01-01",
                    "issuing_body": "Quốc hội",
                    "official_number": "45/2019/QH14",
                    "chapter": u["chapter"],
                    "section": u["section"],
                    "char_count": len(u["text"]),
                },
            )
        )

    # 3. Load Nghị định 145/2020/NĐ-CP across two Công báo .doc issues
    nd_file_1 = "2020_1203 + 1204_145-2020-NĐ-CP.doc"
    nd_file_2 = "2020_1205 + 1206_145-2020-NĐ-CP.doc"
    nd_norm_1 = normalize_text(extract_ole_doc_text(raw_dir / nd_file_1))
    nd_norm_2 = normalize_text(extract_ole_doc_text(raw_dir / nd_file_2))

    # Strip Công báo issue table of contents before the Decree header in part 1
    start_nd1 = nd_norm_1.find("Số: 145/2020/NĐ-CP")
    if start_nd1 > 0:
        anomalies.append(
            {
                "file": f"data/raw/{nd_file_1}",
                "issue_type": "cong_bao_issue_toc_header",
                "chars_removed": start_nd1,
                "action_taken": "Removed Công báo issue cover/table-of-contents before 'Số: 145/2020/NĐ-CP'.",
            }
        )
        nd_norm_1 = nd_norm_1[start_nd1:]

    # In part 2, keep from Mục 2 (continuation of Chương XI) up to before Phụ lục I
    start_nd2 = nd_norm_2.find("Mục 2\nHỘI ĐỒNG TRỌNG TÀI LAO ĐỘNG")
    end_nd2 = nd_norm_2.find("Phụ lục I")
    anomalies.append(
        {
            "file": f"data/raw/{nd_file_2}",
            "issue_type": "non_content_appendices_and_unrelated_treaty",
            "chars_removed_prefix": start_nd2,
            "chars_removed_suffix": len(nd_norm_2) - end_nd2 if end_nd2 > 0 else 0,
            "action_taken": (
                "Excluded Công báo issue TOC, blank form templates (Phụ lục I-III) and unrelated "
                "Thông báo số 61/2020/TB-LPQT (Cambodia treaty) printed in the same Công báo issue."
            ),
        }
    )
    nd_body_2 = nd_norm_2[start_nd2:end_nd2].strip()

    # Record and fix typo in Công báo 1205+1206 where Chương XII was printed as Chương XI
    if "Chương XI\nĐIỀU KHOẢN THI HÀNH" in nd_body_2:
        anomalies.append(
            {
                "file": f"data/raw/{nd_file_2}",
                "issue_type": "source_heading_typo_and_word_autonumbering",
                "detail": (
                    "Source printed 'Chương XI ĐIỀU KHOẢN THI HÀNH' (duplicate Roman numeral XI instead of XII) "
                    "and used Word auto-numbering fields for 'Điều X.' headings (not stored in plain text stream)."
                ),
                "action_taken": "Normalized final chapter label to 'Chương XII' and segmented by Chương/Mục.",
            }
        )
        nd_body_2 = nd_body_2.replace("Chương XI\nĐIỀU KHOẢN THI HÀNH", "Chương XII\nĐIỀU KHOẢN THI HÀNH")

    nd_full = nd_norm_1 + "\n\n" + nd_body_2
    nd_units = _split_chapters_and_sections(nd_full, min_chars=MIN_UNIT_CHARS)

    for idx, u in enumerate(nd_units, start=1):
        # Units 1..19 come from 1203+1204, unit 20 spans the boundary, 21..24 come from 1205+1206
        src_file = f"data/raw/{nd_file_1}" if idx <= 20 else f"data/raw/{nd_file_2}"
        pages.append(
            DocumentPage(
                document_id="nd-145-2020",
                source=src_file,
                page=idx,
                text=u["text"],
                metadata={
                    "unit_id": f"nd-145-2020-p{idx:02d}",
                    "document_type": "nghi_dinh",
                    "year": 2020,
                    "effective_date": "2021-02-01",
                    "issuing_body": "Chính phủ",
                    "official_number": "145/2020/NĐ-CP",
                    "chapter": u["chapter"],
                    "section": u["section"],
                    "char_count": len(u["text"]),
                },
            )
        )

    ingest_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_valid_units": len(pages),
        "min_unit_chars_rule": MIN_UNIT_CHARS,
        "min_unit_chars_observed": min(len(p.text) for p in pages),
        "max_unit_chars_observed": max(len(p.text) for p in pages),
        "total_normalized_chars": sum(len(p.text) for p in pages),
        "documents_summary": {
            "blld-2019": {
                "units": sum(1 for p in pages if p.document_id == "blld-2019"),
                "chars": sum(len(p.text) for p in pages if p.document_id == "blld-2019"),
            },
            "nd-145-2020": {
                "units": sum(1 for p in pages if p.document_id == "nd-145-2020"),
                "chars": sum(len(p.text) for p in pages if p.document_id == "nd-145-2020"),
            },
        },
        "anomalies_and_exclusions": anomalies,
    }
    return pages, ingest_report
