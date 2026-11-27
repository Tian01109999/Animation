// Compile with desktop/StoryToon.cs and /main:UpdateNotificationSmoke.
// Local response fixture: exercise the real update dialog without publishing a fake release.
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

static class UpdateNotificationSmoke {
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hwnd, uint message, IntPtr wparam, IntPtr lparam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr hwnd, EnumProc callback, IntPtr value);
    delegate bool EnumProc(IntPtr hwnd, IntPtr value);

    [STAThread] static void Main(string[] args) {
        string root = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += delegate(object s, ResolveEventArgs e) {
            return Assembly.LoadFrom(Path.Combine(root, new AssemblyName(e.Name).Name + ".dll"));
        };
        Run(root, Path.GetFullPath(args[1]));
    }

    static void Run(string root, string report) {
        Application.EnableVisualStyles();
        var listener = new TcpListener(IPAddress.Loopback, 0); listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        Task server = Task.Run(delegate {
            for (int i = 0; i < 2; i++) {
                using (var connection = listener.AcceptTcpClient())
                using (var stream = connection.GetStream()) {
                    var reader = new StreamReader(stream, Encoding.ASCII, false, 1024, true);
                    string line; do { line = reader.ReadLine(); } while (!String.IsNullOrEmpty(line));
                    byte[] body = Encoding.UTF8.GetBytes("{\"version\":\"1.1.0\",\"available\":true,\"url\":\"https://github.com/Tian01109999/Animation/releases/tag/assets-v1.1.0\"}");
                    byte[] header = Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + body.Length + "\r\nConnection: close\r\n\r\n");
                    stream.Write(header, 0, header.Length); stream.Write(body, 0, body.Length);
                }
            }
        });
        var owner = new Form { Opacity = .01, ShowInTaskbar = false };
        var studio = new StudioWindow(root, report);
        var flags = BindingFlags.Instance | BindingFlags.NonPublic;
        typeof(StudioWindow).GetField("address", flags).SetValue(studio, "http://127.0.0.1:" + port);
        typeof(StudioWindow).GetField("token", flags).SetValue(studio, "test-native-token");
        var method = typeof(StudioWindow).GetMethod("CheckUpdates", flags);
        int dialogs = 0; string dialogText = "";
        var timer = new Timer { Interval = 100 };
        timer.Tick += delegate {
            IntPtr dialog = FindWindow("#32770", "Cập nhật assets");
            if (dialog == IntPtr.Zero) return;
            dialogs++;
            EnumChildWindows(dialog, delegate(IntPtr child, IntPtr unused) {
                var text = new StringBuilder(1024); GetWindowText(child, text, text.Capacity);
                dialogText += text.ToString() + " "; return true;
            }, IntPtr.Zero);
            SendMessage(dialog, 0x0111, new IntPtr(7), IntPtr.Zero); // IDNO: no browser navigation.
        };
        owner.Shown += async delegate {
            try {
                timer.Start();
                await (Task)method.Invoke(studio, null);
                await (Task)method.Invoke(studio, null);
                await server;
                if (dialogs != 1 || !dialogText.Contains("1.1.0") || !dialogText.Contains("assets"))
                    throw new Exception("Update dialog missing or repeated: " + dialogs + " " + dialogText);
                File.WriteAllText(report, "PASS: newer assets opened the real update dialog; repeated version suppressed.\n" + dialogText, Encoding.UTF8);
            } catch (Exception e) { File.WriteAllText(report, "FAIL: " + e, Encoding.UTF8); Environment.ExitCode = 1; }
            finally { timer.Stop(); listener.Stop(); studio.Dispose(); owner.Close(); }
        };
        Application.Run(owner); timer.Dispose(); owner.Dispose();
    }
}
