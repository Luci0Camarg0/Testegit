"""
Reconhecimento Facial de Festas
--------------------------------
Escolha uma pasta com fotos de um evento. O programa encontra os rostos,
agrupa as fotos por pessoa e cria:

    Eventos/festa_N/aluno_1, aluno_2, ...

Cada pasta aluno_X recebe uma copia de todas as fotos em que aquela pessoa
aparece (uma mesma foto pode ir para varias pastas).

Deteccao: YuNet  |  Reconhecimento: SFace  (modelos ONNX do OpenCV Zoo)
"""

import os
import re
import sys
import shutil
import threading
import queue
import subprocess
import urllib.request

import numpy as np
import cv2

APP_NAME = "Reconhecimento Facial"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"
MODEL_URLS = {
    DETECTOR_FILE: "https://github.com/opencv/opencv_zoo/raw/main/models/"
                   "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    RECOGNIZER_FILE: "https://github.com/opencv/opencv_zoo/raw/main/models/"
                     "face_recognition_sface/face_recognition_sface_2021dec.onnx",
}

# Ajustes de deteccao / agrupamento
DETECT_MAX_SIDE = 1920      # fotos maiores sao reduzidas so para detectar
MIN_FACE_PX = 36            # ignora rostos muito pequenos (ruido)
MIN_SCORE = 0.80            # confianca minima do detector
SAME_PERSON = 0.40          # similaridade (cosseno) para considerar a mesma pessoa


# ---------------------------------------------------------------------------
# Pastas
# ---------------------------------------------------------------------------

def app_dir():
    """Pasta onde esta o .exe (ou o .py)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """Pasta dos arquivos embutidos pelo PyInstaller."""
    return getattr(sys, "_MEIPASS", app_dir())


def _writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        test = os.path.join(path, ".teste_escrita")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return True
    except OSError:
        return False


def data_dir():
    """Pasta 'Eventos' ao lado do programa (ou em AppData se nao der)."""
    d = os.path.join(app_dir(), "Eventos")
    if _writable(d):
        return d
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "ReconhecimentoFacial", "Eventos")
    os.makedirs(d, exist_ok=True)
    return d


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def next_numbered_name(parent, prefix):
    """festa_1, festa_2, ... nunca repete um nome ja existente."""
    pat = re.compile(r"^%s_(\d+)$" % re.escape(prefix), re.IGNORECASE)
    used = [0]
    if os.path.isdir(parent):
        for n in os.listdir(parent):
            m = pat.match(n)
            if m:
                used.append(int(m.group(1)))
    return "%s_%d" % (prefix, max(used) + 1)


def list_images(folder):
    files = []
    for root, _dirs, names in os.walk(folder):
        for n in names:
            if os.path.splitext(n)[1].lower() in IMAGE_EXTS:
                files.append(os.path.join(root, n))
    files.sort(key=lambda p: natural_key(os.path.relpath(p, folder)))
    return files


def read_image(path):
    """Le imagens com acentos no caminho (cv2.imread falha no Windows)."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def open_in_explorer(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

def find_model(filename, log=print):
    for d in (os.path.join(resource_dir(), "models"),
              os.path.join(app_dir(), "models")):
        p = os.path.join(d, filename)
        if os.path.isfile(p) and os.path.getsize(p) > 10000:
            return p
    # Nao veio junto: baixa uma vez para a pasta de dados
    d = os.path.join(os.path.dirname(data_dir()), "models")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, filename)
    if not (os.path.isfile(p) and os.path.getsize(p) > 10000):
        log("Baixando modelo %s (somente na primeira vez)..." % filename)
        tmp = p + ".part"
        urllib.request.urlretrieve(MODEL_URLS[filename], tmp)
        os.replace(tmp, p)
    return p


class FaceEngine:
    def __init__(self, log=print):
        self.detector = cv2.FaceDetectorYN.create(
            find_model(DETECTOR_FILE, log), "", (320, 320), MIN_SCORE, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(
            find_model(RECOGNIZER_FILE, log), "")

    def detect(self, img):
        """Retorna linhas no formato YuNet (x, y, w, h, 10 pontos, score)."""
        h, w = img.shape[:2]
        scale = min(1.0, DETECT_MAX_SIDE / float(max(h, w)))
        small = img if scale == 1.0 else cv2.resize(
            img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        self.detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = self.detector.detect(small)
        if faces is None:
            return np.zeros((0, 15), np.float32)
        faces = faces.copy()
        faces[:, :14] /= scale
        return faces

    def embed(self, img, face):
        crop = self.recognizer.alignCrop(img, face)
        feat = self.recognizer.feature(crop).flatten().astype(np.float32)
        return feat / (np.linalg.norm(feat) + 1e-9)


# ---------------------------------------------------------------------------
# Agrupamento
# ---------------------------------------------------------------------------

def cluster_faces(embs, photo_ids, threshold=SAME_PERSON):
    """
    Agrupa rostos por pessoa (agrupamento por media / average linkage).
    Dois rostos da mesma foto nunca vao para o mesmo grupo.
    Retorna lista de listas de indices.
    """
    n = len(embs)
    if n == 0:
        return []
    X = np.asarray(embs, np.float32)
    S = X @ X.T
    ids = np.asarray(photo_ids)
    S[ids[:, None] == ids[None, :]] = -np.inf   # mesma foto (inclui diagonal)
    size = np.ones(n, np.float32)
    clusters = {i: [i] for i in range(n)}

    while True:
        a, b = divmod(int(np.argmax(S)), n)
        if not np.isfinite(S[a, b]) or S[a, b] < threshold:
            break
        # junta b em a: similaridade media ponderada; bloqueios (-inf) se mantem
        blocked = np.isneginf(S[a]) | np.isneginf(S[b])
        row = (S[a] * size[a] + S[b] * size[b]) / (size[a] + size[b])
        row[blocked] = -np.inf
        S[a, :] = row
        S[:, a] = row
        S[b, :] = -np.inf
        S[:, b] = -np.inf
        size[a] += size[b]
        clusters[a].extend(clusters.pop(b))

    return list(clusters.values())


def process_folder(src, engine, log=print, progress=lambda done, total: None,
                   out_root=None):
    """Processa uma pasta de fotos e cria festa_N. Retorna o caminho criado."""
    out_root = out_root or data_dir()
    images = list_images(src)
    if not images:
        raise RuntimeError("Nenhuma foto encontrada nessa pasta.")

    embs, photo_ids, thumbs = [], [], []
    total = len(images)
    for i, path in enumerate(images):
        img = read_image(path)
        if img is None:
            log("Não foi possível abrir: %s" % os.path.basename(path))
            progress(i + 1, total)
            continue
        faces = engine.detect(img)
        kept = 0
        for f in faces:
            if f[2] < MIN_FACE_PX or f[3] < MIN_FACE_PX or f[14] < MIN_SCORE:
                continue
            try:
                embs.append(engine.embed(img, f))
            except cv2.error:
                continue
            photo_ids.append(i)
            kept += 1
        log("%s: %d rosto(s)" % (os.path.basename(path), kept))
        progress(i + 1, total)

    if not embs:
        raise RuntimeError("Nenhum rosto encontrado nas fotos.")

    log("Agrupando %d rostos..." % len(embs))
    groups = cluster_faces(embs, photo_ids)
    # cada grupo -> conjunto de fotos; mais fotos primeiro (aluno_1 = quem mais aparece)
    people = [sorted({photo_ids[k] for k in g}) for g in groups]
    people.sort(key=lambda ph: (-len(ph), ph[0]))

    event = os.path.join(out_root, next_numbered_name(out_root, "festa"))
    os.makedirs(event)
    for idx, ph in enumerate(people, 1):
        d = os.path.join(event, "aluno_%d" % idx)
        os.makedirs(d)
        used = set()
        for p in ph:
            name = os.path.basename(images[p])
            base, ext = os.path.splitext(name)
            k = 2
            while name.lower() in used:     # fotos com mesmo nome em subpastas
                name = "%s_%d%s" % (base, k, ext)
                k += 1
            used.add(name.lower())
            shutil.copy2(images[p], os.path.join(d, name))
    log("Pronto! %d pessoa(s) encontradas em %s" % (len(people), os.path.basename(event)))
    return event


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root_dir = data_dir()
    state = {"current": None, "engine": None, "busy": False}
    msgs = queue.Queue()

    win = tk.Tk()
    win.title(APP_NAME)
    win.geometry("760x560")
    win.minsize(560, 420)
    try:
        win.iconbitmap(os.path.join(resource_dir(), "icone.ico"))
    except Exception:
        pass

    style = ttk.Style()
    try:
        style.theme_use("vista" if sys.platform.startswith("win") else "clam")
    except tk.TclError:
        pass
    style.configure("Big.TButton", padding=(14, 8), font=("Segoe UI", 11, "bold"))

    # --- topo ---------------------------------------------------------------
    top = ttk.Frame(win, padding=10)
    top.pack(fill="x")
    add_btn = ttk.Button(top, text="+ Adicionar pasta de fotos", style="Big.TButton")
    add_btn.pack(side="left")
    back_btn = ttk.Button(top, text="< Voltar")
    back_btn.pack(side="left", padx=(10, 0))
    open_btn = ttk.Button(top, text="Abrir no Explorer")
    open_btn.pack(side="right")

    bar = ttk.Frame(win, padding=(10, 0, 10, 6))
    bar.pack(fill="x")
    ttk.Label(bar, text="Pesquisar:").pack(side="left")
    search_var = tk.StringVar()
    search = ttk.Entry(bar, textvariable=search_var, font=("Segoe UI", 11))
    search.pack(side="left", fill="x", expand=True, padx=(6, 0))
    where_var = tk.StringVar()
    ttk.Label(win, textvariable=where_var, padding=(10, 0),
              font=("Segoe UI", 10, "bold")).pack(anchor="w")

    # --- lista --------------------------------------------------------------
    mid = ttk.Frame(win, padding=10)
    mid.pack(fill="both", expand=True)
    tree = ttk.Treeview(mid, columns=("info",), show="tree headings", selectmode="browse")
    tree.heading("#0", text="Pasta")
    tree.heading("info", text="Conteúdo")
    tree.column("#0", width=380)
    tree.column("info", width=200, anchor="w")
    sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    # --- rodape -------------------------------------------------------------
    bottom = ttk.Frame(win, padding=(10, 0, 10, 10))
    bottom.pack(fill="x")
    prog = ttk.Progressbar(bottom, mode="determinate")
    prog.pack(fill="x")
    status_var = tk.StringVar(value="Pronto. Clique em 'Adicionar pasta de fotos'.")
    ttk.Label(bottom, textvariable=status_var).pack(anchor="w", pady=(4, 0))

    def subdirs(path):
        try:
            return sorted([n for n in os.listdir(path)
                           if os.path.isdir(os.path.join(path, n))], key=natural_key)
        except OSError:
            return []

    def count_files(path):
        try:
            return sum(1 for n in os.listdir(path)
                       if os.path.isfile(os.path.join(path, n)))
        except OSError:
            return 0

    def ordered(names, q):
        # o nome exato pesquisado aparece primeiro (ex.: aluno_1 antes de aluno_10)
        return sorted(names, key=lambda n: (n.lower() != q, natural_key(n)))

    def refresh(*_):
        q = search_var.get().strip().lower()
        tree.delete(*tree.get_children())
        cur = state["current"]
        if cur is None:
            where_var.set("Eventos")
            back_btn.state(["disabled"])
            for ev in ordered(subdirs(root_dir), q):
                ev_path = os.path.join(root_dir, ev)
                alunos = ordered(subdirs(ev_path), q)
                if not q or q in ev.lower():
                    tree.insert("", "end", iid=ev_path, text="\U0001F4C1 " + ev,
                                values=("%d pessoa(s)" % len(alunos),))
                if q:   # fora do evento a pesquisa tambem acha as subpastas
                    for a in alunos:
                        if q in a.lower() or q in ("%s/%s" % (ev, a)).lower():
                            p = os.path.join(ev_path, a)
                            tree.insert("", "end", iid=p, text="     %s / %s" % (ev, a),
                                        values=("%d foto(s)" % count_files(p),))
        else:
            where_var.set("Eventos > " + os.path.basename(cur))
            back_btn.state(["!disabled"])
            for a in ordered(subdirs(cur), q):
                if not q or q in a.lower():
                    p = os.path.join(cur, a)
                    tree.insert("", "end", iid=p, text="\U0001F464 " + a,
                                values=("%d foto(s)" % count_files(p),))

    def enter(path):
        if os.path.dirname(path) == root_dir:
            state["current"] = path
            search_var.set("")
            refresh()
        else:
            open_in_explorer(path)

    def on_double(_e):
        sel = tree.focus()
        if sel:
            enter(sel)

    def go_back():
        state["current"] = None
        search_var.set("")
        refresh()

    def open_sel():
        sel = tree.focus()
        open_in_explorer(sel or state["current"] or root_dir)

    def worker(folder):
        def log(m):
            msgs.put(("status", m))
        try:
            if state["engine"] is None:
                log("Carregando modelos de reconhecimento...")
                state["engine"] = FaceEngine(log)
            ev = process_folder(folder, state["engine"], log,
                                lambda d, t: msgs.put(("prog", d, t)), root_dir)
            msgs.put(("done", ev))
        except Exception as e:  # mostra qualquer erro ao usuario
            msgs.put(("error", str(e)))

    def add_folder():
        if state["busy"]:
            return
        folder = filedialog.askdirectory(title="Escolha a pasta com as fotos da festa")
        if not folder:
            return
        state["busy"] = True
        add_btn.state(["disabled"])
        prog["value"] = 0
        threading.Thread(target=worker, args=(folder,), daemon=True).start()

    def poll():
        try:
            while True:
                m = msgs.get_nowait()
                if m[0] == "status":
                    status_var.set(m[1])
                elif m[0] == "prog":
                    prog["maximum"] = m[2]
                    prog["value"] = m[1]
                    status_var.set("Analisando fotos... %d de %d" % (m[1], m[2]))
                elif m[0] in ("done", "error"):
                    state["busy"] = False
                    add_btn.state(["!disabled"])
                    if m[0] == "done":
                        n = len(subdirs(m[1]))
                        status_var.set("Pronto! %s criada com %d pessoa(s)."
                                       % (os.path.basename(m[1]), n))
                        state["current"] = m[1]
                        search_var.set("")
                        refresh()
                        messagebox.showinfo(APP_NAME, "%s criada com %d pessoa(s)."
                                            % (os.path.basename(m[1]), n))
                    else:
                        status_var.set("Erro: " + m[1])
                        messagebox.showerror(APP_NAME, m[1])
        except queue.Empty:
            pass
        win.after(100, poll)

    add_btn.configure(command=add_folder)
    back_btn.configure(command=go_back)
    open_btn.configure(command=open_sel)
    tree.bind("<Double-1>", on_double)
    tree.bind("<Return>", on_double)
    win.bind("<BackSpace>", lambda e: go_back() if win.focus_get() is not search else None)
    search_var.trace_add("write", refresh)

    refresh()
    poll()
    search.focus_set()
    win.mainloop()


def run_cli(folder):
    """Uso sem interface: reconhecimento.exe C:\\caminho\\fotos"""
    engine = FaceEngine()
    ev = process_folder(folder, engine,
                        progress=lambda d, t: None)
    print(ev)


if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        run_cli(sys.argv[1])
    else:
        run_gui()
