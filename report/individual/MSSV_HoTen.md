# Báo cáo cá nhân - Day 6

- **Họ và tên:** Nguyễn Như Duy An
- **MSSV:** 2A202603783
- **Lớp:** L3B

## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - **Chủ đề:** Quy định pháp luật về điều kiện lao động và quan hệ lao động tại Việt Nam.
  - **Nguồn và quyền sử dụng:**
    1. **Bộ luật Lao động số 45/2019/QH14** (`source_id: blld-2019`), Quốc hội ban hành ngày 20/11/2019, hiệu lực từ 01/01/2021 - bản `.doc` chính thức từ Công báo nước CHXHCN Việt Nam số 993 + 994 (`data/raw/2019_993 + 994_45-2019-QH14.doc`).
    2. **Nghị định số 145/2020/NĐ-CP** (`source_id: nd-145-2020`), Chính phủ ban hành ngày 14/12/2020, hiệu lực từ 01/02/2021 - bản `.doc` chính thức từ Công báo số 1203 + 1204 và 1205 + 1206 (`data/raw/2020_1203 + 1204_145-2020-NĐ-CP.doc` & `data/raw/2020_1205 + 1206_145-2020-NĐ-CP.doc`).
    - **Quyền sử dụng:** Thuộc phạm vi công cộng (Public Domain) theo khoản 2 Điều 15 Luật Sở hữu trí tuệ Việt Nam (văn bản quy phạm pháp luật không thuộc đối tượng bảo hộ quyền tác giả, được phép sao chép, trích dẫn và tái phân phối).
  - **Số đơn vị nội dung và quy tắc tính:**
    - Theo `GUIDE.md` (Mục 1), với văn bản `.doc` không có phân trang vật lý cố định, corpus được chia theo cấu trúc Chương/Mục có ý nghĩa độc lập sao cho mỗi đơn vị có **tối thiểu 1.500 ký tự nội dung đã chuẩn hóa**.
    - Tổng cộng có **52 đơn vị nội dung hợp lệ** (vượt ngưỡng tối thiểu 30 trang/đơn vị): `blld-2019` có **28 đơn vị** (`blld-2019-p01`..`p28`, 189.822 ký tự) và `nd-145-2020` có **24 đơn vị** (`nd-145-2020-p01`..`p24`, 189.337 ký tự). Tổng cộng **379.159 ký tự** chuẩn hóa; đơn vị nhỏ nhất có **1.505 ký tự**, lớn nhất **17.567 ký tự**. Chi tiết từng đơn vị được lưu tại `data/manifest.json`.
- **Chuẩn hóa, lỗi và giới hạn:**
  - **Chuẩn hóa (`starter/src/ingestion.py`):** Giải mã trực tiếp luồng `WordDocument` và `1Table` từ định dạng nhị phân OLE2 Word 97-2003 (`olefile`), chuẩn hóa Unicode về dạng `NFC`, đổi ký tự ngắt dòng mềm `\x0b` thành `\n`, loại bỏ các mã trường Word (`\x13 PAGE \x14...\x15`) và dòng tiêu đề chạy đầu/cuối trang Công báo (`CÔNG BÁO/Số...`), thu gọn khoảng trắng ngang nhưng giữ nguyên cấu trúc xuống dòng giữa các Điều/Khoản.
  - **Ghi nhận lỗi và phần loại trừ (`results/ingest_log.json`):**
    1. Hai file PDF ký số tải từ cổng Chính phủ (`blld-2019-45-qh14.pdf` 83 trang và `nd-145-2020.pdf` 122 trang, tổng 205 trang vật lý) là bản scan ảnh không có lớp văn bản (`pypdf` trích xuất được 0 ký tự ở cả 205 trang) → được ghi log lỗi (`scanned_pdf_no_text_layer`) và thay bằng bản `.doc` Công báo chính thức.
    2. Loại bỏ phần bìa/mục lục số Công báo ở đầu file (521 ký tự ở cuốn 1203+1204 và 827 ký tự ở cuốn 1205+1206) cùng phần Phụ lục biểu mẫu trống (Phụ lục I-III) và Thông báo số 61/2020/TB-LPQT (Hiệp định tương trợ tư pháp với Campuchia in ghép ở cuối cuốn Công báo 1205+1206, 50.105 ký tự).
    3. Trong file `.doc` của Nghị định 145/2020, chữ `"Điều X."` được Word định dạng bằng tính năng đánh số tự động (auto-numbering list) nên không nằm trong luồng plain-text của OLE2 (chỉ còn dòng tiêu đề Điều); ngoài ra Chương cuối ("Điều khoản thi hành") bị Công báo in nhầm số La Mã thành `"Chương XI"` trùng với Chương XI trước đó → đã chuẩn hóa lại thành `"Chương XII"` và ghi log đầy đủ.
- **Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí:**
  - **Embedding model:** `google/embeddinggemma-2` chạy local qua `sentence-transformers` `6.3.0` (`transformers` `5.23.0`, `torch` `2.15.0`, `dtype=torch.float32`), số chiều **768**, chuẩn hóa vector L2 (`normalize_embeddings=True`).
  - **Cách xử lý query/document:** Sử dụng prompt bất đối xứng chuẩn của model: `model.encode_document(...)` cho văn bản chunk và `model.encode_query(...)` cho câu hỏi truy vấn.
  - **Vector store:** `ChromaDB` `1.5.9` (`chromadb.PersistentClient`), lưu bền vững trên đĩa tại `results/chroma`, khoảng cách `cosine` (`hnsw:space = cosine`, Approximate Nearest Neighbor HNSW).
  - **Kiểm tra nạp lại (Re-ingestion idempotency):** Tạo `chunk_id` tất định theo `{document_id}-p{page:02d}-{strategy}-{index:03d}-{sha1_8}` và xóa các chunk cũ của cùng `document_id` không còn trong danh sách mới trước khi `upsert`. Khi chạy nạp lại lần 2, số bản ghi giữ nguyên (`Strategy A: 862 -> 862`, `Strategy B: 658 -> 658`, `obsolete_removed = 0`).
  - **Lệnh chạy tái lập:**
    ```powershell
    $env:PYTHONPATH="."
    .\.venv\Scripts\python.exe starter/scripts/verify_benchmark.py
    .\.venv\Scripts\python.exe -m starter.src.run
    .\.venv\Scripts\python.exe starter/scripts/prepare_audit_sheets.py
    ```
  - **Chi phí:** **0 USD** (chạy hoàn toàn local trên CPU).
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - **Metadata bắt buộc:** `document_id` (`blld-2019` | `nd-145-2020`), `source` (đường dẫn file `.doc` gốc), `page` (số thứ tự đơn vị nội dung `1..28` hoặc `1..24`), `unit_id` (`blld-2019-p01`..).
  - **Trường lọc bổ sung:**
    - `document_type` (`"bo_luat"` vs `"nghi_dinh"`): lấy trực tiếp từ loại văn bản pháp quy, giúp phân biệt quy định khung tại Bộ luật với quy định chi tiết/hướng dẫn tại Nghị định.
    - `year` (`2019` vs `2020`), `effective_date` (`"2021-01-01"` vs `"2021-02-01"`), `chapter`, `section`: trích xuất trực tiếp từ tiêu đề văn bản và cấu trúc Chương/Mục trong nguồn, hoàn toàn không suy đoán.

## Cấu hình và benchmark
- **A / B / C (tham số cụ thể, khác biệt duy nhất B-C):**
  - **Chiến lược A (`fixed_size`):** Chia cửa sổ ký tự cố định `size = 500` ký tự, `overlap = 50` ký tự trên từng đơn vị nội dung; gắn đầy đủ metadata nhưng **không lọc** khi truy xuất (`filters = None`). Tạo ra **862 chunks** (độ dài TB 486,4 ký tự).
  - **Chiến lược B (`by_paragraph`):** Chia theo cấu trúc Điều/Khoản và đoạn văn (`max_size = 800` ký tự), tự động gắn dòng tiêu đề Chương/Mục hoặc tên Điều vào các đoạn bị tách dài, gộp các đoạn đuôi quá ngắn (`< 150` ký tự); gắn cùng bộ metadata như A và **không lọc** khi truy xuất. Tạo ra **658 chunks** (độ dài TB 599,2 ký tự).
  - **Chiến lược C (`by_paragraph` + metadata filter):** Dùng **cùng các chunk và cùng collection vector của B** (658 chunks), chỉ khác duy nhất ở bước truy xuất: áp dụng bộ lọc metadata (`where={"document_type": ...}` hoặc `where={"year": ...}`) đối với các câu hỏi có ngữ cảnh filter được cung cấp trước; với câu không có filter thì chạy giống hệt B.
- **≥20 câu: phân chia ≥15 dev / ≥5 test, câu metadata filter và cách kiểm chứng evidence:**
  - Bộ benchmark (`benchmark/questions.json`) gồm **24 câu hỏi**, chia cố định trước khi chạy thử thành **18 câu `dev` (`q01`..`q18`)** và **6 câu `test` (`q19`..`q24`)**, mỗi tập cân bằng 50% từ `blld-2019` và 50% từ `nd-145-2020`.
  - Bao gồm 4 nhóm câu: trực tiếp (`truc_tiep`), diễn đạt lại (`dien_dat_lai`), điều kiện/ngoại lệ (`dieu_kien_ngoai_le`), và **7 câu kiểm tra lọc metadata (`metadata_filter`)**: 5 câu trên `dev` (`q03, q04, q09, q14, q16`) và 2 câu trên `test` (`q21, q22`). Các câu có nhiều nguồn bằng chứng hợp lệ (`q06`, `q19`) đều ghi nhận đầy đủ trong `alt_gold`.
  - **Kiểm chứng evidence:** Chạy `starter/scripts/verify_benchmark.py` xác nhận 24/24 câu hỏi (`all_passed = true` trong `benchmark/verify_report.json`) có `evidence_quote` tồn tại nguyên văn trong trang gold sau chuẩn hóa.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test:**
  - Chốt trước trong `benchmark/questions.json` (`pre_registered_selection_criteria`): (1) Ưu tiên cao nhất là `Evidence Hit@3` trên tập `dev`; (2) Nếu bằng nhau, xét `Hit@1` trên tập `dev` và tỷ lệ tuân thủ filter (`Filter Compliance`) trên các câu `dev` có filter; (3) Tiếp theo xét điểm mạch lạc `Chunk Coherence` thủ công và chi phí/số lượng chunk.

## Kết quả

### Bảng 1: Kết quả truy xuất tự động và tài nguyên
| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian (Ingest / Query 24 câu) | Chi phí |
|---|---|---|---|---:|---|---|
| **A** (`fixed_size` 500/50) | `dev` | **10/18** (55,6%) | **13/18** (72,2%) | 862 | 346,26s / 0,142s | 0 USD |
| **A** (`fixed_size` 500/50) | `test` | **4/6** (66,7%) | **6/6** (100,0%) | 862 | (dùng chung index A) | 0 USD |
| **B** (`by_paragraph` max 800) | `dev` | **15/18** (83,3%) | **17/18** (94,4%) | 658 | 334,34s / 0,101s | 0 USD |
| **B** (`by_paragraph` max 800) | `test` | **4/6** (66,7%) | **6/6** (100,0%) | 658 | (dùng chung index B) | 0 USD |
| **C** (`B` + metadata filter) | `dev` | **15/18** (83,3%) | **17/18** (94,4%) | 658 | (dùng chung B) / 0,086s | 0 USD |
| **C** (`B` + metadata filter) | `test` | **4/6** (66,7%) | **6/6** (100,0%) | 658 | (dùng chung B) | 0 USD |

### Bảng 2: Kết quả đánh giá thủ công (Coherence, Metadata, Grounding)
| Strategy | Coherence trung bình /2 (n=10) | Metadata đủ và đúng (n/N trên test×top-3) | Filter tuân thủ (dev / test) | Grounding 0/1/2 (số câu trên 6 câu test) và trung bình /2 |
|---|---|---|---|---|
| **A** (`fixed_size` 500/50) | **0,70 / 2** (n=10; `0`: 3, `1`: 7, `2`: 0) | **18/18** (100%) | `3/5` (dev) · `2/2` (test) | `0`: 0 · `1`: 2 (`q19, q23`) · `2`: 4 (`q20, q21, q22, q24`) → **TB: 1,67 / 2** |
| **B** (`by_paragraph` max 800) | **2,00 / 2** (n=10; `0`: 0, `1`: 0, `2`: 10) | **18/18** (100%) | `4/5` (dev) · `2/2` (test) | `0`: 0 · `1`: 1 (`q23`) · `2`: 5 (`q19, q20, q21, q22, q24`) → **TB: 1,83 / 2** |
| **C** (`B` + metadata filter) | **2,00 / 2** (n=10, cùng chunk với B) | **18/18** (100%) | **`5/5` (dev) · `2/2` (test)** | `0`: 0 · `1`: 1 (`q23`) · `2`: 5 (`q19, q20, q21, q22, q24`) → **TB: 1,83 / 2** |

- **Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
  - Trace đầy đủ top-3: `results/traces_A.jsonl`, `results/traces_B.jsonl`, `results/traces_C.jsonl` và tổng hợp tại `results/metrics.json`.
  - File chấm thủ công (đã hoàn tất 100% nhãn và lý do):
    - `results/audit/coherence_audit.csv`: 10 vị trí nguồn cố định trước khi xem điểm (5 đơn vị đầu `blld-2019-p01..p05` và 5 đơn vị đầu `nd-145-2020-p01..p05` tại mốc ký tự ~520). Chiến lược A đạt **0,70/2** (3 vị trí `pos_04, pos_06, pos_08` bị 0 điểm do cắt ngang chữ làm mất tiêu đề Điều và câu dẫn mở đầu; 7 vị trí còn lại đạt 1 điểm do bị cụt đầu/cuối chunk). Chiến lược B & C đạt **2,00/2** nhờ giữ nguyên tiêu đề Chương/Mục/Điều và kết thúc trọn câu.
    - `results/audit/metadata_audit.csv`: 6 câu test × top-3 × 3 chiến lược = **54/54 bản ghi** (`18/18` mỗi chiến lược) đều có metadata `document_id`, `source`, `page`, `document_type`, `year`, `section` đầy đủ và khớp chính xác với đơn vị nội dung gốc. Trường `document_type` và `year` chứng minh tính hữu ích trực tiếp khi giúp Chiến lược C loại bỏ các chunk nhiễu khác văn bản ở `q04`, nhưng có hạn chế là đòi hỏi ngữ cảnh người dùng phải biết trước đang tra cứu ở cấp Luật hay Nghị định.
    - `results/audit/grounding_audit.csv`: Chấm trên 6 câu test (`q19..q24`). Dù chỉ số tự động `Evidence Hit@3` đạt `6/6` cho cả 3 chiến lược, chấm thủ công Grounding phát hiện sự khác biệt quan trọng: ở câu `q19`, Chiến lược A chỉ đạt **1 điểm** (Top 2 bị cắt mất điểm b giải thích ngoại lệ tự ý bỏ việc 05 ngày liên tục) trong khi B và C đạt **2 điểm**; ở câu `q23` (lao động giúp việc gia đình báo trước 15 ngày), cả A, B, C đều đạt **1 điểm** vì đã truy xuất đúng điểm d nêu mốc 15 ngày nhưng phần liệt kê chi tiết các trường hợp không phải báo trước (`d1, d2`) nằm ở đoạn kế tiếp ngoài phạm vi chunk. Nhờ vậy, điểm Grounding trung bình tăng từ **1,67/2** (A) lên **1,83/2** (B và C).
  - **Ghi chú người chấm & nguy cơ thiên lệch:** Người chấm thủ công chính là tác giả xây dựng pipeline nên có nguy cơ thiên lệch xác nhận (confirmation bias); để giảm thiểu, các vị trí chấm coherence và bộ câu hỏi test đã được cố định trước khi chạy và toàn bộ văn bản chunk được xuất minh bạch trong CSV.

## Phân tích và kết luận
- **So sánh A-B và B-C; 2 ví dụ sai cụ thể có ID câu và nguồn:**
  - **So sánh A và B (Tác động của chiến lược Chunking):**
    - Việc chuyển từ chia cố định 500 ký tự (`A`) sang chia theo cấu trúc Điều/Khoản tối đa 800 ký tự (`B`) giúp tăng **Dev Hit@1 từ `10/18` (55,6%) lên `15/18` (83,3%)** và **Dev Evidence Hit@3 từ `13/18` (72,2%) lên `17/18` (94,4%)**, đồng thời giảm 23,7% số lượng chunk (từ 862 xuống 658 chunks) và giảm thời gian ingest từ 346,3s xuống 334,3s.
    - **Ví dụ lỗi 1 - Cắt đứt câu bằng chứng ở ranh giới cửa sổ cố định (`q03` và `q10`, nguồn `blld-2019` page `4` & page `15`):**
      - Ở câu `q03` (*thời hạn báo trước khi đơn phương chấm dứt HĐLĐ xác định thời hạn 12-36 tháng*, gold tại `blld-2019` page `4` - Điều 35), Chiến lược A trả về top-1 là chunk `blld-2019-p04-fixed-006-9af586d1` (score `0.8845`), đúng trang nguồn nhưng cửa sổ 500 ký tự cắt cụt mất phần đầu câu (`"ộng xác định thời hạn có thời hạn từ 12 tháng đến 36 tháng;"`, thiếu hẳn cụm *"b) Ít nhất 30 ngày nếu làm việc theo hợp đồng lao động..."* nằm ở chunk `fixed-005` liền trước). Tương tự ở câu `q10` (`blld-2019` page `15` - Điều 139 khoản 4 về đi làm sớm trước khi hết nghỉ thai sản), chunk top-1 `blld-2019-p15-fixed-014-224d5465` của A cũng cắt đôi khoản 4 (`split=True`). Trong khi đó, Chiến lược B giữ trọn vẹn từng khoản cùng tiêu đề `Điều 35` (`blld-2019-p04-para-004-fa50fd6f`) và `Điều 139` (`blld-2019-p15-para-013-20e725fd`), đạt `Hit@1 = True` ở cả hai câu.
  - **So sánh B và C (Tác động của lọc Metadata) & Ví dụ lỗi 2 (`q04` và `q07`):**
    - Trên các câu hỏi có yêu cầu phạm vi văn bản (`filter`), Chiến lược B (không lọc) đạt `4/5` câu tuân thủ filter trên tập `dev`, còn Chiến lược C (có lọc `document_type`/`year`) đạt tuyệt đối **`5/5` trên `dev` và `2/2` trên `test`**.
    - **Ví dụ lỗi 2a - Nhiễu chéo giữa Bộ luật và Nghị định khi không lọc metadata (`q04`, nguồn `nd-145-2020` page `3`):** Câu `q04` hỏi thời hạn báo trước đối với ngành, nghề đặc thù (tổ lái tàu bay, người quản lý doanh nghiệp) theo Nghị định (`filter: {"document_type": "nghi_dinh"}`). Khi không lọc, Chiến lược B kéo chunk `blld-2019-p04-para-004-fa50fd6f` (quy định báo trước 30/45 ngày của Bộ luật Lao động) vào vị trí Rank 3 (`score = 0.8184`), gây nguy cơ LLM trộn lẫn mức 30/45 ngày với mức 120 ngày của ngành đặc thù. Chiến lược C lọc `document_type = "nghi_dinh"` đã loại bỏ hoàn toàn chunk của Bộ luật khỏi top-3.
    - **Ví dụ lỗi 2b - Trường hợp cả B và C đều trượt `Hit@3` (`q07`, nguồn `blld-2019` page `11` - Điều 107):** Câu `q07` hỏi giới hạn số giờ làm thêm trong 01 năm theo quy định chung (200 giờ) và trường hợp đặc biệt (300 giờ) nhưng không gắn filter. Do Chương VII của Nghị định 145/2020 (`nd-145-2020-p12-para-004-c0353244` và `para-003`) lặp lại rất dày đặc cụm từ *"Giới hạn số giờ làm thêm"*, cả B và C đều xếp 2 chunk của Nghị định lên Rank 1 và Rank 2, còn Rank 3 rơi vào chunk `blld-2019-p11-para-002-6b08df0c` (chứa phần đầu Điều 107 về giới hạn ngày/tháng, ngay trước điểm c khoản 2 quy định 200 giờ/năm).
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - **Chiến lược được chọn:** **Chiến lược C** (`by_paragraph` max 800 ký tự + lọc metadata khi có filter), được chốt dựa trên tiêu chí tập `dev` (`Evidence Hit@3 = 17/18`, `Hit@1 = 15/18`, `Filter Compliance = 5/5`) trước khi đánh giá tập `test` (`Hit@1 = 4/6`, `Evidence Hit@3 = 6/6`).
  - **Đánh đổi (Trade-offs):**
    - Chia theo cấu trúc (`B/C`) đòi hỏi quy tắc nhận diện đầu mục (`Chương`, `Mục`, `Điều`) phù hợp với loại tài liệu và tạo ra các chunk có độ dài biến thiên (155-918 ký tự), nhưng đổi lại giảm 23,7% số vector phải lưu và khắc phục triệt để lỗi đứt câu ở ranh giới cửa sổ cố định.
    - Lọc metadata (`C`) giúp đảm bảo 100% kết quả nằm đúng văn bản mục tiêu khi người dùng/ngữ cảnh biết rõ phạm vi (`bo_luat` hay `nghi_dinh`), nhưng nếu người dùng đặt câu hỏi chung không biết thông tin nằm ở Luật hay Nghị định (hoặc truyền sai filter) thì việc lọc cứng có thể làm mất nguồn giải thích bổ sung ở văn bản kia.
- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí:**
  - Tập `test` chỉ có 6 câu hỏi (và `dev` 18 câu) nên sai số mẫu lớn (1 câu trên tập `test` tương đương 16,7%); kết quả `6/6` Evidence Hit@3 trên `test` chỉ mang tính minh họa cho corpus pháp luật lao động này, không suy rộng cho mọi bộ dữ liệu.
  - File `.doc` của Nghị định 145/2020 bị mất nhãn tự động `"Điều X."` trong luồng plain-text của Word, làm giảm một phần tín hiệu tiêu đề Điều so với Bộ luật Lao động 2019.
  - Việc đo thời gian thực hiện trên CPU một máy cá nhân nên phụ thuộc tải hệ thống; chi phí bằng 0 USD do dùng model mở local nhưng đánh đổi bằng thời gian tính embedding (~5,5 phút cho mỗi chiến lược trên CPU).
- **Nếu làm lại hoặc mở rộng, cải tiến gì?**
  1. **Khôi phục số thứ tự Điều tự động trong file `.doc`:** Phân tích thêm cấu trúc list numbering (`PlcfLst` / `PlfLfo`) trong luồng `1Table` của OLE2 hoặc chuyển đổi qua LibreOffice headless để giữ nguyên chữ `"Điều 1." .. "Điều 115."` cho Nghị định 145/2020.
  2. **Kết hợp Hybrid Retrieval (Dense + BM25):** Như thấy ở lỗi câu `q07` và `q23`, tìm kiếm ngữ nghĩa đơn thuần dễ xếp các đoạn có từ khóa chung ("giới hạn số giờ làm thêm") lên trên đoạn chứa con số cụ thể ("200 giờ", "300 giờ", "15 ngày"). Kết hợp BM25 với embedding `google/embeddinggemma-2` sẽ giúp bắt chính xác hơn các con số định lượng và số hiệu Điều/Khoản.
  3. **Hierarchical / Parent-Document Retrieval:** Lưu vector ở mức Khoản nhỏ (300-400 ký tự) nhưng khi truy xuất thì trả về toàn bộ Điều cha để vừa khớp chính xác câu hỏi hẹp vừa đảm bảo đủ mọi điều kiện/ngoại lệ.
