# Judge audit

Chạy:
- `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 8`
- `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 8`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| `tone_ok` | 100 | 0.757 | 0.857 | 0.800 | Có (κ=0.757 ≥ 0.6, P=0.857 ≥ 0.8, R=0.800 ≥ 0.7) | **dùng** |
| `helpful` | 100 | 0.375 | 1.000 | 0.300 | Không (κ=0.375 < 0.6, R=0.300 < 0.7) | **loại** |

## Audit thủ công các case bất đồng (`judge_tone_public.csv` và `judge_helpful_public.csv`)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | `H-008` | PASS | FAIL | Người đúng | `"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."` — xưng `"em"` + `"nha"` quá suồng sã; cập nhật rubric tone cấm đại từ thân mật (`em/nha/bạn`), bắt buộc `anh/chị` và `LogiX`. |
| 2 | `H-029` | PASS | FAIL | Người đúng | `"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."` — judge bị đánh lừa bởi từ `"Dạ, vui lòng"`; bổ sung negative rule trong rubric: câu mang tính ra lệnh/xua đuổi là `FAIL`. |
| 3 | `H-042` | FAIL | PASS | Người đúng | `"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."` — câu trả lời ngắn gọn, lịch sự, đủ ý; sửa rubric nêu rõ không bắt buộc phải có từ `"xin lỗi"` trong case hoàn tiền bình thường. |
| 4 | `H-051` | FAIL | PASS | Người đúng | `"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."` — chính sách CSKH LogiX cho phép dùng từ `"refund"`; bổ sung whitelist thuật ngữ `"refund"` vào rubric judge. |
| 5 | `H-063` | PASS | FAIL | Người đúng | `"Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ."` — hứa `"sẽ hoàn thêm"` ngoài kết quả hệ thống; cấm cam kết hoàn bổ sung không có trong ledger. |
| 6 | `H-070` | PASS | FAIL | Người đúng | `"Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂"` — dùng emoji cười trong ngữ cảnh khiếu nại; thêm rule cấm emoji vào rubric tone. |
| 7 | `H-081` | FAIL | PASS | Judge đúng | `"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."` — nhãn người đọc nhầm ticket thành FAIL trong khi reply lịch sự đúng mẫu; sửa lại nhãn người trong tập audit. |
| 8 | `H-088` | FAIL | PASS | Người đúng | `"Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ."` — lặp `"Dạ"` do lỗi gõ nhẹ, người chấp nhận; làm rõ mức phạt typo nhẹ không tự động FAIL nếu tổng thể lịch sự. |
| 9 | `HL-015` | PASS | FAIL | Người đúng | `"Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ."` (ledger ghi `40.000đ`) — judge không có ground-truth ledger nên chấm PASS cho câu sai tiền; tách việc kiểm tra số tiền sang code grader `ReplyLedgerMatch` (FM-08). |
| 10 | `HL-016` | PASS | FAIL | Người đúng | `"Dạ, LogiX thành thật xin lỗi... LogiX đã hoàn 55.000đ cho đơn O-404..."` (ledger ghi `35.000đ`) — verbosity bias: reply dài, xin lỗi nhiều làm judge bỏ qua sai số tiền; không dùng judge chấm tính đúng đắn nghiệp vụ/tiền. |

## Kết luận
- **Tiêu chí bị loại:** `helpful` (`judge_helpful_public.csv`) bị **loại** hoàn toàn khỏi gate vì `κ = 0.375 < 0.6` và `Recall = 0.300 < 0.7`. Theo ma trận nhầm lẫn (`tp=9, fp=0, fn=21, tn=70`), judge chỉ bắt được 9/30 ca lỗi thực tế (`observed_fail_rate = 0.09`, trong khi tỷ lệ lỗi thực hiệu chỉnh Rogan-Gladen là `corrected_fail_rate = 0.30`). Nguyên nhân gốc: 18/21 ca bị lọt (`FN`) là lỗi **sai số tiền so với ledger** nhưng câu trả lời dài dòng, lịch sự (verbosity bias), và 3/21 ca là sai xưng hô (`"Ok bạn"`). Vì judge replay chỉ đọc văn bản reply mà không thấy `refund_ledger`, việc dùng `helpful` làm gate sẽ tạo cảm giác an toàn giả và cho lọt 70% ca lỗi.
- **Tiêu chí dùng được:** `tone_ok` (`judge_tone_public.csv`) đạt cả 3 ngưỡng (`n=100, P=0.857, R=0.800, κ=0.757`, ma trận `tp=24, fp=4, fn=6, tn=66`, Rogan-Gladen hiệu chỉnh `0.28 -> 0.30`). Có thể dùng để theo dõi chất lượng giọng văn sau khi sửa rubric như bảng trên, còn mọi kiểm tra tiền và phê duyệt đều chấm bằng code.
- **Rủi ro còn lại:** Judge chỉ được kiểm trên dữ liệu replay đã công khai (`100` mẫu/tiêu chí); cần gán nhãn người mới trên tập held-out trước khi đưa judge vào làm cổng blocking thực tế.
