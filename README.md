# Phân tích giá giao dịch nhà ở Ireland

Đồ án Nhập môn Dữ liệu lớn của Nhóm 2. Pipeline gồm bảy công đoạn từ dữ liệu nguồn tới tín hiệu rà soát theo County. Phần xử lý chính dùng PySpark để chuẩn hóa, lọc và tổng hợp theo tháng, quý. Python dùng bảng quý do Spark tạo để kiểm định, dự báo và đóng gói dashboard.

## Dữ liệu

Dùng `property_price_register.csv` trong [Irish Property Price Register trên Kaggle](https://www.kaggle.com/datasets/fionnhughes/property-price-register), phiên bản 6. Tệp đặt trong `data/` để chạy tại máy. Khi nộp đồ án, gửi mã và báo cáo theo quy định của lớp, để bộ dữ liệu ở ngoài gói nộp.

## Kết quả đã kiểm chứng

Bộ CSV có 807.936 giao dịch từ 01/01/2010 đến 25/09/2026. Kết quả đối chiếu bằng Python ghi nhận 630.422 giao dịch nhà cũ và 1.996 giao dịch nhà mới đạt bộ lọc. Các bảng tháng, quý và thống kê nguồn nằm trong `outputs/doi_chieu_python_v6/`.

Lượt chạy PySpark 4.1.1 trên toàn bộ CSV khớp với bảng đối chiếu Python ở 6.261 nhóm theo tháng và 2.495 nhóm theo quý, gồm số giao dịch, trung vị, trung bình và cờ ngưỡng mẫu. Dữ liệu nhúng trong dashboard khớp với bản đối chiếu, gồm 12 quý dự báo cho cả 26 County. Kết quả nằm trong [outputs/pyspark_v6](outputs/pyspark_v6/), có thể mở trực tiếp [dashboard từ PySpark](outputs/pyspark_v6/dashboard.html).

Trong `outputs/baseline_doi_chieu_q2_2026/`, kết quả kiểm định và dự báo cơ sở bao phủ 26 County. Tệp `dublin_theo_quy.png` minh họa giá trung vị, số giao dịch và hai đường dự báo của Dublin. Quý II/2026 là mốc được chọn vì CSV kết thúc trước khi quý III khép lại.

## Chạy pipeline bảy công đoạn

Dùng Python 3.11–3.13 và bộ JDK đầy đủ phiên bản 17 hoặc 21. Mở PowerShell tại thư mục đồ án và kiểm tra `JAVA_HOME` trỏ đến thư mục gốc của JDK. Trên Windows, đặt môi trường Python và JDK ở đường dẫn không có dấu ngoặc vì trình khởi động Spark có thể lỗi khi đọc các đường dẫn đó.

```powershell
$sparkEnv = Join-Path $env:LOCALAPPDATA 'nhom2-spark'
python -m venv $sparkEnv
$sparkPython = Join-Path $sparkEnv 'Scripts\python.exe'
& $sparkPython -m pip install -r requirements.txt
& $sparkPython -X utf8 .\pipeline.py .\data\property_price_register.csv --through 2026-Q2 --output .\outputs\pipeline_v6_parquet
```

Mỗi lượt chạy chọn một thư mục đầu ra mới. `run_manifest.json` được ghi sau khi cả bảy công đoạn hoàn tất. Tệp này ghi đầu vào, đầu ra và thời gian từng công đoạn. Nếu lượt chạy dừng giữa chừng, thư mục kết quả giữ lại các tệp đã tạo để kiểm tra lỗi.

| Công đoạn | Triển khai và đầu ra |
| --- | --- |
| Sources | Kiểm tra lược đồ CSV, ghi nguồn, phiên bản, dung lượng và SHA-256 vào `01_sources/source.json`. |
| Ingestion | Python producer ghi CSV vào vùng tạm theo khối byte và đối chiếu SHA-256 trước khi bàn giao. Xem `02_ingestion/receipt.json`. |
| Storage | Lưu snapshot CSV để đối chiếu và bản Parquet nén Snappy do PyArrow ghi. `03_storage/catalog.json` ghi đường dẫn, số dòng, dung lượng và SHA-256. |
| Processing | Spark đọc Parquet, dùng API DataFrame của PySpark để chuẩn hóa, lọc và tổng hợp. Kết quả nằm trong `04_processing/tables/`. |
| Analytics | Chọn mô hình, kiểm định giữ riêng và dự báo 12 quý theo County. CSV và JSON trong `05_analytics/`. |
| Presentation | Mở `06_presentation/dashboard.html` để tra cứu và so sánh County, hoặc nhập `06_presentation/grafana_dashboard.json` vào Grafana. |
| Decision/Action | Ghi danh sách County cần rà soát vào `07_decision_action/county_actions.csv`. Mặc định gắn cờ khi trung vị giá nhà cũ tăng hoặc giảm ít nhất 10% so với cùng quý năm trước và mỗi quý có ít nhất 30 giao dịch. |

`--alert-yoy-pct` chỉnh ngưỡng tín hiệu, theo đơn vị phần trăm. Quy tắc áp dụng trên giá thực tế đã quan sát. Lượt chạy lưu tín hiệu và hành động đề xuất tại máy.

Ảnh slide liệt kê sáu đoạn chuyển tiếp nối bảy công đoạn. Các công nghệ nhóm dùng lần lượt là **Python producer theo lô → PyArrow/Parquet → Spark/PySpark → PySpark và Python → Grafana hoặc HTML → Python rule engine**. Dữ liệu đầu vào là snapshot Kaggle, được xử lý theo lô.

### Xem kết quả bằng Grafana

1. Mở một Grafana cục bộ, thêm nguồn dữ liệu **TestData** trong **Connections → Data sources**.
2. Trong **Dashboards → New → Import**, tải lên `06_presentation/grafana_dashboard.json` và chọn nguồn TestData vừa thêm.
3. Dashboard có biểu đồ giá và dự báo, cùng bảng giá, số giao dịch và dự báo cuối kỳ theo County. Các khung dữ liệu nhúng từ lượt chạy thật qua **Raw Frames**, nên xuất lại JSON khi cập nhật snapshot.

### Chạy riêng Processing và dashboard

```powershell
& $sparkPython -X utf8 .\phan_tich.py .\data\property_price_register.csv --output .\outputs\v6
& $sparkPython -X utf8 .\truc_quan_hoa.py .\outputs\v6 --through 2026-Q2 --output .\outputs\v6\dashboard.html
```

Lệnh chạy Spark trên một máy. Mỗi lần chạy chọn một thư mục đầu ra mới.

| Đầu ra | Nội dung |
| --- | --- |
| `quality.json` | Số dòng đầu vào, số giao dịch đạt điều kiện, thống kê chất lượng, phiên bản Spark và SHA-256 của CSV |
| `prices_by_month.csv` | Giá trung vị, giá trung bình và số giao dịch theo County, tháng và loại nhà |
| `prices_by_quarter.csv` | Các chỉ số tương tự theo quý |
| `dashboard.html` | Quan sát đến Q2/2026, kiểm định và dự báo 12 quý tiếp theo, mở trực tiếp bằng trình duyệt |

`truc_quan_hoa.py` đọc `prices_by_quarter.csv` và `quality.json`, kiểm tra tổng số giao dịch giữa hai tệp rồi gọi mô-đun dự báo hiện có. Chỉ các bảng tổng hợp nhỏ được chuyển từ Spark sang Python.

## Bộ dữ liệu sạch ở cấp giao dịch

Để tái tạo bằng thư viện chuẩn của Python, chạy lệnh sau từ thư mục đồ án.

```powershell
python .\lam_sach.py .\data\property_price_register.csv --output .\outputs\lam_sach_lan_moi
```

Bản đối chiếu nằm trong `outputs/lam_sach_v6/`. Tệp `transactions_clean.csv` cũng có thể dùng để tạo dashboard ở chế độ đối chiếu Python. Tệp `cleaning_quality.json` ghi số dòng giữ, loại và thống kê kiểm tra. Xem [báo cáo làm sạch](outputs/lam_sach_v6/BAO_CAO_LAM_SACH.md) để biết cách đọc các cờ.

## Quy tắc tính

- Một giao dịch được đưa vào bảng giá khi ngày, County và giá hợp lệ, hai cờ `not_full_market_price` và `vat_exclusive` đều là `False`, và nhận diện được loại nhà. Nhà mới và nhà đã qua sử dụng được tổng hợp riêng.
- Thiếu Eircode hoặc kích thước nhà được thống kê. Các trường này không tham gia điều kiện lọc. Chương trình giữ các giao dịch nghi trùng để tránh xóa nhầm khi nguồn thiếu mã giao dịch duy nhất. Các bộ đếm lỗi theo trường có thể chồng lấp.
- Cột `meets_count_threshold` cho biết kỳ có đủ số giao dịch cùng County và loại nhà theo ngưỡng `--min-transactions` (mặc định 30). Dashboard và mô hình hiện dùng ngưỡng 30. Ngưỡng số lượng chưa xác nhận kỳ đã đầy đủ.

## Chạy thử dự báo cơ sở

Ví dụ dưới đây dùng quý II/2026 làm mốc thử nghiệm. `--through` nhận ngày đầu của kỳ cuối đã chọn. Cần rà soát độ trễ đăng ký trước khi chốt mốc trong báo cáo.

```powershell
python -X utf8 .\du_bao_co_so.py .\outputs\v6\prices_by_quarter.csv --period quarter --through 2026-04-01 --output .\outputs\baseline_q2_2026
```

Chương trình thử hai mô hình, giữ nguyên giá kỳ gần nhất và lặp lại mức giá cùng kỳ năm trước. Mỗi mô hình được đánh giá bằng MAE/RMSE trên 12 quý hoặc 36 tháng cuối. Trong lần kiểm định, mô hình chỉ dùng dữ liệu có trước đoạn đánh giá. Sau đó chương trình dùng dữ liệu đến mốc đã chọn để tạo dự báo 3 năm tiếp theo. Kết quả gồm `backtest.csv`, `forecasts.csv` và `skipped_counties.csv`. Chương trình bỏ qua County thiếu kỳ hoặc dưới ngưỡng trong cửa sổ dùng để kiểm định.

## Dashboard thị trường và dự báo ba năm

Mở `dashboard.html` được tạo ở trên trực tiếp bằng trình duyệt. Chọn County chính, County so sánh và quý quan sát. Dùng cuộn chuột, kéo ngang, nút thời gian hoặc hai thanh kéo để thay đổi khung đang xem. Nút tải CSV xuất các chuỗi đang xem, trong đó trường `series` phân biệt quan sát và dự báo.

[Báo cáo phân tích thị trường](PHAN_TICH_THI_TRUONG.md) ghi phạm vi, kết quả và cách kiểm định. Bản mặc định quan sát đến quý II/2026 và dự báo 12 quý tiếp theo.

### Tạo dashboard đối chiếu bằng Python

Chương trình dùng thư viện chuẩn của Python, không cần máy chủ. Chọn tên đầu ra mới cho mỗi lần chạy.

```powershell
python -X utf8 .\truc_quan_hoa.py .\outputs\lam_sach_v6\transactions_clean.csv --through 2026-Q2 --output .\outputs\truc_quan_hoa\dashboard_moi.html
```

Ở chế độ đối chiếu, `truc_quan_hoa.py` tổng hợp theo County và quý từ CSV sạch. Cả hai chế độ dùng `du_bao_thi_truong.py` để chọn mô hình, kiểm định và dự báo. Khi tạo tệp HTML, chương trình nhúng giao diện và kết quả, nên người mở dashboard chỉ cần tệp HTML.
