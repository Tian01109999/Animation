# StoryToon Desktop

Ứng dụng Windows portable chuyển kịch bản người dùng nhập thành phim hoạt hình 2D.

1. Mở `StoryToon-Desktop-Portable.exe`, đăng nhập tài khoản 24Media đã được cấp quyền trong Account Manager. Sau đó đăng nhập ChatGPT tại **Tài khoản & Cài đặt** để AI phân tích kịch bản.
2. Nhập kịch bản, bấm **Tách kịch bản**. AI chọn nhân vật và bối cảnh có sẵn trong kho.
3. Mở **Kho assets** để xem, tìm theo giới tính, tuổi, tóc, trang phục; kiểm tra hoặc đổi bản gán cho từng câu chuyện.
4. Chạy âm thanh và xuất phim. Khi thiếu asset phù hợp, app báo rõ và dừng; bổ sung asset từ video hoặc chọn lại asset có sẵn.

Kho chứa nhân vật được mô tả bằng giới tính, độ tuổi và ngoại hình. Tên/vai trong câu chuyện độc lập với asset; cùng một tạo hình dùng lại cho nhiều câu chuyện. Mỗi asset ghi nguồn video, thời điểm lấy, vùng cắt và khả năng chuyển động. Chân dung chỉ dùng trung/cận cảnh; ảnh đã có nét mặt cố định không có khẩu hình như nhân vật rig đầy đủ.

Hình ảnh chỉ lấy từ kho, dùng phong cách cutout. Đăng nhập ChatGPT phục vụ phân tích văn bản và gán assets. Nút **Đăng xuất GPT** ngắt tài khoản của app để đăng nhập tài khoản khác.

## Giọng đọc CapCut và ngôn ngữ

Trong **Tài khoản & Cài đặt**, chọn **Bộ tạo giọng → CapCut TTS**, rồi chọn **Ngôn ngữ giọng đọc**. Kho đi kèm có 32 giọng Việt, 3 giọng Thái và 3 giọng Hàn. Danh sách giọng tự đổi theo ngôn ngữ; kho Thái hiện chỉ có giọng nữ. Edge TTS vẫn có thể chọn lại.

Chọn giọng người kể, nhân vật nam và nhân vật nữ; dùng **Nghe thử** để thử giọng trước khi **Lưu cài đặt**. Tốc độ nhận giá trị từ -50% đến +100%. Ngôn ngữ giọng đọc không tự dịch nội dung kịch bản. Bộ đọc CapCut cần kết nối mạng và không sử dụng tài khoản GPT.

Nội dung nghe thử cố định theo ngôn ngữ, không chỉnh sửa được. Mỗi giọng được tạo mẫu lần đầu rồi lưu vào `cache/voice-previews/` trong thư mục chính; lần sau phát lại, kể cả sau khi khởi động lại app. Đổi tốc độ xử lý từ mẫu đã lưu trên máy, không gọi lại dịch vụ tạo giọng. Giữ thư mục cache khi chuyển app sang máy khác nếu muốn dùng lại các mẫu.

Các giọng đã lưu áp dụng khi chạy **Âm thanh**; app tự tính lại thời lượng, khẩu hình và phụ đề. Giọng Edge cũ do AI ghi trong storyboard không ghi đè lựa chọn này. Đổi bộ đọc/ngôn ngữ/giọng/tốc độ sẽ làm âm thanh cũ cần cập nhật; khi xuất phim, pipeline kiểm tra và tạo lại phần âm thanh nếu cần.

Mã nguồn CapCut do người dùng cung cấp nằm ở [storytoon/vendor/capcut_tts/](storytoon/vendor/capcut_tts/), adapter ở [storytoon/audio/capcut.py](storytoon/audio/capcut.py). Node chạy kèm trong `runtime/node`, không phụ thuộc bản Node cài trên máy hay thư mục Downloads. Vùng dịch vụ giữ cố định VN theo mã nguồn gốc.

Kịch bản tự lưu và cập nhật phân cảnh khi rời ô nhập hoặc bấm lưu. Storyboard JSON được kiểm tra và lưu tự động; kịch bản không đổi sẽ dùng lại bản đã lưu. Khi phân tích lỗi, app giữ bản hợp lệ trước đó và báo lỗi, không dựng phim bằng bản phân cảnh cũ khi kịch bản đã thay đổi. Không có tab chỉnh storyboard thủ công.

Dữ liệu dự án nằm trong `projects`; kho assets trong `assets`, ngay cạnh EXE ở thư mục chính. Tài khoản ChatGPT do Codex quản lý ngoài gói phát hành; bản portable không chứa thông tin đăng nhập.

## Bản portable dùng thư mục chính

Mở `StoryToon-Desktop-Portable.exe` ngay trong thư mục Animation. App dùng `assets/`, `projects/`, `config.yaml` và `runtime/` bên cạnh EXE; không giải nén ra StoryToon-data và không phụ thuộc `dist/`. Nút **Thư mục dữ liệu** mở chính thư mục này.

Có thể xóa `dist/` sau khi chuyển đổi. Khi chép sang máy khác, chép EXE, các DLL bên cạnh, `storytoon/`, `assets/`, `projects/`, `config.yaml` và `runtime/` cùng nhau; không chỉ chép một file EXE. Đăng nhập GPT được giữ ở LocalAppData trên máy hiện tại.

Build lại bằng `runtime/python/python.exe -X utf8 tools/build_root_desktop.py`. Hai lệnh build desktop cũ cũng chuyển tới builder này. Báo cáo chuyển project trùng tên nằm tại `runtime/root-migration.json`.

## Đăng nhập 24Media

App dùng cùng Firebase project `media-srt-translator` với 24Media SRT Translator và 24Media Account Manager. Tài khoản cần có `app_access/<uid>.enabled = true`; kiểm tra thiết bị dùng chung cơ chế `app_devices/<uid>`. Quản trị tài khoản bằng Account Manager hiện có. Không đưa khóa quản trị Firebase vào app hoặc repository.

Giao diện và API yêu cầu đăng nhập. Phiên ghi nhớ được mã hóa bằng Windows DPAPI trong LocalAppData của người dùng, kiểm tra lại quyền khi khôi phục và định kỳ khi sử dụng; mật khẩu không được lưu. Đăng nhập 24Media độc lập với đăng nhập ChatGPT.

## Cập nhật từ GitHub riêng tư

Repository: [Tian01109999/Animation](https://github.com/Tian01109999/Animation). Nhấn **Cập nhật · v0.2.0** và lưu fine-grained GitHub token có quyền **Contents: Read-only** cho repository này. Tài khoản GitHub phải được cấp quyền đọc repo. Token được mã hóa trên từng máy bằng Windows DPAPI, không đi kèm bản portable.

App kiểm tra GitHub Releases lúc mở và mỗi 4 giờ. Khi có bản ổn định mới hơn, thông báo cho phép mở trang tải. Có thể kiểm tra ngay hoặc xóa token trong màn hình Cập nhật. App không tự ghi đè cài đặt đang chạy. Tải ZIP từ Releases, giải nén vào thư mục riêng và chuyển dữ liệu dự án/cấu hình cần giữ sang bản mới.

Để phát hành: cập nhật phiên bản Python và desktop đồng bộ, build EXE, chạy `runtime/python/python.exe -X utf8 tests/auth_updates_test.py`, rồi `runtime/python/python.exe -X utf8 tools/prepare_release.py`. Tải ZIP và SHA256 trong `dist/` lên một GitHub Release với tag `vX.Y.Z` tương ứng. Commit hoặc tag đơn thuần chưa tạo thông báo cập nhật; phải có Release ổn định đã publish. Gói chỉ chứa runtime được chọn, assets, mã app và cấu hình mẫu; loại dự án cá nhân, cache, logs, thông tin đăng nhập và công cụ phát triển.
