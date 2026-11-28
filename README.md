# StoryToon Desktop

Bản chính thức đầu tiên: **v1.0.0** dành cho Windows x64. Tải gói **StoryToon-1.0.0-Windows-x64.zip** từ [Releases](https://github.com/Tian01109999/Animation/releases/tag/v1.0.0), giải nén toàn bộ rồi mở `StoryToon-Desktop-Portable.exe`. Gói có sẵn Python, Node, FFmpeg, Rhubarb và kho assets; máy cần Microsoft Edge WebView2 Runtime. Không cần cài Python hay Node riêng.

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

## Cập nhật trong app

App kiểm tra bản mới lúc mở và mỗi 4 giờ. Khi có bản mới, cửa sổ thông báo hiện phiên bản và nội dung thay đổi; chọn Có để mở trang **Cập nhật**, xem nội dung thay đổi rồi bấm **Cập nhật ngay**. App tự tải gói, kiểm tra mã SHA-256 và cài cả mã ứng dụng, EXE lẫn kho assets; file assets đã bị gỡ trong bản mới cũng được xóa. Dự án, cấu hình, runtime và tài khoản không bị thay đổi. Sau khi cài xong, đóng app và mở lại. Có thể kiểm tra thủ công bằng nút **Cập nhật** trên thanh trên cùng. Khi mất mạng, app vẫn mở bình thường và kiểm tra lại sau.

Để phát hành bản mới: tăng `__version__` trong `storytoon/__init__.py` và phiên bản trong `desktop/StoryToon.cs`, build EXE bằng `tools/build_root_desktop.py`, viết nội dung thay đổi vào `docs/release_notes/X.Y.Z.md`, rồi chạy `runtime/python/python.exe -X utf8 tools/prepare_update.py --notes docs/release_notes/X.Y.Z.md`. Tạo Release ổn định tag **vX.Y.Z**, nội dung Release là nội dung thay đổi, tải lên `StoryToon-Update-X.Y.Z.zip` và `.sha256` từ `dist/`. App chỉ nhận bản đã publish đủ cả hai file. Bản Portable đầy đủ cho người dùng mới vẫn tạo bằng `tools/prepare_release.py`.
