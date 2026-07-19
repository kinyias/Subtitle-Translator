# Subtitle Translate Studio

Nhận dạng phụ đề từ audio/video bằng CapCut, dịch phụ đề bằng AI (tuỳ chọn),
xem trước rồi xuất ra file `.srt`. Bản dịch chỉ thay đổi *nội dung* của từng
dòng phụ đề — thời gian (timeframe) của mỗi câu được giữ nguyên như CapCut trả về.

Recognize subtitles from audio/video via CapCut, optionally translate them with
an AI endpoint, preview, then export `.srt`. Translation only rewrites the text
of each cue; the original timings are preserved.

## Cách dùng / Usage

1. `pip install -r requirements.txt`
2. `python main.py`
3. Trang **Subtitle**:
   - Chọn file audio input.
   - Nhập ngôn ngữ nhận dạng (vd `zh-CN`, `en-US`, `vi-VN`).
   - Bật **Use Translation** để hiện các ô cấu hình AI:
     - **Endpoint URL** — API tương thích OpenAI `/chat/completions`
       (OpenAI, OpenRouter, Groq, LM Studio, Ollama, ...).
     - **API Key** — khoá API (ẩn dạng `*`).
     - **Model** — tên model, vd `gpt-4o-mini`.
     - **Target Language** — ngôn ngữ đích, vd `Vietnamese`.
     - **Style Prompt** — phong cách/tông giọng dịch (textarea).
   - Bấm **Generate Subtitles**: upload → nhận dạng → poll → (dịch AI) chạy ngầm.
   - Xem **Preview** phụ đề, rồi bấm **Export SRT** để lưu file.

Thông tin URL / API key / model / target language / style prompt được lưu vào
`config/config.json` và tự động nạp lại lần sau.

## Vì sao timeframe không bị ảnh hưởng / Why timings are safe

Trình dịch chỉ gửi cho AI một mảng JSON gồm `{"id", "text"}` — **không có
timestamp**. AI trả về đúng số dòng, khớp theo `id`; nếu thiếu dòng nào thì giữ
nguyên bản gốc. SRT xuất ra dùng `start_ms`/`end_ms` gốc từ CapCut, không bao
giờ suy ra từ bản dịch. Dịch theo lô 40 dòng để request nhỏ và ổn định.

## Build

```
pyinstaller --onefile --windowed main.py
```

`config/` và `device.json` được tạo cạnh file thực thi ở lần chạy đầu.

## Cấu trúc / Structure

- `services/capcut_api.py` — backend CapCut (upload + STT), dùng lại nguyên bản.
- `services/stt_service.py`, `uploader.py`, `query_service.py`, `results.py` — lớp bọc STT.
- `services/translator.py` — gọi AI dịch, map theo `id`, giữ thứ tự & số dòng.
- `services/pipeline.py` — upload → recognize → poll → (dịch) → danh sách cue.
- `services/srt.py` — dựng/ghi SRT từ cue, giữ nguyên timing.
- `gui/` — giao diện CustomTkinter (Subtitle / Settings / Logs).
