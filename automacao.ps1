# =====================================================================
#  Automacao SGM - Excel - SGCI  (digitacao de medicao)
#  Executar pelo INICIAR.bat
#  Segure ESC a qualquer momento para interromper.
# =====================================================================
param([switch]$Diagnostico, [string]$Finalizar, [string]$Medicao, [string]$TesteMateriais, [string]$TesteLMN, [switch]$Publicar)

# ---------------------------- CONFIGURACAO ---------------------------
$MODO_TESTE          = $true    # pede confirmacao antes de Encaminhar e de cada Salvar
$TIMEOUT_CONSULTA    = 30       # segundos (SGM consulta)
$TIMEOUT_EXCEL       = 40       # segundos (geracao da planilha)
$TIMEOUT_FILTRO      = 20       # segundos (SGCI filtrar OR)
$TENTATIVAS_DIRETORIA = 3
$TIMEOUT_DESC_UD     = 90       # segundos esperando a descrição da UD aparecer depois do Enter
$SETAS_RELATORIO     = 7        # posicao de Rascunho de Medicao - Digitacao na lista
$NOME_PLANILHA       = 'Modelo_Rascunho_Medicao_Digitacao'
# $true = copia de teste nao procura atualizacao, nao publica, nao envia erro para a rede
$COPIA_TESTE         = $false
$SEM_IMPRESSAO       = $false   # $true SO no automacao_sem_impressao.ps1 (gerado automaticamente a partir deste arquivo)
$PRE_ABRIR_MATERIAL  = $true   # abre o Controle de Material no SGCI enquanto o SGM trabalha (ganha ~30 s por SGM)

$PASTA        = $PSScriptRoot
$ARQ_SGMS     = Join-Path $PASTA 'SGMs.txt'
$ARQ_LOG      = Join-Path $PASTA 'log.txt'
$ARQ_MEDICOES = Join-Path $PASTA 'medicoes.txt'
$ARQ_CONCL    = Join-Path $PASTA 'concluidos.txt'
$PASTA_ERROS  = Join-Path $PASTA 'erros'

$ErrorActionPreference = 'Stop'
$PTBR = [Globalization.CultureInfo]'pt-BR'
$INV  = [Globalization.CultureInfo]::InvariantCulture

# ---------------------------- WIN32 ----------------------------------
Add-Type -AssemblyName System.Windows.Forms, System.Drawing, System.Runtime.WindowsRuntime
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System; using System.Collections.Generic; using System.Text; using System.Threading;
using System.Drawing; using System.Runtime.InteropServices;
public class WinInfo {
  public IntPtr H; public IntPtr Parent; public string Cls; public string Text;
  public int L, T, R, B, Id; public bool Vis, En;
  public int W { get { return R - L; } }  public int Hg { get { return B - T; } }
  public int CX { get { return (L + R) / 2; } }  public int CY { get { return (T + B) / 2; } }
}
public static class U {
  delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder sb, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, StringBuilder l, uint f, uint t, out IntPtr r);
  [DllImport("user32.dll")] static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, IntPtr l, uint f, uint t, out IntPtr r);
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
  [DllImport("user32.dll")] static extern int GetDlgCtrlID(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsChild(IntPtr p, IntPtr c);
  [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool IsHungAppWindow(IntPtr h);
  [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint f);
  [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte sc, uint f, UIntPtr e);
  [DllImport("user32.dll")] static extern void mouse_event(uint f, int x, int y, uint d, UIntPtr e);
  [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
  [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(POINT p);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
  [DllImport("user32.dll")] public static extern IntPtr GetMenu(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetSubMenu(IntPtr m, int pos);
  [DllImport("user32.dll")] public static extern int GetMenuItemCount(IntPtr m);
  [DllImport("user32.dll")] public static extern uint GetMenuItemID(IntPtr m, int pos);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetMenuString(IntPtr m, uint id, StringBuilder sb, int max, uint f);
  [DllImport("oleacc.dll")] static extern int AccessibleObjectFromWindow(IntPtr h, uint id, ref Guid iid, [MarshalAs(UnmanagedType.IDispatch)] out object o);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }

  public static string GetText(IntPtr h) {
    IntPtr r; SendMessageTimeout(h, 0x000E, IntPtr.Zero, IntPtr.Zero, 2, 2000, out r);
    int len = (int)r.ToInt64(); if (len <= 0) return "";
    var sb = new StringBuilder(len + 2);
    SendMessageTimeout(h, 0x000D, new IntPtr(len + 1), sb, 2, 2000, out r);
    return sb.ToString();
  }
  public static WinInfo Info(IntPtr h) {
    var w = new WinInfo(); w.H = h; var sb = new StringBuilder(256); GetClassName(h, sb, 256); w.Cls = sb.ToString();
    w.Text = GetText(h); RECT r; GetWindowRect(h, out r); w.L = r.L; w.T = r.T; w.R = r.R; w.B = r.B;
    w.Vis = IsWindowVisible(h); w.En = IsWindowEnabled(h); w.Id = GetDlgCtrlID(h); w.Parent = GetParent(h); return w;
  }
  public static List<WinInfo> Tops(uint pid) {
    var l = new List<WinInfo>();
    EnumWindows((h, p) => { uint wp; GetWindowThreadProcessId(h, out wp); if ((pid == 0 || wp == pid) && IsWindowVisible(h)) l.Add(Info(h)); return true; }, IntPtr.Zero);
    return l;
  }
  public static List<WinInfo> Desc(IntPtr parent) {
    var l = new List<WinInfo>(); EnumChildWindows(parent, (h, p) => { l.Add(Info(h)); return true; }, IntPtr.Zero); return l;
  }
  public static IntPtr Root(IntPtr h) { return GetAncestor(h, 3); }
  [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
  [DllImport("user32.dll")] public static extern bool EndTask(IntPtr h, bool shutdown, bool force);
  // troca por um instante para outra area de trabalho e volta: mesmo efeito do Ctrl+Alt+Del + Esc
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr CreateDesktop(string name, IntPtr dev, IntPtr dm, int flags, uint access, IntPtr sa);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr OpenDesktop(string name, int flags, bool inherit, uint access);
  [DllImport("user32.dll")] static extern bool SwitchDesktop(IntPtr h);
  [DllImport("user32.dll")] static extern bool CloseDesktop(IntPtr h);
  public static string PiscarDesktop(int ms) {
    IntPtr orig = OpenDesktop("Default", 0, false, 0x0100 | 0x0001);
    if (orig == IntPtr.Zero) return "nao abriu Default";
    IntPtr tmp = CreateDesktop("AutomacaoSGCI_foco", IntPtr.Zero, IntPtr.Zero, 0, 0x01FF, IntPtr.Zero);
    if (tmp == IntPtr.Zero) { CloseDesktop(orig); return "nao criou desktop"; }
    string r = "ok";
    try {
      if (!SwitchDesktop(tmp)) r = "SwitchDesktop falhou";
      Thread.Sleep(ms);
    } finally {
      SwitchDesktop(orig);
      CloseDesktop(tmp); CloseDesktop(orig);
    }
    return r;
  }
  // todas as janelas de um processo, inclusive as invisiveis
  public static List<WinInfo> TopsTodas(uint pid) {
    var l = new List<WinInfo>();
    EnumWindows((h, p) => { uint wp; GetWindowThreadProcessId(h, out wp); if (wp == pid) l.Add(Info(h)); return true; }, IntPtr.Zero);
    return l;
  }
  public static void Minimizar(IntPtr h) { if (h != IntPtr.Zero) ShowWindow(h, 6); }
  public static bool Activate(IntPtr h) {
    if (IsIconic(h)) { ShowWindow(h, 9); Thread.Sleep(300); }
    IntPtr fg = GetForegroundWindow(); uint d; uint t1 = GetWindowThreadProcessId(fg, out d); uint me = GetCurrentThreadId();
    bool att = false; if (t1 != me) att = AttachThreadInput(me, t1, true);
    BringWindowToTop(h); SetForegroundWindow(h);
    if (att) AttachThreadInput(me, t1, false);
    Thread.Sleep(150);
    IntPtr f2 = GetForegroundWindow(); return f2 == h || Root(f2) == h;
  }
  public static IntPtr At(int x, int y) { POINT p; p.X = x; p.Y = y; return WindowFromPoint(p); }
  public static void Click(int x, int y, bool dbl) {
    SetCursorPos(x, y); Thread.Sleep(80);
    mouse_event(2, 0, 0, 0, UIntPtr.Zero); mouse_event(4, 0, 0, 0, UIntPtr.Zero);
    if (dbl) { Thread.Sleep(70); mouse_event(2, 0, 0, 0, UIntPtr.Zero); mouse_event(4, 0, 0, 0, UIntPtr.Zero); }
  }
  public static void MoveMouse(int x, int y) { SetCursorPos(x, y); }
  public static IntPtr Send(IntPtr h, uint m, IntPtr w, IntPtr l) { IntPtr r; SendMessageTimeout(h, m, w, l, 2, 5000, out r); return r; }
  public static string MenuText(IntPtr m, int pos) { var sb = new StringBuilder(256); GetMenuString(m, (uint)pos, sb, 256, 0x400); return sb.ToString(); }
  public static object ExcelWindow(IntPtr h) {
    Guid g = new Guid("00020400-0000-0000-C000-000000000046"); object o;
    int hr = AccessibleObjectFromWindow(h, 0xFFFFFFF0, ref g, out o); return hr >= 0 ? o : null;
  }
  public static Bitmap Capture(IntPtr h, bool screen) {
    RECT r; GetWindowRect(h, out r); int w = r.R - r.L, hh = r.B - r.T; if (w <= 0 || hh <= 0) return null;
    var bmp = new Bitmap(w, hh);
    using (var g = Graphics.FromImage(bmp)) {
      if (screen) g.CopyFromScreen(r.L, r.T, 0, 0, new Size(w, hh));
      else { IntPtr dc = g.GetHdc(); PrintWindow(h, dc, 0); g.ReleaseHdc(dc); }
    }
    return bmp;
  }
  public static bool IsBlank(Bitmap b) {
    var set = new HashSet<int>();
    for (int i = 1; i < 12; i++) for (int j = 1; j < 12; j++) set.Add(b.GetPixel(b.Width * i / 12, b.Height * j / 12).ToArgb());
    return set.Count <= 1;
  }
  public static Bitmap Scale(Bitmap b, int s) {
    var big = new Bitmap(b.Width * s, b.Height * s);
    using (var g = Graphics.FromImage(big)) { g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic; g.DrawImage(b, 0, 0, b.Width * s, b.Height * s); }
    return big;
  }
}
'@
[void][U]::SetProcessDPIAware()

# ---------------------------- OCR (Windows) --------------------------
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]
$script:asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $script:asTask.MakeGenericMethod($t).Invoke($null, @($op)); [void]$task.Wait(-1); $task.Result }
$script:ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language 'pt-BR'))

function Get-Ocr([IntPtr]$h, [int]$scale = 2, [switch]$Tela, [int]$Margem = 0, $Recorte = $null, [switch]$SemRepetir) {
  # programa sem responder (ex SGM carregando depois de salvar) a janela vira uma imagem congelada e
  # esbranquicada e o OCR nao le nada - espera ele voltar (ate 60 s)
  $raizH = [U]::Root($h)
  if ([U]::IsHungAppWindow($raizH)) {
    $t0 = Get-Date
    while ([U]::IsHungAppWindow($raizH) -and ((Get-Date) - $t0).TotalSeconds -lt 60) { Start-Sleep -Milliseconds 400; if ([U]::GetAsyncKeyState(0x1B) -band 0x8000) { break } }
    Start-Sleep -Milliseconds 800
    try { Log ("   (programa sem responder por {0:0} s - esperei antes de ler a tela)" -f ((Get-Date) - $t0).TotalSeconds) } catch {}
  }
  $res = Get-OcrUmaVez $h $scale -Tela:$Tela -Margem $Margem -Recorte $Recorte
  # leitura sem texto tenta na hora com o outro tipo de captura (foto interna - tela)
  # (quando o leitor do Windows trava ele devolve as LINHAS, mas com o texto em branco - conta o texto, nao as linhas)
  if (-not $SemRepetir -and -not (Tem-Texto $res)) {
    $res2 = Get-OcrUmaVez $h $scale -Tela:(-not $Tela) -Margem $Margem -Recorte $Recorte
    if (Tem-Texto $res2) { return $res2 }
    # a imagem tem conteudo e mesmo assim veio sem texto o leitor de texto travou (visto em outro PC
    # imagens perfeitas lidas em branco ate reiniciar a automacao)
    if (-not $script:ocrExterno -and $script:ultimaCaptura -and $script:ultimaCaptura.Width -gt 20 -and $script:ultimaCaptura.Height -gt 10 -and -not [U]::IsBlank($script:ultimaCaptura)) {
      Reiniciar-Ocr
      $res3 = Get-OcrUmaVez $h $scale -Tela:$Tela -Margem $Margem -Recorte $Recorte
      if (Tem-Texto $res3) { try { Log '   (leitor de texto do Windows reiniciado - voltou a ler)' } catch {}; return $res3 }
      # le num leitor separado (outro processo, que fica ligado); se funcionar, usa ele ate o fim da rodada
      $script:ocrExterno = $true
      $res4 = Get-OcrUmaVez $h $scale -Tela:$Tela -Margem $Margem -Recorte $Recorte
      if (Tem-Texto $res4) { try { Log '   (o leitor de texto desta automação travou - passando a usar um leitor separado até o fim da rodada)' } catch {}; return $res4 }
      $script:ocrExterno = $false
    }
  }
  return $res
}
function Tem-Texto($r) { return [bool](@($r.Lines) | Where-Object { $_ -and ([string]$_).Trim() } | Select-Object -First 1) }
# leitor de texto num processo separado, que fica ligado recebe o caminho de um PNG por linha e devolve
# linhas (L) e palavras (W) com posicao, terminando com FIM
$OCR_EXTERNO = @'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); [void]$task.Wait(-1); $task.Result }
$eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language 'pt-BR'))
'PRONTO'; [Console]::Out.Flush()
while ($true) {
  $arq = [Console]::In.ReadLine()
  if ($null -eq $arq) { break }
  $arq = ($arq -replace '^[^A-Za-z]+', '').Trim()   # a 1a linha recebida pode vir com a marca de codificacao (BOM) na frente
  if ($arq -eq 'SAIR') { break }
  try {
    $ms = New-Object IO.MemoryStream (, [IO.File]::ReadAllBytes($arq))
    $st = [IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($ms)
    $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($st)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $sb = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $res = Await ($eng.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
    $i = 0
    foreach ($ln in $res.Lines) {
      "L`t" + $ln.Text
      foreach ($w in $ln.Words) { $b = $w.BoundingRect; "W`t$i`t$([int]$b.X)`t$([int]$b.Y)`t$([int]$b.Width)`t$([int]$b.Height)`t$($w.Text)" }
      $i++
    }
    $sb.Dispose(); $st.Dispose(); $ms.Dispose()
  } catch { "E`t" + $_.Exception.Message }
  'FIM'; [Console]::Out.Flush()
}
'@
function Ocr-Externo([string]$png) {
  for ($tent = 1; $tent -le 2; $tent++) {
    if (-not $script:ocrProc -or $script:ocrProc.HasExited) {
      $hp = Join-Path $env:TEMP 'sgci_ocr_externo.ps1'
      [IO.File]::WriteAllText($hp, $OCR_EXTERNO, (New-Object Text.UTF8Encoding $true))
      $psi = New-Object Diagnostics.ProcessStartInfo 'powershell.exe', ('-NoProfile -NonInteractive -STA -ExecutionPolicy Bypass -File "' + $hp + '"')
      $psi.UseShellExecute = $false; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardInput = $true; $psi.CreateNoWindow = $true
      $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
      $script:ocrProc = [Diagnostics.Process]::Start($psi)
      $pronto = $script:ocrProc.StandardOutput.ReadLine()
      if ($pronto -ne 'PRONTO') { try { $script:ocrProc.Kill() } catch {}; $script:ocrProc = $null; continue }
    }
    try {
      $script:ocrProc.StandardInput.WriteLine($png); $script:ocrProc.StandardInput.Flush()
      $out = @()
      while ($true) { $x = $script:ocrProc.StandardOutput.ReadLine(); if ($null -eq $x -or $x -eq 'FIM') { break }; $out += $x }
      if ($null -ne $x) { return $out }
    } catch {}
    try { $script:ocrProc.Kill() } catch {}; $script:ocrProc = $null
  }
  return @()
}
function Fechar-OcrExterno { try { if ($script:ocrProc -and -not $script:ocrProc.HasExited) { $script:ocrProc.StandardInput.WriteLine('SAIR'); [void]$script:ocrProc.WaitForExit(3000); if (-not $script:ocrProc.HasExited) { $script:ocrProc.Kill() } } } catch {} }
function Reiniciar-Ocr {
  # no maximo 1 vez a cada 5 s (uma area realmente vazia nao deve ficar recriando o leitor sem parar)
  if ($script:ultReinicioOcr -and ((Get-Date) - $script:ultReinicioOcr).TotalSeconds -lt 5) { return }
  $script:ultReinicioOcr = Get-Date
  try { [GC]::Collect(); [GC]::WaitForPendingFinalizers() } catch {}
  $novo = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language 'pt-BR'))
  if ($novo) { $script:ocrEngine = $novo }
}
# guarda a ultima imagem que o OCR leu (para salvar em erros quando uma leitura falha)
function Salvar-UltimaCaptura([string]$nome) {
  try {
    if (-not $script:ultimaCaptura) { return $null }
    New-Item -ItemType Directory -Force $PASTA_ERROS | Out-Null
    $arq = Join-Path $PASTA_ERROS ("ocr_$nome`_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.png')
    $script:ultimaCaptura.Save($arq, [Drawing.Imaging.ImageFormat]::Png)
    Log "      imagem que o OCR leu: $arq"
    # qual janela estava na frente (no outro PC o SGM aparecia inativo quando a leitura falhava)
    $fg = [U]::GetForegroundWindow(); $fi = [U]::Info($fg); $pn = ''
    try { $pn = (Get-Process -Id (Pid-De $fg) -ErrorAction Stop).ProcessName } catch {}
    Log ("      janela na frente: processo '{0}' | título '{1}' | classe '{2}' | {3}x{4} em {5},{6}" -f $pn, $fi.Text, $fi.Cls, $fi.W, $fi.Hg, $fi.L, $fi.T)
    return $arq
  } catch { return $null }
}
function Get-OcrUmaVez([IntPtr]$h, [int]$scale = 2, [switch]$Tela, [int]$Margem = 0, $Recorte = $null, [switch]$Externo) {
  $w = [U]::Info($h)
  $bmp = $null
  if (-not $Tela) { $bmp = [U]::Capture($h, $false); if ($bmp -and [U]::IsBlank($bmp)) { $bmp.Dispose(); $bmp = $null } }
  if (-not $bmp) {
    # captura da tela o programa dono precisa estar na frente
    $raiz = [U]::Root($h)
    if ((Pid-De ([U]::GetForegroundWindow())) -ne (Pid-De $raiz)) { [void][U]::Activate($raiz); Start-Sleep -Milliseconds 300 }
    $bmp = [U]::Capture($h, $true)
  }
  if (-not $bmp) { return [pscustomobject]@{ Text = ''; Lines = @(); Words = @() } }
  # Recorte = @(x, y, largura, altura) relativo a janela le so esse pedaco (ex uma coluna da grade)
  $ox = 0; $oy = 0
  if ($Recorte) {
    $rx = [Math]::Max(0, [int]$Recorte[0]); $ry = [Math]::Max(0, [int]$Recorte[1])
    $rw = [Math]::Min($bmp.Width - $rx, [int]$Recorte[2]); $rh = [Math]::Min($bmp.Height - $ry, [int]$Recorte[3])
    if ($rw -gt 0 -and $rh -gt 0) {
      $cut = $bmp.Clone((New-Object Drawing.Rectangle $rx, $ry, $rw, $rh), $bmp.PixelFormat); $bmp.Dispose(); $bmp = $cut; $ox = $rx; $oy = $ry
    }
  }
  if ($Margem -gt 0) {
    # campos pequenos (ex uma celula com 0,000) o OCR so le com uma margem branca em volta
    $pad = New-Object System.Drawing.Bitmap ($bmp.Width + 2 * $Margem), ($bmp.Height + 2 * $Margem)
    $gp = [System.Drawing.Graphics]::FromImage($pad); $gp.Clear([System.Drawing.Color]::White); $gp.DrawImage($bmp, $Margem, $Margem); $gp.Dispose()
    $bmp.Dispose(); $bmp = $pad
  }
  if ($script:ultimaCaptura) { try { $script:ultimaCaptura.Dispose() } catch {} }
  $script:ultimaCaptura = $bmp.Clone()
  $big = [U]::Scale($bmp, $scale); $bmp.Dispose()
  if ($Externo -or $script:ocrExterno) {
    $png = Join-Path $env:TEMP 'sgci_ocr_externo.png'
    $big.Save($png, [System.Drawing.Imaging.ImageFormat]::Png); $big.Dispose()
    $lines = @(); $words = @()
    foreach ($x in (Ocr-Externo $png)) {
      $p = $x -split "`t"
      if ($p[0] -eq 'L') { $lines += ($p[1..($p.Count - 1)] -join "`t") }
      elseif ($p[0] -eq 'W' -and $p.Count -ge 7) {
        $lt = ''; if ([int]$p[1] -lt $lines.Count) { $lt = $lines[[int]$p[1]] }
        $words += [pscustomobject]@{ Text = $p[6]; Line = [int]$p[1]; LineText = $lt
          X = [int]($w.L + $ox + [int]$p[2] / $scale - $Margem); Y = [int]($w.T + $oy + [int]$p[3] / $scale - $Margem); W = [int]([int]$p[4] / $scale); H = [int]([int]$p[5] / $scale) }
      }
    }
    try { Remove-Item $png -Force -ErrorAction SilentlyContinue } catch {}
    return [pscustomobject]@{ Text = ($lines -join "`n"); Lines = $lines; Words = $words }
  }
  $ms = New-Object IO.MemoryStream; $big.Save($ms, [System.Drawing.Imaging.ImageFormat]::Bmp); $big.Dispose(); $ms.Position = 0
  $stream = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($ms)
  $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $sb = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $res = Await ($script:ocrEngine.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
  $lines = @(); $words = @(); $i = 0
  foreach ($ln in $res.Lines) {
    $lines += $ln.Text
    foreach ($wd in $ln.Words) {
      $b = $wd.BoundingRect
      $words += [pscustomobject]@{ Text = $wd.Text; Line = $i; LineText = $ln.Text
        X = [int]($w.L + $ox + $b.X / $scale - $Margem); Y = [int]($w.T + $oy + $b.Y / $scale - $Margem); W = [int]($b.Width / $scale); H = [int]($b.Height / $scale) }
    }
    $i++
  }
  # libera tudo da leitura (objetos do Windows acumulando podem travar o leitor depois de muitas leituras)
  try { $sb.Dispose() } catch {}; try { $stream.Dispose() } catch {}; try { $ms.Dispose() } catch {}
  $res = $null; $dec = $null
  [pscustomobject]@{ Text = ($lines -join "`n"); Lines = $lines; Words = $words }
}

# ---------------------------- UTILITARIOS ----------------------------
class FalhaAutomacao : System.Exception { FalhaAutomacao([string]$m) : base($m) {} }

function Log([string]$msg) {
  $linha = "{0}  {1}" -f (Get-Date -Format 'dd/MM/yyyy HH:mm:ss'), $msg
  Add-Content -Path $ARQ_LOG -Value $linha -Encoding UTF8
  Write-Host $linha
}
function Fail([string]$msg) { throw [FalhaAutomacao]::new($msg) }
function Check-Esc { if ([U]::GetAsyncKeyState(0x1B) -band 0x8000) { Fail 'Automação interrompida pelo usuário (ESC).' } }
function Pausa([int]$ms) { $fim = (Get-Date).AddMilliseconds($ms); while ((Get-Date) -lt $fim) { Check-Esc; Start-Sleep -Milliseconds 50 } }
function Esperar([scriptblock]$cond, [double]$seg, [int]$intervalo = 400) {
  $fim = (Get-Date).AddSeconds($seg)
  do { Check-Esc; $r = & $cond; if ($r) { return $r }; Pausa $intervalo } while ((Get-Date) -lt $fim)
  return $null
}
# numero lido por OCR numa celula do SGCI (sempre com 3 casas 2,000, 1,500, 250,000)
# corrige trocas comuns do OCR z-2 o-0 lI-1 s-5 B-8 g-9; se a virgula sumir, ela volta antes das 3 ultimas casas
function Num-Ocr([string]$s) {
  if (-not $s) { return $null }
  $t = $s -creplace '[zZ]', '2' -creplace '[oOQD]', '0' -creplace '[lI!]', '1' -creplace '[sS]', '5' -creplace 'B', '8' -creplace 'g', '9' -replace '\.', ','
  $t = $t -replace '[^\d,]', ''
  if (-not $t) { return $null }
  # ponto de milhar 1.245,000 virava 1,245,000 - so a ULTIMA virgula e a decimal
  $iv = $t.LastIndexOf(','); if ($iv -gt 0) { $t = $t.Substring(0, $iv).Replace(',', '') + $t.Substring($iv) }
  if ($t -notmatch ',' -and $t.Length -ge 4) { $t = $t.Substring(0, $t.Length - 3) + ',' + $t.Substring($t.Length - 3) }
  $d = [decimal]0
  if ([decimal]::TryParse($t, [Globalization.NumberStyles]::Number, $PTBR, [ref]$d)) { return $d }
  return $null
}
function Norm([string]$s) {
  if ($null -eq $s) { return '' }
  $d = $s.Normalize([Text.NormalizationForm]::FormD)
  $sb = New-Object Text.StringBuilder
  foreach ($c in $d.ToCharArray()) { if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($c) -ne 'NonSpacingMark') { [void]$sb.Append($c) } }
  (($sb.ToString().ToUpperInvariant()) -replace '&', '' -replace '\s+', ' ').Trim()
}
function Digitos([string]$s) { ($s -replace '[Oo]', '0' -replace '[lI]', '1' -replace '\D', '') }
# ---- pop-up proprio (cantos arredondados, cor por tipo)
function Caminho-Arredondado([int]$x, [int]$y, [int]$w, [int]$h, [int]$r) {
  $p = New-Object Drawing.Drawing2D.GraphicsPath
  $d = $r * 2
  $p.AddArc($x, $y, $d, $d, 180, 90); $p.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
  $p.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90); $p.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
  $p.CloseFigure(); return $p
}
# $icone Information  Question  Error  Success   $botoes OK  YesNo  OKCancel
# retorna 'OK'  'Yes'  'No'  'Cancel'
function Msg([string]$texto, [string]$titulo = 'Automação SGCI', [string]$botoes = 'OK', [string]$icone = 'Information') {
  $temas = @{
    Information = @([Drawing.Color]::FromArgb(37, 99, 235), 'i')
    Question    = @([Drawing.Color]::FromArgb(234, 138, 0), '?')
    Error       = @([Drawing.Color]::FromArgb(220, 38, 38), '!')
    Success     = @([Drawing.Color]::FromArgb(22, 163, 74), [string][char]0x2713)
  }
  $tema = $temas[$icone]; if (-not $tema) { $tema = $temas['Information'] }
  $cor = $tema[0]
  $fonte = 'Segoe UI'

  $f = New-Object Windows.Forms.Form
  $f.FormBorderStyle = 'None'; $f.StartPosition = 'CenterScreen'; $f.TopMost = $true; $f.ShowInTaskbar = $true
  $f.BackColor = [Drawing.Color]::White; $f.KeyPreview = $true; $f.Text = $titulo
  $f.Font = New-Object Drawing.Font($fonte, 10)

  # faixa colorida no topo
  $faixa = New-Object Windows.Forms.Panel; $faixa.BackColor = $cor; $faixa.Height = 5; $faixa.Dock = 'Top'
  $f.Controls.Add($faixa)

  # icone (circulo claro com simbolo)
  $ic = New-Object Windows.Forms.Panel; $ic.Size = New-Object Drawing.Size(46, 46); $ic.Location = New-Object Drawing.Point(26, 30)
  $ic.Tag = @($cor, $tema[1], $fonte)
  $ic.Add_Paint({
    $c = $this.Tag[0]; $g = $_.Graphics; $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'ClearTypeGridFit'
    $g.FillEllipse((New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(32, $c))), 0, 0, 45, 45)
    $fmt = New-Object Drawing.StringFormat; $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
    $g.DrawString($this.Tag[1], (New-Object Drawing.Font($this.Tag[2], 17, [Drawing.FontStyle]::Bold)), (New-Object Drawing.SolidBrush $c), (New-Object Drawing.RectangleF(0, 1, 46, 46)), $fmt)
  })
  $f.Controls.Add($ic)

  $larg = 470
  $lt = New-Object Windows.Forms.Label; $lt.Text = $titulo; $lt.AutoSize = $true
  $lt.Font = New-Object Drawing.Font($fonte, 13, [Drawing.FontStyle]::Bold); $lt.ForeColor = [Drawing.Color]::FromArgb(17, 24, 39)
  $lt.Location = New-Object Drawing.Point(88, 28); $lt.MaximumSize = New-Object Drawing.Size(($larg - 110), 0)
  $f.Controls.Add($lt)

  $lm = New-Object Windows.Forms.Label; $lm.Text = $texto; $lm.AutoSize = $true
  $lm.Font = New-Object Drawing.Font($fonte, 10); $lm.ForeColor = [Drawing.Color]::FromArgb(75, 85, 99)
  $lm.MaximumSize = New-Object Drawing.Size(($larg - 110), 0)
  $lm.Location = New-Object Drawing.Point(89, ($lt.Top + $lt.PreferredHeight + 8))
  $f.Controls.Add($lm)

  # area dos botoes
  $rod = New-Object Windows.Forms.Panel; $rod.Dock = 'Bottom'; $rod.Height = 62; $rod.BackColor = [Drawing.Color]::FromArgb(248, 250, 252)
  $f.Controls.Add($rod)
  switch ($botoes) {
    'YesNo'    { $defs = @(@('Sim', 'Yes', $true), @('Não', 'No', $false)) }
    'OKCancel' { $defs = @(@('OK', 'OK', $true), @('Cancelar', 'Cancel', $false)) }
    default    { $defs = @(, @('OK', 'OK', $true)) }
  }
  $x = $larg - 24
  for ($i = $defs.Count - 1; $i -ge 0; $i--) {
    $d = $defs[$i]
    $b = New-Object Windows.Forms.Button; $b.Text = $d[0]; $b.Tag = $d[1]
    $b.Size = New-Object Drawing.Size(112, 36); $x -= 112; $b.Location = New-Object Drawing.Point($x, 13); $x -= 10
    $b.FlatStyle = 'Flat'; $b.Cursor = [Windows.Forms.Cursors]::Hand
    $b.Font = New-Object Drawing.Font($fonte, 10, [Drawing.FontStyle]::Bold)
    if ($d[2]) {
      $b.BackColor = $cor; $b.ForeColor = [Drawing.Color]::White; $b.FlatAppearance.BorderSize = 0
      $b.FlatAppearance.MouseOverBackColor = [Drawing.Color]::FromArgb(220, $cor)
      $f.AcceptButton = $b
    } else {
      $b.BackColor = [Drawing.Color]::White; $b.ForeColor = [Drawing.Color]::FromArgb(55, 65, 81)
      $b.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(209, 213, 219); $b.FlatAppearance.BorderSize = 1
      $f.CancelButton = $b
    }
    $b.Add_Click({ $fm = $this.FindForm(); $fm.Tag = $this.Tag; $fm.Close() })
    $rod.Controls.Add($b)
  }
  if ($defs.Count -eq 1) { $f.CancelButton = $f.AcceptButton }

  $alt = [Math]::Max(($lm.Top + $lm.PreferredHeight), 76) + 26 + $rod.Height
  $f.ClientSize = New-Object Drawing.Size($larg, $alt)
  $f.Region = New-Object Drawing.Region (Caminho-Arredondado 0 0 $larg $alt 14)
  $f.Add_Paint({
    $_.Graphics.SmoothingMode = 'AntiAlias'
    $_.Graphics.DrawPath((New-Object Drawing.Pen ([Drawing.Color]::FromArgb(209, 213, 219))), (Caminho-Arredondado 0 0 ($this.ClientSize.Width - 1) ($this.ClientSize.Height - 1) 14))
  })
  # arrastar pela janela
  $arrasta = { if ($_.Button -eq 'Left') { $script:dlgPos = [Windows.Forms.Cursor]::Position; $script:dlgOrig = $this.FindForm().Location } }
  $move = { if ($_.Button -eq 'Left' -and $script:dlgPos) { $p = [Windows.Forms.Cursor]::Position; $fm = $this.FindForm(); $fm.Location = New-Object Drawing.Point(($script:dlgOrig.X + $p.X - $script:dlgPos.X), ($script:dlgOrig.Y + $p.Y - $script:dlgPos.Y)) } }
  foreach ($ctl in @($f, $lt, $lm, $faixa)) { $ctl.Add_MouseDown($arrasta); $ctl.Add_MouseMove($move) }

  $f.Add_Shown({ [void][U]::Activate($this.Handle); $this.Activate() })
  [void]$f.ShowDialog()
  $r = $f.Tag; if (-not $r) { if ($botoes -eq 'YesNo') { $r = 'No' } elseif ($botoes -eq 'OKCancel') { $r = 'Cancel' } else { $r = 'OK' } }
  $f.Dispose()
  return [string]$r
}
function Confirmar([string]$texto) {
  if (-not $MODO_TESTE) { return }
  $r = Msg $texto 'Confirme' 'YesNo' 'Question'
  if ($r -ne 'Yes') { Fail 'Cancelado pelo usuário na confirmação do modo teste.' }
}
function Salvar-Print([string]$nome) {
  try {
    New-Item -ItemType Directory -Force $PASTA_ERROS | Out-Null
    $b = [Windows.Forms.SystemInformation]::VirtualScreen
    $bmp = New-Object Drawing.Bitmap $b.Width, $b.Height
    $g = [Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size); $g.Dispose()
    $arq = Join-Path $PASTA_ERROS ("$nome`_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.png')
    $bmp.Save($arq, [Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose(); return $arq
  } catch { return '' }
}

# ---- janelas  controles
function Filhos([IntPtr]$h) { @([U]::Desc($h)) }
function Visiveis([IntPtr]$h) { @([U]::Desc($h) | Where-Object { $_.Vis }) }
function Texto([IntPtr]$h) { [U]::GetText($h).Trim() }
function SemE([string]$s) { ($s -replace '&', '').Trim() }

function Ativar([IntPtr]$h, [string]$nome) {
  for ($i = 0; $i -lt 4; $i++) { if ([U]::Activate($h)) { Pausa 200; return }; Pausa 400 }
  Fail "Não consegui trazer o $nome para a frente."
}
function Pid-De([IntPtr]$h) { $p = [uint32]0; [void][U]::GetWindowThreadProcessId($h, [ref]$p); return $p }
# a janela em primeiro plano precisa ser do mesmo programa (inclui popupsdialogos dele)
function Garantir-Frente([IntPtr]$raiz, [string]$nome) {
  if ((Pid-De ([U]::GetForegroundWindow())) -ne (Pid-De $raiz)) { Ativar $raiz $nome }
  if ((Pid-De ([U]::GetForegroundWindow())) -ne (Pid-De $raiz)) { Fail "O $nome não está em primeiro plano. Digitação cancelada por segurança." }
}
# aperta uma tecla como tecla fisica, sem esperar o programa terminar de processar (ex 0x0D Enter, 0x09 Tab)
function Tecla-Solta([byte]$vk) {
  Check-Esc
  [U]::keybd_event($vk, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 40; [U]::keybd_event($vk, 0, 2, [UIntPtr]::Zero)
}
# equivalente ao Ctrl+Alt+Del + Esc troca rapido para outra tela do Windows e volta, depois devolve o foco
function Destravar-Foco([IntPtr]$raiz) {
  $r = [U]::PiscarDesktop(250)
  if ($r -ne 'ok') { Log "   (troca de tela: $r)" }
  Pausa 500
  Ativar $raiz 'SGCI'
  Pausa 300
}
# tira o foco do programa (ativa a barra de tarefas do Windows por um instante) e devolve
function Desfocar-E-Voltar([IntPtr]$raiz) {
  $barra = [U]::Tops(0) | Where-Object { $_.Cls -eq 'Shell_TrayWnd' } | Select-Object -First 1
  if ($barra) { [void][U]::Activate($barra.H) }
  Pausa 400
  Ativar $raiz 'SGCI'
  Pausa 300
}
function Clicar([WinInfo]$c, [int]$dx = -1, [int]$dy = -1, [switch]$Duplo) {
  Check-Esc
  if (-not [U]::IsWindow($c.H)) { Fail "Controle não existe mais ($($c.Cls) '$($c.Text)')." }
  $c = [U]::Info($c.H)
  if ($dx -lt 0) { $x = $c.CX } else { $x = $c.L + $dx }
  if ($dy -lt 0) { $y = $c.CY } else { $y = $c.T + $dy }
  $alvo = [U]::At($x, $y)
  if ($alvo -ne $c.H -and -not [U]::IsChild($c.H, $alvo)) {
    Ativar ([U]::Root($c.H)) 'programa'
    $alvo = [U]::At($x, $y)
    if ($alvo -ne $c.H -and -not [U]::IsChild($c.H, $alvo)) { Fail "Algo está cobrindo o controle '$($c.Text)' ($($c.Cls)). Clique cancelado por segurança." }
  }
  [U]::Click($x, $y, [bool]$Duplo); Pausa 250
}
function Clicar-Ponto([IntPtr]$dono, [int]$x, [int]$y, [switch]$Duplo) {
  Check-Esc
  $alvo = [U]::At($x, $y)
  if ($alvo -ne $dono -and -not [U]::IsChild($dono, $alvo)) { Fail 'O ponto de clique não está na janela esperada. Clique cancelado por segurança.' }
  [U]::Click($x, $y, [bool]$Duplo); Pausa 250
}
function Teclas([string]$k, [IntPtr]$raiz, [string]$nome) {
  Check-Esc; Garantir-Frente $raiz $nome
  [Windows.Forms.SendKeys]::SendWait($k); Pausa 150
}
function EscSK([string]$t) { ($t -replace '([+^%~(){}\[\]])', '{$1}') }
function Digitar([string]$t, [IntPtr]$raiz, [string]$nome) { Teclas (EscSK $t) $raiz $nome }
function Botao([IntPtr]$pai, [string]$legenda) {
  $n = Norm $legenda
  Visiveis $pai | Where-Object { $_.Cls -match 'Button|BitBtn|TButton' -and (Norm $_.Text) -eq $n } | Select-Object -First 1
}

# ---- popups (MessageBox do Windows ou do Delphi)
function Popups([int]$procId, [IntPtr[]]$ignorar) {
  @([U]::Tops([uint32]$procId) | Where-Object { ($_.Cls -eq '#32770' -or $_.Cls -eq 'TMessageForm') -and ($ignorar -notcontains $_.H) })
}
function Texto-Popup([WinInfo]$p) {
  $t = (Filhos $p.H | Where-Object { $_.Cls -eq 'Static' -and $_.Text } | ForEach-Object { $_.Text }) -join ' '
  if (-not $t) { Ativar $p.H 'popup'; $t = (Get-Ocr $p.H 2 -Tela).Text -replace "`n", ' ' }
  return $t.Trim()
}
function Responder-Popup([WinInfo]$p, [string[]]$botoes) {
  foreach ($b in $botoes) {
    $btn = Filhos $p.H | Where-Object { $_.Vis -and (Norm $_.Text) -eq (Norm $b) } | Select-Object -First 1
    if ($btn) { Ativar $p.H 'popup'; Clicar $btn; return }
  }
  Ativar $p.H 'popup'; [Windows.Forms.SendKeys]::SendWait('{ENTER}'); Pausa 300
}

# ---- OCR helpers
function Linha-Com([object]$ocr, [string]$alvo) {
  foreach ($w in $ocr.Words) { if ((Digitos $w.Text) -eq $alvo) { return $w } }
  for ($i = 0; $i -lt $ocr.Lines.Count; $i++) {
    if ((Digitos $ocr.Lines[$i]) -like "*$alvo*") { return ($ocr.Words | Where-Object { $_.Line -eq $i } | Select-Object -First 1) }
  }
  return $null
}
# texto da linha inteira da grade junta todas as palavras na mesma altura da palavra achada
# (em grades com colunas largas o OCR quebra a mesma linha em varios pedacos)
function Linha-Texto([object]$ocr, $w) {
  $meio = $w.Y + $w.H / 2
  (@($ocr.Words | Where-Object { [Math]::Abs(($_.Y + $_.H / 2) - $meio) -le [Math]::Max(6, $w.H * 0.6) } | Sort-Object X | ForEach-Object { $_.Text })) -join ' '
}
function Total-Registros([string]$t) {
  if ($t -match 'Registros\s*:\s*(\d+)') { return [int]$Matches[1] }
  return -1
}
# encontra a palavrasequencia de palavras de um rotulo (ex 'Situação Medição Cliente')
function Rotulo([object]$ocr, [string]$rot, [string]$naoPrecedidoPor = '') {
  $partes = (Norm $rot).Split(' ')
  $achados = @()
  $ws = @($ocr.Words)
  for ($i = 0; $i -lt $ws.Count; $i++) {
    $ok = $true
    for ($k = 0; $k -lt $partes.Count; $k++) {
      $j = $i + $k
      if ($j -ge $ws.Count -or $ws[$j].Line -ne $ws[$i].Line -or ((Norm $ws[$j].Text) -replace '[^A-Z0-9.]', '') -ne ($partes[$k] -replace '[^A-Z0-9.]', '')) { $ok = $false; break }
    }
    if ($ok -and $naoPrecedidoPor -and $i -gt 0 -and $ws[$i - 1].Line -eq $ws[$i].Line -and (Norm $ws[$i - 1].Text) -eq (Norm $naoPrecedidoPor)) { $ok = $false }
    if ($ok) { $u = $ws[$i + $partes.Count - 1]; $achados += [pscustomobject]@{ X = $ws[$i].X; Y = $ws[$i].Y; R = $u.X + $u.W; B = [Math]::Max($ws[$i].Y + $ws[$i].H, $u.Y + $u.H) } }
  }
  $achados | Sort-Object Y, X | Select-Object -First 1
}
function Campo-Abaixo([IntPtr]$pai, $rot) {
  if (-not $rot) { return $null }
  Visiveis $pai | Where-Object { $_.Hg -ge 13 -and $_.Hg -le 32 -and $_.W -ge 15 -and $_.T -ge ($rot.B - 4) -and $_.T -le ($rot.B + 24) -and $_.L -le ($rot.X + 15) -and $_.R -ge ($rot.X + 5) -and $_.Cls -notmatch 'Panel|GroupBox|TabSheet|PageControl|Grid|Btn' } |
    Sort-Object T, @{ Expression = { [Math]::Abs($_.L - $rot.X) } } | Select-Object -First 1
}
function Campo-Direita([IntPtr]$pai, [WinInfo]$c) {
  Visiveis $pai | Where-Object { [Math]::Abs($_.T - $c.T) -le 5 -and $_.L -ge ($c.R - 2) -and $_.W -ge 60 -and $_.Hg -le 32 -and $_.Cls -notmatch 'Panel|GroupBox|Btn' } |
    Sort-Object L | Select-Object -First 1
}
function Escrever-Campo([WinInfo]$c, [string]$valor, [IntPtr]$raiz, [string]$nome) {
  # ja esta com o valor certo (ex MQ  Nº  AGU feitos antes, na opcao Continuar) nao mexe
  $atual = ([string](Texto $c.H)).Trim()
  Clicar $c 8   # mesmo sem digitar, deixa o foco no campo (ex na pesquisa o Enter vem logo depois)
  if ($atual -eq $valor) { return }
  # apaga o que tiver com Backspace (selecionar e digitar por cima as vezes deixava sobra MQ virava MMQ)
  Teclas '{END}' $raiz $nome
  if ($atual.Length -gt 0) { Teclas ('{BACKSPACE ' + ($atual.Length + 2) + '}') $raiz $nome }
  if (([string](Texto $c.H)).Trim()) { Teclas '{HOME}+{END}{DEL}' $raiz $nome }
  Digitar $valor $raiz $nome
}

# =====================================================================
#  SGM
# =====================================================================
function SGM-Principal {
  $p = Get-Process SGM -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $p) { Fail 'SGM não encontrado. Abra o SGM e tente novamente.' }
  $w = [U]::Tops([uint32]$p.Id) | Where-Object { $_.Cls -eq 'TfrmPrincipal' } | Select-Object -First 1
  if (-not $w) { Fail 'Janela principal do SGM não encontrada.' }
  $script:sgmPid = $p.Id; $script:sgmMain = $w.H; return $w
}
function SGM-MdiClient { Filhos $script:sgmMain | Where-Object { $_.Cls -eq 'MDIClient' } | Select-Object -First 1 }
function SGM-Filha([string]$tituloContem) {
  $mdi = SGM-MdiClient
  Filhos $mdi.H | Where-Object { $_.Parent -eq $mdi.H -and $_.Vis -and $_.Text -like "*$tituloContem*" } | Select-Object -First 1
}
# telas internas que o script sabe abrir pelo menu Medicao titulo - (texto do item, setas p baixo)
$SGM_MENU = @{
  'Rascunho de Medição' = @('*RASCUNHO*MEDICAO*', 8)
  'Visão Medição'       = @('*VISAO*MEDICAO*', 3)
}
function SGM-AtivarFilha([string]$titulo) {
  $f = SGM-Filha $titulo
  if (-not $f) {
    if (-not $SGM_MENU.ContainsKey($titulo)) { Fail "Tela '$titulo' não está aberta no SGM." }
    Log "   SGM: abrindo '$titulo' pelo menu Medição"
    return (SGM-AbrirPeloMenu $titulo)
  }
  $mdi = SGM-MdiClient
  [void][U]::Send($mdi.H, 0x0222, $f.H, [IntPtr]::Zero)   # WM_MDIACTIVATE
  Ativar $script:sgmMain 'SGM'
  return (SGM-Maximizar $titulo)
}
# maximiza a tela interna (igual ao botao Maximizar) e confere pelo titulo do SGM
function SGM-Maximizar([string]$titulo) {
  $f = SGM-Filha $titulo
  if (-not $f) { Fail "Tela '$titulo' não está aberta no SGM." }
  $mdi = SGM-MdiClient
  [void][U]::Send($mdi.H, 0x0225, $f.H, [IntPtr]::Zero)   # WM_MDIMAXIMIZE
  $ok = Esperar { (Texto $script:sgmMain) -like "*$titulo*" } 8
  if (-not $ok) { Fail "Não consegui maximizar a tela '$titulo' no SGM." }
  Pausa 500
  return (SGM-Filha $titulo)
}
function SGM-ControlesConsulta($filha) {
  # a tela pode sumir por um instante (SGM recarregando depois de salvar) devolve tudo vazio em vez de quebrar
  if (-not $filha -or -not $filha.H -or $filha.H -eq [IntPtr]::Zero) {
    return [pscustomobject]@{ Campo = $null; Valor = $null; Grade = $null; Status = $null; Barra = $null }
  }
  $vis = Visiveis $filha.H
  $combos = @($vis | Where-Object { $_.Cls -eq 'TComboBox' } | Sort-Object L)
  [pscustomobject]@{
    Campo  = $combos | Select-Object -First 1
    Valor  = $vis | Where-Object { $_.Cls -eq 'TJvComboEdit' } | Select-Object -First 1
    Grade  = $vis | Where-Object { $_.Cls -eq 'TwwDBGrid' } | Sort-Object { $_.W * $_.Hg } -Descending | Select-Object -First 1
    Status = $vis | Where-Object { $_.Cls -eq 'TStatusBar' } | Select-Object -First 1
    Barra  = $vis | Where-Object { $_.Cls -eq 'TJvExpress' } | Select-Object -First 1
  }
}
# Seleciona a opcao do Campo, cola o valor, pesquisa e espera a linha com o codigo
function SGM-Pesquisar([WinInfo]$filha, [string]$opcao, [string]$codigo, [string]$erroNaoAchou) {
  $c = SGM-ControlesConsulta $filha
  if (-not $c.Campo -or -not $c.Valor -or -not $c.Grade) { Fail "A tela '$($filha.Text)' não está na aba Consulta." }
  Clicar $c.Campo
  Teclas '{HOME}' $script:sgmMain 'SGM'; Teclas '{DOWN}' $script:sgmMain 'SGM'; Teclas '{ENTER}' $script:sgmMain 'SGM'
  Pausa 300
  $txt = Texto $c.Campo.H
  if ((Norm $txt) -ne (Norm $opcao)) {
    Teclas '{ESC}' $script:sgmMain 'SGM'
    Fail "Campo de pesquisa ficou '$txt' (esperado '$opcao')."
  }
  Escrever-Campo $c.Valor $codigo $script:sgmMain 'SGM'
  $lido = Texto $c.Valor.H
  if ((Digitos $lido) -ne $codigo) { Fail "Valor de pesquisa ficou '$lido' (esperado '$codigo')." }
  Teclas '{ENTER}' $script:sgmMain 'SGM'
  Log "   SGM: pesquisando $opcao = $codigo"
  $ini = Get-Date
  # o texto branco na linha laranja as vezes escapa do OCR numa ampliacao e aparece em outra - alterna
  $script:escalasPesq = @(2, 4, 5, 3); $script:iPesq = 0; $script:pesqDiag = @()
  $linha = $null
  try {
  $linha = Esperar {
    # tentativas pares foto interna da janela; impares captura da tela (em alguns PCs a foto interna vem errada)
    $tela = ($script:iPesq % 2 -eq 1)
    $o = Get-Ocr $c.Grade.H $script:escalasPesq[$script:iPesq % $script:escalasPesq.Count] -Tela:$tela; $script:iPesq++
    $st = (Get-Ocr $c.Status.H 3).Text
    $tot = Total-Registros $st
    if ($tot -eq 0 -and ((Get-Date) - $ini).TotalSeconds -gt 8) { Fail $erroNaoAchou }
    if ($tot -gt 1) { Fail "A pesquisa retornou $tot registros para $codigo (esperado 1)." }
    $w = Linha-Com $o $codigo
    if (-not $w -and $tot -eq 1) {
      # o texto branco na linha laranja escapa do OCR da grade inteira - le so a coluna pesquisada, com margem
      $cab = Rotulo $o $opcao
      $gi = [U]::Info($c.Grade.H)
      $recs = @()
      if ($cab) {
        $prox = @($o.Words | Where-Object { [Math]::Abs($_.Y - $cab.Y) -le 6 -and $_.X -gt ($cab.R + 3) } | Sort-Object X | Select-Object -First 1)
        $dir = if ($prox) { $prox[0].X - 3 } else { $cab.X + 150 }
        $topo = $cab.B - $gi.T + 2
        # a coluna exata e uma um pouco mais larga (o numero pode encostar na coluna vizinha)
        $recs += , @(($cab.X - $gi.L - 4), $topo, ($dir - $cab.X + 4), ($gi.Hg - $topo))
        $recs += , @(($cab.X - $gi.L - 14), $topo, ($dir - $cab.X + 24), ($gi.Hg - $topo))
      } else {
        # cabecalho nao lido tenta o lado esquerdo da grade, logo abaixo do cabecalho
        $recs += , @(0, 16, [int]($gi.W * 0.45), [Math]::Min(120, $gi.Hg - 16))
      }
      foreach ($rec in $recs) {
        foreach ($esc in @(3, 2, 4)) { $w = Linha-Com (Get-Ocr $c.Grade.H $esc -Margem 20 -Recorte $rec -Tela:$tela) $codigo; if ($w) { break } }
        if ($w) { break }
      }
    }
    if ($w -and $tot -eq 1) { return $w }
    $script:pesqDiag += @("tentativa $($script:iPesq): status='$($st -replace '\s+', ' ')' | cabeçalho=$([bool]$cab) | grade='$((@($o.Lines) | Select-Object -First 8) -join ' / ')'")
    return $null
  } $TIMEOUT_CONSULTA 700
  if (-not $linha) { $linha = 'FALHOU' }
  } finally {
    # se nao confirmou (ou ESC no meio), grava no log o que o OCR leu
    if ((-not $linha -or $linha -eq 'FALHOU') -and $script:pesqDiag.Count) {
      Add-Content -Path $ARQ_LOG -Encoding UTF8 -Value (@("----- OCR da pesquisa ($opcao = $codigo) -----") + @($script:pesqDiag | Select-Object -Last 6) + '-----')
      [void](Salvar-UltimaCaptura 'pesquisa')
    }
  }
  if ($linha -eq 'FALHOU') { Fail $erroNaoAchou }
  Log "   SGM: linha confirmada ($codigo)"
  return [pscustomobject]@{ Linha = $linha; Ctl = $c }
}
# Abre o registro (duplo clique) e espera a aba Cadastro, identificada por um rotulo
function SGM-AbrirCadastro([WinInfo]$filha, $pesquisa, [string]$rotuloEsperado) {
  Pausa 2000
  $l = $pesquisa.Linha
  Clicar-Ponto $pesquisa.Ctl.Grade.H ($l.X + [int]($l.W / 2)) ($l.Y + [int]($l.H / 2)) -Duplo
  # o rotulo as vezes escapa do OCR numa ampliacao (depende da telaresolucao) - alterna
  # o SGM as vezes demora para carregar o cadastro (janela em branco  sem responder) - espera ate 60 s
  $script:escalasCad = @(2, 3, 4); $script:iCad = 0; $script:cadDiag = @(); $script:t0Cad = Get-Date; $script:cliquesCad = 1
  $ocr = Esperar {
    $seg = [int]((Get-Date) - $script:t0Cad).TotalSeconds
    if ([U]::IsWindowVisible($pesquisa.Ctl.Campo.H)) {
      $script:cadDiag += "${seg}s: ainda na aba Consulta"
      # o duplo clique as vezes nao pega (SGM ocupado ou outra janela na frente) clica de novo aos 12 s e aos 28 s
      if (($seg -ge 12 -and $script:cliquesCad -lt 2) -or ($seg -ge 28 -and $script:cliquesCad -lt 3)) {
        $script:cliquesCad++
        Ativar $script:sgmMain 'SGM'
        if ($script:cliquesCad -eq 2) {
          Log "   SGM: a aba Cadastro não abriu - duplo clique de novo na linha"
          Clicar-Ponto $pesquisa.Ctl.Grade.H ($l.X + [int]($l.W / 2)) ($l.Y + [int]($l.H / 2)) -Duplo
        } else {
          # outro caminho seleciona a linha com 1 clique e clica na aba Cadastro (no topo da tela)
          Log "   SGM: a aba Cadastro não abriu - selecionando a linha e clicando na aba Cadastro"
          Clicar-Ponto $pesquisa.Ctl.Grade.H ($l.X + [int]($l.W / 2)) ($l.Y + [int]($l.H / 2))
          Pausa 600
          $fi = [U]::Info($filha.H)
          $oa = Get-Ocr $filha.H 3 -Margem 10 -Recorte @(0, 0, [Math]::Min(400, $fi.W), 30)
          $aba = $oa.Words | Where-Object { (Norm $_.Text) -eq 'CADASTRO' } | Select-Object -First 1
          if ($aba) { Clicar-Ponto $filha.H ($aba.X + [int]($aba.W / 2)) ($aba.Y + [int]($aba.H / 2)) }
          else { Log "      aba 'Cadastro' não lida na tela" }
        }
      }
      return $null
    }
    $tela = ($script:iCad % 2 -eq 1)
    $esc = $script:escalasCad[$script:iCad % $script:escalasCad.Count]
    $o = Get-Ocr $filha.H $esc -Tela:$tela; $script:iCad++
    if (Rotulo $o $rotuloEsperado) { return $o }
    $script:cadDiag += "${seg}s: escala $esc tela=$tela - $(@($o.Lines).Count) linhas: " + ((@($o.Lines) | Select-Object -First 12) -join ' / ')
    return $null
  } 60 800
  if (-not $ocr) {
    Add-Content -Path $ARQ_LOG -Encoding UTF8 -Value (@("----- aba Cadastro (procurando '$rotuloEsperado') -----") + @($script:cadDiag | Select-Object -Last 8) + '-----')
    [void](Salvar-UltimaCaptura 'cadastro')
    Fail "A aba Cadastro não abriu (rótulo '$rotuloEsperado' não encontrado)."
  }
  $seg = [int]((Get-Date) - $script:t0Cad).TotalSeconds
  if ($seg -ge 10) { Log "   SGM: a aba Cadastro demorou $seg s para aparecer" }
  return $ocr
}
# Salvar + tratar popups ate aparecer sucesso
function SGM-Salvar([WinInfo]$filha) {
  $btn = Botao $filha.H 'Salvar'
  if (-not $btn) { Fail 'Botão Salvar não encontrado no SGM.' }
  if (-not $btn.En) { Fail 'Botão Salvar está desabilitado no SGM.' }
  Clicar $btn
  $sucesso = $false; $semPopupDesde = $null; $algumPopup = $false; $reclicou = $false; $t0 = Get-Date
  $fim = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $fim) {
    Check-Esc
    $ps = Popups $script:sgmPid
    # clique no Salvar sem nenhuma resposta do SGM em 10 s (ex outra janela passou na frente na hora) clica de novo uma vez
    if ($ps.Count -eq 0 -and -not $algumPopup -and -not $reclicou -and ((Get-Date) - $t0).TotalSeconds -ge 10) {
      $btn2 = Botao $filha.H 'Salvar'
      if ($btn2 -and $btn2.En) { Log '   SGM: Salvar sem resposta em 10 s - clicando de novo'; Clicar $btn2; $reclicou = $true; $fim = (Get-Date).AddSeconds(30) }
    }
    if ($ps.Count -gt 0) {
      $semPopupDesde = $null; $algumPopup = $true
      $p = $ps[0]; $t = Texto-Popup $p; $nt = Norm $t
      Log "   SGM popup: $t"
      # Deseja realmente Fechar este Rascunho - Sim (depois vem ...foi Fechado com sucesso - OK)
      if ($nt -match 'DESEJA REALMENTE FECHAR ESTE RASCUNHO') { Responder-Popup $p @('&Sim', 'Sim'); Pausa 500; continue }
      Responder-Popup $p @('OK')
      if ($nt -match 'SUCESSO') { $sucesso = $true }
      # aviso Não foi encontrado nenhum Valor Previsto ... Relatórios de Rua so OK e segue
      elseif ($nt -match 'VALOR PREVISTO') { }
      elseif ($nt -notmatch 'VOCE ALTEROU A SITUACAO') { Fail "SGM mostrou a mensagem: $t" }
      Pausa 500
    } else {
      if (-not $semPopupDesde) { $semPopupDesde = Get-Date }
      if ($sucesso -and ((Get-Date) - $semPopupDesde).TotalSeconds -ge 2) { break }
      Pausa 300
    }
  }
  if (-not $sucesso) { Fail 'O SGM não confirmou "Registro salvo com sucesso".' }
}

# Imprimir  escolhe o relatorio (n setas para baixo)  Enter, Enter
function SGM-Imprimir($ctl, [int]$setas) {
  $barra = $ctl.Barra
  if (-not $barra) { Fail 'Barra de botões do SGM não encontrada.' }
  $ob = Get-Ocr $barra.H 3
  $wImp = $ob.Words | Where-Object { (Norm $_.Text) -eq 'IMPRIMIR' } | Select-Object -First 1
  if (-not $wImp) { Fail "Botão 'Imprimir' não encontrado na barra do SGM." }
  Clicar-Ponto $barra.H ($wImp.X + [int]($wImp.W / 2)) ($wImp.Y + [int]($wImp.H / 2))
  $rel = Esperar { [U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Text -like '*Relat*Rascunho*' } | Select-Object -First 1 } 15
  if (-not $rel) { Fail "A janela 'Relatórios do Rascunho de Medição' não abriu." }
  Pausa 600
  Ativar $rel.H 'Relatórios'
  for ($i = 0; $i -lt $setas; $i++) { Teclas '{DOWN}' $rel.H 'Relatórios' }
  Teclas '{ENTER}' $rel.H 'Relatórios'; Teclas '{ENTER}' $rel.H 'Relatórios'
}
function SGM-FecharVisualizar {
  foreach ($v in @([U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Text -eq 'Visualizar' })) {
    [void][U]::PostMessage($v.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
  }
  [void](Esperar { if (-not ([U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Text -eq 'Visualizar' })) { $true } } 10)
}
# Imprimir  Rascunho de Medição (1a opcao) e confere Valor Total  Total Pontos com o SGCI
function SGM-ConferirRelatorio([string]$sgm, $conf) {
  SGM-FecharVisualizar
  $filha = SGM-AtivarFilha 'Rascunho de Medição'
  $c = SGM-ControlesConsulta $filha
  if (-not $c.Grade) { Fail 'Rascunho de Medição não está na aba Consulta.' }
  if (-not (Linha-Com (Get-Ocr $c.Grade.H 2) $sgm)) {
    $c = (SGM-Pesquisar $filha 'Cód. Obra' $sgm 'SGM divergente ou errado. Por favor verifique.').Ctl
  }
  SGM-Imprimir $c 0
  $vis = Esperar { [U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Text -eq 'Visualizar' } | Select-Object -First 1 } 40 700
  if (-not $vis) { Fail "O relatório 'Rascunho de Medição' do SGM não abriu." }
  $valA = $conf.Valor.ToString('#,##0.0000', $PTBR); $valB = $conf.Valor.ToString('0.0000', $PTBR)
  $pts = $conf.Pontos.ToString('0.0000', $PTBR)
  $ultimo = ''
  $achou = Esperar {
    Ativar $vis.H 'Visualizar'
    $t = (Get-Ocr $vis.H 3 -Tela).Text
    $script:ultimoOcrRel = $t
    $s = $t -replace '\s', ''
    if (($s.Contains($valA) -or $s.Contains($valB)) -and $s.Contains($pts)) { $true }
  } 25 1500
  SGM-FecharVisualizar
  if (-not $achou) {
    Add-Content -Path $ARQ_LOG -Value ("----- OCR do relatório SGM -----`r`n" + $script:ultimoOcrRel + "`r`n-----") -Encoding UTF8
    Fail "O relatório 'Rascunho de Medição' do SGM não mostra Valor $valA / Pontos $pts (valores do SGCI)."
  }
  Log "   SGM: relatório Rascunho de Medição confere (Pontos $pts / Valor $valA)"
}

# =====================================================================
#  EXCEL
# =====================================================================
function Excel-Janelas {
  @([U]::Tops(0) | Where-Object { $_.Cls -eq 'XLMAIN' -and $_.Text -like "*$NOME_PLANILHA*" })
}
function Excel-Pasta {
  foreach ($x in Excel-Janelas) {
    $e7 = Filhos $x.H | Where-Object { $_.Cls -eq 'EXCEL7' } | Select-Object -First 1
    if ($e7) { $o = [U]::ExcelWindow($e7.H); if ($o) { try { return $o.Parent } catch {} } }
  }
  return $null
}
function Excel-Fechar {
  for ($i = 0; $i -lt 5; $i++) {
    $wb = Excel-Pasta
    if (-not $wb) { return }
    try { $app = $wb.Application; $wb.Close($false); if ($app.Workbooks.Count -eq 0) { $app.Quit() } } catch { Pausa 1000 }
    Pausa 800
  }
  [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
function Cel($ws, [string]$addr) {
  $v = $ws.Range($addr).Value2
  if ($null -eq $v) { return '' }
  if ($v -is [double]) { return ([decimal]$v).ToString($INV) }
  return ([string]$v).Trim()
}
function Num($ws, [string]$addr) {
  $v = $ws.Range($addr).Value2
  if ($null -eq $v -or $v -eq '') { return $null }
  if ($v -is [double]) { return [decimal]$v }
  $s = ([string]$v).Trim()
  $d = [decimal]0
  if ([decimal]::TryParse($s, [Globalization.NumberStyles]::Any, $PTBR, [ref]$d)) { return $d }
  return $null
}
function Excel-Ler([string]$sgm) {
  $dados = $null
  for ($tent = 0; $tent -lt 20 -and -not $dados; $tent++) {
    Check-Esc
    try {
      $wb = Excel-Pasta
      if ($wb) {
        $ws = $wb.Worksheets.Item(1)
        if ((Cel $ws 'A3') -ne '') {
          $servicos = @(); $r = 3
          while ((Cel $ws "S$r") -ne '') {
            $servicos += [pscustomobject]@{
              Linha = $r; Codigo = (Cel $ws "S$r"); Desc = (Cel $ws "T$r")
              Ref1 = (Cel $ws "P$r"); Ref2 = (Cel $ws "Q$r"); Qtd = (Num $ws "U$r")
              Pontos = (Num $ws "W$r"); Valor = (Num $ws "Y$r") }
            $r++
          }
          $dados = [pscustomobject]@{
            SGM = (Cel $ws 'A3'); Rascunho = (Cel $ws 'B3'); Descricao = (Cel $ws 'C3'); Localidade = (Cel $ws 'D3')
            OR = (Cel $ws 'F3'); ATA = (Cel $ws 'H3'); Servicos = $servicos }
        }
      }
    } catch { $dados = $null }
    if (-not $dados) { Pausa 1000 }
  }
  if (-not $dados) { Fail 'Não consegui ler a planilha gerada pelo SGM.' }
  if ((Digitos $dados.SGM) -ne $sgm) { Fail "Planilha divergente: A3 = '$($dados.SGM)', esperado SGM $sgm." }
  if (-not $dados.OR) { Fail "A OR (F3) está vazia na planilha do SGM $sgm." }
  if ($dados.Servicos.Count -eq 0) { Fail "Nenhum serviço (coluna S) na planilha do SGM $sgm." }
  foreach ($s in $dados.Servicos) {
    if ($s.Codigo -notmatch '^\d+$') { Fail "Cód. Serviço inválido na linha $($s.Linha): '$($s.Codigo)'." }
    if ($null -eq $s.Qtd -or $s.Qtd -le 0) { Fail "Quantidade inválida na linha $($s.Linha) (serviço $($s.Codigo))." }
    if (-not $s.Ref1 -or -not $s.Ref2) { Fail "Ref.1/Ref.2 vazia na linha $($s.Linha) (serviço $($s.Codigo))." }
    if ($null -eq $s.Valor -or $null -eq $s.Pontos) { Fail "Pontos/Valor vazio na linha $($s.Linha) (serviço $($s.Codigo))." }
  }
  $dados | Add-Member SomaPontos ([Math]::Round(($dados.Servicos | Measure-Object Pontos -Sum).Sum, 4))
  $dados | Add-Member SomaValor ([Math]::Round(($dados.Servicos | Measure-Object Valor -Sum).Sum, 4))
  return $dados
}

# =====================================================================
#  SGCI
# =====================================================================
function SGCI-Principal {
  $p = Get-Process SGCI -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $p) { Fail 'SGCI não encontrado. Abra o SGCI e tente novamente.' }
  $w = [U]::Tops([uint32]$p.Id) | Where-Object { $_.Cls -like '*ThunderRT6Form*' -and $_.Text -like '*Telef*S.G.C.I*' } | Select-Object -First 1
  if (-not $w) { Fail 'SGCI não encontrado. Abra o SGCI e tente novamente.' }
  $script:sgciPid = $p.Id; $script:sgciMain = $w.H; return $w
}
function SGCI-Form {
  $f = [U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Cls -like '*ThunderRT6Form*' -and $_.Text -eq 'Medição Quantificada' } | Select-Object -First 1
  if (-not $f) { $f = Filhos $script:sgciMain | Where-Object { $_.Vis -and $_.Cls -like '*ThunderRT6Form*' -and $_.Text -eq 'Medição Quantificada' } | Select-Object -First 1 }
  if (-not $f) { Fail "A tela 'Medição Quantificada' não está aberta no SGCI." }
  $script:sgciRaiz = [U]::Root($f.H)
  return $f
}
function SGCI-Janela([string]$titulo) {
  # o SGCI as vezes coloca espaco antes do titulo (ex ' Detalhe - Medição')
  $t = [U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Text.Trim() -eq $titulo } | Select-Object -First 1
  if ($t) { return $t }
  Filhos $script:sgciMain | Where-Object { $_.Vis -and $_.Text.Trim() -eq $titulo -and $_.Cls -like '*ThunderRT6Form*' } | Select-Object -First 1
}
function Por-Id([IntPtr]$pai, [int]$id, [string]$clsLike) {
  $c = Filhos $pai | Where-Object { $_.Id -eq $id -and $_.Cls -like "*$clsLike*" } | Select-Object -First 1
  if (-not $c) { Fail "Controle id=$id ($clsLike) não encontrado no SGCI. A versão da tela pode ser diferente." }
  return $c
}
function SGCI-Ctl {
  $f = SGCI-Form
  $todos = Filhos $f.H
  $nova = $todos | Where-Object { (Norm $_.Text) -eq 'NOVA MEDICAO' -and $_.Cls -like '*CommandButton*' } | Select-Object -First 1
  $inserir = $todos | Where-Object { (Norm $_.Text) -eq 'INSERIR' -and $_.Cls -like '*CommandButton*' } | Select-Object -First 1
  $frameDet = $todos | Where-Object { $_.Cls -like '*Frame*' -and (Norm $_.Text) -eq 'MEDICAO - DETALHE' } | Select-Object -First 1
  if (-not $nova -or -not $inserir -or -not $frameDet) { Fail 'Botões da tela Medição Quantificada não encontrados.' }
  [pscustomobject]@{
    Form       = $f
    Servico    = Por-Id $f.H 22 'TextBox'
    NumMedicao = Por-Id $f.H 23 'TextBox'
    Ata        = Por-Id $f.H 26 'TextBox'
    Diretoria  = Por-Id $f.H 5 'ComboBox'
    UD         = Por-Id $f.H 44 'ComboBox'
    UDDesc     = Por-Id $f.H 43 'TextBox'
    NovaMed    = $nova
    Inserir    = $inserir
    Impressora = $todos | Where-Object { $_.Cls -like '*CommandButton*' -and -not $_.Text -and [Math]::Abs($_.T - $nova.T) -le 4 -and $_.R -le ($nova.L + 2) } | Sort-Object L -Descending | Select-Object -First 1
    Encaminhar = $todos | Where-Object { (Norm $_.Text) -eq 'ENCAMINHAR' } | Select-Object -First 1
    Sair       = $todos | Where-Object { (Norm $_.Text) -eq 'SAIR' -and $_.Parent -eq $f.H } | Select-Object -First 1
    AtaProv    = $todos | Where-Object { (Norm $_.Text) -eq 'ATA PROVISORIA' } | Select-Object -First 1
    ExcluirTodas = $todos | Where-Object { (Norm $_.Text) -eq 'EXCLUIR TODAS' } | Select-Object -First 1
    GradeItem  = $todos | Where-Object { $_.Cls -like '*SPR32*' -and $_.Parent -eq $inserir.Parent } | Select-Object -First 1
    GradeDet   = $todos | Where-Object { $_.Cls -like '*SPR32*' -and $_.Parent -eq $frameDet.H } | Select-Object -First 1
  }
}
function SGCI-ChecarPopup([string]$contexto) {
  $ps = Popups $script:sgciPid
  if ($ps.Count -gt 0) {
    $t = Texto-Popup $ps[0]
    Responder-Popup $ps[0] @('OK')
    Fail "SGCI mostrou a mensagem ($contexto): $t"
  }
}
# espera a tela voltar ao normal depois de um popup rapido (Ata Provisoria  impressora)
function SGCI-JanelasAgora { @([U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Cls -notlike '*tooltips*' } | ForEach-Object { $_.H }) }
# $antes = janelas do SGCI que ja existiam antes do clique; espera as novas sumirem
function SGCI-EsperarPopupRapido([WinInfo]$form, $antes) {
  Pausa 700
  $limpo = {
    $novas = @(SGCI-JanelasAgora | Where-Object { $antes -notcontains $_ })
    if ($novas.Count -eq 0 -and [U]::IsWindowEnabled($form.H)) { return $true }
    return $null
  }
  if (-not (Esperar $limpo 90 400)) { Fail 'O popup de impressão do SGCI não fechou.' }
  Pausa 1200
  if (-not (Esperar $limpo 30 300)) { Fail 'O popup de impressão do SGCI não fechou.' }
}

# Parte 4 abre Nova Medicao e seleciona a OR
# janela Selecione (filtro do Nova Medicao) que ficou aberta de antes fica na frente da Medicao Quantificada
# e o script achava que o SGCI nao vinha para a frente - fecha com Cancelar
function SGCI-FecharSelecione {
  foreach ($s in @([U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Vis -and $_.Text.Trim() -eq 'Selecione' })) {
    Log '   SGCI: a janela Selecione estava aberta de antes - fechando (Cancelar)'
    $can = Filhos $s.H | Where-Object { $_.Vis -and (Norm $_.Text) -eq 'CANCELAR' } | Select-Object -First 1
    if ($can) { [void][U]::Activate($s.H); Clicar $can } else { [void][U]::PostMessage($s.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
    [void](Esperar { if (-not ([U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Vis -and $_.Text.Trim() -eq 'Selecione' })) { $true } } 5)
  }
}
function SGCI-AbrirOR($dados) {
  SGCI-FecharSelecione
  for ($tent = 1; $tent -le $TENTATIVAS_DIRETORIA; $tent++) {
    Ativar $script:sgciRaiz 'SGCI'
    $c = SGCI-Ctl
    Clicar $c.NovaMed
    $sel = Esperar { SGCI-Janela 'Selecione' } 15
    if (-not $sel) { SGCI-ChecarPopup 'Nova Medição'; Fail "A janela 'Selecione' não abriu." }
    Pausa 500
    $selKids = Visiveis $sel.H
    $combo = $selKids | Where-Object { $_.Cls -like '*ComboBox*' } | Select-Object -First 1
    $caixa = $selKids | Where-Object { $_.Cls -like '*TextBox*' } | Select-Object -First 1
    $filtrar = $selKids | Where-Object { (Norm $_.Text) -eq 'FILTRAR' } | Select-Object -First 1
    $grade = $selKids | Where-Object { $_.Cls -like '*SPR32*' } | Sort-Object { $_.W * $_.Hg } -Descending | Select-Object -First 1
    if (-not $combo -or -not $caixa -or -not $filtrar -or -not $grade) { Fail "Controles da janela 'Selecione' não encontrados." }
    Clicar $combo
    Teclas '{DOWN}' $script:sgciRaiz 'SGCI'; Teclas '{ENTER}' $script:sgciRaiz 'SGCI'
    Pausa 300
    if ((Norm (Texto $combo.H)) -ne 'SERVICO') { Fail "Filtrar por ficou '$(Texto $combo.H)' (esperado 'Serviço')." }
    Clicar $caixa
    Teclas '{HOME}+{END}' $script:sgciRaiz 'SGCI'
    Digitar $dados.OR $script:sgciRaiz 'SGCI'
    if ((Texto $caixa.H) -ne $dados.OR) { Fail "Caixa do filtro ficou '$(Texto $caixa.H)' (esperado OR $($dados.OR))." }
    Clicar $filtrar
    Log "   SGCI: filtrando OR $($dados.OR)"
    $ini = Get-Date
    $linha = Esperar {
      SGCI-ChecarPopup 'Filtrar'
      $o = Get-Ocr $grade.H 3 -Tela
      $w = Linha-Com $o $dados.OR
      if ($w) { return [pscustomobject]@{ W = $w; Txt = (Linha-Texto $o $w) } }
      if (((Get-Date) - $ini).TotalSeconds -gt 7) {
        $t = (Get-Ocr $sel.H 2 -Tela).Text
        if ((Total-Registros $t) -eq 0) { Fail 'OR não encontrada no SGCI. Por favor verifique.' }
      }
      return $null
    } $TIMEOUT_FILTRO 800
    if (-not $linha) { Fail 'OR não encontrada no SGCI. Por favor verifique.' }
    Log "   SGCI: linha encontrada: $($linha.Txt)"
    # coluna Medicao preenchida = OR ja medida
    $toks = @($linha.Txt -split '\s+')
    $idx = -1; for ($i = 0; $i -lt $toks.Count; $i++) { if ((Digitos $toks[$i]) -eq $dados.OR) { $idx = $i; break } }
    if ($idx -ge 0) {
      for ($i = $idx + 1; $i -lt $toks.Count; $i++) { if ($toks[$i] -match '^\d{3,}$') { Fail "A OR $($dados.OR) já possui medição ($($toks[$i])) no SGCI. Verifique." } }
    }
    Clicar-Ponto $grade.H ($linha.W.X + [int]($linha.W.W / 2)) ($linha.W.Y + [int]($linha.W.H / 2)) -Duplo
    $ok = Esperar { if (-not (SGCI-Janela 'Selecione') -and (Texto $c.Servico.H) -eq $dados.OR) { $true } } 15
    if (-not $ok) { SGCI-ChecarPopup 'seleção da OR'; Fail "Após selecionar, o campo Serviço não ficou igual à OR $($dados.OR)." }
    Pausa 500
    $ata = Texto $c.Ata.H
    if ($dados.ATA -and $ata -ne $dados.ATA) { Fail "Ata divergente: SGCI = '$ata', planilha = '$($dados.ATA)'." }
    $dir = Texto $c.Diretoria.H
    if ($dir) { Log "   SGCI: OR carregada (Ata $ata, Diretoria $dir)"; return }
    Log "   SGCI: Diretoria vazia (tentativa $tent de $TENTATIVAS_DIRETORIA) - refazendo Nova Medição"
  }
  Fail "A Diretoria continua vazia após $TENTATIVAS_DIRETORIA tentativas."
}

# Parte 5 digita os servicos
function SGCI-DigitarServicos($dados) {
  $c = SGCI-Ctl
  $udEdit = Filhos $c.UD.H | Where-Object { $_.Cls -eq 'Edit' } | Select-Object -First 1
  if (-not $udEdit) { $udEdit = $c.UD }
  $g = [U]::Info($c.GradeItem.H)
  $f = $g.W / 623.0      # proporcao da grade (623 px a 100%)
  $yLinha = [int](28 * $f)
  foreach ($s in $dados.Servicos) {
    $lerDesc = { SGCI-ChecarPopup "Código da UD $($s.Codigo)"; $d = Texto $c.UDDesc.H; if ($d) { $d } }
    # digita o código, aperta ENTER e ESPERA a descrição aparecer (o SGCI pode demorar bastante).
    # nao mexe em nada enquanto espera; so tenta de novo se passar do tempo
    $desc = $null
    for ($tent = 1; $tent -le 2 -and -not $desc; $tent++) {
      Ativar $script:sgciRaiz 'SGCI'
      Clicar $udEdit
      if ($tent -eq 2) {
        # limpa de vez (o SGCI pode ignorar quando o codigo digitado e igual ao que ja estava)
        Teclas '{HOME}+{END}{DEL}' $script:sgciRaiz 'SGCI'; Teclas '{ENTER}' $script:sgciRaiz 'SGCI'; Pausa 1500
        Clicar $udEdit
      }
      Teclas '{HOME}+{END}{DEL}' $script:sgciRaiz 'SGCI'
      Pausa 200
      # digita o código, espera 0,3 s e dá ENTER (sem mexer em mais nada no meio)
      Garantir-Frente $script:sgciRaiz 'SGCI'
      [Windows.Forms.SendKeys]::SendWait((EscSK $s.Codigo))
      Start-Sleep -Milliseconds 300
      $lido = Texto $udEdit.H
      if ($lido -and $lido -ne $s.Codigo) { Log "   SGCI: Código da UD ficou '$lido' (esperado $($s.Codigo)) - tentativa $tent"; continue }
      # ENTER solto (como tecla fisica) nao espera o SGCI terminar a busca, para a contagem dos 5 s valer de verdade
      Tecla-Solta 0x0D
      $ini = Get-Date; $como = 'Enter'
      $desc = Esperar $lerDesc 5 300
      if (-not $desc) {
        # o SGCI as vezes so busca a descrição quando PERDE O FOCO faz o equivalente ao Ctrl+Alt+Del + Esc
        $como = 'Ctrl+Alt+Del (troca de tela)'
        Destravar-Foco $script:sgciRaiz
        $desc = Esperar $lerDesc 3 300
      }
      if (-not $desc) {
        $como = 'troca de foco pela barra de tarefas'
        Desfocar-E-Voltar $script:sgciRaiz
        $desc = Esperar $lerDesc 3 300
      }
      if (-not $desc) { $como = 'espera longa'; $desc = Esperar $lerDesc ($TIMEOUT_DESC_UD - 11) 500 }
      if ($desc) { Log ("   SGCI: descrição da UD {0} apareceu em {1:0} s (com {2})" -f $s.Codigo, ((Get-Date) - $ini).TotalSeconds, $como) }
      else { Log "   SGCI: descrição da UD $($s.Codigo) não apareceu em $TIMEOUT_DESC_UD s (tentativa $tent)" }
    }
    if (-not $desc) { Fail "Código da UD [$($s.Codigo)] inválido ou divergente. Por favor verifique." }
    # o SGCI abrevia descricoes (ex pre-conect x PRE-CONECTORIZADA), entao confere as 2 primeiras palavras
    $a = @((Norm $desc) -split '[^A-Z0-9]+' | Where-Object { $_ })
    $b = @((Norm $s.Desc) -split '[^A-Z0-9]+' | Where-Object { $_ })
    $confere = $a.Count -ge 2 -and $b.Count -ge 2
    for ($k = 0; $k -lt 2 -and $confere; $k++) {
      $n = [Math]::Min(5, [Math]::Min($a[$k].Length, $b[$k].Length))
      if ($a[$k].Substring(0, $n) -ne $b[$k].Substring(0, $n)) { $confere = $false }
    }
    if (-not $confere) { Fail "Código da UD [$($s.Codigo)] divergente: SGCI = '$desc' / planilha = '$($s.Desc)'." }
    Log "   SGCI: UD $($s.Codigo) = '$desc'"
    Pausa 300
    $qtd = $s.Qtd.ToString('0.######', $PTBR)
    Clicar $c.GradeItem ([int](85 * $f)) $yLinha;  Digitar $s.Ref1 $script:sgciRaiz 'SGCI'
    Clicar $c.GradeItem ([int](205 * $f)) $yLinha; Digitar $s.Ref2 $script:sgciRaiz 'SGCI'
    Clicar $c.GradeItem ([int](538 * $f)) $yLinha; Digitar $qtd $script:sgciRaiz 'SGCI'
    Pausa 200
    Clicar $c.Inserir
    $ok = Esperar { SGCI-ChecarPopup "Inserir $($s.Codigo)"; if (-not (Texto $c.UDDesc.H)) { $true } } 10
    if (-not $ok) { Fail "O serviço $($s.Codigo) não foi inserido (a tela não limpou após Inserir)." }
    Log "   SGCI: inserido $($s.Codigo) / $($s.Ref1) / $($s.Ref2) / qtd $qtd"
  }
}

# Parte 6 conferencia no Detalhe - Medicao
function SGCI-Conferir($dados) {
  $c = SGCI-Ctl
  Ativar $script:sgciRaiz 'SGCI'
  $g = [U]::Info($c.GradeDet.H)
  Clicar $c.GradeDet ([int]($g.W * 0.4)) ([int](28 * $g.W / 721.0))
  $det = Esperar { SGCI-Janela 'Detalhe - Medição' } 15
  if (-not $det) { SGCI-ChecarPopup 'abrir Detalhe'; Fail "A janela 'Detalhe - Medição' não abriu." }
  Pausa 800
  Ativar $det.H 'Detalhe - Medição'
  [U]::MoveMouse($det.L + 20, $det.T + 10)
  $kids = Visiveis $det.H
  $resultado = [pscustomobject]@{ Ok = $true; Motivo = ''; Valor = $null; Pontos = $null }

  # 1) copia para area de transferencia (lista completa)
  $copiar = $kids | Where-Object { (Norm $_.Text) -like '*COPIAR PARA*' } | Select-Object -First 1
  if (-not $copiar) { Fail "Botão 'Copiar para área de transferência' não encontrado." }
  try { Set-Clipboard -Value ' ' } catch {}
  Clicar $copiar
  # o SGCI mostra o aviso Copiado para área de transferência ! - OK
  $aviso = Esperar { $x = Popups $script:sgciPid; if ($x.Count -gt 0) { $x[0] } } 8
  if ($aviso) {
    $t = Texto-Popup $aviso
    Responder-Popup $aviso @('OK')
    if ((Norm $t) -notmatch 'COPIADO') { Fail "SGCI mostrou a mensagem ao copiar: $t" }
    [void](Esperar { if ((Popups $script:sgciPid).Count -eq 0) { $true } } 5)
  }
  $clip = ''
  for ($k = 0; $k -lt 5 -and $clip.Trim().Length -lt 10; $k++) { try { $clip = [string](Get-Clipboard -Raw) } catch { $clip = '' }; if ($clip.Trim().Length -lt 10) { Pausa 500 } }
  Add-Content -Path $ARQ_LOG -Value ("----- área de transferência (Detalhe - Medição) -----`r`n" + $clip + "`r`n-----") -Encoding UTF8
  if ($clip.Trim().Length -lt 10) { Fail 'A cópia do Detalhe - Medição veio vazia.' }

  # confere linha a linha Serviço  Referência 1  Referência 2  Qtde
  $linhas = @($clip -split "`r?`n" | Where-Object { $_.Trim() })
  $cab = @($linhas[0] -split "`t" | ForEach-Object { Norm $_ })
  $iServ = [array]::IndexOf($cab, 'SERVICO'); $iR1 = [array]::IndexOf($cab, 'REFERENCIA 1'); $iR2 = [array]::IndexOf($cab, 'REFERENCIA 2')
  $iQtd = -1; for ($k = 0; $k -lt $cab.Count; $k++) { if ($cab[$k] -like '*QTDE*') { $iQtd = $k } }
  if ($iServ -lt 0 -or $iR1 -lt 0 -or $iR2 -lt 0 -or $iQtd -lt 0) { Fail "Formato da cópia do Detalhe não reconhecido: $($linhas[0])" }
  $regs = @($linhas | Select-Object -Skip 1 | ForEach-Object { $p = $_ -split "`t"; [pscustomobject]@{ Cod = $p[$iServ].Trim(); R1 = $p[$iR1].Trim(); R2 = $p[$iR2].Trim(); Qtd = $p[$iQtd].Trim() } } | Where-Object { $_.Cod -match '^\d+$' })
  if ($regs.Count -ne $dados.Servicos.Count) { $resultado.Ok = $false; $resultado.Motivo += "SGCI tem $($regs.Count) serviços, planilha tem $($dados.Servicos.Count); " }
  # o mesmo serviço pode aparecer mais de uma vez (ex com Ref.2 diferente) cada linha da planilha
  # precisa achar UMA linha do SGCI ainda nao usada com mesmo código + Ref.1 + Ref.2 + quantidade
  $usadas = New-Object System.Collections.Generic.HashSet[int]
  foreach ($s in $dados.Servicos) {
    $achou = -1
    for ($i = 0; $i -lt $regs.Count -and $achou -lt 0; $i++) {
      if ($usadas.Contains($i)) { continue }
      $r = $regs[$i]; $q = [decimal]0
      if ($r.Cod -eq $s.Codigo -and (Norm $r.R1) -eq (Norm $s.Ref1) -and (Norm $r.R2) -eq (Norm $s.Ref2) -and
          [decimal]::TryParse($r.Qtd, [Globalization.NumberStyles]::Any, $PTBR, [ref]$q) -and $q -eq $s.Qtd) { $achou = $i }
    }
    if ($achou -ge 0) { [void]$usadas.Add($achou) }
    else { $resultado.Ok = $false; $resultado.Motivo += "linha $($s.Linha) da planilha ($($s.Codigo) / $($s.Ref1) / $($s.Ref2) / qtd $($s.Qtd)) não está no SGCI; " }
  }
  Ativar $det.H 'Detalhe - Medição'
  $kids = Visiveis $det.H

  # 2) Total da Medicao (Pontos  Valor) via OCR
  $frameTot = Filhos $det.H | Where-Object { $_.Cls -like '*Frame*' -and (Norm $_.Text) -eq 'TOTAL DA MEDICAO' } | Select-Object -First 1
  if (-not $frameTot) { Fail "Quadro 'Total da Medição' não encontrado." }
  # le Pontos e Valor pelo rotulo o numero e a 1a linha numerica depois de Pontos  Valor.
  # o OCR costuma perder a virgula (1.225,2303 - 1.2252303, 3,430 - 3430), entao sem virgula
  # usa as casas fixas do SGCI (Valor 4, Pontos 3). Se a leitura bate com a planilha aceita na hora;
  # senao tenta todas as ampliacoes e fica com a leitura que mais se repetiu.
  $lerNum = {
    param($linhas, [string]$rotulo, [int]$casas)
    for ($i = 0; $i -lt $linhas.Count; $i++) {
      if ((Norm $linhas[$i]) -ne $rotulo) { continue }
      for ($j = $i + 1; $j -lt $linhas.Count; $j++) {
        $s = ([string]$linhas[$j]) -creplace '[oOQD]', '0' -creplace '[lI!]', '1' -creplace '[zZ]', '2' -creplace '[sS]', '5' -replace '\s', ''
        if ($s -notmatch '^[\d.,]*\d[\d.,]*$') { continue }
        if ($s -match '^[\d.]+,\d+$') { return [decimal]::Parse($s, $PTBR) }
        return [decimal]($s -replace '\D', '') / [decimal][Math]::Pow(10, $casas)
      }
    }
    return $null
  }
  $leVal = @(); $lePts = @(); $t = ''
  foreach ($tent in @(@(2, 0), @(3, 0), @(3, 20), @(4, 20), @(5, 30), @(6, 30), @(2, 20))) {
    $o = Get-Ocr $frameTot.H $tent[0] -Tela -Margem $tent[1]; $t = $o.Text
    $v = & $lerNum @($o.Lines) 'VALOR' 4
    $p = & $lerNum @($o.Lines) 'PONTOS' 3
    if ($null -ne $v) { $leVal += $v }
    if ($null -ne $p) { $lePts += $p }
    if ($null -ne $v -and [Math]::Abs($v - $dados.SomaValor) -le 0.0001 -and ($null -eq $p -or [Math]::Abs($p - $dados.SomaPontos) -le 0.001)) { break }
    Pausa 300
  }
  $maisLido = { param($xs) ($xs | Group-Object | Sort-Object Count -Descending | Select-Object -First 1).Values[0] }
  $okV = @($leVal | Where-Object { [Math]::Abs($_ - $dados.SomaValor) -le 0.0001 })
  $okP = @($lePts | Where-Object { [Math]::Abs($_ - $dados.SomaPontos) -le 0.001 })
  if ($okV.Count) { $resultado.Valor = $okV[0] } elseif ($leVal.Count) { $resultado.Valor = [decimal](& $maisLido $leVal) }
  if ($okP.Count) { $resultado.Pontos = $okP[0] } elseif ($lePts.Count) { $resultado.Pontos = [decimal](& $maisLido $lePts) }
  Log "   SGCI: Total da Medição (OCR): pontos $($resultado.Pontos) / valor $($resultado.Valor)"
  if ($null -eq $resultado.Valor) { Fail "Não consegui ler o Valor do Total da Medição (OCR): '$($t -replace '\s+', ' ')'. Confira o valor manualmente." }
  if ($null -eq $resultado.Pontos) { Log "   ATENÇÃO: não consegui ler os Pontos do Total da Medição - conferindo só o Valor" }
  if ([Math]::Abs($resultado.Valor - $dados.SomaValor) -gt 0.0001) { $resultado.Ok = $false; $resultado.Motivo += "valor SGCI $($resultado.Valor) x planilha $($dados.SomaValor); " }
  if ($null -ne $resultado.Pontos -and [Math]::Abs($resultado.Pontos - $dados.SomaPontos) -gt 0.001) { $resultado.Ok = $false; $resultado.Motivo += "pontos SGCI $($resultado.Pontos) x planilha $($dados.SomaPontos); " }

  # fecha o Detalhe
  $sair = $kids | Where-Object { (Norm $_.Text) -eq 'SAIR' } | Select-Object -First 1
  if (-not $sair) { Fail "Botão Sair do 'Detalhe - Medição' não encontrado." }
  Clicar $sair
  $ok = Esperar { if (-not (SGCI-Janela 'Detalhe - Medição')) { $true } } 10
  if (-not $ok) { Fail "A janela 'Detalhe - Medição' não fechou." }
  return $resultado
}
function SGCI-ExcluirTodas {
  $c = SGCI-Ctl
  Ativar $script:sgciRaiz 'SGCI'
  Clicar $c.ExcluirTodas
  $p = Esperar { $x = Popups $script:sgciPid; if ($x.Count -gt 0) { $x[0] } } 10
  if (-not $p) { Fail 'A confirmação de Excluir Todas não apareceu.' }
  $t = Texto-Popup $p
  if ((Norm $t) -notmatch 'EXCLUIRA TODOS') { Responder-Popup $p @('Não', 'Nao', 'OK'); Fail "Mensagem inesperada ao Excluir Todas: $t" }
  Responder-Popup $p @('Sim', '&Sim')
  Pausa 1500
  SGCI-ChecarPopup 'Excluir Todas'
}

# Parte 7 encaminhar + impressoes
function SGCI-Encaminhar($dados) {
  $c = SGCI-Ctl
  Ativar $script:sgciRaiz 'SGCI'
  if (-not $c.Encaminhar.En) { Fail 'O botão Encaminhar está desabilitado.' }
  Clicar $c.Encaminhar
  $p = Esperar { $x = Popups $script:sgciPid; if ($x.Count -gt 0) { $x[0] } } 30
  if (-not $p) { Fail 'O SGCI não confirmou o encaminhamento.' }
  $t = Texto-Popup $p
  Responder-Popup $p @('OK')
  if ((Norm $t) -notmatch 'SUCESSO') { Fail "SGCI ao encaminhar: $t" }
  $num = Esperar { $n = Texto $c.NumMedicao.H; if ($n -match '^\d+$') { $n } } 10
  if (-not $num) { Fail 'Nº da Medição não apareceu após encaminhar.' }
  Log "   SGCI: ENCAMINHADO - Nº da Medição $num"
  Add-Content -Path $ARQ_MEDICOES -Encoding UTF8 -Value @(
    '==============================',
    "Data/Hora : $(Get-Date -Format 'dd/MM/yyyy HH:mm')",
    "SGM        : $($dados.SGM)",
    "OR         : $($dados.OR)",
    "Nº Medição : $num",
    "Valor      : $($dados.SomaValor.ToString('0.0000', $PTBR))",
    '==============================')

  if ($SEM_IMPRESSAO) { Log '   SGCI: (sem impressão) Ata Provisória e impressão da medição puladas'; return $num }
  $c = SGCI-Ctl
  $ok = Esperar { if ([U]::IsWindowEnabled($c.AtaProv.H)) { $true } } 10
  if (-not $ok) { Fail 'O botão Ata Provisória não habilitou.' }
  $antes = SGCI-JanelasAgora
  Clicar $c.AtaProv
  SGCI-EsperarPopupRapido $c.Form $antes
  Log '   SGCI: Ata Provisória impressa'
  if (-not $c.Impressora) { Fail 'Botão da impressora (ao lado de Nova Medição) não encontrado.' }
  Ativar $script:sgciRaiz 'SGCI'
  $antes = SGCI-JanelasAgora
  Clicar $c.Impressora
  SGCI-EsperarPopupRapido $c.Form $antes
  Log '   SGCI: impressão da medição concluída'
  return $num
}

# =====================================================================
#  SGM - partes finais
# =====================================================================
function SGM-AtualizarRascunho($dados, [string]$sgm, [string]$num) {
  $vis = [U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Text -eq 'Visualizar' }
  foreach ($v in $vis) { [void][U]::PostMessage($v.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero); Pausa 800 }
  $filha = SGM-AtivarFilha 'Rascunho de Medição'
  $c = SGM-ControlesConsulta $filha
  if (-not $c.Grade) { Fail 'Rascunho de Medição não está na aba Consulta.' }
  $o = Get-Ocr $c.Grade.H 2
  $l = Linha-Com $o $sgm
  if (-not $l) { $pesq = SGM-Pesquisar $filha 'Cód. Obra' $sgm 'SGM divergente ou errado. Por favor verifique.' }
  else { $pesq = [pscustomobject]@{ Linha = $l; Ctl = $c } }
  $ocr = SGM-AbrirCadastro $filha $pesq 'Documento'

  $codigo = Campo-Abaixo $filha.H (Rotulo $ocr 'Código')
  if ($codigo -and $dados.Rascunho -and (Digitos (Texto $codigo.H)) -ne (Digitos $dados.Rascunho)) {
    Fail "Rascunho aberto ($(Texto $codigo.H)) diferente do esperado ($($dados.Rascunho))."
  }
  $rDoc = Rotulo $ocr 'Documento'
  $doc = Campo-Abaixo $filha.H $rDoc
  $rNum = $ocr.Words | Where-Object { (Norm $_.Text) -eq 'NUMERO' -and [Math]::Abs($_.Y - $rDoc.Y) -le 8 -and $_.X -gt $rDoc.X } | Sort-Object X | Select-Object -First 1
  if ($rNum) { $rNum = [pscustomobject]@{ X = $rNum.X; Y = $rNum.Y; R = $rNum.X + $rNum.W; B = $rNum.Y + $rNum.H } }
  $numero = Campo-Abaixo $filha.H $rNum
  $sit = Campo-Abaixo $filha.H (Rotulo $ocr 'Situação Medição Cliente' 'Alteração')
  if (-not $doc -or -not $numero -or -not $sit) { Fail 'Campos Documento / Número / Situação Medição Cliente não encontrados no SGM.' }

  Escrever-Campo $doc 'MQ' $script:sgmMain 'SGM'
  Escrever-Campo $numero $num $script:sgmMain 'SGM'
  $ok = $false
  for ($t = 0; $t -lt 2 -and -not $ok; $t++) {
    Escrever-Campo $sit 'AGU' $script:sgmMain 'SGM'
    Teclas '{TAB}' $script:sgmMain 'SGM'; Pausa 1200
    $descSit = Campo-Direita $filha.H ([U]::Info($sit.H))
    if ((Texto $sit.H) -eq 'AGU' -and $descSit -and (Norm (Texto $descSit.H)) -like '*AGUARDANDO*') { $ok = $true }
  }
  # o MQ as vezes some depois de preencher os outros campos digita de novo
  for ($t = 0; $t -lt 2 -and (Texto $doc.H) -ne 'MQ'; $t++) {
    Log "   SGM: Documento ficou '$(Texto $doc.H)' - digitando MQ de novo"
    Escrever-Campo $doc 'MQ' $script:sgmMain 'SGM'
    Teclas '{TAB}' $script:sgmMain 'SGM'; Pausa 800
  }
  if ((Texto $doc.H) -ne 'MQ') { Fail "Documento ficou '$(Texto $doc.H)' (esperado MQ)." }
  if ((Digitos (Texto $numero.H)) -ne $num) { Fail "Número ficou '$(Texto $numero.H)' (esperado $num)." }
  if (-not $ok) { Fail 'Situação Medição Cliente não ficou AGU / AGUARDANDO APROVAÇÃO MEDIÇÃO.' }
  Confirmar "Rascunho (MQ / $num / AGU)`n`nSalvar?"
  SGM-Salvar $filha
  # o Deseja realmente Fechar este Rascunho  ...Fechado com sucesso pode vir depois do salvar
  $volta = Esperar {
    foreach ($p in @(Popups $script:sgmPid)) {
      $t = Texto-Popup $p; $nt = Norm $t
      if ($nt -match 'DESEJA REALMENTE FECHAR ESTE RASCUNHO') { Log "   SGM popup: $t"; Responder-Popup $p @('&Sim', 'Sim'); Pausa 500 }
      elseif ($nt -match 'FECHADO COM SUCESSO|VALOR PREVISTO') { Log "   SGM popup: $t"; Responder-Popup $p @('OK'); Pausa 500 }
    }
    $cc = SGM-ControlesConsulta (SGM-Filha 'Rascunho de Medição'); if ($cc.Campo) { $true }
  } 40
  if (-not $volta) { Fail 'O Rascunho de Medição não voltou para a aba Consulta após salvar.' }
  # a pergunta de fechar o rascunho aparece por cima da Consulta so segue quando nao houver mais aviso por 2 s
  $fimAv = (Get-Date).AddSeconds(15); $semAv = Get-Date
  while ((Get-Date) -lt $fimAv -and ((Get-Date) - $semAv).TotalSeconds -lt 2) {
    $ps = @(Popups $script:sgmPid)
    if ($ps.Count) {
      $t = Texto-Popup $ps[0]; $nt = Norm $t; Log "   SGM popup: $t"
      if ($nt -match 'DESEJA REALMENTE FECHAR ESTE RASCUNHO') { Responder-Popup $ps[0] @('&Sim', 'Sim') }
      elseif ($nt -match 'FECHADO COM SUCESSO|VALOR PREVISTO|SUCESSO') { Responder-Popup $ps[0] @('OK') }
      else { Fail "SGM mostrou a mensagem: $t" }
      Pausa 500; $semAv = Get-Date
    } else { Pausa 300 }
  }
  Log "   SGM: rascunho atualizado (MQ / $num / AGU)"
}

function SGM-AbrirVisaoMedicao { return (SGM-AbrirPeloMenu 'Visão Medição') }

# Medicao (barra de menu)  item; espera a tela abrir e maximiza
function SGM-AbrirPeloMenu([string]$titulo) {
  $itemMenu = $SGM_MENU[$titulo][0]; $setas = $SGM_MENU[$titulo][1]
  Ativar $script:sgmMain 'SGM'
  $menu = [U]::GetMenu($script:sgmMain)
  $enviado = $false
  if ($menu -ne [IntPtr]::Zero) {
    for ($i = 0; $i -lt [U]::GetMenuItemCount($menu) -and -not $enviado; $i++) {
      if ((Norm ([U]::MenuText($menu, $i))) -eq 'MEDICAO') {
        $sub = [U]::GetSubMenu($menu, $i)
        for ($j = 0; $j -lt [U]::GetMenuItemCount($sub); $j++) {
          if ((Norm ([U]::MenuText($sub, $j))) -like $itemMenu) {
            $id = [U]::GetMenuItemID($sub, $j)
            [void][U]::PostMessage($script:sgmMain, 0x0111, [IntPtr][int]$id, [IntPtr]::Zero)
            $enviado = $true; break
          }
        }
      }
    }
  }
  if (-not $enviado) {
    # menu desenhado pelo SGM clica em Medição na barra de menu (achado por OCR) e depois no item
    # 1a tentativa igual a antes (janela inteira); depois le so a faixa do menu (acima da area das telas),
    # com margem e ampliacoes diferentes - em outras resolucoes o OCR da janela inteira quebra a linha do menu
    $barra = $null; $diag = @()
    $mi = [U]::Info($script:sgmMain); $mdi = SGM-MdiClient
    $faixa = if ($mdi) { [Math]::Max(30, $mdi.T - $mi.T + 2) } else { 70 }
    $tents = @(@(2, $true, $false), @(2, $true, $true), @(3, $true, $true), @(4, $true, $true), @(3, $false, $true), @(2, $false, $true))
    foreach ($tt in $tents) {
      if ($tt[2]) { $ocr = Get-Ocr $script:sgmMain $tt[0] -Tela:$tt[1] -Margem 10 -Recorte @(0, 0, $mi.W, $faixa) }
      else { $ocr = Get-Ocr $script:sgmMain $tt[0] -Tela:$tt[1] }
      $cands = @($ocr.Words | Where-Object { (Norm $_.Text) -eq 'MEDICAO' })
      $barra = $cands | Where-Object { (Norm $_.LineText) -match 'PROTOCOLOS|CADASTRO|RELATORIOS|OPERACOES|MOVIMENTACOES|JANELAS' } | Select-Object -First 1
      # na faixa do menu a palavra mais de baixo (a de cima pode ser o titulo ... Rascunho de Medição])
      if (-not $barra -and $tt[2]) { $barra = $cands | Where-Object { $_.Y -gt ($mi.T + 12) } | Sort-Object Y -Descending | Select-Object -First 1 }
      if ($barra) { break }
      $diag += "escala $($tt[0]) tela=$($tt[1]) faixa=$($tt[2]): " + ((@($ocr.Lines) | Select-Object -First 4) -join ' | ')
      Pausa 400
    }
    if (-not $barra) {
      Add-Content -Path $ARQ_LOG -Encoding UTF8 -Value (@('----- OCR da barra de menu do SGM -----') + $diag + '-----')
      [void](Salvar-UltimaCaptura 'menu')
      Fail "Menu 'Medição' não encontrado na barra do SGM."
    }
    Clicar-Ponto $script:sgmMain ($barra.X + [int]($barra.W / 2)) ($barra.Y + [int]($barra.H / 2))
    $pop = Esperar { [U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Cls -eq '#32768' } | Select-Object -First 1 } 5
    $clicou = $false
    if ($pop) {
      Pausa 300
      $om = Get-Ocr $pop.H 2 -Tela
      $item = $om.Words | Where-Object { (Norm $_.LineText) -like $itemMenu } | Select-Object -First 1
      if ($item) { [U]::Click($item.X + [int]($item.W / 2), $item.Y + [int]($item.H / 2), $false); $clicou = $true }
    }
    if (-not $clicou) {
      # alternativa teclado (n setas ate o item)
      Log "   SGM: item '$titulo' não lido por OCR - usando $setas setas"
      [void](Salvar-UltimaCaptura 'item_menu')
      for ($i = 0; $i -lt $setas; $i++) { Teclas '{DOWN}' $script:sgmMain 'SGM' }
      Teclas '{ENTER}' $script:sgmMain 'SGM'
    }
  }
  # a tela pode abrir pequena (nao maximizada) espera ela existir e maximiza
  $ok = Esperar { SGM-Filha $titulo } 20
  if (-not $ok) { Fail "A tela '$titulo' não abriu." }
  Pausa 1000
  return (SGM-Maximizar $titulo)
}

function SGM-FecharVisaoMedicao {
  $f = SGM-Filha 'Visão Medição'
  if ($f) { [void][U]::PostMessage($f.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
  $ok = Esperar { if (-not (SGM-Filha 'Visão Medição')) { $true } } 10
  if (-not $ok) {
    $ps = Popups $script:sgmPid
    if ($ps.Count -gt 0) { $t = Texto-Popup $ps[0]; Fail "Ao fechar a Visão Medição o SGM perguntou: $t" }
    Fail 'Não consegui fechar a Visão Medição.'
  }
}
# (so na versao SEM IMPRESSAO) aba AsBuiltsInformações Adicionais se Sistema Cliente estiver 54, apaga.
# Devolve $true se apagou (ai precisa salvar)
function SGM-LimparSistemaCliente([WinInfo]$filha) {
  # o texto das abas e pequeno lido so na faixa de cima de cada conjunto de abas (o OCR le AsBuitsÃnformações)
  $aba = $null
  $pcs = @(Visiveis $filha.H | Where-Object { $_.Cls -match 'PageControl|TabControl' -and $_.W -gt 300 } | Sort-Object T -Descending)
  foreach ($pc in $pcs) {
    foreach ($esc in 3, 2) {
      $o = Get-Ocr $pc.H $esc -Tela -Margem 10 -Recorte @(0, 0, $pc.W, 24)
      $aba = $o.Words | Where-Object { (Norm $_.Text) -like '*ASBU*' } | Select-Object -First 1
      if ($aba) { break }
    }
    if ($aba) { break }
  }
  if (-not $aba) { [void](Salvar-UltimaCaptura 'aba_asbuilts'); Fail "Aba 'AsBuilts/Informações Adicionais' não encontrada na Visão Medição." }
  Clicar-Ponto $filha.H ($aba.X + [int]($aba.W / 2)) ($aba.Y + [int]($aba.H / 2))
  Pausa 800
  $campo = $null
  [void](Esperar {
    $o2 = Get-Ocr $filha.H 2
    $script:rotSisCli = Rotulo $o2 'Sistema Cliente'
    if ($script:rotSisCli) { $script:campoSisCli = Campo-Abaixo $filha.H $script:rotSisCli; if ($script:campoSisCli) { $true } }
  } 8 500)
  $campo = $script:campoSisCli; $script:campoSisCli = $null
  if (-not $campo) { [void](Salvar-UltimaCaptura 'sistema_cliente'); Fail "Campo 'Sistema Cliente' (AsBuilts) não encontrado na Visão Medição." }
  $v = ([string](Texto $campo.H)).Trim()
  if ($v -ne '54') { if ($v) { Log "   SGM: Sistema Cliente (AsBuilts) = '$v' - mantido" }; return $false }
  Clicar $campo 8
  Teclas '{END}' $script:sgmMain 'SGM'; Teclas ('{BACKSPACE ' + ($v.Length + 2) + '}') $script:sgmMain 'SGM'
  if (([string](Texto $campo.H)).Trim()) { Teclas '{HOME}+{END}{DEL}' $script:sgmMain 'SGM' }
  Teclas '{TAB}' $script:sgmMain 'SGM'; Pausa 800
  $depois = ([string](Texto $campo.H)).Trim()
  if ($depois) { Fail "Sistema Cliente (AsBuilts) ficou '$depois' (esperado em branco)." }
  Log '   SGM: Sistema Cliente (AsBuilts) estava 54 - apagado'
  return $true
}
function SGM-Finalizar([string]$sgm, [string]$Etapa = '') {
  $filha = SGM-AbrirVisaoMedicao
  $pesq = SGM-Pesquisar $filha 'Código' $sgm "SGM [$sgm] não encontrado na Visão Medição. Por favor verifique."
  $ocr = SGM-AbrirCadastro $filha $pesq 'Situação da Medição'
  $cod = Campo-Abaixo $filha.H (Rotulo $ocr 'Código')
  if (-not $cod -or (Digitos (Texto $cod.H)) -ne $sgm) { Fail "Visão Medição abriu o código '$(if ($cod) { Texto $cod.H })' (esperado $sgm)." }
  $sit = Campo-Abaixo $filha.H (Rotulo $ocr 'Situação da Medição')
  if (-not $sit) { Fail "Campo 'Situação da Medição' não encontrado." }
  # o campo pode demorar a carregar (SGM lento) espera ele ter algum valor antes de decidir
  # (no outro PC leu vazio, digitou FSAAC por cima do FSAAC que ja estava e o SGM nao tinha o que salvar)
  $atual = Esperar { $x = ([string](Texto $sit.H)).Trim(); if ($x) { $x } } 10 500
  if (-not $atual) { $atual = '' }
  if ($atual -and $atual -ne 'FSAAC') { Log "   SGM: Situação da Medição atual = $atual" }
  # DEVPEND (devolvido com pendências) o SGM não aceita FSAAC direto -
  # CANC, salva, entra de novo - UNICA, salva, entra de novo - FSAAC
  $passo = $null
  if ((Norm $atual) -match '^DEV' -and $Etapa -eq '') { $passo = 'CANC' }
  elseif ($Etapa -eq 'CANC') { $passo = 'UNICA' }
  if ($passo) {
    Log "   SGM: Situação da Medição está $atual - passando para $passo (DEVPEND > CANC > UNICA > FSAAC)"
    $ok = $false
    for ($t = 0; $t -lt 2 -and -not $ok; $t++) {
      Escrever-Campo $sit $passo $script:sgmMain 'SGM'
      Teclas '{TAB}' $script:sgmMain 'SGM'; Pausa 1200
      $d = Campo-Direita $filha.H ([U]::Info($sit.H))
      if ((Texto $sit.H) -eq $passo -and $d -and (Texto $d.H).Trim()) { $ok = $true }
    }
    if (-not $ok) { Fail "Situação da Medição não ficou $passo (estava $atual)." }
    Log "   SGM: Situação da Medição = $passo ($(Texto $d.H))"
    Confirmar "Visão Medição ($passo, a caminho do FSAAC)`n`nSalvar?"
    SGM-Salvar $filha
    SGM-FecharVisaoMedicao
    return (SGM-Finalizar $sgm -Etapa $passo)
  }
  if ($atual -eq 'FSAAC') {
    Log '   SGM: Situação da Medição já estava FSAAC'
    if ($SEM_IMPRESSAO -and (SGM-LimparSistemaCliente $filha)) {
      Confirmar "Visão Medição (Sistema Cliente apagado)`n`nSalvar?"
      SGM-Salvar $filha
    }
  } else {
    $ok = $false
    for ($t = 0; $t -lt 2 -and -not $ok; $t++) {
      Escrever-Campo $sit 'FSAAC' $script:sgmMain 'SGM'
      Teclas '{TAB}' $script:sgmMain 'SGM'; Pausa 1200
      $d = Campo-Direita $filha.H ([U]::Info($sit.H))
      if ((Texto $sit.H) -eq 'FSAAC' -and $d -and (Norm (Texto $d.H)) -like '*FINALIZADA*') { $ok = $true }
    }
    if (-not $ok) { $era = ''; if ($atual) { $era = " (estava '$atual')" }; Fail "Situação da Medição não ficou FSAAC / FINALIZADA SGM / AG. APROV. CLIENTE$era." }
    # versao sem impressao antes de salvar o FSAAC, Sistema Cliente 54 (AsBuilts) fica em branco
    if ($SEM_IMPRESSAO) { [void](SGM-LimparSistemaCliente $filha) }
    Confirmar "Visão Medição (FSAAC)`n`nSalvar?"
    SGM-Salvar $filha
    Log '   SGM: Situação da Medição = FSAAC'
  }
  # fecha somente a janela interna Visao Medicao (X claro)
  SGM-FecharVisaoMedicao
}

# 12) volta ao Rascunho de Medicao (Medicao  Rascunho Medicao se nao estiver aberto), maximiza e pesquisa o SGM
function SGM-VoltarRascunho([string]$sgm) {
  $filha = SGM-AtivarFilha 'Rascunho de Medição'
  $pesq = SGM-Pesquisar $filha 'Cód. Obra' $sgm 'SGM divergente ou errado. Por favor verifique.'
  Log "   SGM: Rascunho de Medição pesquisado de novo ($sgm)"
  return $pesq
}

# 13) Imprimir  Enter, Enter (1a opcao Rascunho de Medição) - abre a tela Visualizar; confere a OR no relatorio
function SGM-AbrirRelatorioRascunho($pesq, [string]$or) {
  SGM-FecharVisualizar
  SGM-Imprimir $pesq.Ctl 0
  $vis = Esperar { [U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Text -eq 'Visualizar' } | Select-Object -First 1 } 40 700
  if (-not $vis) { Fail "O relatório 'Rascunho de Medição' (tela Visualizar) não abriu." }
  Pausa 1000
  if ($or) {
    $achou = Esperar {
      Ativar $vis.H 'Visualizar'
      $o = Get-Ocr $vis.H 3 -Tela
      $script:ultimoOcrRel = $o.Text
      if (Linha-Com $o $or) { $true }
    } 20 1500
    if (-not $achou) {
      Add-Content -Path $ARQ_LOG -Value ("----- OCR do relatório SGM -----`r`n" + $script:ultimoOcrRel + "`r`n-----") -Encoding UTF8
      Fail "O relatório aberto no SGM não mostra a OR $or."
    }
  }
  Log "   SGM: relatório Rascunho de Medição aberto (OR $or)"
  return $vis
}

# =====================================================================
#  MATERIAIS  (relatorio SGM - Controle de Material no SGCI - LMN)
# =====================================================================
$PASTA_TEMP = Join-Path $PASTA 'temp'
$MODELO_LMN = Join-Path ([Environment]::GetFolderPath('Desktop')) 'MODELO LMN.xls'

# le o relatorio Rascunho de Medição salvo como .fp3 (texto exato, sem OCR)
function Ler-Fp3([string]$arq) {
  $x = [IO.File]::ReadAllText($arq, [Text.Encoding]::UTF8)
  $or = ''; $m = [regex]::Match($x, '\bu="OR\s*(\d+)'); if ($m.Success) { $or = $m.Groups[1].Value }
  # m92 = CLASSECÓD. COMPL. (vem antes do código na mesma linha; ex 451272 - 184956-5 - lote 184956-5)
  $els = [regex]::Matches($x, '(m90|m92|m94|m100|m102) [^>]*?\bu="([^"]*)"')
  $compl = $null
  if ($els.Count -eq 0) { Fail 'Formato do relatório Rascunho de Medição não reconhecido (colunas Tipo/Código/QT).' }
  $tipo = ''; $atual = $null; $linhas = @()
  foreach ($e in $els) {
    $v = [Net.WebUtility]::HtmlDecode($e.Groups[2].Value).Trim()
    switch ($e.Groups[1].Value) {
      'm90'  { if ($v) { $tipo = $v } }   # celula mesclada vale para as linhas de baixo
      'm92'  { $compl = $v }
      'm94'  {
        if ($atual) { $linhas += $atual }
        # lote 00000 - 0000000 - sempre a parte depois do primeiro  - 
        $lote = ''; if ($compl -match '^\s*\S+\s+-\s+(\S.*?)\s*$') { $lote = $Matches[1] }
        $atual = [pscustomobject]@{ Tipo = $tipo; Codigo = $v; QtdTxt = ''; Qtd = $null; Desc = ''; Compl = $compl; Lote = $lote }
        $compl = $null
      }
      'm100' { if ($atual) { $atual.QtdTxt = $v } }
      'm102' { if ($atual) { $atual.Desc = $v } }
    }
  }
  if ($atual) { $linhas += $atual }
  foreach ($l in $linhas) {
    $q = [decimal]0
    if ([decimal]::TryParse($l.QtdTxt, [Globalization.NumberStyles]::Any, $PTBR, [ref]$q)) { $l.Qtd = $q }
  }
  [pscustomobject]@{ OR = $or; Linhas = $linhas }
}

# 13) Visualizar  disquete  Relatório Preparado  le materiais  fecha o Visualizar
function SGM-LerMateriais([string]$sgm, $pesq, [string]$or) {
  $vis = SGM-AbrirRelatorioRascunho $pesq ''
  New-Item -ItemType Directory -Force $PASTA_TEMP | Out-Null
  $arq = Join-Path $PASTA_TEMP "relatorio_$sgm.fp3"
  if (Test-Path $arq) { Remove-Item $arq -Force }
  Ativar $vis.H 'Visualizar'
  $tb = Visiveis $vis.H | Where-Object { $_.Cls -eq 'TToolBar' } | Select-Object -First 1
  if (-not $tb) { Fail 'Barra de botões do Visualizar não encontrada.' }
  Clicar-Ponto $tb.H ($tb.L + 60) $tb.CY        # 3o icone = disquete (Salvar)
  $pop = Esperar { [U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Cls -eq '#32768' } | Select-Object -First 1 } 5
  if (-not $pop) { Fail 'O menu do botão Salvar do Visualizar não abriu.' }
  Pausa 300
  $it = (Get-Ocr $pop.H 2 -Tela).Words | Where-Object { (Norm $_.LineText) -like '*PREPARADO*' } | Select-Object -First 1
  if (-not $it) { Teclas '{ESC}' $vis.H 'Visualizar'; Fail "Opção 'Relatório Preparado' não encontrada no menu Salvar." }
  [U]::Click($it.X + 5, $it.Y + [int]($it.H / 2), $false)
  $dlg = Esperar { [U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Cls -eq '#32770' -and $_.Text -like '*Salvar*' } | Select-Object -First 1 } 10
  if (-not $dlg) { Fail "A janela 'Salvar como' do relatório não abriu." }
  Pausa 500
  $ed = Visiveis $dlg.H | Where-Object { $_.Cls -eq 'Edit' } | Select-Object -First 1
  Clicar $ed
  Teclas '^a' $dlg.H 'Salvar como'; Digitar $arq $dlg.H 'Salvar como'
  if ((Texto $ed.H) -ne $arq) { Fail "Não consegui digitar o caminho do arquivo no 'Salvar como'." }
  Teclas '{ENTER}' $dlg.H 'Salvar como'
  $ok = Esperar { if ((Test-Path $arq) -and -not ([U]::Tops([uint32]$script:sgmPid) | Where-Object { $_.Cls -eq '#32770' })) { $true } } 20
  if (-not $ok) { Fail 'O relatório não foi salvo (Relatório Preparado).' }
  Pausa 800
  $rel = Ler-Fp3 $arq
  Remove-Item $arq -Force -ErrorAction SilentlyContinue
  SGM-FecharVisualizar
  if ($or -and $rel.OR -ne $or) { Fail "O relatório Rascunho de Medição é da OR $($rel.OR), esperado $or." }
  # so conhecemos 1 - SERV., 2 - MAT INST e 3 - MAT RET qualquer outro tipo para o processo
  $outros = @($rel.Linhas | Where-Object { $_.Tipo -notmatch '^\s*[123]\s*-' } | ForEach-Object { "'$($_.Tipo)' ($($_.Codigo))" } | Select-Object -Unique)
  if ($outros.Count) { Fail ("O relatório tem um tipo de linha que o script não conhece: " + ($outros -join ', ') + ". Faça esse SGM manualmente.") }
  # materiais com código começando em TEM não são digitados ignora só essa linha
  foreach ($x in @($rel.Linhas | Where-Object { $_.Tipo -match '^\s*[23]\b' -and $_.Codigo -match '^\s*TEM' })) {
    Log ("   SGM: material ignorado (código TEM): {0} | {1} | qtd {2} | {3}" -f $x.Tipo, $x.Codigo, $x.QtdTxt, $x.Desc)
  }
  $mats = @($rel.Linhas | Where-Object { $_.Tipo -match '^\s*[23]\b' -and $_.Codigo -notmatch '^\s*TEM' } | ForEach-Object {
    if ($null -eq $_.Qtd -or $_.Qtd -le 0) { Fail "Quantidade inválida no material $($_.Codigo): '$($_.QtdTxt)'." }
    # REAPRAZO codigo R0252-0032-1 + lote REAP132964 - no SGCI digita 0252-0032-1REAP (o R so identifica o reap)
    $reap = $false; $codigo = $_.Codigo
    $ehR = $codigo -match '^R(\d{4}-\d{4}-\d)$'; $ehLoteReap = ([string]$_.Lote) -match '^REAP'
    if ($ehR -or $ehLoteReap) {
      if (-not ($ehR -and $ehLoteReap)) { Fail "Material $codigo com lote '$($_.Lote)': parece reaprazo, mas falta o R no código ou o REAP no lote. Verifique manualmente." }
      $codigo = $_.Codigo.Substring(1) + 'REAP'; $reap = $true
    }
    elseif ($codigo -notmatch '^\d{4}-\d{4}-\d$') { Fail "Código de material com formato inesperado: '$codigo'." }
    # CÓD. COMPL. preenchido (diferente de -) mas fora do formato 00000 - 0000000 nao arrisca, para e avisa
    $cc = ([string]$_.Compl).Trim()
    if ($cc -and $cc -ne '-' -and -not $_.Lote) { Fail "Material $($_.Codigo): CÓD. COMPL. '$cc' em formato desconhecido (esperado '00000 - 0000000'). Verifique o lote manualmente." }
    $tp = 'RET'; if ($_.Tipo -match '^\s*2') { $tp = 'INST' }
    [pscustomobject]@{ Tipo = $tp; Codigo = $codigo; Qtd = $_.Qtd; Desc = $_.Desc; Lote = $_.Lote; Reap = $reap } })
  Log ("   SGM: relatório lido - OR {0}: {1} instalado(s) / {2} retirado(s)" -f $rel.OR, @($mats | Where-Object Tipo -eq 'INST').Count, @($mats | Where-Object Tipo -eq 'RET').Count)
  foreach ($m in $mats) { $lt = ''; if ($m.Lote) { $lt = " | LOTE $($m.Lote)" }; if ($m.Reap) { $lt += '  (REAPRAZO)' }; Log ("      {0} {1} | qtd {2} | {3}{4}" -f $m.Tipo, $m.Codigo, $m.Qtd.ToString('0.####', $PTBR), $m.Desc, $lt) }
  [pscustomobject]@{ OR = $rel.OR; Materiais = $mats }
}

# ---- SGCI menu nativo (Serviço  ...)
function SGCI-Menu([string[]]$caminho, [switch]$SemAtivar) {
  if (-not $SemAtivar) { Ativar $script:sgciMain 'SGCI' }
  $m = [U]::GetMenu($script:sgciMain)
  if ($m -eq [IntPtr]::Zero) { Fail 'Menu do SGCI não encontrado.' }
  for ($k = 0; $k -lt $caminho.Count; $k++) {
    $alvo = Norm $caminho[$k]; $pos = -1
    for ($i = 0; $i -lt [U]::GetMenuItemCount($m); $i++) {
      $t = (Norm ([U]::MenuText($m, $i))) -replace '\t.*$', ''
      if ($t -eq $alvo -or $t -like "$alvo*") { $pos = $i; break }
    }
    if ($pos -lt 0) { Fail "Item de menu '$($caminho[$k])' não encontrado no SGCI." }
    if ($k -eq $caminho.Count - 1) {
      $id = [U]::GetMenuItemID($m, $pos)
      [void][U]::PostMessage($script:sgciMain, 0x0111, [IntPtr][int]$id, [IntPtr]::Zero)
      return
    }
    $m = [U]::GetSubMenu($m, $pos)
  }
}
# controles realmente na tela (o SSTab do VB6 esconde as outras abas jogando os controles para fora da janela)
function NaTela([WinInfo]$form) {
  $f = [U]::Info($form.H)
  @(Visiveis $form.H | Where-Object { $_.L -ge ($f.L - 5) -and $_.R -le ($f.R + 5) -and $_.T -ge ($f.T - 5) -and $_.B -le ($f.B + 5) -and $_.W -gt 0 })
}
function SGCI-GarantirMedicaoQuantificada {
  $f = [U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Cls -like '*ThunderRT6Form*' -and $_.Text -eq 'Medição Quantificada' } | Select-Object -First 1
  if ($f) { return (SGCI-Form) }
  Log '   SGCI: abrindo Medição Quantificada (Serviço > Medição Quantificada)'
  # queda da conexão com o banco (ORA-12170 timeout etc.) responde OK, espera a rede voltar e tenta de novo
  for ($tent = 1; ; $tent++) {
    try {
      SGCI-Menu @('Serviço', 'Medição Quantificada')
      $ok = Esperar { [U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Text -eq 'Medição Quantificada' } | Select-Object -First 1 } 40
      if (-not $ok) { SGCI-ChecarPopup 'abrir Medição Quantificada'; Fail "A tela 'Medição Quantificada' não abriu." }
      break
    } catch {
      $m = $_.Exception.Message
      if ($tent -ge 3 -or $m -notmatch 'ORA-|TNS|Conex[aã]o com a Base') { throw }
      Log "   SGCI: falha de conexão com o banco ao abrir a Medição Quantificada (tentativa $tent) - esperando 20 s e tentando de novo"
      Pausa 20000
    }
  }
  Pausa 1000
  return (SGCI-Form)
}
# 14) fecha a Medição Quantificada e abre Serviço  Controle de Materiais  Requisição de Material
# pede a tela ao SGCI sem esperar ela carregar (o SGCI leva ~30 s) chamado logo depois de encaminhar,
# a tela carrega enquanto o SGM faz o Rascunho  FSAAC. O menu vai por mensagem, sem mexer no foco.
$script:cmPedido = $null
function SGCI-PreAbrirRequisicao {
  try {
    if (SGCI-Janela 'Controle de Material') { return }
    $mq = [U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Text -eq 'Medição Quantificada' } | Select-Object -First 1
    if ($mq) {
      [void][U]::PostMessage($mq.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
      $ok = Esperar { if (-not ([U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Text -eq 'Medição Quantificada' })) { $true } } 10
      if (-not $ok) { Log '   SGCI: (adiantar Controle de Material: Medição Quantificada não fechou - fica para depois)'; return }
    }
    # o SGCI fica ~30 s ocupado carregando a tela. Se ele estiver na frente nesse tempo, trazer o SGM
    # para a frente trava junto (o SGM ficava ~30 s parado no Rascunho) - poe o SGM na frente ANTES de pedir
    Ativar $script:sgmMain 'SGM'
    SGCI-Menu @('Serviço', 'Controle de Materiais', 'Requisição de Material') -SemAtivar
    $script:cmPedido = Get-Date
    Log '   SGCI: Controle de Material pedido antecipado (vai carregando enquanto o SGM trabalha)'
  } catch { Log "   SGCI: (não consegui adiantar o Controle de Material: $($_.Exception.Message))" }
}
function SGCI-AbrirRequisicao {
  if ($script:cmPedido) {
    $cm = Esperar { SGCI-Janela 'Controle de Material' } 60 700
    if ($cm) { Log ("   SGCI: Controle de Material já estava aberto (pedido há {0:0} s)" -f ((Get-Date) - $script:cmPedido).TotalSeconds) }
    $script:cmPedido = $null
    if (-not $cm) { SGCI-ChecarPopup 'Requisição de Material'; Fail "A tela 'Controle de Material' não abriu." }
    Pausa 500
    $script:sgciRaiz = [U]::Root($cm.H)
    return $cm
  }
  $mq = [U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Text -eq 'Medição Quantificada' } | Select-Object -First 1
  if ($mq) {
    [void][U]::PostMessage($mq.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
    $ok = Esperar { if (-not ([U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Text -eq 'Medição Quantificada' })) { $true } } 10
    if (-not $ok) { SGCI-ChecarPopup 'fechar Medição Quantificada'; Fail 'Não consegui fechar a Medição Quantificada.' }
  }
  $cm = SGCI-Janela 'Controle de Material'
  if (-not $cm) {
    SGCI-Menu @('Serviço', 'Controle de Materiais', 'Requisição de Material')
    Log '   SGCI: abrindo Requisição de Material...'
    $cm = Esperar { SGCI-Janela 'Controle de Material' } 60 700
    if (-not $cm) { SGCI-ChecarPopup 'Requisição de Material'; Fail "A tela 'Controle de Material' não abriu." }
    Pausa 1500
  }
  $script:sgciRaiz = [U]::Root($cm.H)
  return $cm
}
function CM-Botao([WinInfo]$cm, [string]$legenda) {
  $n = Norm $legenda
  NaTela $cm | Where-Object { $_.Cls -like '*CommandButton*' -and (Norm $_.Text) -like "*$n*" } | Select-Object -First 1
}
# clica na aba (Utilizado  Retirado) achando o texto da aba na tela
function CM-Aba([WinInfo]$cm, [string]$aba) {
  Ativar $cm.H 'Controle de Material'
  $o = Get-Ocr $cm.H 2 -Tela
  $f = [U]::Info($cm.H)
  $w = $o.Words | Where-Object { (Norm $_.Text) -eq (Norm $aba) -and $_.Y -lt ($f.T + 90) } | Select-Object -First 1
  if (-not $w) { Fail "Aba '$aba' não encontrada no Controle de Material." }
  Clicar-Ponto $cm.H ($w.X + [int]($w.W / 2)) ($w.Y + [int]($w.H / 2))
  Pausa 800
  Log "   SGCI: aba $aba"
}
function CM-Campos([WinInfo]$cm) {
  $tela = NaTela $cm
  $frMat = $tela | Where-Object { $_.Cls -like '*Frame*' -and (Norm $_.Text) -eq 'MATERIAL' } | Select-Object -First 1
  $frLista = $tela | Where-Object { $_.Cls -like '*Frame*' -and (Norm $_.Text) -eq 'MATERIAIS' } | Select-Object -First 1
  if (-not $frMat -or -not $frLista) { Fail "Quadros 'Material' / 'Materiais' não encontrados no Controle de Material." }
  $dentro = @($tela | Where-Object { $_.L -ge $frMat.L -and $_.R -le $frMat.R -and $_.T -ge $frMat.T -and $_.B -le $frMat.B })
  $combos = @($dentro | Where-Object { $_.Cls -like '*ComboBox*' } | Sort-Object T, L)
  $cod = $combos | Select-Object -First 1
  $desc = $combos | Where-Object { [Math]::Abs($_.T - $cod.T) -le 6 -and $_.L -gt $cod.R } | Sort-Object L | Select-Object -First 1
  $ins = $dentro | Where-Object { (Norm $_.Text) -eq 'INSERIR' } | Select-Object -First 1
  # Quantidade e uma celula (Spread) ou caixa de texto na mesma linha do Código, logo antes do Inserir
  $qtd = $null
  if ($ins) { $qtd = $dentro | Where-Object { ($_.Cls -like '*SPR32*' -or $_.Cls -like '*TextBox*') -and [Math]::Abs($_.T - $cod.T) -le 8 -and $_.R -le ($ins.L + 2) -and $_.L -gt $cod.R } | Sort-Object L -Descending | Select-Object -First 1 }
  $codEd = Filhos $cod.H | Where-Object { $_.Cls -eq 'Edit' } | Select-Object -First 1
  if (-not $codEd) { $codEd = $cod }
  $grade = $tela | Where-Object { $_.Cls -like '*SPR32*' -and $_.L -ge $frLista.L -and $_.R -le $frLista.R -and $_.T -ge $frLista.T -and $_.B -le $frLista.B } | Sort-Object { $_.W * $_.Hg } -Descending | Select-Object -First 1
  $frReq = $tela | Where-Object { $_.Cls -like '*Frame*' -and (Norm $_.Text) -like '*REQUISICAO*' } | Select-Object -First 1
  $req = $null; if ($frReq) { $req = $tela | Where-Object { $_.Cls -like '*TextBox*' -and $_.L -ge $frReq.L -and $_.R -le $frReq.R -and $_.T -ge $frReq.T -and $_.B -le $frReq.B } | Select-Object -First 1 }
  if (-not $cod -or -not $desc -or -not $qtd -or -not $ins) { Fail 'Campos Código / Descrição / Quantidade / Inserir não encontrados no Controle de Material.' }
  # Lote 2a linha do quadro Material, caixa de texto mais a esquerda (a da direita e Bobina)
  $lote = $dentro | Where-Object { $_.Cls -like '*TextBox*' -and $_.T -gt ($cod.B + 5) -and $_.T -lt ($cod.B + 60) } | Sort-Object L | Select-Object -First 1
  [pscustomobject]@{ Codigo = $cod; CodigoEd = $codEd; Desc = $desc; Qtd = $qtd; Inserir = $ins; Grade = $grade; Req = $req; Lote = $lote; Tela = $tela }
}
# Novo  Selecione  Serviço  OR  Filtrar  duplo clique; confere Serviço = OR e Medição
function CM-CarregarOR([WinInfo]$cm, [string]$or, [string]$medicao) {
  $novo = CM-Botao $cm 'NOVO'
  if (-not $novo) { Fail 'Botão Novo não encontrado no Controle de Material.' }
  Clicar $novo
  $sel = Esperar { SGCI-Janela 'Selecione' } 15
  if (-not $sel) { SGCI-ChecarPopup 'Novo'; Fail "A janela 'Selecione' não abriu." }
  Pausa 500
  $k = NaTela $sel
  $combo = $k | Where-Object { $_.Cls -like '*ComboBox*' -and $_.En } | Sort-Object L -Descending | Select-Object -First 1
  $caixa = $k | Where-Object { $_.Cls -like '*TextBox*' } | Select-Object -First 1
  $filtrar = $k | Where-Object { (Norm $_.Text) -eq 'FILTRAR' } | Select-Object -First 1
  $grade = $k | Where-Object { $_.Cls -like '*SPR32*' } | Sort-Object { $_.W * $_.Hg } -Descending | Select-Object -First 1
  if (-not $combo -or -not $caixa -or -not $filtrar -or -not $grade) { Fail "Controles da janela 'Selecione' (Controle de Material) não encontrados." }
  Clicar $combo
  Teclas '{DOWN}' $sel.H 'SGCI'; Teclas '{ENTER}' $sel.H 'SGCI'; Pausa 300
  if ((Norm (Texto $combo.H)) -ne 'SERVICO') { Fail "Filtrar por ficou '$(Texto $combo.H)' (esperado 'Serviço')." }
  Clicar $caixa
  Teclas '{HOME}+{END}' $sel.H 'SGCI'; Digitar $or $sel.H 'SGCI'
  if ((Texto $caixa.H) -ne $or) { Fail "Caixa do filtro ficou '$(Texto $caixa.H)' (esperado OR $or)." }
  Clicar $filtrar
  $ini = Get-Date
  $linha = Esperar {
    SGCI-ChecarPopup 'Filtrar (Controle de Material)'
    $o = Get-Ocr $grade.H 3 -Tela
    $w = Linha-Com $o $or
    if ($w) { return [pscustomobject]@{ W = $w; Txt = (Linha-Texto $o $w) } }
    if (((Get-Date) - $ini).TotalSeconds -gt 7 -and (Total-Registros (Get-Ocr $sel.H 2 -Tela).Text) -eq 0) { Fail "OR $or não encontrada no Controle de Material." }
    return $null
  } $TIMEOUT_FILTRO 800
  if (-not $linha) { Fail "OR $or não encontrada no Controle de Material." }
  Log "   SGCI: Controle de Material - linha: $($linha.Txt)"
  if ($medicao -and (Digitos $linha.Txt) -notlike "*$medicao*") { Fail "No Controle de Material a OR $or não mostra a medição $medicao ($($linha.Txt))." }
  Clicar-Ponto $grade.H ($linha.W.X + [int]($linha.W.W / 2)) ($linha.W.Y + [int]($linha.W.H / 2)) -Duplo
  $ok = Esperar { if (-not (SGCI-Janela 'Selecione') -and (NaTela $cm | Where-Object { $_.Cls -like '*TextBox*' -and (Texto $_.H) -eq $or })) { $true } } 15
  if (-not $ok) { SGCI-ChecarPopup 'seleção da OR'; Fail "Controle de Material não carregou a OR $or." }
  Pausa 500
}
function CM-ConferirCabecalho([WinInfo]$cm, [string]$or, [string]$medicao) {
  $tela = NaTela $cm
  if (-not ($tela | Where-Object { $_.Cls -like '*TextBox*' -and (Texto $_.H) -eq $or })) { return $false }
  if ($medicao -and -not ($tela | Where-Object { $_.Cls -like '*TextBox*' -and (Texto $_.H) -eq $medicao })) { Fail "Controle de Material: a Medição mostrada não é $medicao." }
  return $true
}
# digita os materiais de um tipo (aba Utilizado = INST  Retirado = RET), confirma e grava
# $gravacao$total o mesmo codigo com lotes diferentes nao pode ir na mesma gravacao - cada repeticao vai numa gravacao a parte
function CM-DigitarTipo([WinInfo]$cm, [string]$tipo, $mats, [string]$or, [string]$medicao, [string]$sgm, [int]$gravacao = 1, [int]$total = 1) {
  $aba = 'Retirado'; $nomeTipo = 'RETIRADO'; if ($tipo -eq 'INST') { $aba = 'Utilizado'; $nomeTipo = 'INSTALADO' }
  $parte = ''; if ($total -gt 1) { $parte = " (gravação $gravacao de $total)" }
  CM-Aba $cm $aba
  if ($gravacao -gt 1) {
    # depois de gravar a anterior Novo + OR de novo, na mesma aba
    Log "   SGCI: $nomeTipo - nova requisição para a gravação $gravacao de $total (mesmo código com outro lote)"
    CM-CarregarOR $cm $or $medicao; [void](CM-ConferirCabecalho $cm $or $medicao)
  }
  elseif (-not (CM-ConferirCabecalho $cm $or $medicao)) { CM-CarregarOR $cm $or $medicao; [void](CM-ConferirCabecalho $cm $or $medicao) }
  $c = CM-Campos $cm
  # trava contra duplicidade se a lista ja tem materiais, nao digita de novo
  if ($c.Grade) {
    $ja = (Get-Ocr $c.Grade.H 3 -Tela).Text
    if ($ja -match '\d{4}\s*-\s*\d{4}\s*-\s*\d') { Fail "A aba $aba já tem materiais lançados para a OR $or ($($Matches[0])). Para não duplicar, o script parou - confira manualmente." }
  }
  foreach ($m in $mats) {
    $qtd = $m.Qtd.ToString('0.######', $PTBR)
    Clicar $c.CodigoEd
    Teclas '{HOME}+{END}{DEL}' $script:sgciRaiz 'SGCI'
    Digitar $m.Codigo $script:sgciRaiz 'SGCI'
    Garantir-Frente $script:sgciRaiz 'SGCI'
    Tecla-Solta 0x09    # TAB solto nao espera o SGCI terminar a busca da descrição
    $lerMat = { SGCI-ChecarPopup "material $($m.Codigo)"; $d = Texto $c.Desc.H; if ($d) { $d } }
    $ini = Get-Date
    $desc = Esperar $lerMat 5 300
    if (-not $desc) { Destravar-Foco $script:sgciRaiz; $desc = Esperar $lerMat 3 300; if ($desc) { Log "   SGCI: descrição do material $($m.Codigo) apareceu após Ctrl+Alt+Del (troca de tela)" } }
    if (-not $desc) { Desfocar-E-Voltar $script:sgciRaiz; $desc = Esperar $lerMat 3 300; if ($desc) { Log "   SGCI: descrição do material $($m.Codigo) apareceu após troca de foco" } }
    if (-not $desc) { $desc = Esperar $lerMat ($TIMEOUT_DESC_UD - 11) 500 }
    if ($desc) { Log ("   SGCI: descrição do material {0} apareceu em {1:0} s" -f $m.Codigo, ((Get-Date) - $ini).TotalSeconds) }
    if (-not $desc) { Fail "Código de material [$($m.Codigo)] não reconhecido pelo SGCI. Por favor verifique." }
    if (((Norm (Texto $c.Codigo.H)) -replace '\s', '') -ne ((Norm $m.Codigo) -replace '\s', '')) { Fail "Código ficou '$(Texto $c.Codigo.H)' (esperado $($m.Codigo))." }
    $p1 = ((Norm $desc) -replace '[^A-Z0-9]', ''); $p2 = ((Norm $m.Desc) -replace '[^A-Z0-9]', '')
    # reaprazo no relatorio a descricao vem com REUT- na frente (ex REUT-CABO TEL CTP-APL...)
    if ($m.Reap) { $p2 = $p2 -replace '^REUT', ''; $p1 = $p1 -replace '^REUT', '' }
    $n = [Math]::Min(4, [Math]::Min($p1.Length, $p2.Length))
    if ($n -lt 3 -or $p1.Substring(0, $n) -ne $p2.Substring(0, $n)) { Log "   ATENÇÃO: descrição do SGCI '$desc' diferente do relatório '$($m.Desc)' (código $($m.Codigo) confere)" }
    Clicar $c.Qtd
    if ($c.Qtd.Cls -like '*TextBox*') { Teclas '{HOME}+{END}' $script:sgciRaiz 'SGCI' }
    Digitar $qtd $script:sgciRaiz 'SGCI'
    $lida = $null; $leituras = @()
    if ($c.Qtd.Cls -like '*TextBox*') {
      $txtQ = Texto $c.Qtd.H; $leituras += $txtQ
      $d = [decimal]0; if ([decimal]::TryParse(($txtQ -replace '[^\d,.]', ''), [Globalization.NumberStyles]::Any, $PTBR, [ref]$d)) { $lida = $d }
    } else {
      # celula Spread sai da celula (confirma o valor) e le o numero na tela, em algumas ampliacoes
      Teclas '{TAB}' $script:sgciRaiz 'SGCI'; Pausa 400
      foreach ($tent in @(@(3, 30), @(4, 30), @(2, 30), @(5, 40))) {
        $bruto = ((Get-Ocr $c.Qtd.H $tent[0] -Tela -Margem $tent[1]).Text -replace '\s', '')
        $leituras += $bruto
        $lida = Num-Ocr $bruto
        if ($null -ne $lida -and $lida -eq $m.Qtd) { break }
        Pausa 200
      }
    }
    if ($null -eq $lida -or $lida -ne $m.Qtd) {
      Fail "Quantidade ficou '$($leituras -join ' / ')' (esperado $qtd) no material $($m.Codigo)."
    }
    # material com lote (CÓD. COMPL. 00000 - 0000000) antes de inserir, preenche o campo Lote
    if ($m.Lote) {
      if (-not $c.Lote) { Fail "Campo 'Lote' não encontrado no Controle de Material (material $($m.Codigo))." }
      Clicar $c.Lote
      Teclas '{HOME}+{END}' $script:sgciRaiz 'SGCI'
      Digitar $m.Lote $script:sgciRaiz 'SGCI'
      $lidoLote = Texto $c.Lote.H
      if ($lidoLote -ne $m.Lote) { Fail "Lote ficou '$lidoLote' (esperado $($m.Lote)) no material $($m.Codigo)." }
      Log "   SGCI: lote $($m.Lote) preenchido no material $($m.Codigo)"
    }
    Clicar $c.Inserir
    $ok = Esperar { SGCI-ChecarPopup "Inserir material $($m.Codigo)"; if (-not (Texto $c.Codigo.H)) { $true } } 10
    if (-not $ok) { Fail "O material $($m.Codigo) não foi inserido (a tela não limpou após Inserir)." }
    $lt = ''; if ($m.Lote) { $lt = " | lote $($m.Lote)" }
    Log "   SGCI: $nomeTipo inserido: $($m.Codigo) | qtd $qtd$lt | $desc"
  }
  # conferencia visual da lista (OCR, so registra no log)
  if ($c.Grade) { Log ("   SGCI: lista Materiais (OCR): " + ((Get-Ocr $c.Grade.H 3 -Tela).Lines -join ' | ')) }
  $lista = ($mats | ForEach-Object { "   • $($_.Codigo) | qtd $($_.Qtd.ToString('0.####', $PTBR))" }) -join "`n"
  Confirmar "Materiais $nomeTipo$parte`n`nGravar?"
  $gravar = CM-Botao $cm 'GRAVAR'
  if (-not $gravar -or -not $gravar.En) { Fail 'Botão Gravar não disponível no Controle de Material.' }
  Clicar $gravar
  $p = Esperar { $x = Popups $script:sgciPid; if ($x.Count -gt 0) { $x[0] } } 30
  if (-not $p) { Fail "O SGCI não confirmou a gravação dos materiais ($nomeTipo)." }
  $t = Texto-Popup $p
  Responder-Popup $p @('OK')
  if ((Norm $t) -notmatch 'SUCESSO') { Fail "SGCI ao gravar materiais ($nomeTipo): $t" }
  $req = ''; if ($c.Req) { $req = Esperar { $r = Texto $c.Req.H; if ($r) { $r } } 5 }
  Log "   SGCI: $nomeTipo GRAVADO$parte - Nº da Requisição: $req"
  return $req
}
# separa os materiais em gravacoes. Numa mesma gravacao NAO pode ter
#  - o mesmo codigo duas vezes (lotes diferentes) e
#  - dois reaprazos (REAP), mesmo de codigos diferentes. Material comum vai junto com qualquer um.
# cada material entra na 1a gravacao em que cabe (a 1a fica com o maximo possivel)
function Separar-Gravacoes($mats) {
  $grupos = @()
  foreach ($m in @($mats)) {
    $k = 0
    while ($k -lt $grupos.Count) {
      $g = @($grupos[$k])
      $conflito = @($g | Where-Object { $_.Codigo -eq $m.Codigo }).Count -or ($m.Reap -and @($g | Where-Object { $_.Reap }).Count)
      if (-not $conflito) { break }
      $k++
    }
    if ($k -ge $grupos.Count) { $grupos += , @() }
    $grupos[$k] += $m
  }
  return , $grupos
}

# ---- Excel do LMN
# confirma (OKEnter) avisos que travam o Excel, ex Não foi possível abrir '...MODELO LMN.xls'
# o Excel usa janelas proprias para avisos; por isso se a janela principal estiver bloqueada, o aviso e a janela habilitada do mesmo Excel
function Excel-PopupsOk {
  foreach ($p in @(Get-Process EXCEL -ErrorAction SilentlyContinue)) {
    $tops = @([U]::Tops([uint32]$p.Id))
    $mains = @($tops | Where-Object { $_.Cls -eq 'XLMAIN' })
    $bloqueado = @($mains | Where-Object { -not [U]::IsWindowEnabled($_.H) }).Count -gt 0
    $avisos = @($tops | Where-Object { $_.Cls -eq '#32770' -or $_.Cls -like '*bosa_sdm*' -or ($bloqueado -and $_.Cls -ne 'XLMAIN' -and $_.En -and $_.W -gt 150 -and $_.W -lt 900 -and $_.Hg -gt 80 -and $_.Hg -lt 600 -and $_.Cls -notlike '*tooltips*') })
    foreach ($d in $avisos) {
      $t = (Filhos $d.H | Where-Object { $_.Cls -eq 'Static' -and $_.Text } | ForEach-Object { $_.Text }) -join ' '
      if (-not $t) { try { $t = (Get-Ocr $d.H 2 -Tela).Text -replace "`n", ' ' } catch {} }
      Log "   Excel: aviso ($($d.Cls)): $t"
      Responder-Popup $d @('OK')
      Pausa 500
    }
  }
}
# todas as planilhas LMN abertas (pode abrir mais de uma), com o F3 de cada uma
function LMN-Todas {
  $lista = @()
  foreach ($x in @([U]::Tops(0) | Where-Object { $_.Cls -eq 'XLMAIN' -and $_.Text -like '*LMN*' })) {
    foreach ($e7 in @(Filhos $x.H | Where-Object { $_.Cls -eq 'EXCEL7' })) {
      try {
        $o = [U]::ExcelWindow($e7.H)
        if ($o) { $wb = $o.Parent; $lista += [pscustomobject]@{ Wb = $wb; Nome = [string]$wb.Name; F3 = (Digitos ([string]$wb.Worksheets.Item(1).Range('F3').Text)) } }
      } catch {}
    }
  }
  return $lista
}
# a planilha LMN cuja OR (F3) e a que estamos fazendo
function LMN-Pasta([string]$or) {
  $p = @(LMN-Todas | Where-Object { $_.F3 -and $_.F3 -eq $or } | Select-Object -First 1)
  if ($p.Count) { return $p[0].Wb }
  return $null
}
# codigo do material numa celula do LMN 0252-0032-1 ou reaprazo 0252-0032-1REAP
function Cod-Lmn($v) {
  $s = ([string]$v).ToUpper()
  if ($s -match '(\d{4}-\d{4}-\d)\s*(REAP)?') { return $Matches[1] + $Matches[2] }
  return ''
}
function LMN-Conferir($wb, [string]$or, [string]$medicao, $mats) {
  $ws = $wb.Worksheets.Item(1)
  $f3 = Digitos ([string]$ws.Range('F3').Text)
  if ($f3 -ne $or) { Fail "A OR do relatório LMN ($f3) não bate com a OR que estamos digitando ($or)." }
  if ($medicao) {
    # MEDIÇÃO Nº fica na linha 4 (celula mesclada) procura o numero entre as colunas L e O
    $achouMed = $false; $vistos = @()
    foreach ($col in 'L', 'M', 'N', 'O') { $v = Digitos ([string]$ws.Range("${col}4").Text); if ($v) { $vistos += $v; if ($v -eq $medicao) { $achouMed = $true } } }
    if (-not $achouMed -and $vistos.Count) { Fail "Medição do LMN ($($vistos -join '/')) diferente de $medicao." }
    if (-not $vistos.Count) { Log '   ATENÇÃO: não achei o Nº da Medição na linha 4 do LMN' }
  }
  # layout esperado G = INSTALADO GASTO, L = RETIRADO QTD.
  $cabG = Norm (([string]$ws.Range('G10').Text) + ' ' + ([string]$ws.Range('G11').Text))
  $cabL = Norm (([string]$ws.Range('L10').Text) + ' ' + ([string]$ws.Range('L11').Text))
  if ($cabG -notmatch 'GASTO' -or $cabL -notmatch 'QTD') { Fail "Layout do relatório LMN diferente do esperado (G='$cabG' / L='$cabL')." }
  $numero = { param($v) if ($null -eq $v -or $v.Trim() -eq '') { return $null }; if ($v -is [double]) { return [decimal]$v }; $d = [decimal]0; if ([decimal]::TryParse($v.Trim(), [Globalization.NumberStyles]::Any, $PTBR, [ref]$d)) { return $d }; return $null }
  $achados = @()
  for ($r = 12; $r -le 120; $r++) {
    $cod = ''
    foreach ($col in 'E', 'F', 'D') { $cod = Cod-Lmn $ws.Range("$col$r").Value2; if ($cod) { break } }
    if (-not $cod) { continue }
    # Gasto (G) e Qtd. (L) podem vir vazias, mas NUNCA com , #### ou texto - isso indica relatorio errado
    foreach ($col in 'G', 'L') {
      $txt = ([string]$ws.Range("$col$r").Text).Trim(); $val = $ws.Range("$col$r").Value2
      $nome = 'Gasto (Instalado)'; if ($col -eq 'L') { $nome = 'Qtd. (Retirado)' }
      if ($txt -match '[#]' -or ($val -is [string] -and $val.Trim() -ne '' -and $null -eq (& $numero $val))) {
        Fail "LMN com valor inválido em $nome na linha $r (material $cod): '$txt'. O relatório veio errado - não vou imprimir."
      }
    }
    # o LMN coloca 0 na coluna que nao se aplica so conta quantidade maior que zero
    $gi = & $numero $ws.Range("G$r").Value2; $lr = & $numero $ws.Range("L$r").Value2
    if ($null -ne $gi -and $gi -gt 0) { $achados += [pscustomobject]@{ Tipo = 'INST'; Codigo = $cod; Qtd = $gi } }
    if ($null -ne $lr -and $lr -gt 0) { $achados += [pscustomobject]@{ Tipo = 'RET'; Codigo = $cod; Qtd = $lr } }
    if (-not ($gi -gt 0) -and -not ($lr -gt 0)) { $achados += [pscustomobject]@{ Tipo = ''; Codigo = $cod; Qtd = 0 } }
  }
  # confere por tipo + codigo, somando o mesmo codigo com lotes diferentes pode vir em 2 linhas ou somado numa so
  $prob = @()
  $chaves = @(@($mats) + @($achados | Where-Object { $_.Tipo -ne '' }) | ForEach-Object { "$($_.Tipo)|$($_.Codigo)" } | Select-Object -Unique)
  foreach ($k in $chaves) {
    $tp, $cd = $k -split '\|'
    $esp = [decimal]0; @($mats | Where-Object { $_.Tipo -eq $tp -and $_.Codigo -eq $cd }) | ForEach-Object { $esp += $_.Qtd }
    $lmn = [decimal]0; @($achados | Where-Object { $_.Tipo -eq $tp -and $_.Codigo -eq $cd }) | ForEach-Object { $lmn += $_.Qtd }
    if ($esp -eq 0) { $prob += "$tp $cd qtd $lmn está no LMN mas não no relatório do SGM" }
    elseif ($lmn -ne $esp) { $prob += "$tp $cd qtd $esp não confere no LMN (LMN: $lmn)" }
  }
  foreach ($a in @($achados | Where-Object { $_.Tipo -eq '' })) { $prob += "material $($a.Codigo) no LMN sem quantidade" }
  foreach ($a in $achados) { Log ("   LMN: {0} {1} qtd {2}" -f $a.Tipo, $a.Codigo, $a.Qtd) }
  if ($prob.Count) { Fail ("Relatório LMN não confere: " + ($prob -join '; ')) }
}
# 17) Relatorio LMN  Iniciar Impressão  o SGCI grava CRELATORIO_LMN.XLS  o script abre uma COPIA
#     num Excel proprio (escondido, sem macros)  confere F3 = OR e materiais  imprime  fecha sem salvar
#     (nao depende do Excel que o SGCI abre - e ele que trava com o erro da macro 'fMsgPergunta' em algumas maquinas)
$ARQ_LMN = 'C:\RELATORIO_LMN.XLS'
# escreve o lote na coluna OBS. (Q) da linha de cada material com lote e confere
function LMN-ObsLote($wb, $mats) {
  $ws = $wb.Worksheets.Item(1)
  if ((Norm ([string]$ws.Range('Q10').Text)) -notmatch 'OBS') { Fail 'Coluna OBS. (Q10) não encontrada no LMN.' }
  $codLinha = { param($r) foreach ($c in 'E', 'F', 'D') { $v = Cod-Lmn $ws.Range("$c$r").Value2; if ($v) { return $v } }; return '' }
  $linhasDe = { param($cod, $col)
    $res = @()
    for ($r = 12; $r -le 120; $r++) {
      if ((& $codLinha $r) -ne $cod) { continue }
      $q = $ws.Range("$col$r").Value2
      if ($q -is [double] -and [decimal]$q -gt 0) { $res += [pscustomobject]@{ R = $r; Q = [decimal]$q } }
    }
    return , $res
  }
  # 1) o mesmo codigo com lotes diferentes o SGCI soma tudo numa linha so - abre uma linha para cada lote,
  #    cada uma com o gastoqtd daquele lote (as linhas de baixo descem; a tabela vai ate a linha 37)
  $grupos = @($mats | Group-Object { "$($_.Tipo)|$($_.Codigo)" } | Where-Object { $_.Count -ge 2 -and @($_.Group | Where-Object { $_.Lote }).Count })
  foreach ($gr in $grupos) {
    $tp, $cd = $gr.Name -split '\|'
    $col = 'L'; if ($tp -eq 'INST') { $col = 'G' }
    $doCod = @($mats | Where-Object { $_.Tipo -eq $tp -and $_.Codigo -eq $cd })
    $lin = & $linhasDe $cd $col
    if ($lin.Count -ge $doCod.Count) { continue }   # o LMN ja veio com uma linha por lote
    $soma = [decimal]0; $doCod | ForEach-Object { $soma += $_.Qtd }
    if ($lin.Count -ne 1 -or $lin[0].Q -ne $soma) { Fail "LMN: o material $cd veio em $($lin.Count) linha(s) e não consegui separar por lote (esperado $($doCod.Count) lotes, total $soma)." }
    $r0 = $lin[0].R; $extra = $doCod.Count - 1
    $ult = $r0; for ($r = $r0 + 1; $r -le 37; $r++) { if (& $codLinha $r) { $ult = $r } }
    if ($ult + $extra -gt 37) { Fail "LMN sem linhas livres para separar os lotes do material $cd (a tabela vai até a linha 37)." }
    # (Range.Copy direto na planilha atribuir o Value2 de varias linhas falha no PowerShell - Object[,] - String)
    if ($ult -gt $r0) {
      for ($rr = $ult; $rr -gt $r0; $rr--) { [void]$ws.Range("A${rr}:Q${rr}").Copy($ws.Range("A$($rr + $extra)")) }
    }
    for ($i = 1; $i -le $extra; $i++) { [void]$ws.Range("A${r0}:Q${r0}").Copy($ws.Range("A$($r0 + $i)")) }
    for ($i = 0; $i -lt $doCod.Count; $i++) { $ws.Range("$col$($r0 + $i)").Value2 = [double]$doCod[$i].Qtd }
    Log ("   LMN: material $cd separado em $($doCod.Count) linhas (uma por lote): " + (($doCod | ForEach-Object { $_.Qtd.ToString('0.###', $PTBR) }) -join ' + '))
  }
  # 2) cada material com lote vai na OBS da sua linha (linhas diferentes para o mesmo codigo)
  $usadas = @{}
  foreach ($m in @($mats | Where-Object { $_.Lote })) {
    $col = 'L'; if ($m.Tipo -eq 'INST') { $col = 'G' }
    $todas = & $linhasDe $m.Codigo $col
    $linha = @($todas | Where-Object { $_.Q -eq $m.Qtd -and -not $usadas.ContainsKey($_.R) } | Select-Object -First 1)
    if (-not $linha.Count) { Fail "Não achei a linha do material $($m.Codigo) (qtd $($m.Qtd)) no LMN para escrever o lote $($m.Lote)." }
    $r = $linha[0].R; $usadas[$r] = $true
    $cel = $ws.Range("Q$r")
    $cel.NumberFormat = '@'
    $cel.Value2 = [string]$m.Lote
    if (([string]$cel.Text).Trim() -ne $m.Lote) { Fail "A OBS do material $($m.Codigo) ficou '$($cel.Text)' (esperado lote $($m.Lote))." }
    Log "   LMN: lote $($m.Lote) escrito na OBS (linha $r, material $($m.Codigo))"
  }
}
# fecha o Excel que o SGCI abriu para o LMN. NUNCA para a automacao por causa disso
# 1) fecha a janela normalmente e responde Não Salvar; 2) tenta encerrar; 3) se nada der certo, so registra no log
function Encerrar-Excel($ids) {
  foreach ($id in @($ids)) {
    try {
      if (-not (Get-Process -Id $id -ErrorAction SilentlyContinue)) { continue }
      Log "   Fechando Excel aberto pelo SGCI (PID $id)"
      foreach ($x in @([U]::Tops([uint32]$id) | Where-Object { $_.Cls -eq 'XLMAIN' })) { [void][U]::PostMessage($x.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
      # (nos logs ele nunca fecha so com o pedido - sempre precisou do Finalizar tarefa; espera pouco)
      $fim = (Get-Date).AddSeconds(2.5)
      while ((Get-Date) -lt $fim -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
        foreach ($d in @([U]::Tops([uint32]$id) | Where-Object { $_.Cls -ne 'XLMAIN' -and $_.En })) {
          $nao = Filhos $d.H | Where-Object { $_.Vis -and (Norm $_.Text) -match '^NAO( SALVAR)?$' } | Select-Object -First 1
          if ($nao) { Log "      respondendo 'Não Salvar'"; try { Clicar $nao } catch {} }
        }
        Start-Sleep -Milliseconds 400
      }
      if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
        # Finalizar tarefa (mesmo comando do Gerenciador de Tarefas) - funciona no Excel aberto pelo SGCI
        $jan = @([U]::TopsTodas([uint32]$id) | Where-Object { $_.Cls -eq 'XLMAIN' }) + @([U]::TopsTodas([uint32]$id) | Select-Object -First 1)
        foreach ($j in $jan) { if ($j -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { [void][U]::EndTask($j.H, $false, $true); $fim = (Get-Date).AddSeconds(3); while ((Get-Date) -lt $fim -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 200 } } }
      }
      if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
        try { Stop-Process -Id $id -Force -ErrorAction Stop } catch {}
        Start-Sleep -Milliseconds 1500
      }
      if (Get-Process -Id $id -ErrorAction SilentlyContinue) { Log "      ATENÇÃO: o Windows não deixou fechar o Excel PID $id - seguindo mesmo assim (o LMN é lido pela cópia)" }
      else { Log "      Excel PID $id fechado" }
    } catch { Log "      ATENÇÃO: erro ao fechar o Excel PID ${id}: $($_.Exception.Message) - seguindo mesmo assim" }
  }
}
# o arquivo do LMN esta preso (um Excel travado de antes esta com ele aberto)
function LMN-ArquivoPreso {
  if (-not (Test-Path $ARQ_LMN)) { return $false }
  # leitura exclusiva falha so se outro programa estiver com o arquivo aberto (o usuario nao tem permissao de ESCRITA na raiz do C)
  try { $fs = [IO.File]::Open($ARQ_LMN, 'Open', 'Read', 'None'); $fs.Close(); return $false } catch { return $true }
}
# Excel invisivel (sem janela principal visivel) = sobra travada do SGCI; o Excel que o usuario usa e visivel e nunca e tocado
function Excel-Invisiveis {
  @(Get-Process EXCEL -ErrorAction SilentlyContinue | Where-Object { -not ([U]::TopsTodas([uint32]$_.Id) | Where-Object { $_.Cls -eq 'XLMAIN' -and $_.Vis }) } | ForEach-Object { $_.Id })
}
function SGCI-LMN([WinInfo]$cm, [string]$or, [string]$medicao, $mats, [string]$sgm) {
  if (LMN-ArquivoPreso) {
    Log "   O arquivo $ARQ_LMN está preso por um Excel travado - fechando os Excel invisíveis"
    Encerrar-Excel (Excel-Invisiveis)
    if (LMN-ArquivoPreso) { Fail "O arquivo $ARQ_LMN está preso por um Excel. Feche o Excel pelo Gerenciador de Tarefas e rode de novo." }
  }
  $excelAntes = @(Get-Process EXCEL -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
  $btn = NaTela $cm | Where-Object { $_.Cls -like '*CommandButton*' -and (Norm $_.Text) -like '*RELATORIO*LMN*' } | Select-Object -First 1
  if (-not $btn) { Fail "Botão 'Relatório LMN' não encontrado." }
  Ativar $cm.H 'Controle de Material'
  Clicar $btn
  $dlgFn = { [U]::Tops([uint32]$script:sgciPid) | Where-Object { $_.Text -like '*Relat*Lista*Materiais*' } | Select-Object -First 1 }
  $dlg = Esperar $dlgFn 15
  if (-not $dlg) { SGCI-ChecarPopup 'Relatório LMN'; Fail "A janela 'Relatório de Lista de Materiais Necessários' não abriu." }
  $iniciar = Filhos $dlg.H | Where-Object { $_.Vis -and (Norm $_.Text) -like '*INICIAR*IMPRESSAO*' } | Select-Object -First 1
  $t0 = (Get-Date).AddSeconds(-2)
  Clicar $iniciar
  Log '   SGCI: gerando relatório LMN...'

  # 1) espera o SGCI gravar o arquivo novo (e confirma os avisos que aparecerem no caminho)
  $arqOk = Esperar {
    foreach ($x in @(Popups $script:sgciPid)) { Log "   SGCI: $(Texto-Popup $x)"; Responder-Popup $x @('OK') }
    if ((Test-Path $ARQ_LMN) -and (Get-Item $ARQ_LMN).LastWriteTime -ge $t0) { $true }
  } 90 800
  if (-not $arqOk) { Fail "O SGCI não gerou o arquivo do LMN ($ARQ_LMN)." }
  # espera o arquivo parar de mudar
  $script:tamLmn = -1
  [void](Esperar { $n = (Get-Item $ARQ_LMN).Length; if ($n -gt 0 -and $n -eq $script:tamLmn) { $true } else { $script:tamLmn = $n; $null } } 15 700)
  Pausa 800

  # 2) fecha o que o SGCI abriu (Excel novo, avisos de macro  Permission denied)
  foreach ($x in @(Popups $script:sgciPid)) { Log "   SGCI: $(Texto-Popup $x)"; Responder-Popup $x @('OK') }
  Encerrar-Excel @(Get-Process EXCEL -ErrorAction SilentlyContinue | Where-Object { $excelAntes -notcontains $_.Id } | ForEach-Object { $_.Id })
  Pausa 500
  foreach ($x in @(Popups $script:sgciPid)) { Log "   SGCI: $(Texto-Popup $x)"; Responder-Popup $x @('OK') }

  # 3) abre uma copia num Excel proprio, escondido e sem macros
  New-Item -ItemType Directory -Force $PASTA_TEMP | Out-Null
  $copia = Join-Path $PASTA_TEMP ("LMN_" + $or + ".xls")
  [void](Esperar { if (-not (LMN-ArquivoPreso)) { $true } } 10)
  try { Copy-Item $ARQ_LMN $copia -Force -ErrorAction Stop }
  catch { Fail "Não consegui copiar o $ARQ_LMN (preso pelo Excel do SGCI). Feche o Excel pelo Gerenciador de Tarefas e rode de novo." }
  $xl = New-Object -ComObject Excel.Application
  try {
    $xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.AutomationSecurity = 3
    try { $xl.AskToUpdateLinks = $false } catch {}
    $wb = $xl.Workbooks.Open($copia, 0, $true)
    $ws = $wb.Worksheets.Item(1)
    Log "   LMN: aberto (cópia de $ARQ_LMN) - F3 = $([string]$ws.Range('F3').Text)"
    # o RELATORIO_LMN vem protegido e com a coluna Retirado estreita (numero aparece ####).
    # igual ao processo manual cola tudo numa COPIA do MODELO LMN (o original nunca e alterado) e imprime de la
    $imprimir = $wb
    if (Test-Path $MODELO_LMN) {
      $copiaMod = Join-Path $PASTA_TEMP ("MODELO_" + $or + ".xls")
      Copy-Item $MODELO_LMN $copiaMod -Force
      $wm = $xl.Workbooks.Open($copiaMod, 0, $false)
      $u = $ws.UsedRange
      $ultLin = $u.Row + $u.Rows.Count - 1; $ultCol = $u.Column + $u.Columns.Count - 1
      [void]$ws.Range($ws.Cells.Item(1, 1), $ws.Cells.Item($ultLin, $ultCol)).Copy()
      [void]$wm.Worksheets.Item(1).Range('A1').PasteSpecial(-4104)
      try { $xl.CutCopyMode = 0 } catch {}
      $imprimir = $wm
      Log "   LMN: colado na cópia do MODELO LMN (linhas 1-$ultLin)"
    } else {
      Log "   ATENÇÃO: $MODELO_LMN não encontrado - imprimindo o RELATORIO_LMN direto"
    }
    LMN-Conferir $imprimir $or $medicao $mats
    # materiais com lote escreve o lote na coluna OBS. (Q) da linha do material
    if (@($mats | Where-Object { $_.Lote }).Count) {
      if ($imprimir -eq $wb) { Fail 'Há material com lote mas o MODELO LMN não está na Área de Trabalho - não consigo escrever o lote na OBS do relatório protegido.' }
      LMN-ObsLote $imprimir $mats
      LMN-Conferir $imprimir $or $medicao $mats   # confere de novo depois de separar as linhas por lote
    }
    Confirmar "Relatório LMN (OR $or)`n`nImprimir?"
    $imprimir.Worksheets.Item(1).PrintOut()
    Log '   LMN: impresso'
    Pausa 1000
    if ($imprimir -ne $wb) { $imprimir.Close($false) }
    $wb.Close($false)
  } finally {
    try { $xl.Quit() } catch {}
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
  }

  # 4) fecha o pop-up de impressao do SGCI
  foreach ($x in @(Popups $script:sgciPid)) { Log "   SGCI: $(Texto-Popup $x)"; Responder-Popup $x @('OK') }
  $dlg = & $dlgFn
  if ($dlg) {
    $cancel = Filhos $dlg.H | Where-Object { $_.Vis -and (Norm $_.Text) -eq 'CANCELAR' } | Select-Object -First 1
    if ($cancel) { Clicar $cancel } else { [void][U]::PostMessage($dlg.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
  }
  foreach ($x in @(Popups $script:sgciPid)) { Log "   SGCI: $(Texto-Popup $x)"; Responder-Popup $x @('OK') }
}
# 14-18) tudo da parte de materiais
function Processar-Materiais([string]$sgm, $lidos, [string]$medicao) {
  $mats = @($lidos.Materiais)
  if ($mats.Count -eq 0) {
    Log '   Sem materiais (só 1 - SERV.) - nada a digitar'
    if ($script:cmPedido) {
      # o Controle de Material foi aberto adiantado e nao vai ser usado fecha e volta para a Medição Quantificada
      $script:cmPedido = $null
      $cm = Esperar { SGCI-Janela 'Controle de Material' } 60 700
      if ($cm) {
        Pausa 500
        $sair = CM-Botao $cm 'SAIR'
        if ($sair) { Clicar $sair } else { [void][U]::PostMessage($cm.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
        [void](Esperar { if (-not (SGCI-Janela 'Controle de Material')) { $true } } 10)
      }
      [void](SGCI-GarantirMedicaoQuantificada)
    }
    return
  }
  $or = $lidos.OR
  $cm = SGCI-AbrirRequisicao
  $inst = @($mats | Where-Object Tipo -eq 'INST'); $ret = @($mats | Where-Object Tipo -eq 'RET')
  foreach ($tp in @(@('INST', $inst), @('RET', $ret))) {
    if (-not @($tp[1]).Count) { continue }
    $grav = Separar-Gravacoes $tp[1]
    for ($g = 0; $g -lt $grav.Count; $g++) { [void](CM-DigitarTipo $cm $tp[0] @($grav[$g]) $or $medicao $sgm ($g + 1) $grav.Count) }
  }
  if ($SEM_IMPRESSAO) { Log '   SGCI: (sem impressão) relatório LMN pulado' }
  else { SGCI-LMN $cm $or $medicao $mats $sgm }
  # 18) fecha a Requisição de Material e reabre a Medição Quantificada
  $cm = SGCI-Janela 'Controle de Material'
  if ($cm) {
    $sair = CM-Botao $cm 'SAIR'
    if ($sair) { Clicar $sair } else { [void][U]::PostMessage($cm.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
    $ok = Esperar { if (-not (SGCI-Janela 'Controle de Material')) { $true } } 10
    if (-not $ok) { SGCI-ChecarPopup 'fechar Controle de Material'; Fail 'Não consegui fechar o Controle de Material.' }
  }
  [void](SGCI-GarantirMedicaoQuantificada)
  Log '   SGCI: materiais concluídos, Medição Quantificada reaberta'
}

# =====================================================================
#  CICLO DE UM SGM
# =====================================================================
function Processar([string]$sgm) {
  Log "===== SGM $sgm ====="
  $inicioSgm = Get-Date
  # 1) SGM - pesquisa no Rascunho
  if (SGM-Filha 'Visão Medição') { Fail "A tela 'Visão Medição' está aberta no SGM. Feche-a e rode de novo." }
  $filha = SGM-AtivarFilha 'Rascunho de Medição'
  $pesq = SGM-Pesquisar $filha 'Cód. Obra' $sgm 'SGM divergente ou errado. Por favor verifique.'

  # 2) SGM - Imprimir  Rascunho de Medicao - Digitacao
  Excel-Fechar
  SGM-Imprimir $pesq.Ctl $SETAS_RELATORIO
  Log '   SGM: gerando planilha...'
  $xl = Esperar { $x = Excel-Janelas; if ($x.Count -gt 0) { $x[0] } } $TIMEOUT_EXCEL 700
  if (-not $xl) { Fail 'A planilha do Excel não foi gerada.' }
  Pausa 1500

  # 3) Excel
  $dados = Excel-Ler $sgm
  Log ("   Excel: OR {0} | ATA {1} | {2} serviços | pontos {3} | valor {4}" -f $dados.OR, $dados.ATA, $dados.Servicos.Count, $dados.SomaPontos, $dados.SomaValor)
  Excel-Fechar   # ja temos tudo da planilha; fecha agora para nao misturar com o Excel do LMN

  # 4) SGCI - abre a OR
  SGCI-AbrirOR $dados

  # 5) e 6) digitacao + conferencia (1 nova tentativa se nao bater)
  $conf = $null
  for ($t = 1; $t -le 2; $t++) {
    SGCI-DigitarServicos $dados
    $conf = SGCI-Conferir $dados
    if ($conf.Ok) { break }
    Log "   CONFERÊNCIA NÃO BATEU (tentativa $t): $($conf.Motivo)"
    if ($t -eq 2) { Fail "Conferência não bateu após redigitar: $($conf.Motivo)" }
    SGCI-ExcluirTodas
  }
  Log ("   Conferência OK: pontos {0} | valor {1}" -f $conf.Pontos, $conf.Valor)

  # 7) Encaminhar
  Confirmar ("Valor: {0}`n`nEncaminhar?" -f $conf.Valor.ToString('#,##0.0000', $PTBR))
  $num = SGCI-Encaminhar $dados
  if ($PRE_ABRIR_MATERIAL) { SGCI-PreAbrirRequisicao }

  # 8) SGM - Rascunho MQ  Numero  AGU
  SGM-AtualizarRascunho $dados $sgm $num

  # 9) e 10) SGM - Visao Medicao FSAAC
  SGM-Finalizar $sgm

  # 12) SGM - Rascunho de Medicao pesquisa o SGM de novo
  $pesqFim = SGM-VoltarRascunho $sgm

  # 13) SGM - Imprimir  Rascunho de Medicao le os materiais (2 - MAT INST  3 - MAT RET)
  $lidos = SGM-LerMateriais $sgm $pesqFim $dados.OR

  # 14-18) SGCI - Requisicao de Material (Utilizado  Retirado) + LMN, e volta para a Medição Quantificada
  Processar-Materiais $sgm $lidos $num
  Add-Content -Path $ARQ_CONCL -Value $sgm -Encoding UTF8
  $dur = (Get-Date) - $inicioSgm
  Log ("===== SGM $sgm CONCLUÍDO (OR $($dados.OR) | Medição $num) em {0}min{1:00}s =====" -f [int][Math]::Floor($dur.TotalMinutes), $dur.Seconds)
}

# =====================================================================
#  DIAGNOSTICO (somente leitura)
# =====================================================================
function Rodar-Diagnostico {
  Log '--- DIAGNÓSTICO (somente leitura) ---'
  $m = SGM-Principal; Log "SGM: '$($m.Text)'"
  $mdi = SGM-MdiClient
  Filhos $mdi.H | Where-Object { $_.Parent -eq $mdi.H } | ForEach-Object { Log "   tela SGM aberta: '$($_.Text)'" }
  $r = SGM-Filha 'Rascunho de Medição'
  if ($r) {
    $c = SGM-ControlesConsulta $r
    Log "   Campo='$(if ($c.Campo) { Texto $c.Campo.H })' Valor='$(if ($c.Valor) { Texto $c.Valor.H })'"
    if ($c.Grade) { Log ("   OCR grade: " + ((Get-Ocr $c.Grade.H 2).Lines -join ' | ')) }
    if ($c.Status) { Log ("   OCR status: " + (Get-Ocr $c.Status.H 3).Text) }
    if ($c.Barra) { Log ("   OCR barra: " + ((Get-Ocr $c.Barra.H 3).Lines -join ' | ')) }
  } else { Log '   ATENÇÃO: Rascunho de Medição não está aberto' }
  $s = SGCI-Principal; Log "SGCI: '$($s.Text)'"
  try {
    $c = SGCI-Ctl
    Log "   Serviço='$(Texto $c.Servico.H)' Ata='$(Texto $c.Ata.H)' Diretoria='$(Texto $c.Diretoria.H)' NºMedição='$(Texto $c.NumMedicao.H)'"
    Log "   Botões: Nova Medição=$([bool]$c.NovaMed) Inserir=$([bool]$c.Inserir) Encaminhar=$([bool]$c.Encaminhar) AtaProv=$([bool]$c.AtaProv) Impressora=$([bool]$c.Impressora) ExcluirTodas=$([bool]$c.ExcluirTodas)"
    Log "   Grades: item=$([bool]$c.GradeItem) detalhe=$([bool]$c.GradeDet)"
    Ativar $script:sgciRaiz 'SGCI'
    Log ("   OCR Medição-Detalhe: " + ((Get-Ocr $c.GradeDet.H 3 -Tela).Lines -join ' | '))
  } catch { Log "   SGCI: $($_.Exception.Message)" }
  Log '--- FIM DO DIAGNÓSTICO ---'
}

# =====================================================================
#  ATUALIZACAO (versao oficial numa pasta de rede)
# =====================================================================
# pasta oficial pode ser trocada em atualizacao.txt (1a linha que nao comeca com #)
$ORIGEM_PADRAO   = '\\172.20.2.11\Arquivos 2\Medicao OT\192.168.144.66\LUCIO\Automacao_SGCI_Oficial'
$ARQ_VERSAO      = Join-Path $PASTA 'versao.txt'
$ARQS_PROGRAMA   = @('automacao.ps1', 'INICIAR.bat', 'CONTINUAR.bat', 'versao.txt')   # so isso e atualizado (log, concluidos etc. ficam)

# o servidor da rede bloqueia arquivos .ps1.bat - na pasta oficial eles ficam como .ps1.txt  .bat.txt
function Nome-Rede([string]$a) { if ($a -match '\.(ps1|bat)$') { return "$a.txt" }; return $a }
function Origem-Atualizacao {
  $cfg = Join-Path $PASTA 'atualizacao.txt'
  if (Test-Path $cfg) {
    $l = @(Get-Content $cfg -Encoding UTF8 | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') } | Select-Object -First 1)
    if ($l.Count) { return $l[0] }
  }
  return $ORIGEM_PADRAO
}
# versao.txt 1a linha = numero (2026.10.08.1), demais linhas = o que mudou
function Ler-Versao([string]$arq) {
  try {
    $l = @(Get-Content $arq -Encoding UTF8 -ErrorAction Stop)
    $v = $null; if (-not [version]::TryParse(([string]$l[0]).Trim(), [ref]$v)) { return $null }
    return [pscustomobject]@{ Versao = $v; Texto = ([string]$l[0]).Trim(); Notas = (@($l | Select-Object -Skip 1 | Where-Object { $_.Trim() }) -join "`n") }
  } catch { return $null }
}
function Versao-Local { $v = Ler-Versao $ARQ_VERSAO; if ($v) { $v } else { [pscustomobject]@{ Versao = [version]'0.0'; Texto = 'desconhecida'; Notas = '' } } }
# le a versao da rede num processo a parte com limite de tempo (pasta de rede fora do ar trava por ~20 s)
function Checar-Atualizacao([int]$ms = 3000) {
  $origem = Origem-Atualizacao
  $ps = [powershell]::Create()
  [void]$ps.AddScript({ param($p) $a = Join-Path $p 'versao.txt'; if (Test-Path $a) { [IO.File]::ReadAllText($a, [Text.Encoding]::UTF8) } }).AddArgument($origem)
  $h = $ps.BeginInvoke()
  $txt = $null
  if ($h.AsyncWaitHandle.WaitOne($ms)) { try { $txt = [string](@($ps.EndInvoke($h)) -join '') } catch {} }
  else { [void]$ps.BeginStop($null, $null) }
  if (-not $txt) { return $null }
  $tmp = [IO.Path]::GetTempFileName()
  try { [IO.File]::WriteAllText($tmp, $txt, (New-Object Text.UTF8Encoding $true)); $r = Ler-Versao $tmp } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
  if ($r) { $r | Add-Member Pasta $origem }
  return $r
}
# quando a automacao para com erro em outro PC copia print + log da rodada + imagens do OCR para a rede
# (LUCIOLOG - PRINT SGCIPC_usuariodata_SGMn). No PC que publica (tem PUBLICAR.bat) nao envia.
$PASTA_LOG_REDE = Join-Path (Split-Path $ORIGEM_PADRAO -Parent) 'LOG - PRINT SGCI'
function Enviar-Erro([string]$msg, [string]$print) {
  try {
    if ($COPIA_TESTE -or (Test-Path (Join-Path $PASTA 'PUBLICAR.bat'))) { return }
    $loc = Join-Path $PASTA_TEMP 'envio_erro'
    New-Item -ItemType Directory -Force $loc | Out-Null
    Get-ChildItem $loc -File | ForEach-Object { $_.Delete() }
    # parte do log.txt escrita nesta rodada
    $txt = ''
    if (Test-Path $ARQ_LOG) {
      $fs = [IO.File]::Open($ARQ_LOG, 'Open', 'Read', 'ReadWrite')
      try {
        $ini = [long]$script:logInicio; if ($ini -gt $fs.Length) { $ini = 0 }
        [void]$fs.Seek($ini, 'Begin'); $txt = (New-Object IO.StreamReader($fs, [Text.Encoding]::UTF8)).ReadToEnd()
      } finally { $fs.Dispose() }
    }
    $cab = "PC: $env:COMPUTERNAME | usuário: $env:USERNAME | versão: $((Versao-Local).Texto) | tela: $([Windows.Forms.SystemInformation]::VirtualScreen.Size)`r`nSGM: $($script:sgmAtual)`r`nERRO: $msg`r`n`r`n----- log desta rodada -----`r`n"
    [IO.File]::WriteAllText((Join-Path $loc 'log.txt'), $cab + $txt, (New-Object Text.UTF8Encoding $true))
    $arqs = @(Join-Path $loc 'log.txt')
    if ($print -and (Test-Path $print)) { $arqs += $print }
    if (Test-Path $PASTA_ERROS) { $arqs += @(Get-ChildItem $PASTA_ERROS -Filter 'ocr_*.png' | Where-Object { $_.LastWriteTime -ge $script:inicioRodada } | ForEach-Object { $_.FullName }) }
    $dest = Join-Path $PASTA_LOG_REDE ("$env:COMPUTERNAME`_$env:USERNAME`_" + (Get-Date -Format 'yyyy-MM-dd_HHmmss') + "_SGM$($script:sgmAtual)")
    # copia num processo a parte com limite de tempo (rede fora do ar  outra localidade nao trava a automacao)
    $ps = [powershell]::Create()
    [void]$ps.AddScript({ param($d, $a) New-Item -ItemType Directory -Force $d | Out-Null; foreach ($x in $a) { Copy-Item $x $d -Force }; 'ok' }).AddArgument($dest).AddArgument($arqs)
    $h = $ps.BeginInvoke()
    if ($h.AsyncWaitHandle.WaitOne(20000) -and (@($ps.EndInvoke($h)) -contains 'ok')) { Log "      erro enviado para a rede: $dest" }
    else { [void]$ps.BeginStop($null, $null); Log '      (não consegui enviar o erro para a pasta da rede)' }
  } catch { try { Log "      (não consegui enviar o erro para a pasta da rede: $($_.Exception.Message))" } catch {} }
}
# confere se o automacao.ps1 e um script inteiro desta automacao (sintaxe ok, UTF-8 com BOM)
function Script-Valido([string]$arq) {
  $b = [IO.File]::ReadAllBytes($arq)
  if ($b.Length -lt 1000 -or $b[0] -ne 0xEF -or $b[1] -ne 0xBB -or $b[2] -ne 0xBF) { return 'arquivo incompleto ou sem codificação UTF-8 (BOM)' }
  if (-not ([IO.File]::ReadAllText($arq, [Text.Encoding]::UTF8) -match 'Automacao SGM - Excel - SGCI')) { return 'não é o script da automação' }
  $e = $null; [void][Management.Automation.Language.Parser]::ParseFile($arq, [ref]$null, [ref]$e)
  if ($e.Count) { return "erro de sintaxe na linha $($e[0].Extent.StartLineNumber): $($e[0].Message)" }
  return $null
}
function Instalar-Atualizacao($remota) {
  $local = Versao-Local
  $tmp = Join-Path $PASTA_TEMP 'atualizacao'
  New-Item -ItemType Directory -Force $tmp | Out-Null
  Get-ChildItem $tmp -File | ForEach-Object { $_.Delete() }
  foreach ($a in $ARQS_PROGRAMA) {
    $src = Join-Path $remota.Pasta (Nome-Rede $a)
    if (-not (Test-Path $src)) { throw "Arquivo '$(Nome-Rede $a)' não está na pasta de atualização." }
    Copy-Item $src (Join-Path $tmp $a) -Force
  }
  $nova = Ler-Versao (Join-Path $tmp 'versao.txt')
  if (-not $nova -or $nova.Versao -le $local.Versao) { throw 'A versão da pasta de atualização não é mais nova que a instalada.' }
  $prob = Script-Valido (Join-Path $tmp 'automacao.ps1')
  if ($prob) { throw "A versão $($nova.Texto) da rede está com problema ($prob). Nada foi alterado." }
  # guarda a versao atual e troca os arquivos do programa
  $bk = Join-Path $PASTA ("backup\v" + $local.Texto + '_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
  New-Item -ItemType Directory -Force $bk | Out-Null
  foreach ($a in $ARQS_PROGRAMA) { $atual = Join-Path $PASTA $a; if (Test-Path $atual) { Copy-Item $atual (Join-Path $bk $a) -Force } }
  foreach ($a in $ARQS_PROGRAMA) { Copy-Item (Join-Path $tmp $a) (Join-Path $PASTA $a) -Force }
  Log "##### ATUALIZADO: v$($local.Texto) -> v$($nova.Texto) (cópia anterior em $bk)"
  return $nova
}
# retoma um SGM que ja foi encaminhado Rascunho (MQ  Nº  AGU) - Visao Medicao (FSAAC) - materiais - LMN
function Continuar-Sgm([string]$sgm, [string]$med) {
  $script:sgmAtual = $sgm
  [void](SGM-Principal)
  if ($sgm -notmatch '^\d{6,15}$') { Fail "SGM inválido: '$sgm'." }
  if ($med) {
    if ($med -notmatch '^\d+$') { Fail "Nº da Medição inválido: '$med'." }
    Log "##### CONTINUAR SGM $sgm a partir do Rascunho (Nº Medição $med)"
    SGM-AtualizarRascunho ([pscustomobject]@{ Rascunho = '' }) $sgm $med
  } else {
    Log "##### CONTINUAR SGM $sgm a partir da Visão Medição (FSAAC)"
  }
  SGM-Finalizar $sgm
  $pesqFim = SGM-VoltarRascunho $sgm
  [void](SGCI-Principal)
  $lidos = SGM-LerMateriais $sgm $pesqFim ''
  Processar-Materiais $sgm $lidos $med
  Excel-Fechar
  Add-Content -Path $ARQ_CONCL -Value $sgm -Encoding UTF8
  Log "===== SGM $sgm CONCLUÍDO (continuação) ====="
}
# automacao_sem_impressao.ps1 = copia DESTE arquivo com $SEM_IMPRESSAO = $true (pula Ata Provisória,
# impressão da medição e LMN). E sempre recriado a partir daqui - as correções valem para os dois.
$ARQ_SEM_IMPRESSAO = Join-Path $PASTA 'automacao_sem_impressao.ps1'
function Gerar-SemImpressao {
  try {
    $txt = [IO.File]::ReadAllText((Join-Path $PASTA 'automacao.ps1'), [Text.Encoding]::UTF8)
    $novo = ([regex]'(?m)^\$SEM_IMPRESSAO(\s*)= \$false').Replace($txt, '$$SEM_IMPRESSAO$1= $$true', 1)
    if ($novo -eq $txt) { Log '   (não consegui gerar o automacao_sem_impressao.ps1: marcador não encontrado)'; return }
    $novo = ([regex]'(?m)^#  Executar pelo INICIAR\.bat').Replace($novo, '#  VERSAO SEM IMPRESSAO - gerada automaticamente pelo automacao.ps1: NAO EDITE ESTE ARQUIVO', 1)
    if ((Test-Path $ARQ_SEM_IMPRESSAO) -and [IO.File]::ReadAllText($ARQ_SEM_IMPRESSAO, [Text.Encoding]::UTF8) -eq $novo) { return }
    [IO.File]::WriteAllText($ARQ_SEM_IMPRESSAO, $novo, (New-Object Text.UTF8Encoding $true))
  } catch { Log "   (não consegui gerar o automacao_sem_impressao.ps1: $($_.Exception.Message))" }
}
# cria os atalhos .bat que faltarem na pasta (PCs que atualizaram de uma versao que nao copiava esses arquivos)
function Garantir-Atalhos {
  if ($SEM_IMPRESSAO) { return }
  Gerar-SemImpressao
  $cont = Join-Path $PASTA 'CONTINUAR.bat'
  if (Test-Path $cont) { return }
  $txt = @(
    '@echo off', 'title Continuar um SGM ja encaminhado', 'cd /d "%~dp0"', 'echo.',
    'echo  CONTINUAR para um SGM que JA FOI ENCAMINHADO no SGCI.',
    'echo  Faz Rascunho (MQ / N. Medicao / AGU) - Visao Medicao (FSAAC)',
    'echo       - materiais (Requisicao de Material) - LMN.',
    'echo  Se o MQ ou o FSAAC ja estiverem feitos, ele so confere e segue.',
    'echo  ATENCAO: os materiais desse SGM ainda NAO podem ter sido digitados.', 'echo.',
    'set /p SGM=  Digite o SGM (Cod. Obra): ', 'set /p MED=  Digite o N. da Medicao do SGCI: ', 'echo.',
    'if "%SGM%"=="" goto fim', 'if "%MED%"=="" goto fim',
    'start "Automacao SGCI - continuar" /min powershell -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0automacao.ps1" -Finalizar %SGM% -Medicao %MED%',
    ':fim') -join "`r`n"
  try { [IO.File]::WriteAllText($cont, $txt + "`r`n", [Text.Encoding]::ASCII); Log '   CONTINUAR.bat criado na pasta' } catch {}
}
# PUBLICAR.bat (so no PC de quem mantem o script) manda esta versao para a pasta oficial
function Publicar-Versao {
  $origem = Origem-Atualizacao
  $prob = Script-Valido (Join-Path $PASTA 'automacao.ps1')
  if ($prob) { Fail "O automacao.ps1 deste PC está com problema ($prob). Nada foi publicado." }
  $par = Split-Path $origem -Parent
  if (-not (Test-Path $par)) { Fail "Não consegui acessar a pasta de rede: $par" }
  if (-not (Test-Path $origem)) { New-Item -ItemType Directory -Force $origem | Out-Null }
  $remota = Ler-Versao (Join-Path $origem 'versao.txt'); $local = Versao-Local
  $hoje = Get-Date -Format 'yyyy.MM.dd'; $n = 1
  foreach ($x in @($remota, $local)) { if ($x -and $x.Texto -like "$hoje.*") { $n = [Math]::Max($n, $x.Versao.Revision + 1) } }
  $novo = "$hoje.$n"
  Add-Type -AssemblyName Microsoft.VisualBasic
  $notas = [Microsoft.VisualBasic.Interaction]::InputBox("Publicar a versão $novo para todos os PCs.`n`nO que mudou? (aparece para quem for atualizar)", 'Publicar atualização', '')
  if (-not $notas.Trim()) { Msg 'Publicação cancelada (sem descrição).' 'Publicar'; return }
  $r = Msg ("Publicar v$novo na pasta:`n$origem`n`nO que mudou: $notas") 'Publicar atualização' 'YesNo' 'Question'
  if ($r -ne 'Yes') { return }
  # a versao nova so vale neste PC depois que a copia na rede deu certo
  New-Item -ItemType Directory -Force $PASTA_TEMP | Out-Null
  $verTmp = Join-Path $PASTA_TEMP 'versao_publicar.txt'
  [IO.File]::WriteAllText($verTmp, ($novo + "`r`n" + $notas.Trim() + "`r`n"), (New-Object Text.UTF8Encoding $true))
  # copia com nome temporario e renomeia; versao.txt por ultimo (quem checar no meio do caminho ainda ve a versao antiga)
  foreach ($a in $ARQS_PROGRAMA) {   # versao.txt e o ultimo da lista
    $src = Join-Path $PASTA $a; if ($a -eq 'versao.txt') { $src = $verTmp }
    $dst = Join-Path $origem (Nome-Rede $a); $tmp = "$dst.novo"
    try {
      Copy-Item $src $tmp -Force -ErrorAction Stop
      try { if (Test-Path $dst) { [IO.File]::Replace($tmp, $dst, $null) } else { [IO.File]::Move($tmp, $dst) } }
      catch { Copy-Item $tmp $dst -Force -ErrorAction Stop; Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    } catch { Fail "Não consegui gravar '$(Nome-Rede $a)' na pasta da rede: $($_.Exception.Message)" }
  }
  $prob = Script-Valido (Join-Path $origem (Nome-Rede 'automacao.ps1'))
  if ($prob) { Fail "A cópia na rede ficou com problema ($prob). Rode o PUBLICAR de novo." }
  Copy-Item $verTmp $ARQ_VERSAO -Force
  Log "##### PUBLICADO v$novo em $origem - $notas"
  Msg "Versão $novo publicada.`n`nOs outros PCs vão ver o botão Atualizar ao abrir a automação." 'Publicado' 'OK' 'Success'
}

# =====================================================================
#  HUB (tela inicial, tema café)
# =====================================================================
function Ler-ListaSgm([string]$texto) {
  $tok = @($texto -split '[\s,;]+' | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  $feitos = @(); if (Test-Path $ARQ_CONCL) { $feitos = @(Get-Content $ARQ_CONCL -Encoding UTF8 | ForEach-Object { $_.Trim() }) }
  $validos = @($tok | Where-Object { $_ -match '^\d{6,15}$' } | Select-Object -Unique)
  [pscustomobject]@{
    Validos   = $validos
    Pendentes = @($validos | Where-Object { $feitos -notcontains $_ })
    Feitos    = @($validos | Where-Object { $feitos -contains $_ })
    Invalidos = @($tok | Where-Object { $_ -notmatch '^\d{6,15}$' } | Select-Object -Unique)
  }
}
# lista SGM  Nº Medição (um par por linha) para continuar SGMs ja encaminhados
function Ler-ListaContinuar([string]$texto) {
  $feitos = @(); if (Test-Path $ARQ_CONCL) { $feitos = @(Get-Content $ARQ_CONCL -Encoding UTF8 | ForEach-Object { $_.Trim() }) }
  $ok = @(); $inv = @(); $ja = @()
  foreach ($ln in @($texto -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    if ($ln -match '^(\d{6,15})[\s;,-]+(\d{3,})$') {
      if ($feitos -contains $Matches[1]) { $ja += $Matches[1] }
      elseif (-not ($ok | Where-Object { $_.Sgm -eq $Matches[1] })) { $ok += [pscustomobject]@{ Sgm = $Matches[1]; Medicao = $Matches[2] } }
    } else { $inv += $ln }
  }
  [pscustomobject]@{ Pares = $ok; Invalidos = $inv; Feitos = $ja }
}
function Show-Continuar {
  $C = $script:hubC; $fonte = 'Segoe UI'; $larg = 500; $alt = 470
  $f = New-Object Windows.Forms.Form
  $f.FormBorderStyle = 'None'; $f.StartPosition = 'CenterScreen'; $f.ClientSize = New-Object Drawing.Size($larg, $alt)
  $f.BackColor = $C.Creme; $f.Text = 'Continuar SGM'; $f.ShowInTaskbar = $false; $f.TopMost = $true
  $f.Font = New-Object Drawing.Font($fonte, 10); $f.Region = New-Object Drawing.Region (Caminho-Arredondado 0 0 $larg $alt 18)
  $cab = New-Object Windows.Forms.Panel; $cab.Dock = 'Top'; $cab.Height = 70; $cab.BackColor = $C.Espresso; $f.Controls.Add($cab)
  $tit = New-Object Windows.Forms.Label; $tit.Text = 'Continuar SGM já encaminhado'; $tit.AutoSize = $true
  $tit.Font = New-Object Drawing.Font('Georgia', 15, [Drawing.FontStyle]::Bold); $tit.ForeColor = $C.Creme; $tit.BackColor = $C.Espresso
  $tit.Location = New-Object Drawing.Point(26, 22); $cab.Controls.Add($tit)
  $exp = New-Object Windows.Forms.Label; $exp.AutoSize = $false; $exp.Size = New-Object Drawing.Size(($larg - 52), 62); $exp.Location = New-Object Drawing.Point(26, 82)
  $exp.ForeColor = $C.Texto; $exp.Font = New-Object Drawing.Font($fonte, 9.5)
  $exp.Text = "Para SGMs já encaminhados no SGCI: faz MQ / Nº / AGU, FSAAC, materiais e LMN (o que já estiver feito ele só confere).`nUm por linha:  SGM  e  Nº da Medição   (ex: 2026700391  90665)"
  $f.Controls.Add($exp)
  $mol = New-Object Windows.Forms.Panel; $mol.Location = New-Object Drawing.Point(26, 150); $mol.Size = New-Object Drawing.Size(($larg - 52), 170)
  $mol.BackColor = $C.Borda; $mol.Padding = New-Object Windows.Forms.Padding(1)
  $tb = New-Object Windows.Forms.TextBox; $tb.Multiline = $true; $tb.ScrollBars = 'Vertical'; $tb.Dock = 'Fill'; $tb.BorderStyle = 'None'
  $tb.Font = New-Object Drawing.Font('Consolas', 12); $tb.ForeColor = $C.Texto; $tb.BackColor = [Drawing.Color]::White
  $mol.Controls.Add($tb); $f.Controls.Add($mol)
  $info = New-Object Windows.Forms.Label; $info.AutoSize = $false; $info.Size = New-Object Drawing.Size(($larg - 52), 44); $info.Location = New-Object Drawing.Point(26, 326)
  $info.Font = New-Object Drawing.Font($fonte, 9.5); $info.ForeColor = $C.Suave; $f.Controls.Add($info)
  $aviso = New-Object Windows.Forms.Label; $aviso.AutoSize = $false; $aviso.Size = New-Object Drawing.Size(($larg - 52), 22); $aviso.Location = New-Object Drawing.Point(26, 372)
  $aviso.Font = New-Object Drawing.Font($fonte, 9, [Drawing.FontStyle]::Bold); $aviso.ForeColor = $C.Erro
  $aviso.Text = 'Só use se os materiais desse SGM ainda NÃO foram digitados.'; $f.Controls.Add($aviso)
  $rod = New-Object Windows.Forms.Panel; $rod.Dock = 'Bottom'; $rod.Height = 64; $rod.BackColor = [Drawing.Color]::FromArgb(240, 228, 214); $f.Controls.Add($rod)
  $btOk = New-Object Windows.Forms.Button; $btOk.Text = 'Continuar'; $btOk.Size = New-Object Drawing.Size(150, 40); $btOk.Location = New-Object Drawing.Point(($larg - 176), 12)
  $btOk.FlatStyle = 'Flat'; $btOk.FlatAppearance.BorderSize = 0; $btOk.BackColor = $C.Cafe; $btOk.ForeColor = $C.Creme
  $btOk.FlatAppearance.MouseOverBackColor = $C.CafeHov; $btOk.Font = New-Object Drawing.Font($fonte, 11, [Drawing.FontStyle]::Bold); $btOk.Cursor = [Windows.Forms.Cursors]::Hand
  $rod.Controls.Add($btOk)
  $btCan = New-Object Windows.Forms.Button; $btCan.Text = 'Voltar'; $btCan.Size = New-Object Drawing.Size(110, 40); $btCan.Location = New-Object Drawing.Point(($larg - 296), 12)
  $btCan.FlatStyle = 'Flat'; $btCan.FlatAppearance.BorderColor = $C.Latte; $btCan.BackColor = $C.Creme; $btCan.ForeColor = $C.Texto; $btCan.Cursor = [Windows.Forms.Cursors]::Hand
  $btCan.Add_Click({ $this.FindForm().Close() }); $rod.Controls.Add($btCan); $f.CancelButton = $btCan
  $f.Add_Paint({ $_.Graphics.SmoothingMode = 'AntiAlias'; $_.Graphics.DrawPath((New-Object Drawing.Pen $script:hubC.Borda), (Caminho-Arredondado 0 0 ($this.ClientSize.Width - 1) ($this.ClientSize.Height - 1) 18)) })

  $script:contTb = $tb; $script:contInfo = $info; $script:contOk = $btOk; $script:contRes = $null
  $val = {
    $C = $script:hubC; $l = Ler-ListaContinuar $script:contTb.Text
    $t = "SGMs para continuar: $($l.Pares.Count)"
    if ($l.Feitos.Count) { $t += "   •   já concluídos (pulados): $($l.Feitos.Count)" }
    if ($l.Invalidos.Count) { $t += "`nLinha inválida: " + (($l.Invalidos | Select-Object -First 2) -join '  |  '); $script:contInfo.ForeColor = $C.Erro } else { $script:contInfo.ForeColor = $C.Suave }
    $script:contInfo.Text = $t
    $script:contOk.Enabled = ($l.Pares.Count -gt 0 -and $l.Invalidos.Count -eq 0)
    if ($script:contOk.Enabled) { $script:contOk.BackColor = $C.Cafe } else { $script:contOk.BackColor = $C.Latte }
  }
  $tb.Add_TextChanged($val); & $val
  $btOk.Add_Click({ $script:contRes = (Ler-ListaContinuar $script:contTb.Text).Pares; $this.FindForm().Close() })
  $f.Add_Shown({ [void][U]::Activate($this.Handle); $this.Activate(); [void]$script:contTb.Focus() })
  [void]$f.ShowDialog(); $f.Dispose()
  return $script:contRes
}
function Show-Hub {
  $C = @{
    Espresso = [Drawing.Color]::FromArgb(62, 39, 35);   Cafe    = [Drawing.Color]::FromArgb(111, 78, 55)
    CafeHov  = [Drawing.Color]::FromArgb(139, 94, 60);  Caramelo = [Drawing.Color]::FromArgb(192, 133, 82)
    Latte    = [Drawing.Color]::FromArgb(215, 184, 153); Creme   = [Drawing.Color]::FromArgb(250, 244, 236)
    Texto    = [Drawing.Color]::FromArgb(78, 52, 46);   Suave    = [Drawing.Color]::FromArgb(141, 110, 99)
    Borda    = [Drawing.Color]::FromArgb(222, 205, 188); Erro    = [Drawing.Color]::FromArgb(183, 28, 28)
  }
  $fonte = 'Segoe UI'
  $larg = 560; $alt = 570
  # versao instalada x versao oficial na rede (se a rede nao responder em 3 s, segue sem aviso)
  $vLocal = Versao-Local
  # (a versao sem impressao nao atualiza sozinha ela e recriada pelo automacao.ps1)
  $vRede = $null; if (-not $COPIA_TESTE -and -not $SEM_IMPRESSAO) { try { $vRede = Checar-Atualizacao 3000 } catch {} }
  $temNova = ($vRede -and $vRede.Versao -gt $vLocal.Versao)
  $alt += 50   # botao Continuar SGM ja encaminhado
  if (-not $SEM_IMPRESSAO) { $alt += 50 }   # botao Iniciar SEM impressão
  if ($temNova) { $alt += 58 }
  $f = New-Object Windows.Forms.Form
  $f.FormBorderStyle = 'None'; $f.StartPosition = 'CenterScreen'; $f.ClientSize = New-Object Drawing.Size($larg, $alt)
  $f.BackColor = $C.Creme; $f.Text = 'Automação SGCI'; $f.ShowInTaskbar = $true; $f.KeyPreview = $true
  $f.Font = New-Object Drawing.Font($fonte, 10)
  $f.Region = New-Object Drawing.Region (Caminho-Arredondado 0 0 $larg $alt 18)

  # ---- cabecalho com a xicara
  $cab = New-Object Windows.Forms.Panel; $cab.Dock = 'Top'; $cab.Height = 100; $cab.BackColor = $C.Espresso
  $f.Controls.Add($cab)

  $tit = New-Object Windows.Forms.Label; $tit.Text = 'Automação SGCI'; if ($COPIA_TESTE) { $tit.Text += ' (TESTE)'; $f.Text += ' (TESTE)' }; $tit.AutoSize = $true
  $tit.Font = New-Object Drawing.Font('Georgia', 22, [Drawing.FontStyle]::Bold); $tit.ForeColor = $C.Creme; $tit.BackColor = $C.Espresso
  $tit.Location = New-Object Drawing.Point(30, 30); $cab.Controls.Add($tit)
  if ($SEM_IMPRESSAO) {
    $tit.Location = New-Object Drawing.Point(30, 18); $f.Text += ' - SEM IMPRESSÃO'
    $sub = New-Object Windows.Forms.Label; $sub.Text = 'SEM IMPRESSÃO  •  não imprime Ata Provisória, medição nem LMN'; $sub.AutoSize = $true
    $sub.Font = New-Object Drawing.Font($fonte, 10, [Drawing.FontStyle]::Bold); $sub.ForeColor = $C.Caramelo; $sub.BackColor = $C.Espresso
    $sub.Location = New-Object Drawing.Point(32, 66); $cab.Controls.Add($sub)
  }
  $fechar = New-Object Windows.Forms.Label; $fechar.Text = [string][char]0x2715; $fechar.AutoSize = $true; $fechar.Cursor = [Windows.Forms.Cursors]::Hand
  $fechar.Font = New-Object Drawing.Font($fonte, 13); $fechar.ForeColor = $C.Latte; $fechar.BackColor = $C.Espresso
  $fechar.Location = New-Object Drawing.Point(($larg - 36), 10); $fechar.Add_Click({ $this.FindForm().Close() }); $cab.Controls.Add($fechar)

  # ---- corpo
  $lbl = New-Object Windows.Forms.Label; $lbl.Text = 'SGMs (Cód. Obra) - um por linha'; $lbl.AutoSize = $true
  $lbl.Font = New-Object Drawing.Font($fonte, 10.5, [Drawing.FontStyle]::Bold); $lbl.ForeColor = $C.Texto
  $lbl.Location = New-Object Drawing.Point(30, 120); $f.Controls.Add($lbl)

  $moldura = New-Object Windows.Forms.Panel; $moldura.Location = New-Object Drawing.Point(30, 146); $moldura.Size = New-Object Drawing.Size(($larg - 60), 230)
  $moldura.BackColor = $C.Borda; $moldura.Padding = New-Object Windows.Forms.Padding(1)
  $tb = New-Object Windows.Forms.TextBox; $tb.Multiline = $true; $tb.ScrollBars = 'Vertical'; $tb.Dock = 'Fill'; $tb.BorderStyle = 'None'
  $tb.Font = New-Object Drawing.Font('Consolas', 12); $tb.ForeColor = $C.Texto; $tb.BackColor = [Drawing.Color]::White
  $moldura.Controls.Add($tb); $f.Controls.Add($moldura)
  # preenche com os pendentes do SGMs.txt
  if (Test-Path $ARQ_SGMS) {
    $ini = Ler-ListaSgm ((Get-Content $ARQ_SGMS -Encoding UTF8) -join "`n")
    $tb.Text = ($ini.Pendentes -join "`r`n")
  }

  $info = New-Object Windows.Forms.Label; $info.AutoSize = $false; $info.Size = New-Object Drawing.Size(($larg - 60), 40)
  $info.Location = New-Object Drawing.Point(30, 382); $info.Font = New-Object Drawing.Font($fonte, 9.5); $info.ForeColor = $C.Suave
  $f.Controls.Add($info)

  $chk = New-Object Windows.Forms.CheckBox; $chk.Text = 'Pedir minha confirmação antes de encaminhar / gravar / imprimir'
  if ($SEM_IMPRESSAO) { $chk.Text = 'Pedir minha confirmação antes de encaminhar / gravar' }
  $chk.Checked = [bool]$MODO_TESTE; $chk.AutoSize = $true; $chk.ForeColor = $C.Texto; $chk.Cursor = [Windows.Forms.Cursors]::Hand
  $chk.Location = New-Object Drawing.Point(30, 426); $f.Controls.Add($chk)

  $dica = New-Object Windows.Forms.Label; $dica.AutoSize = $true; $dica.ForeColor = $C.Suave; $dica.Font = New-Object Drawing.Font($fonte, 9)
  $dica.Text = "Deixe o SGM no Rascunho de Medição e o SGCI aberto.`nDurante o processo não mexa no mouse/teclado  •  para parar segure ESC"
  $dica.Location = New-Object Drawing.Point(30, 456); $f.Controls.Add($dica)

  # ---- rodape
  $rod = New-Object Windows.Forms.Panel; $rod.Dock = 'Bottom'; $rod.Height = 64; $rod.BackColor = [Drawing.Color]::FromArgb(240, 228, 214)
  $f.Controls.Add($rod)
  $btIni = New-Object Windows.Forms.Button; $btIni.Text = 'Iniciar'
  $btIni.Size = New-Object Drawing.Size(150, 40); $btIni.Location = New-Object Drawing.Point(($larg - 180), 12)
  $btIni.FlatStyle = 'Flat'; $btIni.FlatAppearance.BorderSize = 0; $btIni.BackColor = $C.Cafe; $btIni.ForeColor = $C.Creme
  $btIni.FlatAppearance.MouseOverBackColor = $C.CafeHov; $btIni.Font = New-Object Drawing.Font('Segoe UI Symbol', 11, [Drawing.FontStyle]::Bold); $btIni.Cursor = [Windows.Forms.Cursors]::Hand
  $rod.Controls.Add($btIni)
  $btCan = New-Object Windows.Forms.Button; $btCan.Text = 'Cancelar'
  $btCan.Size = New-Object Drawing.Size(110, 40); $btCan.Location = New-Object Drawing.Point(($larg - 300), 12)
  $btCan.FlatStyle = 'Flat'; $btCan.FlatAppearance.BorderColor = $C.Latte; $btCan.BackColor = $C.Creme; $btCan.ForeColor = $C.Texto
  $btCan.Font = New-Object Drawing.Font($fonte, 10); $btCan.Cursor = [Windows.Forms.Cursors]::Hand
  $btCan.Add_Click({ $this.FindForm().Close() }); $rod.Controls.Add($btCan)
  $lnk = New-Object Windows.Forms.LinkLabel; $lnk.Text = 'ver medições'; $lnk.AutoSize = $true
  $lnk.LinkColor = $C.Cafe; $lnk.ActiveLinkColor = $C.Caramelo; $lnk.Location = New-Object Drawing.Point(28, 13)
  $lnk.Add_LinkClicked({
    if (Test-Path $ARQ_MEDICOES) { Start-Process notepad.exe ('"' + $ARQ_MEDICOES + '"') }
    else { [void](Msg 'Nenhuma medição registrada ainda.' 'Medições') }
  }); $rod.Controls.Add($lnk)
  $ver = New-Object Windows.Forms.Label; $ver.AutoSize = $true; $ver.ForeColor = $C.Suave; $ver.BackColor = $rod.BackColor
  $ver.Font = New-Object Drawing.Font($fonte, 8.5); $ver.Location = New-Object Drawing.Point(30, 36)
  $ver.Text = "versão $($vLocal.Texto)"; if ($vRede -and -not $temNova) { $ver.Text += '  •  atualizada' }
  $rod.Controls.Add($ver)
  $f.CancelButton = $btCan

  # ---- continuar SGMs que ja foram encaminhados (MQ  FSAAC  materiais  LMN)
  $btCont = New-Object Windows.Forms.Button; $btCont.Text = 'Continuar SGM já encaminhado  (MQ / FSAAC / materiais)'
  $btCont.Size = New-Object Drawing.Size(($larg - 60), 38); $btCont.Location = New-Object Drawing.Point(30, 502)
  $btCont.FlatStyle = 'Flat'; $btCont.FlatAppearance.BorderColor = $C.Caramelo; $btCont.BackColor = [Drawing.Color]::White; $btCont.ForeColor = $C.Cafe
  $btCont.FlatAppearance.MouseOverBackColor = [Drawing.Color]::FromArgb(250, 238, 224); $btCont.Font = New-Object Drawing.Font($fonte, 10, [Drawing.FontStyle]::Bold)
  $btCont.Cursor = [Windows.Forms.Cursors]::Hand; $f.Controls.Add($btCont)
  $btCont.Add_Click({
    $pares = Show-Continuar
    if ($pares) { $script:hubResultado = [pscustomobject]@{ Continuar = $pares; Confirmar = $script:hubChk.Checked }; $this.FindForm().Close() }
  })

  # ---- mesmo processo sem imprimir nada (abre o automacao_sem_impressao.ps1)
  $yAviso = 552
  if (-not $SEM_IMPRESSAO) {
    $btSem = New-Object Windows.Forms.Button; $btSem.Text = 'Iniciar SEM impressão  (sem Ata Provisória, medição e LMN)'
    $btSem.Size = New-Object Drawing.Size(($larg - 60), 38); $btSem.Location = New-Object Drawing.Point(30, 552)
    $btSem.FlatStyle = 'Flat'; $btSem.FlatAppearance.BorderColor = $C.Caramelo; $btSem.BackColor = [Drawing.Color]::White; $btSem.ForeColor = $C.Cafe
    $btSem.FlatAppearance.MouseOverBackColor = [Drawing.Color]::FromArgb(250, 238, 224); $btSem.Font = New-Object Drawing.Font($fonte, 10, [Drawing.FontStyle]::Bold)
    $btSem.Cursor = [Windows.Forms.Cursors]::Hand; $f.Controls.Add($btSem)
    $btSem.Add_Click({ $script:hubResultado = [pscustomobject]@{ SemImpressao = $true; Texto = $script:hubTb.Text }; $this.FindForm().Close() })
    $yAviso = 602
  }

  # ---- aviso de versao nova
  if ($temNova) {
    $av = New-Object Windows.Forms.Panel; $av.Location = New-Object Drawing.Point(30, $yAviso); $av.Size = New-Object Drawing.Size(($larg - 60), 48)
    $av.BackColor = [Drawing.Color]::FromArgb(253, 236, 200); $f.Controls.Add($av)
    $avT = New-Object Windows.Forms.Label; $avT.AutoSize = $false; $avT.Location = New-Object Drawing.Point(12, 4); $avT.Size = New-Object Drawing.Size(($larg - 60 - 140), 42)
    $avT.ForeColor = $C.Texto; $avT.Font = New-Object Drawing.Font($fonte, 9)
    $nota = ($vRede.Notas -split "`n")[0]; if ($nota.Length -gt 70) { $nota = $nota.Substring(0, 67) + '...' }
    $avT.Text = "Nova versão $($vRede.Texto) disponível`n$nota"; $avT.TextAlign = 'MiddleLeft'; $av.Controls.Add($avT)
    $btAt = New-Object Windows.Forms.Button; $btAt.Text = 'Atualizar'; $btAt.Size = New-Object Drawing.Size(110, 32)
    $btAt.Location = New-Object Drawing.Point(($larg - 60 - 122), 8); $btAt.FlatStyle = 'Flat'; $btAt.FlatAppearance.BorderSize = 0
    $btAt.BackColor = $C.Caramelo; $btAt.ForeColor = [Drawing.Color]::White; $btAt.Font = New-Object Drawing.Font($fonte, 10, [Drawing.FontStyle]::Bold)
    $btAt.Cursor = [Windows.Forms.Cursors]::Hand; $av.Controls.Add($btAt)
    $script:hubRede = $vRede
    $btAt.Add_Click({ $script:hubResultado = [pscustomobject]@{ Atualizar = $true; Remota = $script:hubRede }; $this.FindForm().Close() })
  }

  # validacao ao vivo (os eventos usam variaveis $script para enxergar os controles)
  $script:hubTb = $tb; $script:hubInfo = $info; $script:hubBtIni = $btIni; $script:hubChk = $chk; $script:hubC = $C
  $atualizar = {
    $C = $script:hubC
    $l = Ler-ListaSgm $script:hubTb.Text
    $txt = "Na fila: $($l.Pendentes.Count)"
    if ($l.Feitos.Count) { $txt += "   •   já concluídos (serão pulados): $($l.Feitos.Count)" }
    if ($l.Invalidos.Count) { $txt += "`nInválido(s): " + (($l.Invalidos | Select-Object -First 4) -join ', '); $script:hubInfo.ForeColor = $C.Erro } else { $script:hubInfo.ForeColor = $C.Suave }
    $script:hubInfo.Text = $txt
    $script:hubBtIni.Enabled = ($l.Pendentes.Count -gt 0 -and $l.Invalidos.Count -eq 0)
    if ($script:hubBtIni.Enabled) { $script:hubBtIni.BackColor = $C.Cafe } else { $script:hubBtIni.BackColor = $C.Latte }
  }
  $tb.Add_TextChanged($atualizar)
  & $atualizar

  $script:hubResultado = $null
  $btIni.Add_Click({
    $l = Ler-ListaSgm $script:hubTb.Text
    $script:hubResultado = [pscustomobject]@{ Sgms = $l.Pendentes; Confirmar = $script:hubChk.Checked }
    $this.FindForm().Close()
  })

  # arrastar pelo cabecalho
  $md = { if ($_.Button -eq 'Left') { $script:hubPos = [Windows.Forms.Cursor]::Position; $script:hubOrig = $this.FindForm().Location } }
  $mm = { if ($_.Button -eq 'Left' -and $script:hubPos) { $p = [Windows.Forms.Cursor]::Position; $fm = $this.FindForm(); $fm.Location = New-Object Drawing.Point(($script:hubOrig.X + $p.X - $script:hubPos.X), ($script:hubOrig.Y + $p.Y - $script:hubPos.Y)) } }
  foreach ($ctl in @($cab, $tit)) { $ctl.Add_MouseDown($md); $ctl.Add_MouseMove($mm) }
  $f.Add_Paint({ $_.Graphics.SmoothingMode = 'AntiAlias'; $_.Graphics.DrawPath((New-Object Drawing.Pen $script:hubC.Borda), (Caminho-Arredondado 0 0 ($this.ClientSize.Width - 1) ($this.ClientSize.Height - 1) 18)) })
  $f.Add_Shown({ [void][U]::Activate($this.Handle); $this.Activate(); [void]$script:hubTb.Focus(); $script:hubTb.SelectionStart = $script:hubTb.TextLength })
  [void]$f.ShowDialog()
  $f.Dispose()
  return $script:hubResultado
}

# =====================================================================
#  PRINCIPAL
# =====================================================================
$script:inicioRodada = (Get-Date).AddSeconds(-2)
$script:logInicio = 0; try { if (Test-Path $ARQ_LOG) { $script:logInicio = (Get-Item $ARQ_LOG).Length } } catch {}
try {
  if ([Console]::CapsLock) { [U]::keybd_event(0x14, 0, 0, [UIntPtr]::Zero); [U]::keybd_event(0x14, 0, 2, [UIntPtr]::Zero) }
  if ($Diagnostico) { Rodar-Diagnostico; Msg 'Diagnóstico concluído. Veja o log.txt.'; exit 0 }
  if ($Publicar) { if ($COPIA_TESTE -or $SEM_IMPRESSAO) { Msg 'Esta é a cópia de teste - publique pela pasta Automacao_SGCI.'; exit 0 }; Publicar-Versao; exit 0 }
  if ($Finalizar) {
    # retoma um SGM que ja foi encaminhado (CONTINUAR.bat)
    Continuar-Sgm $Finalizar $Medicao
    Msg "SGM $Finalizar finalizado." 'Tudo certo!' 'OK' 'Success'
    exit 0
  }
  if ($TesteLMN) {
    # TESTE so o Relatorio LMN (Controle de Material aberto, materiais ja gravados)
    $script:sgmAtual = $TesteLMN
    if ($TesteLMN -notmatch '^\d{6,15}$') { Fail "SGM inválido: '$TesteLMN'." }
    if ($Medicao -and $Medicao -notmatch '^\d+$') { Fail "Nº da Medição inválido: '$Medicao'." }
    [void](SGM-Principal); [void](SGCI-Principal)
    $cm = SGCI-Janela 'Controle de Material'
    if (-not $cm) { Fail 'Abra o Controle de Material (Requisição de Material) com a OR carregada antes de rodar o teste do LMN.' }
    $r = Msg ("Teste do RELATÓRIO LMN do SGM $TesteLMN.`n`nNão digita nem grava nada no SGCI: só gera, confere e imprime o LMN.`n`nNão mexa no mouse nem no teclado. Para parar segure ESC.") 'Teste do LMN' 'OKCancel' 'Question'
    if ($r -ne 'OK') { exit 0 }
    [U]::Minimizar([U]::GetConsoleWindow())
    Log "##### TESTE LMN - SGM $TesteLMN (Medição '$Medicao')"
    # materiais esperados le do relatorio do SGM
    $pesqFim = SGM-VoltarRascunho $TesteLMN
    $lidos = SGM-LerMateriais $TesteLMN $pesqFim ''
    if (@($lidos.Materiais).Count -eq 0) { Fail "O SGM $TesteLMN não tem materiais (só 1 - SERV.) - não há LMN para imprimir." }
    $cm = SGCI-Janela 'Controle de Material'
    if (-not $cm) { Fail 'O Controle de Material foi fechado.' }
    $script:sgciRaiz = [U]::Root($cm.H)
    Ativar $cm.H 'Controle de Material'
    if (-not (CM-ConferirCabecalho $cm $lidos.OR $Medicao)) { Fail "O Controle de Material aberto não está com a OR $($lidos.OR) carregada (na aba que está na tela)." }
    SGCI-LMN $cm $lidos.OR $Medicao @($lidos.Materiais) $TesteLMN
    Log "===== TESTE LMN - SGM $TesteLMN CONCLUÍDO ====="
    Msg "Relatório LMN do SGM $TesteLMN conferido e impresso." 'Teste concluído' 'OK' 'Success'
    exit 0
  }
  if ($TesteMateriais) {
    # TESTE so a parte de materiais de um SGM ja encaminhado (passos 12 a 18)
    $script:sgmAtual = $TesteMateriais
    if ($TesteMateriais -notmatch '^\d{6,15}$') { Fail "SGM inválido: '$TesteMateriais'." }
    if ($Medicao -and $Medicao -notmatch '^\d+$') { Fail "Nº da Medição inválido: '$Medicao'." }
    [void](SGM-Principal); [void](SGCI-Principal)
    $r = Msg ("Teste da parte de MATERIAIS do SGM $TesteMateriais.`n`nO SGM já precisa estar encaminhado no SGCI e os materiais ainda NÃO podem ter sido digitados (senão ficam em dobro).`n`nNão mexa no mouse nem no teclado. Para parar segure ESC.") 'Teste de materiais' 'OKCancel' 'Question'
    if ($r -ne 'OK') { exit 0 }
    Log "##### TESTE MATERIAIS - SGM $TesteMateriais (Medição '$Medicao')"
    $pesqFim = SGM-VoltarRascunho $TesteMateriais
    $lidos = SGM-LerMateriais $TesteMateriais $pesqFim ''
    Processar-Materiais $TesteMateriais $lidos $Medicao
    Log "===== TESTE MATERIAIS - SGM $TesteMateriais CONCLUÍDO ====="
    Msg "Parte de materiais do SGM $TesteMateriais concluída." 'Teste concluído' 'OK' 'Success'
    exit 0
  }

  # hub pede os SGMs
  Garantir-Atalhos
  $hub = Show-Hub
  if ($hub -and $hub.Atualizar) {
    try { $nova = Instalar-Atualizacao $hub.Remota }
    catch { Log "!!!!! ATUALIZAÇÃO FALHOU: $($_.Exception.Message)"; Msg ("Não consegui atualizar:`n$($_.Exception.Message)`n`nA versão atual continua instalada.") 'Atualização' 'OK' 'Error'; $nova = $null }
    if ($nova) { Msg "Automação atualizada para a versão $($nova.Texto).`n`nEla vai abrir de novo." 'Atualizado' 'OK' 'Success' }
    # reabre o hub (com a versao nova, se instalou)
    Start-Process powershell.exe -ArgumentList @('-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $PASTA 'automacao.ps1') + '"')) -WindowStyle Minimized
    exit 0
  }
  if ($hub -and $hub.SemImpressao) {
    # abre o hub da versao sem impressao com os SGMs que estavam digitados
    Set-Content -Path $ARQ_SGMS -Encoding UTF8 -Value (@('# SGMs da última execução (preenchido pelo hub)') + @($hub.Texto -split "`r?`n"))
    Gerar-SemImpressao
    if (-not (Test-Path $ARQ_SEM_IMPRESSAO)) { Fail 'Não consegui criar o automacao_sem_impressao.ps1 na pasta da automação.' }
    Start-Process powershell.exe -ArgumentList @('-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $ARQ_SEM_IMPRESSAO + '"')) -WindowStyle Minimized
    exit 0
  }
  if ($hub -and $hub.Continuar) {
    # SGMs ja encaminhados so a parte que falta (um par SGM  Nº Medição por vez)
    $pares = @($hub.Continuar)
    $MODO_TESTE = [bool]$hub.Confirmar
    [U]::Minimizar([U]::GetConsoleWindow())
    Pausa 400
    [void](SGM-Principal); [void](SGCI-Principal)
    Log "##### CONTINUAR - $($pares.Count) SGM(s): $(($pares | ForEach-Object { "$($_.Sgm)/$($_.Medicao)" }) -join ', ')"
    foreach ($p in $pares) { Continuar-Sgm $p.Sgm $p.Medicao }
    Log "##### FIM CONTINUAR - $($pares.Count) SGM(s)"
    Msg "$($pares.Count) SGM(s) finalizado(s)." 'Automação concluída' 'OK' 'Success'
    exit 0
  }
  if (-not $hub -or @($hub.Sgms).Count -eq 0) { exit 0 }
  $pendentes = @($hub.Sgms)
  $MODO_TESTE = [bool]$hub.Confirmar
  Set-Content -Path $ARQ_SGMS -Encoding UTF8 -Value (@('# SGMs da última execução (preenchido pelo hub)') + $pendentes)
  # minimiza a janela preta para nao atrapalhar os cliques
  [U]::Minimizar([U]::GetConsoleWindow())
  Pausa 400

  [void](SGM-Principal); [void](SGCI-Principal); [void](SGCI-GarantirMedicaoQuantificada)
  Log "##### INÍCIO - $($pendentes.Count) SGM(s): $($pendentes -join ', ')"
  $n = 0
  foreach ($sgm in $pendentes) {
    $script:sgmAtual = $sgm
    [void](SGM-Principal); [void](SGCI-Principal)
    Processar $sgm
    $n++
  }
  Log "##### FIM - $n SGM(s) concluído(s)"
  Msg "$n SGM(s) processado(s) com sucesso.`nOs números das medições estão em medicoes.txt." 'Automação concluída' 'OK' 'Success'
}
catch {
  $msg = $_.Exception.Message
  if ($_.Exception -isnot [FalhaAutomacao]) { $msg = "Erro inesperado: $msg`n(linha $($_.InvocationInfo.ScriptLineNumber))" }
  $print = Salvar-Print 'erro'
  Log "!!!!! ERRO (SGM $($script:sgmAtual)): $msg"
  if ($print) { Log "      print da tela: $print" }
  Enviar-Erro $msg $print
  $quem = ''; if ($script:sgmAtual) { $quem = "SGM $($script:sgmAtual)`n`n" }
  Msg ($quem + $msg + "`n`nA automação foi encerrada. Detalhes e print da tela na pasta da automação.") 'A automação parou' 'OK' 'Error'
  exit 1
}
