# Trace case: từ trace tới quyết định sai đầu tiên

Lệnh đối chiếu chạy từ `src/`:
```bash
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
```

## Case phân tích (`seeded_regression C-002@11`)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, report `reports/eval_seeded_regression.json`, run ID `E-seeded_regression-20261117-d35f` |
| Triệu chứng | `lab8` grader fail (`status resolved != denied`); reply nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."` và ledger ghi `refund_vnd=20000`, `refund_count=1`, trong khi nhãn chuẩn là `status=denied`, `refund_vnd=0`, `refund_count=0`. |
| Bước sai đầu tiên | Event **3** `model_override`: `{"delay_days": 5}` — agent lấy số ngày trễ `5` từ văn bản ticket (`"Đơn giao trễ 5 ngày..."`) ghi đè lên dữ liệu DB (`delay_days=2`). |
| Vì sao là bước *đầu tiên* | Event **1** (`handoff`) tạo handoff read-only hợp lệ cho `C-002` không rò secret; Event **2** (`investigator`) gọi `lookup_order` trả về đúng dữ liệu DB của `O-202` (`visible=true`, `status="delivered"`, `delay_days=2`, `shipping_fee_vnd=20000`). Mọi thông tin đầu vào trước bước 3 đều chính xác; sai lệch chỉ xuất hiện từ event 3 trở đi và kéo theo event 4 (`quote=20000`) và việc commit refund sai. |
| Failure mode | `FM-03` (`ticket_trust` — tin ticket hơn DB) trong [failure_taxonomy.md](file:///c:/Users/duong/.gemini/antigravity/scratch/K5-L3A-DAY09-DuongManhHung-2A202603431-EvaluationandFailureAnalysis/docs/failure_taxonomy.md) |
| Đối chứng | Trên `fixed C-002@11`: không có event `model_override`. Sau event 2 (`investigator`), event 3 là `quote` (`{"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": [], "parts": {}}`), event 4 là `reply` từ chối, ledger ghi `refund_vnd=0`, `refund_count=0`, `status=denied` (`PASS`). |
| Regression test | `test_trace_case_c002_seed11_catches_fm03_and_passes_fixed` trong [test_lab9_trace_case.py](file:///c:/Users/duong/.gemini/antigravity/scratch/K5-L3A-DAY09-DuongManhHung-2A202603431-EvaluationandFailureAnalysis/src/tests/test_lab9_trace_case.py): kiểm tra `DbFactKept` (bắt event `model_override` ở bước 3) và `RefundAmountCorrect` (`20000 != 0`) đều fail trên `seeded_regression C-002@11` và pass trên `fixed C-002@11`. |
| Chưa chắc chắn | Một bug tin ticket nhưng **không ghi event `model_override`** (ví dụ `quiet_override`) sẽ lọt qua `DbFactKept`, nên vẫn cần outcome grader `RefundAmountCorrect` và các slice gate (`denial`, `adversarial`) để chặn ở mức kết quả ledger. |
