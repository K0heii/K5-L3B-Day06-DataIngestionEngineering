# Day 06 · Data Ingestion Engineering - Pháp luật Lao động Việt Nam

Bài thực hành cá nhân Day 06: Xây dựng pipeline chuẩn bị dữ liệu (Data Ingestion Engineering) và đánh giá truy xuất (Retrieval Benchmark) trên bộ văn bản pháp quy về Lao động Việt Nam với 3 chiến lược cấu hình (**A: Fixed-size**, **B: Structure-aware Paragraph/Article**, **C: Structure-aware + Metadata Filter**).

---

## 1. Tổng quan Corpus, Công nghệ & Cấu hình

| Hạng mục | Chi tiết |
|---|---|
| **Corpus** | **Bộ luật Lao động số 45/2019/QH14** (`blld-2019`, 28 đơn vị nội dung, 189.822 ký tự) & **Nghị định số 145/2020/NĐ-CP** (`nd-145-2020`, 24 đơn vị nội dung, 189.337 ký tự). Tổng cộng **52 đơn vị nội dung hợp lệ** (**379.159 ký tự** chuẩn hóa, mỗi đơn vị ≥ 1.505 ký tự). |
| **Giấy phép** | Phạm vi công cộng (Public Domain) theo khoản 2 Điều 15 Luật Sở hữu trí tuệ Việt Nam. Xem chi tiết tại [data/manifest.json](data/manifest.json). |
| **Embedding Model** | `google/embeddinggemma-2` (Apache 2.0, chạy local qua `sentence-transformers` 6.3.0, **768 chiều**, `float32`, chuẩn hóa L2, dùng prompt bất đối xứng `encode_document` / `encode_query`). Chi phí: **0 USD**. |
| **Vector Store** | `ChromaDB` 1.5.9 (`PersistentClient` lưu bền vững trên đĩa tại `results/chroma`), metric `cosine` (HNSW). |
| **Chiến lược A** | `fixed_size(size=500, overlap=50)`, không lọc metadata (`862 chunks`). |
| **Chiến lược B** | `by_paragraph(max_size=800)` theo cấu trúc Chương/Mục/Điều, không lọc metadata (`658 chunks`). |
| **Chiến lược C** | Dùng chung 658 chunks và index của **B**, bật lọc metadata (`document_type` / `year`) khi câu hỏi có `filter`. |
| **Benchmark** | **24 câu hỏi** ([benchmark/questions.json](benchmark/questions.json)), tách cố định trước thử nghiệm: **18 câu `dev` / 6 câu `test`** (có **7 câu lọc metadata**: 5 ở `dev`, 2 ở `test`). |

---

## 2. Hướng dẫn Cài đặt & Chạy Tái lập (Reproducibility)

### Yêu cầu môi trường
- Python **3.11+** (đã kiểm tra trên Python 3.11.0, Windows).
- Không cần API key (model `google/embeddinggemma-2` và `ChromaDB` chạy hoàn toàn local).

### Các bước cài đặt và chạy lại từ đầu

```powershell
# 1. Tạo và kích hoạt môi trường ảo
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Cài đặt dependencies
python -m pip install -r starter/requirements.txt

# 3. Đặt PYTHONPATH ở thư mục gốc repo
$env:PYTHONPATH="."

# 4. Kiểm chứng 100% evidence_quote của 24 câu hỏi tồn tại trong corpus đã chuẩn hóa
python starter/scripts/verify_benchmark.py

# 5. Chạy toàn bộ pipeline (Ingest -> Chunk A/B -> Embed -> Upsert Chroma -> Re-ingest check -> Truy xuất A/B/C)
python -m starter.src.run

# 6. Tạo các bảng mẫu phục vụ chấm thủ công (Coherence, Metadata, Grounding)
python starter/scripts/prepare_audit_sheets.py
```

---

## 3. Cấu trúc Thư mục & Artifacts Bài nộp

```text
├── STUDENT.md                           # Thông tin học viên
├── README.md                            # Hướng dẫn cài đặt, chạy tái lập và tóm tắt kết quả
├── data/
│   ├── manifest.json                    # Manifest nguồn, quyền sử dụng, quy tắc tính 52 đơn vị nội dung
│   └── raw/                             # Các file .doc Công báo gốc và file .pdf scan (đối chứng lỗi)
├── benchmark/
│   ├── questions.json                   # 24 câu hỏi (18 dev / 6 test), tiêu chí chọn chốt trước và gold evidence
│   └── verify_report.json               # Báo cáo xác minh tự động 24/24 evidence khớp nguồn
├── starter/
│   ├── requirements.txt                 # Danh sách thư viện và phiên bản
│   ├── scripts/
│   │   ├── verify_benchmark.py          # Script kiểm chứng gold evidence trong nguồn
│   │   └── prepare_audit_sheets.py      # Script xuất bảng chấm thủ công
│   └── src/
│       ├── models.py                    # Data contracts (DocumentPage, Chunk)
│       ├── ingestion.py                 # Đọc .doc OLE2 / .pdf, chuẩn hóa Unicode NFC, ghi log lỗi
│       ├── chunking.py                  # Chia chunk fixed_size (A) và by_paragraph (B/C)
│       ├── embeddings.py                # Adapter thực cho google/embeddinggemma-2 (768d)
│       ├── store.py                     # ChromaVectorStore lưu bền vững, upsert không trùng, lọc metadata
│       ├── evaluation.py                # Chấm Hit@1, Evidence Hit@3, Filter compliance
│       └── run.py                       # Entry point chạy toàn bộ thí nghiệm
├── artifacts/
│   └── experiment_log.csv               # Nhật ký cấu hình, giả thuyết và kết quả A/B/C
├── results/
│   ├── ingest_log.json                  # Log chi tiết các trang PDF scan lỗi và phần loại trừ
│   ├── chunks_A.jsonl                   # 862 chunks của Chiến lược A
│   ├── chunks_B.jsonl                   # 658 chunks của Chiến lược B & C
│   ├── traces_A.jsonl                   # Trace top-3 đầy đủ 24 câu hỏi của Chiến lược A
│   ├── traces_B.jsonl                   # Trace top-3 đầy đủ 24 câu hỏi của Chiến lược B
│   ├── traces_C.jsonl                   # Trace top-3 đầy đủ 24 câu hỏi của Chiến lược C
│   ├── metrics.json                     # Thống kê độ dài chunk, thời gian, re-ingest và chỉ số dev/test
│   └── audit/                           # Bảng chấm thủ công Coherence, Metadata, Grounding & AUDIT_GUIDE.md
└── report/
    └── individual/
        └── 2A202603783_NguyenNhuDuyAn.md # Báo cáo cá nhân chi tiết
```
