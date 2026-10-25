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
MIN_FACE_PX = 28            # ignora rostos muito pequenos (ruido)
MIN_SCORE = 0.60            # confianca minima do detector
ROTATIONS = (0, 90, 270, 180)   # procura tambem rostos deitados / de cabeca para baixo
CLOSEUP_SIDE = 640          # tamanho usado para achar rostos muito grandes (fotos de perto)
SAME_PERSON = 0.36          # similaridade (cosseno) para juntar rostos
MERGE_GROUPS = 0.42         # similaridade entre medias para juntar grupos da mesma pessoa
SURE_FACE = 0.80            # pessoa que so aparece em rostos abaixo disso e ignorada (maos, pele...)


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

    def _detect_once(self, img):
        self.detector.setInputSize((img.shape[1], img.shape[0]))
        _, faces = self.detector.detect(img)
        return np.zeros((0, 15), np.float32) if faces is None else faces.copy()

    def _detect_multiscale(self, img):
        """Detecta em tamanho normal e tambem numa versao pequena com bordas,
        que acha rostos muito grandes (fotos bem de perto / selfies)."""
        h, w = img.shape[:2]
        found = list(self._detect_once(img))
        pad = int(0.25 * max(h, w))
        padded = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT)
        k = CLOSEUP_SIDE / float(max(padded.shape[:2]))
        small = cv2.resize(padded, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        for f in self._detect_once(small):
            f[:14] /= k
            f[[0, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]] -= pad   # tira a borda
            found.append(f)
        faces = [f for f in found if _plausible(f, img.shape)]
        return _dedupe(np.array(faces, np.float32)) if faces else []

    def detect(self, img):
        """
        Retorna linhas no formato YuNet (x, y, w, h, 10 pontos, score) nas
        coordenadas da foto original.
        """
        h, w = img.shape[:2]
        scale = min(1.0, DETECT_MAX_SIDE / float(max(h, w)))
        small = img if scale == 1.0 else cv2.resize(
            img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        sh, sw = small.shape[:2]
        # Cada foto e testada em 4 rotacoes e fica so a rotacao em que o
        # detector tem mais certeza (fotos tiradas deitadas / de lado).
        best, best_score = None, -1.0
        for rot in ROTATIONS:
            if rot == 0:
                im = small
            else:
                im = cv2.rotate(small, {90: cv2.ROTATE_90_CLOCKWISE,
                                        180: cv2.ROTATE_180,
                                        270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rot])
            faces = self._detect_multiscale(im)
            if len(faces) == 0:
                continue
            # media dos rostos mais confiaveis: de cabeca para baixo o detector
            # ainda acerta, mas com um pouco menos de certeza
            top = sorted((float(f[14]) for f in faces), reverse=True)
            top = [t for t in top if t >= SURE_FACE][:3] or top[:1]
            score = sum(top) / len(top) + (0.01 if rot == 0 else 0.0)
            if score > best_score:
                best_score = score
                best = [_unrotate(f, rot, sw, sh) for f in faces]
        if not best:
            return np.zeros((0, 15), np.float32)
        faces = np.array(best, np.float32)
        faces[:, :14] /= scale
        return faces

    def embed(self, img, face):
        crop = self.recognizer.alignCrop(img, face)
        f1 = self.recognizer.feature(crop).flatten()
        f2 = self.recognizer.feature(cv2.flip(crop, 1)).flatten()   # espelhado
        feat = (f1 / np.linalg.norm(f1) + f2 / np.linalg.norm(f2)).astype(np.float32)
        return feat / (np.linalg.norm(feat) + 1e-9)


def _unrotate(f, rot, w, h):
    """Converte uma deteccao feita na imagem girada para a imagem original (w x h)."""
    f = f.copy()
    pts = f[4:14].reshape(5, 2).copy()
    x, y, bw, bh = f[:4]
    corners = np.array([[x, y], [x + bw, y], [x, y + bh], [x + bw, y + bh]], np.float32)

    def back(p):
        p = p.copy()
        if rot == 90:        # girada no horario: (x', y') = (h-1-y, x)
            p[:, 0], p[:, 1] = p[:, 1].copy(), (h - 1) - p[:, 0]
        elif rot == 270:     # anti-horario: (x', y') = (y, w-1-x)
            p[:, 0], p[:, 1] = (w - 1) - p[:, 1], p[:, 0].copy()
        elif rot == 180:
            p[:, 0], p[:, 1] = (w - 1) - p[:, 0], (h - 1) - p[:, 1]
        return p

    if rot:
        pts = back(pts)
        c = back(corners)
        x0, y0 = c.min(0)
        x1, y1 = c.max(0)
        f[:4] = (x0, y0, x1 - x0, y1 - y0)
        f[4:14] = pts.flatten()
    return f


def _plausible(f, shape):
    """Descarta deteccoes falsas (maos, pele, cabelo): olhos, nariz e boca
    precisam estar dentro da foto e na ordem certa de cima para baixo."""
    h, w = shape[:2]
    pts = f[4:14].reshape(5, 2)
    if (pts[:, 0] < 0).any() or (pts[:, 1] < 0).any() or \
            (pts[:, 0] >= w).any() or (pts[:, 1] >= h).any():
        return False
    reye, leye, nose, rmouth, lmouth = pts
    eye_y = (reye[1] + leye[1]) / 2
    mouth_y = (rmouth[1] + lmouth[1]) / 2
    eye_dist = np.hypot(*(leye - reye))
    if eye_dist < 0.2 * f[2]:
        return False
    return eye_y < nose[1] < mouth_y and reye[0] < leye[0]


def _dedupe(faces, iou_max=0.35):
    """Remove o mesmo rosto achado duas vezes (fica o de maior confianca)."""
    order = np.argsort(-faces[:, 14])
    keep = []
    for i in order:
        x, y, w, h = faces[i, :4]
        ok = True
        for j in keep:
            X, Y, W, H = faces[j, :4]
            iw = max(0.0, min(x + w, X + W) - max(x, X))
            ih = max(0.0, min(y + h, Y + H) - max(y, Y))
            inter = iw * ih
            if inter / (w * h + W * H - inter + 1e-9) > iou_max or \
                    inter / (min(w * h, W * H) + 1e-9) > 0.5:   # um dentro do outro
                ok = False
                break
        if ok:
            keep.append(i)
    return faces[keep]


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

    groups = list(clusters.values())
    return merge_groups(X, groups, ids)


def merge_groups(X, groups, ids, threshold=MERGE_GROUPS):
    """
    Segunda passada: junta grupos cuja media de rostos e muito parecida
    (a mesma pessoa com careta, de lado, com luz diferente...), desde que
    os dois grupos nao tenham rostos na mesma foto.
    """
    groups = [list(g) for g in groups]
    while len(groups) > 1:
        C = np.array([X[g].mean(0) for g in groups])
        C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9
        S = C @ C.T
        np.fill_diagonal(S, -np.inf)
        photos = [set(ids[g].tolist()) for g in groups]
        merged = False
        for flat in np.argsort(-S, axis=None):
            a, b = divmod(int(flat), len(groups))
            if S[a, b] < threshold:
                break
            if a < b and not (photos[a] & photos[b]):
                groups[a].extend(groups.pop(b))
                merged = True
                break
        if not merged:
            break
    return groups


def process_folder(src, engine, log=print, progress=lambda done, total: None,
                   out_root=None):
    """Processa uma pasta de fotos e cria festa_N. Retorna o caminho criado."""
    out_root = out_root or data_dir()
    images = list_images(src)
    if not images:
        raise RuntimeError("Nenhuma foto encontrada nessa pasta.")

    embs, photo_ids, scores = [], [], []
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
            scores.append(float(f[14]))
            kept += 1
        log("%s: %d rosto(s)" % (os.path.basename(path), kept))
        progress(i + 1, total)

    if not embs:
        raise RuntimeError("Nenhum rosto encontrado nas fotos.")

    log("Agrupando %d rostos..." % len(embs))
    groups = cluster_faces(embs, photo_ids)
    # grupo formado so por deteccoes duvidosas = provavelmente nao e um rosto
    groups = [g for g in groups if max(scores[k] for k in g) >= SURE_FACE]
    if not groups:
        raise RuntimeError("Nenhum rosto encontrado nas fotos.")
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

INVALID_CHARS = '\\/:*?"<>|'

# Cores do tema escuro
BG = "#121212"
PANEL = "#1c1c1c"
ROW_HOVER = "#262626"
ROW_SEL = "#7a1c1c"
ACCENT = "#c62828"
ACCENT_HOVER = "#e53935"
FG = "#ffffff"
FG_DIM = "#b0b0b0"
LOGO_OPACITY = 0.22         # logo de fundo bem suave para nao atrapalhar a leitura
ROW_H = 34


def validate_new_name(parent, old, new):
    """Retorna mensagem de erro ou None se o novo nome pode ser usado."""
    new = new.strip()
    if not new:
        return "O nome não pode ficar vazio."
    if any(c in new for c in INVALID_CHARS):
        return "O nome não pode ter estes caracteres:  %s" % " ".join(INVALID_CHARS)
    if new.endswith(".") or new.endswith(" "):
        return "O nome não pode terminar com ponto ou espaço."
    if new.lower() != old.lower():
        for n in os.listdir(parent):
            if n.lower() == new.lower():
                return "Já existe uma pasta chamada \"%s\" aqui." % n
    return None


def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from PIL import Image, ImageTk

    root_dir = data_dir()
    state = {"current": None, "engine": None, "busy": False,
             "rows": [], "sel": None, "hover": None, "editor": None}
    msgs = queue.Queue()

    win = tk.Tk()
    win.title(APP_NAME)
    win.geometry("820x600")
    win.minsize(560, 420)
    win.configure(bg=BG)
    try:
        win.iconbitmap(os.path.join(resource_dir(), "assets", "icone.ico"))
    except Exception:
        pass

    font = ("Segoe UI", 11)
    font_b = ("Segoe UI", 11, "bold")
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Dark.Horizontal.TProgressbar", troughcolor=PANEL,
                    background=ACCENT, bordercolor=PANEL, lightcolor=ACCENT, darkcolor=ACCENT)
    style.configure("Dark.Vertical.TScrollbar", background=PANEL, troughcolor=BG,
                    bordercolor=BG, arrowcolor=FG_DIM, lightcolor=PANEL, darkcolor=PANEL)
    style.map("Dark.Vertical.TScrollbar", background=[("active", ROW_HOVER)])

    def make_button(parent, text, cmd, primary=False):
        base = ACCENT if primary else PANEL
        hover = ACCENT_HOVER if primary else ROW_HOVER
        b = tk.Button(parent, text=text, command=cmd, bg=base, fg=FG,
                      activebackground=hover, activeforeground=FG,
                      disabledforeground="#666666", relief="flat", bd=0,
                      font=font_b if primary else font, padx=16, pady=8, cursor="hand2")
        b.bind("<Enter>", lambda e: b.configure(bg=hover) if b["state"] == "normal" else None)
        b.bind("<Leave>", lambda e: b.configure(bg=base))
        return b

    # --- topo ---------------------------------------------------------------
    top = tk.Frame(win, bg=BG, padx=12, pady=12)
    top.pack(fill="x")
    add_btn = make_button(top, "+  Adicionar pasta de fotos", None, primary=True)
    add_btn.pack(side="left")
    back_btn = make_button(top, "‹  Voltar", None)
    back_btn.pack(side="left", padx=(10, 0))
    open_btn = make_button(top, "Abrir no Explorer", None)
    open_btn.pack(side="right")

    bar = tk.Frame(win, bg=BG, padx=12)
    bar.pack(fill="x")
    tk.Label(bar, text="Pesquisar:", bg=BG, fg=FG, font=font).pack(side="left")
    search_var = tk.StringVar()
    search = tk.Entry(bar, textvariable=search_var, font=font, bg=PANEL, fg=FG,
                      insertbackground=FG, relief="flat", highlightthickness=1,
                      highlightbackground="#333333", highlightcolor=ACCENT)
    search.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=6)
    where_var = tk.StringVar()
    tk.Label(win, textvariable=where_var, bg=BG, fg=FG, font=("Segoe UI", 12, "bold"),
             padx=12, pady=8, anchor="w").pack(fill="x")

    # --- lista (canvas com a logo no fundo) ---------------------------------
    mid = tk.Frame(win, bg=BG, padx=12)
    mid.pack(fill="both", expand=True)
    canvas = tk.Canvas(mid, bg=BG, highlightthickness=1, highlightbackground="#2a2a2a", bd=0,
                       yscrollincrement=ROW_H)
    sb = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview,
                       style="Dark.Vertical.TScrollbar")
    canvas.configure(yscrollcommand=lambda a, b: (sb.set(a, b), place_logo()))
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    # --- rodape -------------------------------------------------------------
    bottom = tk.Frame(win, bg=BG, padx=12, pady=10)
    bottom.pack(fill="x")
    prog = ttk.Progressbar(bottom, mode="determinate", style="Dark.Horizontal.TProgressbar")
    prog.pack(fill="x")
    status_var = tk.StringVar(value="Pronto. Clique em 'Adicionar pasta de fotos'.  "
                                    "Botão direito numa pasta para renomear.")
    tk.Label(bottom, textvariable=status_var, bg=BG, fg=FG_DIM, font=("Segoe UI", 10),
             anchor="w").pack(fill="x", pady=(6, 0))

    # --- logo ---------------------------------------------------------------
    logo_src = None
    try:
        logo_src = Image.open(os.path.join(resource_dir(), "assets", "logo.png")).convert("RGBA")
        r, g, b, a = logo_src.split()
        a = a.point(lambda v: int(v * LOGO_OPACITY))
        logo_src = Image.merge("RGBA", (r, g, b, a))
    except Exception:
        logo_src = None
    logo = {"img": None, "size": None}

    def place_logo():
        if logo["img"] is None:
            return
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        canvas.coords("logo", canvas.canvasx(cw / 2), canvas.canvasy(ch / 2))
        canvas.tag_lower("logo")

    def resize_logo(_e=None):
        if logo_src is None:
            return
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw < 50 or ch < 50:
            return
        k = min(cw * 0.7 / logo_src.width, ch * 0.7 / logo_src.height)
        size = (max(1, int(logo_src.width * k)), max(1, int(logo_src.height * k)))
        if size != logo["size"]:
            logo["size"] = size
            logo["img"] = ImageTk.PhotoImage(logo_src.resize(size, Image.LANCZOS))
            canvas.delete("logo")
            canvas.create_image(0, 0, image=logo["img"], tags="logo")
        draw_rows()

    # --- dados --------------------------------------------------------------
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
        cancel_edit()
        q = search_var.get().strip().lower()
        rows = []   # (caminho, texto, info, icone)
        cur = state["current"]
        if cur is None:
            where_var.set("Eventos")
            back_btn.configure(state="disabled")
            for ev in ordered(subdirs(root_dir), q):
                ev_path = os.path.join(root_dir, ev)
                alunos = ordered(subdirs(ev_path), q)
                if not q or q in ev.lower():
                    rows.append((ev_path, ev, "%d pessoa(s)" % len(alunos), "festa"))
                if q:   # fora do evento a pesquisa tambem acha as subpastas
                    for a in alunos:
                        if q in a.lower() or q in ("%s/%s" % (ev, a)).lower():
                            p = os.path.join(ev_path, a)
                            rows.append((p, "%s / %s" % (ev, a),
                                         "%d foto(s)" % count_files(p), "pessoa"))
        else:
            where_var.set("Eventos  ›  " + os.path.basename(cur))
            back_btn.configure(state="normal")
            for a in ordered(subdirs(cur), q):
                p = os.path.join(cur, a)
                rows.append((p, a, "%d foto(s)" % count_files(p), "pessoa"))
        state["rows"] = rows
        if state["sel"] not in [r[0] for r in rows]:
            state["sel"] = None
        state["hover"] = None
        draw_rows()

    def draw_rows():
        canvas.delete("row")
        cw = max(canvas.winfo_width(), 200)
        col2 = int(cw * 0.66)
        canvas.create_text(16, ROW_H / 2, text="Pasta", anchor="w", fill=FG_DIM,
                           font=font_b, tags="row")
        canvas.create_text(col2, ROW_H / 2, text="Conteúdo", anchor="w", fill=FG_DIM,
                           font=font_b, tags="row")
        canvas.create_line(8, ROW_H, cw - 8, ROW_H, fill="#333333", tags="row")
        for i, (path, text, info, kind) in enumerate(state["rows"]):
            y = ROW_H * (i + 1) + 2
            if path == state["sel"]:
                canvas.create_rectangle(4, y, cw - 4, y + ROW_H - 2, fill=ROW_SEL,
                                        outline="", tags="row")
            elif i == state["hover"]:
                canvas.create_rectangle(4, y, cw - 4, y + ROW_H - 2, fill="",
                                        outline="#444444", tags="row")
            draw_icon(18, y + ROW_H / 2 - 1, kind)
            canvas.create_text(42, y + ROW_H / 2 - 1, text=text, anchor="w", fill=FG,
                               font=font, tags="row")
            canvas.create_text(col2, y + ROW_H / 2 - 1, text=info, anchor="w", fill=FG,
                               font=font, tags="row")
        if not state["rows"]:
            msg = ("Nenhuma pasta encontrada." if search_var.get().strip() else
                   "Nenhum evento ainda. Clique em 'Adicionar pasta de fotos'."
                   if state["current"] is None else "Este evento está vazio.")
            canvas.create_text(16, ROW_H * 1.6, text=msg, anchor="w", fill=FG_DIM,
                               font=font, tags="row")
        total_h = ROW_H * (len(state["rows"]) + 1) + 8
        canvas.configure(scrollregion=(0, 0, cw, max(total_h, canvas.winfo_height())))
        place_logo()

    def draw_icon(x, y, kind):
        # icones desenhados (emoji nao aparece direito em todo Windows)
        if kind == "festa":
            canvas.create_polygon(x - 9, y - 6, x - 3, y - 6, x - 1, y - 4, x + 9, y - 4,
                                  x + 9, y + 7, x - 9, y + 7, fill=ACCENT, outline="",
                                  tags="row")
        else:
            canvas.create_oval(x - 4, y - 8, x + 4, y, fill=FG, outline="", tags="row")
            canvas.create_arc(x - 8, y + 1, x + 8, y + 15, start=0, extent=180,
                              fill=FG, outline="", tags="row")

    def row_at(event):
        i = int(canvas.canvasy(event.y) // ROW_H) - 1
        return i if 0 <= i < len(state["rows"]) else None

    # --- acoes --------------------------------------------------------------
    def enter(path):
        if os.path.dirname(path) == root_dir:
            state["current"] = path
            state["sel"] = None
            search_var.set("")
            canvas.yview_moveto(0)
            refresh()
        else:
            open_in_explorer(path)

    def on_click(e):
        cancel_edit()
        i = row_at(e)
        state["sel"] = state["rows"][i][0] if i is not None else None
        draw_rows()
        canvas.focus_set()

    def on_double(e):
        i = row_at(e)
        if i is not None:
            enter(state["rows"][i][0])

    def on_motion(e):
        i = row_at(e)
        if i != state["hover"]:
            state["hover"] = i
            draw_rows()

    def on_leave(_e):
        if state["hover"] is not None:
            state["hover"] = None
            draw_rows()

    def on_wheel(e):
        if canvas.yview() != (0.0, 1.0):
            canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")

    def move_sel(step):
        paths = [r[0] for r in state["rows"]]
        if not paths:
            return
        i = paths.index(state["sel"]) + step if state["sel"] in paths else 0
        state["sel"] = paths[max(0, min(len(paths) - 1, i))]
        draw_rows()

    def go_back():
        if state["current"] is None:
            return
        state["sel"] = state["current"]
        state["current"] = None
        search_var.set("")
        refresh()

    def open_sel():
        open_in_explorer(state["sel"] or state["current"] or root_dir)

    # --- renomear -----------------------------------------------------------
    def cancel_edit(*_):
        ed = state.get("editor")
        if ed is not None:
            state["editor"] = None
            ed.destroy()

    def start_rename(path=None):
        path = path or state["sel"]
        if not path or state["busy"]:
            return
        paths = [r[0] for r in state["rows"]]
        if path not in paths:
            return
        cancel_edit()
        i = paths.index(path)
        old = os.path.basename(path)
        canvas.update_idletasks()
        y = ROW_H * (i + 1) + 2
        cw = canvas.winfo_width()
        ed = tk.Entry(canvas, font=font, bg="#2b2b2b", fg=FG, insertbackground=FG,
                      relief="flat", highlightthickness=1, highlightcolor=ACCENT,
                      highlightbackground=ACCENT)
        ed.busy = False
        ed.insert(0, old)
        ed.select_range(0, "end")
        canvas.create_window(38, y + 2, window=ed, anchor="nw",
                             width=int(cw * 0.66) - 54, height=ROW_H - 6, tags="row")
        state["editor"] = ed
        ed.focus_set()

        def confirm(_e=None):
            if state.get("editor") is not ed or ed.busy:
                return
            new = ed.get().strip()
            if new == old:
                cancel_edit()
                return
            parent = os.path.dirname(path)
            err = validate_new_name(parent, old, new)
            if err:
                ed.busy = True      # evita confirmar de novo enquanto o aviso esta aberto
                messagebox.showerror(APP_NAME, err, parent=win)
                ed.busy = False
                ed.focus_set()
                return
            new_path = os.path.join(parent, new)
            try:
                os.rename(path, new_path)
            except OSError as ex:
                ed.busy = True
                messagebox.showerror(APP_NAME, "Não foi possível renomear:\n%s\n\n"
                                     "Feche as janelas ou fotos abertas dessa pasta e "
                                     "tente de novo." % ex, parent=win)
                ed.busy = False
                ed.focus_set()
                return
            if state["current"] == path:
                state["current"] = new_path
            state["sel"] = new_path
            status_var.set("\"%s\" renomeada para \"%s\"." % (old, new))
            cancel_edit()
            refresh()

        ed.bind("<Return>", confirm)
        ed.bind("<KP_Enter>", confirm)
        ed.bind("<Escape>", cancel_edit)
        ed.bind("<FocusOut>", confirm)

    menu = tk.Menu(win, tearoff=0, bg=PANEL, fg=FG, activebackground=ACCENT,
                   activeforeground=FG, bd=0, font=font)

    def on_right(e):
        cancel_edit()
        i = row_at(e)
        if i is None:
            return
        path = state["rows"][i][0]
        state["sel"] = path
        draw_rows()
        menu.delete(0, "end")
        is_event = os.path.dirname(path) == root_dir
        menu.add_command(label="Abrir" if is_event else "Abrir pasta",
                         command=lambda: enter(path))
        menu.add_command(label="Abrir no Explorer", command=lambda: open_in_explorer(path))
        menu.add_separator()
        menu.add_command(label="Renomear        F2", command=lambda: start_rename(path))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    # --- processamento ------------------------------------------------------
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
        add_btn.configure(state="disabled", bg=ACCENT)
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
                    add_btn.configure(state="normal")
                    if m[0] == "done":
                        n = len(subdirs(m[1]))
                        status_var.set("Pronto! %s criada com %d pessoa(s)."
                                       % (os.path.basename(m[1]), n))
                        state["current"] = m[1]
                        state["sel"] = None
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
    canvas.bind("<Configure>", resize_logo)
    canvas.bind("<Button-1>", on_click)
    canvas.bind("<Double-1>", on_double)
    canvas.bind("<Button-3>", on_right)
    canvas.bind("<Motion>", on_motion)
    canvas.bind("<Leave>", on_leave)
    canvas.bind("<MouseWheel>", on_wheel)
    canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
    canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
    canvas.bind("<Up>", lambda e: move_sel(-1))
    canvas.bind("<Down>", lambda e: move_sel(1))
    canvas.bind("<Return>", lambda e: state["sel"] and enter(state["sel"]))
    canvas.bind("<BackSpace>", lambda e: go_back())
    win.bind("<F2>", lambda e: start_rename())
    search.bind("<Down>", lambda e: (canvas.focus_set(), move_sel(1)))
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
