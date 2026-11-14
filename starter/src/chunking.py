"""Implement fixed-size and structure-aware (paragraph/article) chunking."""
from __future__ import annotations

import hashlib
import re
from .models import Chunk, DocumentPage


def _make_chunk_id(document_id: str, page: int, strategy_tag: str, index: int, text: str) -> str:
    content_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{document_id}-p{page:02d}-{strategy_tag}-{index:03d}-{content_hash}"


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Split text into overlapping character windows and retain page metadata."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    text = page.text.strip()
    if not text:
        return []

    step = size - overlap
    chunks: list[Chunk] = []
    start = 0
    idx = 1

    while start < len(text):
        end = min(start + size, len(text))
        window = text[start:end].strip()
        if window:
            meta = dict(page.metadata)
            meta.update(
                {
                    "chunk_strategy": "fixed_size",
                    "chunk_size_param": size,
                    "overlap_param": overlap,
                    "char_start": start,
                    "char_end": end,
                    "chunk_char_len": len(window),
                }
            )
            chunks.append(
                Chunk(
                    chunk_id=_make_chunk_id(page.document_id, page.page, "fixed", idx, window),
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=window,
                    metadata=meta,
                )
            )
            idx += 1
        if end >= len(text):
            break
        start += step

    return chunks


def _split_into_semantic_blocks(text: str) -> list[str]:
    """Split legal text into article/section blocks or paragraphs while keeping headings attached."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return []

    blocks: list[str] = []
    current: list[str] = []

    # Heading patterns that start a new legal article or major section
    article_re = re.compile(r"^(Điều\s+\d+[\.\:]|Chương\s+[IVXLCDM]+\b|Mục\s+\d+\b)")

    for ln in lines:
        if article_re.match(ln) and current:
            blocks.append("\n".join(current))
            current = [ln]
        else:
            current.append(ln)
    if current:
        blocks.append("\n".join(current))

    # Attach standalone chapter/section heading blocks (<140 chars) to the next block
    combined: list[str] = []
    idx = 0
    while idx < len(blocks):
        if len(blocks[idx]) < 140 and idx + 1 < len(blocks):
            blocks[idx + 1] = f"{blocks[idx]}\n{blocks[idx + 1]}"
            idx += 1
        else:
            combined.append(blocks[idx])
            idx += 1
    return combined


def by_paragraph(page: DocumentPage, max_size: int = 800) -> list[Chunk]:
    """Group paragraphs/articles up to max_size, split oversized blocks by line/clause, and retain metadata."""
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    text = page.text.strip()
    if not text:
        return []

    blocks = _split_into_semantic_blocks(text)
    raw_chunks: list[str] = []
    buffer = ""

    def flush_buffer() -> None:
        nonlocal buffer
        if buffer.strip():
            raw_chunks.append(buffer.strip())
        buffer = ""

    for blk in blocks:
        if len(blk) <= max_size:
            candidate = f"{buffer}\n{blk}".strip() if buffer else blk
            if len(candidate) <= max_size:
                buffer = candidate
            else:
                flush_buffer()
                buffer = blk
        else:
            # Oversized block: split by individual lines/clauses, keeping context header if possible
            flush_buffer()
            blk_lines = [ln.strip() for ln in blk.split("\n") if ln.strip()]
            header = blk_lines[0] if blk_lines and len(blk_lines[0]) < 140 else ""
            sub_buf = ""
            for i, ln in enumerate(blk_lines):
                if len(ln) > max_size:
                    # Fallback sentence/window split for an extremely long single clause
                    if sub_buf:
                        raw_chunks.append(sub_buf.strip())
                        sub_buf = ""
                    step = max_size - 60 if max_size > 120 else max_size
                    for pos in range(0, len(ln), step):
                        seg = ln[pos : pos + max_size].strip()
                        if seg:
                            prefix = f"{header}\n" if header and pos > 0 and len(header) + len(seg) + 1 <= max_size else ""
                            raw_chunks.append(f"{prefix}{seg}".strip())
                else:
                    cand = f"{sub_buf}\n{ln}".strip() if sub_buf else ln
                    if len(cand) <= max_size:
                        sub_buf = cand
                    else:
                        if sub_buf:
                            raw_chunks.append(sub_buf.strip())
                        if header and i > 0 and len(header) + len(ln) + 1 <= max_size:
                            sub_buf = f"{header}\n{ln}"
                        else:
                            sub_buf = ln
            if sub_buf.strip():
                raw_chunks.append(sub_buf.strip())

    flush_buffer()

    # Merge any trailing tiny chunk (<150 chars) into the preceding chunk on the same page
    merged_chunks: list[str] = []
    for ch in raw_chunks:
        if len(ch) < 150 and merged_chunks and len(merged_chunks[-1]) + len(ch) + 1 <= max_size + 150:
            merged_chunks[-1] = f"{merged_chunks[-1]}\n{ch}"
        else:
            merged_chunks.append(ch)

    chunks: list[Chunk] = []
    for idx, ch_text in enumerate(merged_chunks, start=1):
        meta = dict(page.metadata)
        meta.update(
            {
                "chunk_strategy": "by_paragraph",
                "max_size_param": max_size,
                "chunk_char_len": len(ch_text),
            }
        )
        chunks.append(
            Chunk(
                chunk_id=_make_chunk_id(page.document_id, page.page, "para", idx, ch_text),
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=ch_text,
                metadata=meta,
            )
        )
    return chunks
