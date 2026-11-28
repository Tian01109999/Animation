using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: System.Reflection.AssemblyTitle("StoryToon Desktop")]
[assembly: System.Reflection.AssemblyProduct("StoryToon")]
[assembly: System.Reflection.AssemblyDescription("StoryToon - ứng dụng dựng phim hoạt hình 2D")]
[assembly: System.Reflection.AssemblyVersion("1.1.3.0")]

static class Program {
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        string smoke = null; bool afterUpdate = false;
        foreach (string arg in args) {
            if (arg.StartsWith("--smoke-test=")) smoke = Path.GetFullPath(arg.Substring(13));
            if (arg == "--after-update") afterUpdate = true;
        }
        string key; using (var hash = SHA256.Create()) key = BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(root.ToLowerInvariant()))).Replace("-", "").Substring(0, 24);
        bool owns; using (var mutex = new Mutex(true, "Local\\StoryToonDesktop-" + key, out owns)) {
            if (!owns && afterUpdate) {
                // Restarted by the updater: wait for the previous window to finish closing.
                try { owns = mutex.WaitOne(60000); } catch (AbandonedMutexException) { owns = true; }
                if (owns) Thread.Sleep(800);
            }
            if (!owns) { MessageBox.Show("StoryToon đang mở. Hãy chuyển về cửa sổ ứng dụng hiện tại.", "StoryToon"); return; }
            try { Application.Run(new StudioWindow(root, smoke)); }
            catch (Exception ex) { MessageBox.Show("Không mở được StoryToon:\n" + ex.Message, "StoryToon", MessageBoxButtons.OK, MessageBoxIcon.Error); Environment.ExitCode = 1; }
        }
    }
}

sealed class StudioWindow : Form {
    readonly string root, smoke;
    readonly Label status = new Label();
    readonly Panel host = new Panel();
    WebView2 view; Process backend; IntPtr job = IntPtr.Zero;
    StreamWriter log; readonly object logLock = new object();
    string address, token; bool shuttingDown, ready, allowClose;
    readonly System.Windows.Forms.Timer updateTimer = new System.Windows.Forms.Timer();
    string notifiedVersion = "";
    public StudioWindow(string root, string smoke) {
        this.root = root; this.smoke = smoke;
        Text = "StoryToon v1.1.3 · Xưởng phim hoạt hình"; Width = 1360; Height = 900; MinimumSize = new Size(980, 680);
        StartPosition = FormStartPosition.CenterScreen; BackColor = Color.FromArgb(20, 25, 34);
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        var bar = new Panel { Dock = DockStyle.Top, Height = 58, BackColor = Color.FromArgb(24, 31, 43) };
        var brand = new Label { Text = "STORYTOON", ForeColor = Color.FromArgb(187, 238, 141), Font = new Font("Segoe UI", 15, FontStyle.Bold), AutoSize = true, Location = new Point(20, 15) };
        status.Text = "Đang chuẩn bị ứng dụng…"; status.ForeColor = Color.FromArgb(174, 185, 201); status.AutoSize = true; status.Location = new Point(210, 23);
        var data = new Button { Text = "Thư mục dữ liệu", Dock = DockStyle.Right, Width = 145, FlatStyle = FlatStyle.Flat, ForeColor = Color.White };
        data.FlatAppearance.BorderSize = 0; data.Click += delegate { Process.Start(new ProcessStartInfo("explorer.exe", Quote(root)) { UseShellExecute = true }); };
        bar.Controls.Add(brand); bar.Controls.Add(status); bar.Controls.Add(data);
        var updates = new Button { Text = "Cập nhật", Dock = DockStyle.Right, Width = 120, FlatStyle = FlatStyle.Flat, ForeColor = Color.White };
        updates.FlatAppearance.BorderSize = 0;
        updates.Click += delegate { if (view != null && ready) view.CoreWebView2.Navigate(address + "/updates"); };
        bar.Controls.Add(updates);
        updateTimer.Interval = 4 * 60 * 60 * 1000;
        updateTimer.Tick += async delegate { await CheckUpdates(); };
        host.Dock = DockStyle.Fill; Controls.Add(host); Controls.Add(bar);
        Shown += async delegate { await StartStudio(); };
        FormClosing += ClosingStudio; FormClosed += delegate { Cleanup(); };
        if (smoke != null) { Opacity = .01; ShowInTaskbar = false; }
    }
    static string Quote(string value) { return "\"" + value.Replace("\"", "\\\"") + "\""; }
    async Task StartStudio() {
        try {
            string python = Path.Combine(root, "runtime", "python", "python.exe");
            if (!File.Exists(python)) throw new Exception("Thiếu Python portable. Hãy giữ nguyên thư mục ứng dụng.");
            if (!Directory.Exists(Path.Combine(root, "assets")) || !Directory.Exists(Path.Combine(root, "storytoon")))
                throw new Exception("Đặt app cạnh thư mục assets và storytoon trong thư mục chính.");
            try { CoreWebView2Environment.GetAvailableBrowserVersionString(); }
            catch { throw new Exception("Máy chưa có Microsoft Edge WebView2 Runtime. Cài từ https://go.microsoft.com/fwlink/p/?LinkId=2124703 rồi mở lại ứng dụng."); }
            Directory.CreateDirectory(Path.Combine(root, "logs"));
            log = new StreamWriter(Path.Combine(root, "logs", "desktop.log"), true, new UTF8Encoding(false)); log.AutoFlush = true;
            int port; var socket = new TcpListener(IPAddress.Loopback, 0); socket.Start(); port = ((IPEndPoint)socket.LocalEndpoint).Port; socket.Stop();
            address = "http://127.0.0.1:" + port;
            byte[] bytes = new byte[32]; using (var random = RandomNumberGenerator.Create()) random.GetBytes(bytes);
            token = BitConverter.ToString(bytes).Replace("-", "");
            var start = new ProcessStartInfo(python, "-X utf8 -m storytoon.desktop_server --port " + port) {
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
            };
            start.EnvironmentVariables.Remove("PYTHONHOME"); start.EnvironmentVariables.Remove("PYTHONPATH");
            start.EnvironmentVariables["PYTHONUTF8"] = "1"; start.EnvironmentVariables["STORYTOON_DESKTOP_TOKEN"] = token;
            start.EnvironmentVariables["STORYTOON_DATA_ROOT"] = root;
            start.EnvironmentVariables["PATH"] = Path.Combine(root, "runtime", "ffmpeg") + ";" + start.EnvironmentVariables["PATH"];
            job = Native.MakeJob();
            backend = new Process { StartInfo = start, EnableRaisingEvents = true };
            backend.OutputDataReceived += LogLine; backend.ErrorDataReceived += LogLine;
            backend.Start();
            if (!Native.AssignProcessToJobObject(job, backend.Handle)) throw new Exception("Không quản lý được tiến trình xử lý của ứng dụng.");
            backend.BeginOutputReadLine(); backend.BeginErrorReadLine();
            var deadline = DateTime.UtcNow.AddSeconds(300);
            while (DateTime.UtcNow < deadline && !shuttingDown) {
                if (backend.HasExited) throw new Exception("Bộ xử lý không khởi động được. Xem logs\\desktop.log trong thư mục ứng dụng.");
                try { if ((await BackendStatus()).Contains("\"ready\":true")) { ready = true; break; } } catch { }
                await Task.Delay(350);
            }
            if (shuttingDown) return;
            if (!ready) throw new Exception("Khởi động quá thời gian. Xem logs\\desktop.log.");
            status.Text = "Đang mở giao diện…";
            view = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.FromArgb(247, 247, 250) }; host.Controls.Add(view);
            var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(root, "runtime", "desktop-webview"));
            await view.EnsureCoreWebView2Async(environment);
            view.CoreWebView2.Settings.AreDevToolsEnabled = false; view.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            view.CoreWebView2.Settings.IsStatusBarEnabled = false; view.CoreWebView2.Settings.IsZoomControlEnabled = true;
            view.CoreWebView2.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e) {
                Uri uri; if (Uri.TryCreate(e.Uri, UriKind.Absolute, out uri) && uri.GetLeftPart(UriPartial.Authority) == address) return;
                e.Cancel = true; OpenExternal(e.Uri);
            };
            view.CoreWebView2.NewWindowRequested += delegate(object sender, CoreWebView2NewWindowRequestedEventArgs e) { e.Handled = true; OpenExternal(e.Uri); };
            view.CoreWebView2.NavigationCompleted += delegate { status.Text = "Sẵn sàng · Dữ liệu lưu trên máy"; };
            view.CoreWebView2.WebMessageReceived += delegate(object sender, CoreWebView2WebMessageReceivedEventArgs e) {
                Uri uri; if (!Uri.TryCreate(e.Source, UriKind.Absolute, out uri) || uri.GetLeftPart(UriPartial.Authority) != address) return;
                string message; try { message = e.TryGetWebMessageAsString(); } catch { return; }
                if (message == "storytoon:restart-after-update") RestartAfterUpdate();
            };
            view.CoreWebView2.Navigate(address);
            if (smoke == null) { updateTimer.Start(); await CheckUpdates(); }
            if (smoke != null) await SmokeTest();
        } catch (Exception ex) {
            if (shuttingDown) return;
            status.Text = "Không khởi động được ứng dụng";
            if (smoke != null) { File.WriteAllText(smoke, "ERROR: " + ex, Encoding.UTF8); Environment.ExitCode = 1; allowClose = true; Close(); }
            else MessageBox.Show(this, ex.Message, "StoryToon", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
    void LogLine(object sender, DataReceivedEventArgs args) { if (args.Data == null) return; lock (logLock) { if (log != null) log.WriteLine(args.Data); } }
    async Task CheckUpdates() {
        try {
            var request = (HttpWebRequest)WebRequest.Create(address + "/__desktop__/updates");
            request.Proxy = null; request.Headers["X-StoryToon-Desktop"] = token; request.Timeout = 20000;
            string json = await Task.Run(delegate { using (var response = request.GetResponse()) using (var reader = new StreamReader(response.GetResponseStream())) return reader.ReadToEnd(); });
            var result = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(json);
            string version = Convert.ToString(result["version"]);
            if (shuttingDown || !Convert.ToBoolean(result["available"]) || version == notifiedVersion) return;
            notifiedVersion = version;
            string notes = result.ContainsKey("notes") ? Convert.ToString(result["notes"]) : "";
            if (notes.Length > 1200) notes = notes.Substring(0, 1200) + "…";
            string text = "Có bản cập nhật StoryToon " + version + "." + (notes.Length > 0 ? "\n\nNội dung thay đổi:\n" + notes : "") + "\n\nCập nhật ngay? App sẽ tự tải, cài đặt và khởi động lại.";
            if (MessageBox.Show(this, text, "Cập nhật StoryToon", MessageBoxButtons.YesNo, MessageBoxIcon.Information) == DialogResult.Yes && view != null && ready)
                view.CoreWebView2.Navigate(address + "/updates?start=1");
        } catch { /* Updates must never prevent opening the studio. */ }
    }
    bool restarting;
    async void RestartAfterUpdate() {
        if (restarting || shuttingDown) return;
        // Only restart when the backend really finished installing an update.
        try {
            var request = (HttpWebRequest)WebRequest.Create(address + "/__desktop__/update-state");
            request.Proxy = null; request.Headers["X-StoryToon-Desktop"] = token; request.Timeout = 10000;
            string json = await Task.Run(delegate { using (var response = request.GetResponse()) using (var reader = new StreamReader(response.GetResponseStream())) return reader.ReadToEnd(); });
            if (!json.Contains("\"state\":\"done\"")) return;
        } catch { return; }
        restarting = true;
        string exe = Path.Combine(root, "StoryToon-Desktop-Portable.exe");
        if (!File.Exists(exe)) exe = Application.ExecutablePath;
        try { Process.Start(new ProcessStartInfo(exe, "--after-update") { UseShellExecute = false, WorkingDirectory = root }); }
        catch (Exception ex) {
            restarting = false;
            MessageBox.Show(this, "Đã cài bản mới nhưng không tự mở lại được (" + ex.Message + "). Hãy mở lại StoryToon.", "StoryToon");
        }
        allowClose = true; Close();
    }
    async Task<string> BackendStatus() {
        var request = (HttpWebRequest)WebRequest.Create(address + "/__desktop__/status");
        request.Proxy = null; request.Headers["X-StoryToon-Desktop"] = token; request.Timeout = 10000; request.ReadWriteTimeout = 10000;
        return await Task.Run(delegate { using (var response = request.GetResponse()) using (var reader = new StreamReader(response.GetResponseStream())) return reader.ReadToEnd(); });
    }
    void OpenExternal(string value) { Uri uri; if (Uri.TryCreate(value, UriKind.Absolute, out uri) && (uri.Scheme == "https" || uri.Scheme == "http")) Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true }); }
    async Task SmokeTest() {
        var deadline = DateTime.UtcNow.AddSeconds(90);
        while (DateTime.UtcNow < deadline) {
            if (shuttingDown) return;
            string loginReady = await view.CoreWebView2.ExecuteScriptAsync("!!document.querySelector('[data-storytoon-login]')");
            if (loginReady == "true") {
                using (var stream = File.Create(Path.ChangeExtension(smoke, ".login.png"))) await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream);
                File.WriteAllText(smoke, await BackendStatus(), Encoding.UTF8);
                allowClose = true; Close(); return;
            }
            string valid = await view.CoreWebView2.ExecuteScriptAsync("document.body.innerText.includes('Kịch bản') && document.body.innerText.includes('Xuất phim') && document.querySelectorAll('textarea,input').length > 2");
            if (valid == "true") {
                string settings = await view.CoreWebView2.ExecuteScriptAsync("(() => { const tabs = [...document.querySelectorAll('[role=tab]')]; if (tabs.some(e => e.innerText.trim() === 'Storyboard')) return false; tabs.find(e => e.innerText.includes('Tài khoản')).click(); return true; })()");
                if (settings != "true") throw new Exception("Tab Storyboard chưa được gỡ.");
                await Task.Delay(400);
                string settingsValid = await view.CoreWebView2.ExecuteScriptAsync("document.body.innerText.includes('Đăng xuất GPT') && document.body.innerText.includes('Bộ tạo giọng') && document.body.innerText.includes('Ngôn ngữ giọng đọc') && document.body.innerText.includes('Nghe thử') && !document.body.innerText.includes('Gemini') && !document.body.innerText.includes('Người que')");
                if (settingsValid != "true") throw new Exception("Cài đặt tài khoản chưa đúng bản GPT-only.");
                using (var stream = File.Create(Path.ChangeExtension(smoke, ".settings.png"))) await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream);
                string library = await view.CoreWebView2.ExecuteScriptAsync("(() => { const tab = [...document.querySelectorAll('[role=tab]')].find(e => e.innerText.includes('Kho assets')); if (!tab) return false; tab.click(); return true; })()");
                if (library != "true") throw new Exception("Không tìm thấy tab Kho assets.");
                await Task.Delay(1800);
                string libraryReady = await view.CoreWebView2.ExecuteScriptAsync("document.body.innerText.includes('AI phân tích và gán assets') && [...document.querySelectorAll('img')].filter(e => e.complete && e.naturalWidth > 0).length >= 1");
                if (libraryReady != "true") { await Task.Delay(500); continue; }
                string shot = Path.ChangeExtension(smoke, ".png");
                using (var stream = File.Create(shot)) await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream);
                File.WriteAllText(smoke, await BackendStatus(), Encoding.UTF8);
                allowClose = true; Close(); return;
            } await Task.Delay(500);
        } throw new Exception("Giao diện chưa hiện đủ các tab trong cửa sổ desktop.");
    }
    async void ClosingStudio(object sender, FormClosingEventArgs e) {
        if (allowClose || shuttingDown || !ready) { shuttingDown = true; return; }
        e.Cancel = true;
        bool busy = true;
        try { busy = (await BackendStatus()).Contains("\"busy\":true"); } catch { }
        if (busy && MessageBox.Show(this, "Ứng dụng đang xử lý. Đóng bây giờ sẽ dừng tác vụ chưa hoàn thành. Bạn muốn đóng?", "StoryToon", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        allowClose = true; Close();
    }
    void Cleanup() {
        shuttingDown = true;
        updateTimer.Stop(); updateTimer.Dispose();
        if (view != null) { view.Dispose(); view = null; }
        if (job != IntPtr.Zero) { Native.CloseHandle(job); job = IntPtr.Zero; }
        if (backend != null) { try { if (!backend.HasExited) backend.Kill(); backend.WaitForExit(5000); } catch { } backend.Dispose(); }
        lock (logLock) { if (log != null) { log.Dispose(); log = null; } }
    }
}

static class Native {
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits { public long PerProcessUserTimeLimit, PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize; public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass, SchedulingClass; }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters { public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount, ReadTransferCount, WriteTransferCount, OtherTransferCount; }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits { public BasicLimits BasicLimitInformation; public IoCounters IoInfo; public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed; }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int info, IntPtr data, uint length);
    [DllImport("kernel32.dll", SetLastError = true)] public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
    public static IntPtr MakeJob() {
        IntPtr job = CreateJobObject(IntPtr.Zero, null); if (job == IntPtr.Zero) throw new Exception("Không tạo được phiên ứng dụng.");
        var limits = new ExtendedLimits(); limits.BasicLimitInformation.LimitFlags = 0x2000;
        int size = Marshal.SizeOf(limits); IntPtr data = Marshal.AllocHGlobal(size);
        try { Marshal.StructureToPtr(limits, data, false); if (!SetInformationJobObject(job, 9, data, (uint)size)) { CloseHandle(job); throw new Exception("Không đặt được vòng đời bộ xử lý."); } }
        finally { Marshal.FreeHGlobal(data); } return job;
    }
}
