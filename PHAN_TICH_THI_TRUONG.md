# Phân tích giá nhà ở Ireland và dự báo ba năm

## Phạm vi dữ liệu

Bản Kaggle v6 gồm 807.936 giao dịch ghi nhận từ 01/01/2010 đến 25/09/2026. Sau lọc cờ giá thị trường và VAT, còn 632.418 giao dịch gồm 630.422 nhà đã qua sử dụng và 1.996 nhà mới. Chuỗi chính dùng **620.495 giao dịch nhà đã qua sử dụng** trên 26 County từ quý I/2010 đến quý II/2026. Dữ liệu quý III/2026 dừng ngày 25/09, nên quý đó nằm ngoài phần quan sát của bản phân tích này. [Nguồn Irish Property Price Register, Kaggle v6](https://www.kaggle.com/datasets/fionnhughes/property-price-register)

Trong dữ liệu gốc, 556.504 bản ghi thiếu Eircode và 755.328 bản ghi thiếu kích thước nhà. Đơn vị địa lý dùng để gom nhóm là County. Mỗi điểm giá là trung vị của các giao dịch đủ điều kiện trong quý, đi cùng số giao dịch. Kỳ dưới 30 giao dịch vẫn có thể xem trên biểu đồ lịch sử. Bảng xếp hạng, thay đổi cùng kỳ và chuỗi dùng cho dự báo áp dụng ngưỡng 30.

## Kết quả quan sát quý II/2026

| County | Giá trung vị (EUR) | Giao dịch |
| --- | ---: | ---: |
| Dublin | 490.000 | 3.333 |
| Wicklow | 465.000 | 303 |
| Kildare | 433.000 | 449 |
| Cork | 340.000 | 1.126 |
| Kilkenny | 295.000 | 176 |

Dublin, Wicklow và Kildare có trung vị cao nhất. Dublin có số giao dịch lớn nhất, tiếp theo là Cork. Giá trung vị ở Kilkenny tăng 9,26% so với cùng quý năm trước. Các mức giá được tính theo EUR danh nghĩa và có thể thay đổi theo cơ cấu nhà được giao dịch.

## Cách dự báo và kiểm định

- So sánh ba mô hình theo County. Hai mô hình cơ sở giữ nguyên giá gần nhất hoặc lặp lại bốn quý gần nhất. Mô hình xu hướng lấy độ dốc log giá trong 20 quý, neo ở mức giá log trung bình của bốn quý cuối đã điều chỉnh tới quý cuối, rồi giảm tác động của độ dốc theo từng quý với hệ số 0,85.
- Chọn mô hình theo MAE trung bình của dự báo 12 bước ở các mốc cuốn chiếu. Cửa sổ có thể chồng lấp. Các quý dùng để chọn mô hình kết thúc trước quý III/2023.
- Giữ riêng quý III/2023 đến quý II/2026 để kiểm tra cả ba mô hình. Dự báo đoạn kiểm tra từ dữ liệu có đến hết quý II/2023. Sau kiểm tra, chạy mô hình đã chọn với dữ liệu đến quý II/2026 để dự báo **quý III/2026 đến quý II/2029**.
- Mục **Kiểm định** của dashboard vẽ giá thật và giá dự báo giả lập của mô hình đã chọn qua từng quý giữ riêng. Bảng bên cạnh cho biết giá thật, dự báo và chênh lệch có dấu. Khoảng giữ riêng gồm 12 quý đầy đủ cuối của chuỗi, bao gồm toàn bộ năm 2024–2025 và hai quý đầu năm 2026.
- Dải sai số dùng phân vị 10% và 90% của sai số cuốn chiếu theo từng bước dự báo, mở rộng để bao đường dự báo khi cần và chặn cận dưới tại 0 EUR. Đây là dải sai số thực nghiệm, chưa xác nhận độ bao phủ tương lai.
- Trong biểu đồ kiểm định, dải vàng cho dự báo cố định lấy sai số phát triển tương ứng từng bước từ 1 đến 12. Chế độ cập nhật luôn dự báo một quý nên dùng sai số phát triển của bước 1 cho cả 12 điểm. Dữ liệu ở giai đoạn kiểm tra chỉ dùng để đếm số quý giá thật nằm trong dải và tính sai số kiểm tra.

## Kết quả dự báo

Quy trình chọn mô hình xu hướng cho 19 County và mô hình giữ giá gần nhất cho 7 County. Trên giai đoạn giữ riêng, mô hình đã chọn có MAE thấp hơn mô hình giữ giá gần nhất ở 19 County. Dashboard hiển thị sai số từng mô hình theo County để người đọc tự đối chiếu.

| County | Quan sát quý II/2026 | Dự báo quý II/2029 | Dải sai số cuối kỳ | MAE kiểm tra |
| --- | ---: | ---: | ---: | ---: |
| Dublin | 490.000 EUR | 538.722 EUR | 523.924–614.025 EUR | 30.102 EUR |
| Kilkenny | 295.000 EUR | 326.541 EUR | 326.541–385.720 EUR | 18.777 EUR |

Dự báo phản ánh giá trung vị giao dịch của một County theo giả định từ chuỗi lịch sử. Biểu đồ dùng đường xanh liền cho quan sát và đường vàng đứt nét cho dự báo. Số giao dịch chỉ xuất hiện ở phần quan sát. Có thể tải CSV khung đang xem và dùng trường `series` để phân biệt hai loại dữ liệu.

Đoạn nối nét đứt đi từ điểm quan sát cuối tới điểm dự báo đầu. Hai điểm giữ nguyên giá trị gốc của chúng. Khi so sánh hai County, County thứ hai có đường quan sát xanh lục và đường dự báo tím đứt nét. CSV khung đang xem cũng gồm dự báo của cả hai County khi bật chế độ dự báo.

## Sai số ở Dublin và tác dụng của cập nhật theo quý

Giá trung vị Dublin tăng từ 430.000 EUR ở quý II/2024 lên 465.000 EUR ở quý III/2024. Tại quý III/2024, mô hình cố định từ quý II/2023 dự báo 432.748 EUR, thấp hơn khoảng 32.252 EUR. Đến quý II/2026, dự báo 441.346 EUR so với giá thật 490.000 EUR. Trên cả 12 quý, mô hình có MAE 30.102 EUR, sai số tương đối tuyệt đối trung bình 6,26% và lệch trung bình −28.114 EUR. Mô hình ngoại suy xu hướng cũ và giảm tác động của độ dốc theo thời gian, nên phản ứng kém với đợt tăng này. Trung vị cũng có thể đổi theo nhóm nhà giao dịch. Phép kiểm định chưa tách được các nguyên nhân thị trường.

Thử bỏ giảm tốc trong cùng mô hình xu hướng cho Dublin cho MAE khoảng 16.084 EUR trên đoạn kiểm tra, nhưng MAE ở giai đoạn chọn mô hình tăng từ 24.419 lên 31.669 EUR. Đây là thử nghiệm sau khi đã xem đoạn kiểm tra. Kết quả chưa đủ để đổi mô hình dự báo ba năm.

Chế độ **Dự báo quý kế tiếp, cập nhật mỗi quý** giữ nguyên mô hình đã chọn và dùng giá quan sát đến quý trước để dự báo một bước. Trên cùng 12 quý, MAE ở Dublin là khoảng 9.426 EUR. Cách này kiểm tra dự báo ngắn hạn khi có dữ liệu mới. Chân trời một quý và chân trời 12 quý trả lời hai câu hỏi khác nhau. Dữ liệu hiện tại là bản chụp đã công bố, nên kiểm định cập nhật giả định trung vị quý trước đã có sẵn. Để đo hiệu năng sát vận hành, cần lưu bản chụp theo ngày công bố và chỉ dùng bản đã có tại mỗi mốc.

Thiết kế tham khảo cách chọn khu vực, xem diễn biến và tải dữ liệu ở các cổng thị trường, cùng cách điều khiển khung thời gian trên biểu đồ chứng khoán. [Redfin](https://www.redfin.com/news/data-center/home-price-index/) · [Zillow](https://www.zillow.com/research/market-data/) · [TradingView](https://www.tradingview.com/support/solutions/43000748166-how-to-configure-your-supercharts/)

## Luồng demo và phạm vi xác nhận

`CSV Kaggle v6 → PySpark làm sạch và tổng hợp → bảng giá và số giao dịch theo County × quý → Python kiểm định và dự báo 12 quý → dashboard HTML`

PySpark 4.1.1 đã chạy trên toàn bộ CSV để chuẩn hóa, lọc và gom nhóm giao dịch. Python đọc bảng quý và thống kê chất lượng do Spark tạo, sau đó kiểm định, dự báo và đóng gói HTML. JavaScript trình bày số liệu và xử lý tương tác trên trình duyệt.

Trên một máy, kết quả Spark khớp với bản đối chiếu Python ở 6.261 nhóm theo tháng và 2.495 nhóm theo quý về số giao dịch, trung vị, trung bình và cờ ngưỡng mẫu. Dữ liệu nhúng trong [dashboard từ PySpark](outputs/pyspark_v6/dashboard.html) cũng khớp với bản đối chiếu, gồm 12 quý dự báo cho 26 County.
