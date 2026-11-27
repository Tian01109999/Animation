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

Repository: [Tian01109999/Animation](https://github.com/Tian01109999/Animation). Nhấn **Cập nhật assets** và lưu fine-grained GitHub token có quyền **Contents: Read-only** cho repository này. Tài khoản GitHub phải được cấp quyền đọc repo. Token được mã hóa trên từng máy bằng Windows DPAPI, không đi kèm bản portable.

Từ app 0.2.1, phiên bản kho assets độc lập với phiên bản app. App kiểm tra các Release `assets-vX.Y.Z` lúc mở và mỗi 4 giờ; chỉ thông báo khi có kho assets mới hơn. Release app thông thường không kích hoạt thông báo này. Có thể kiểm tra ngay hoặc xóa token trong màn hình Cập nhật.

Người dùng tải **StoryToon-Assets-X.Y.Z.zip**, đóng app, giải nén vào thư mục chứa EXE và đồng ý ghi đè file trùng trong `assets/`, rồi mở lại. ZIP có sẵn thư mục `assets/`; không giải nén vào bên trong thư mục assets lần nữa. Gói không chứa EXE, runtime, dự án, cấu hình hoặc tài khoản. File riêng không trùng tên được giữ lại; file có sẵn đã chỉnh sửa có thể bị thay thế. Sao lưu kho nếu cần giữ các chỉnh sửa này. App chưa tự cài gói; người dùng giải nén thủ công. Marker `assets/.storytoon-assets-version.json` đi kèm gói giúp app biết đã cập nhật.

Máy đang dùng app 0.2.0 chỉ cần nâng cấp một lần: tải **StoryToon-App-Patch-0.2.1.zip**, đóng app, giải nén ngay vào thư mục chứa EXE và ghi đè. Bản vá yêu cầu đã có bản Portable 0.2.0 đầy đủ. Sau đó dùng các gói assets cho những lần cập nhật kho tiếp theo.

Để phát hành kho mới: sửa/thêm nội dung trong `assets/`, chạy `runtime/python/python.exe -X utf8 tools/prepare_assets_release.py --version 1.1.0` (tăng phiên bản mỗi lần phát hành). Commit assets và marker phiên bản, push lên main; tạo Release ổn định với tag **assets-v1.1.0**, tải ZIP và SHA256 từ `dist/` lên và đặt `--latest=false`. App chỉ nhận gói khi cả ZIP lẫn SHA256 đã upload xong và Release đã publish. Giữ các kho đã phát hành bất biến; sửa nội dung thì tăng phiên bản. Không cần build EXE hoặc đóng gói Python/runtime khi chỉ thay assets.

Nếu thay mã app, cập nhật phiên bản Python và desktop đồng bộ, build EXE bằng `tools/build_root_desktop.py`; tạo bản vá nhỏ bằng `tools/prepare_app_patch.py` hoặc bản Portable đầy đủ bằng `tools/prepare_release.py`. Các công cụ này chạy qua Python portable đi kèm. Với bản vá nhỏ, chỉ giải nén lên app có đủ runtime tương thích.
