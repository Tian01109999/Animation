using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("StoryToon Portable")]
[assembly: System.Reflection.AssemblyProduct("StoryToon")]
[assembly: System.Reflection.AssemblyVersion("0.1.0.0")]
static class Portable {
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new ExtractWindow(args));
    }
}
sealed class ExtractWindow : Form {
    readonly string[] args;
    readonly Label status = new Label();
    readonly ProgressBar progress = new ProgressBar();
    bool working = true;
    public ExtractWindow(string[] args) {
        this.args = args; Text = "StoryToon"; Width = 490; Height = 210; FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen; BackColor = Color.FromArgb(24, 31, 43);
        var title = new Label { Text = "STORYTOON", ForeColor = Color.FromArgb(187, 238, 141), Font = new Font("Segoe UI", 20, FontStyle.Bold), AutoSize = true, Location = new Point(26, 24) };
        status.Text = "Đang chuẩn bị ứng dụng…"; status.ForeColor = Color.White; status.AutoSize = true; status.Location = new Point(29, 83);
        progress.Location = new Point(29, 115); progress.Size = new Size(410, 13); Controls.Add(title); Controls.Add(status); Controls.Add(progress);
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (working) e.Cancel = true; };
        Shown += async delegate {
            try {
                string root = await Task.Run(() => Prepare());
                var command = new StringBuilder(); foreach (string arg in args) command.Append(" \"").Append(arg.Replace("\"", "\\\"")).Append("\"");
                Process.Start(new ProcessStartInfo(Path.Combine(root, "StoryToon.exe"), command.ToString()) { WorkingDirectory = root, UseShellExecute = false });
                working = false; Close();
            } catch (Exception ex) { working = false; MessageBox.Show(this, "Không mở được bản portable:\n" + ex.Message, "StoryToon", MessageBoxButtons.OK, MessageBoxIcon.Error); Environment.ExitCode = 1; Close(); }
        };
    }
    void Report(int value, string message) { if (!IsDisposed) BeginInvoke((Action)delegate { progress.Value = Math.Max(0, Math.Min(100, value)); status.Text = message; }); }
    string Prepare() {
        using (var input = File.OpenRead(Application.ExecutablePath)) {
            if (input.Length < 56) throw new InvalidDataException("Thiếu dữ liệu đóng gói.");
            input.Position = input.Length - 56;
            var reader = new BinaryReader(input); long length = reader.ReadInt64(); byte[] expected = reader.ReadBytes(32);
            if (Encoding.ASCII.GetString(reader.ReadBytes(16)) != "STORYTOON-PKG001" || length <= 0 || length > input.Length - 56) throw new InvalidDataException("Dữ liệu đóng gói không hợp lệ.");
            string hash = BitConverter.ToString(expected).Replace("-", "").ToLowerInvariant();
            string parent = Path.GetDirectoryName(Application.ExecutablePath);
            try { string check = Path.Combine(parent, ".storytoon-write-" + Guid.NewGuid().ToString("N")); File.WriteAllText(check, ""); File.Delete(check); }
            catch (UnauthorizedAccessException) { parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "StoryToon"); Directory.CreateDirectory(parent); }
            string root = Path.Combine(parent, "StoryToon-data");
            if (Directory.Exists(root) && (!File.Exists(Path.Combine(root, ".bundle-id")) || File.ReadAllText(Path.Combine(root, ".bundle-id")).Trim() != hash)) root = Path.Combine(parent, "StoryToon-data-" + hash.Substring(0, 12));
            using (var mutex = new Mutex(false, "Local\\StoryToonExtract-" + hash.Substring(0, 24))) {
                try { mutex.WaitOne(); } catch (AbandonedMutexException) { }
                try {
                    if (File.Exists(Path.Combine(root, ".bundle-id")) && File.ReadAllText(Path.Combine(root, ".bundle-id")).Trim() == hash && File.Exists(Path.Combine(root, "StoryToon.exe")) && File.Exists(Path.Combine(root, "runtime", "python", "python.exe"))) return root;
                    if (Directory.Exists(root)) throw new IOException("Thư mục ứng dụng chưa hoàn chỉnh: " + root + ". Hãy đổi tên thư mục đó rồi mở lại; dữ liệu cũ sẽ không bị ghi đè.");
                    Report(1, "Lần mở đầu: đang kiểm tra bộ ứng dụng…");
                    long offset = input.Length - 56 - length;
                    using (var payload = new PayloadStream(input, offset, length)) using (var sha = SHA256.Create()) {
                        byte[] actual = sha.ComputeHash(payload);
                        if (BitConverter.ToString(actual) != BitConverter.ToString(expected)) throw new InvalidDataException("File portable bị hỏng. Hãy lấy lại bản đầy đủ.");
                    }
                    string staging = root + ".install-" + Guid.NewGuid().ToString("N"); Directory.CreateDirectory(staging);
                    // An interrupted install remains a separate staging directory; existing user data is never deleted.
                    using (var payload = new PayloadStream(input, offset, length)) using (var zip = new ZipArchive(payload, ZipArchiveMode.Read)) {
                        int count = 0; string prefix = Path.GetFullPath(staging) + Path.DirectorySeparatorChar;
                        foreach (var entry in zip.Entries) {
                            string dest = Path.GetFullPath(Path.Combine(staging, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                            if (!dest.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Đường dẫn không an toàn trong bộ ứng dụng.");
                            if (entry.FullName.EndsWith("/")) Directory.CreateDirectory(dest);
                            else { Directory.CreateDirectory(Path.GetDirectoryName(dest)); using (var src = entry.Open()) using (var target = new FileStream(dest, FileMode.CreateNew)) src.CopyTo(target); }
                            count++; if (count % 150 == 0) Report(5 + count * 94 / zip.Entries.Count, "Lần mở đầu: đang chuẩn bị ứng dụng… " + (count * 100 / zip.Entries.Count) + "%");
                        }
                    }
                    if (!File.Exists(Path.Combine(staging, "StoryToon.exe")) || !File.Exists(Path.Combine(staging, "runtime", "python", "python.exe"))) throw new InvalidDataException("Bộ ứng dụng thiếu tệp bắt buộc.");
                    File.WriteAllText(Path.Combine(staging, ".bundle-id"), hash); Directory.Move(staging, root);
                    Report(100, "Đang mở StoryToon…"); return root;
                } finally { mutex.ReleaseMutex(); }
            }
        }
    }
}
sealed class PayloadStream : Stream {
    readonly Stream source; readonly long offset, length; long position;
    public PayloadStream(Stream source, long offset, long length) { this.source = source; this.offset = offset; this.length = length; }
    public override bool CanRead { get { return true; } } public override bool CanSeek { get { return true; } } public override bool CanWrite { get { return false; } }
    public override long Length { get { return length; } } public override long Position { get { return position; } set { Seek(value, SeekOrigin.Begin); } }
    public override int Read(byte[] buffer, int start, int count) { source.Position = offset + position; int read = source.Read(buffer, start, (int)Math.Min(count, length-position)); position += read; return read; }
    public override long Seek(long amount, SeekOrigin origin) { long next = origin == SeekOrigin.Begin ? amount : origin == SeekOrigin.Current ? position+amount : length+amount; if (next<0 || next>length) throw new IOException("Payload offset out of range"); return position=next; }
    public override void Flush() { } public override void SetLength(long value) { throw new NotSupportedException(); } public override void Write(byte[] buffer,int offset,int count) { throw new NotSupportedException(); }
}
