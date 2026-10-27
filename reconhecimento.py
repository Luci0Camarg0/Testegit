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
import json
import sys
import shutil
import threading
import queue
import subprocess
import urllib.request

import numpy as np
import cv2

APP_NAME = "Reconhecimento Facial"

# Atualizacao automatica: a cada mudanca no codigo, aumente VERSAO aqui e em
# versao.json. RUNTIME_NEEDED so aumenta quando o .exe inteiro precisa ser
# baixado de novo (biblioteca ou modelo novo); veja iniciar.py.
VERSAO = 11
RUNTIME_NEEDED = 1
UPDATE_BASE = os.environ.get("RF_UPDATE_BASE") or \
    "https://raw.githubusercontent.com/Luci0Camarg0/Testegit/reconhecimento-facial/"
FULL_DOWNLOAD = ("https://github.com/Luci0Camarg0/Testegit/releases/download/"
                 "ultima/ReconhecimentoFacial.exe")
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
MATCH_STUDENT = 0.38        # com cadastro: similaridade media minima entre a pessoa e o aluno
SEQ_MATCH = 0.30            # foto logo depois da ficha: basta isso para ser do mesmo aluno
SEQ_SLACK = 0.05            # ...desde que nao pareca mais com outro aluno
FREE_MATCH = 0.40           # foto fora da sequencia da ficha: precisa parecer mais
FREE_MARGIN = 0.04          # ...e mais que com o segundo aluno mais parecido


# ---------------------------------------------------------------------------
# Pastas
# ---------------------------------------------------------------------------

def app_dir():
    """Pasta onde esta o .exe (ou o .py)."""
    if os.environ.get("RF_APP_DIR"):        # definido pelo iniciar.py
        return os.environ["RF_APP_DIR"]
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
    os dois grupos nao tenham rostos na mesma foto e um deles seja pequeno.
    Dois grupos grandes nunca se juntam por aqui: a media de muitos rostos
    parece com a de qualquer outra pessoa no mesmo cenario.
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
            small = min(len(groups[a]), len(groups[b])) <= 3
            if a < b and small and not (photos[a] & photos[b]):
                groups[a].extend(groups.pop(b))
                merged = True
                break
        if not merged:
            break
    return groups


def scan_faces(images, engine, log=print, progress=lambda done, total, text=None: None):
    """
    Detecta e descreve todos os rostos. Retorna (embeddings, foto de cada
    rosto, confianca, caixa x,y,w,h de cada rosto).
    """
    embs, photo_ids, scores, boxes = [], [], [], []
    total = len(images)
    for i, path in enumerate(images):
        img = read_image(path)
        if img is None:
            log("Não foi possível abrir: %s" % os.path.basename(path))
            progress(i + 1, total, "Analisando fotos...")
            continue
        kept = 0
        for f in engine.detect(img):
            if f[2] < MIN_FACE_PX or f[3] < MIN_FACE_PX or f[14] < MIN_SCORE:
                continue
            try:
                embs.append(engine.embed(img, f))
            except cv2.error:
                continue
            photo_ids.append(i)
            scores.append(float(f[14]))
            boxes.append([float(v) for v in f[:4]])
            kept += 1
        log("%s: %d rosto(s)" % (os.path.basename(path), kept))
        progress(i + 1, total, "Analisando fotos...")
    return (np.array(embs, np.float32).reshape(-1, 128), np.array(photo_ids, int),
            np.array(scores), np.array(boxes, np.float32).reshape(-1, 4))


# ---------------------------------------------------------------------------
# Alunos (fichas)
# ---------------------------------------------------------------------------

def _name_quality(name):
    words = name.split()
    return (sum(w in NAMES for w in words), 2 <= len(words) <= 5, len(name))


def group_cards(embs, cards):
    """
    Junta as fotos de ficha do mesmo aluno (o mesmo numero, ou duas fotos
    seguidas da ficha com o mesmo rosto) e escolhe a melhor leitura do nome e
    do numero. Retorna [(pasta, [fotos da ficha], [rostos])] na ordem das fotos.
    """
    X = np.asarray(embs, np.float32)
    groups = []
    for ph, (name, code, k) in sorted(cards.items()):
        g = None
        for cand in groups:
            if code and code in cand["codes"]:
                g = cand
        last = groups[-1] if groups else None
        if g is None and last and ph - last["photos"][-1] <= 2 and \
                float(np.max(X[last["faces"]] @ X[k])) >= 0.6 and \
                not (code and last["codes"] and code not in last["codes"]):
            g = last
        if g is None:
            g = {"photos": [], "faces": [], "codes": [], "names": []}
            groups.append(g)
        g["photos"].append(ph)
        g["faces"].append(k)
        if code:
            g["codes"].append(code)
        if name:
            g["names"].append(name)
    out, used = [], set()
    for g in groups:
        code = max(sorted(set(g["codes"])), key=lambda c: (g["codes"].count(c), len(c))) \
            if g["codes"] else ""
        name = max(g["names"], key=_name_quality) if g["names"] else ""
        folder = base = folder_name_for(name, code)
        n = 2
        while folder in used:           # mesmo nome lido em fichas diferentes
            folder = "%s_%d" % (base, n)
            n += 1
        used.add(folder)
        out.append((folder, g["photos"], g["faces"]))
    return out


def assign_by_cards(embs, photo_ids, scores, cards, n_photos):
    """
    Separa as fotos pelos alunos das fichas, sem agrupar todo mundo antes.
    1. Sequencia: as fotos logo depois da ficha sao do mesmo aluno enquanto o
       rosto dele continuar aparecendo e nao for claramente outro aluno (para
       na proxima ficha ou depois de 2 fotos sem ele). Fotos sem rosto no meio
       da sequencia (de costas) vao junto.
    2. O resto: cada rosto vai para o aluno mais parecido, comparando com a
       ficha e com as fotos ja separadas dele, se for claramente ele.
    cards: {foto: (nome, codigo, rosto)}. Retorna {pasta: [fotos]}.
    """
    X = np.asarray(embs, np.float32)
    students = group_cards(X, cards)
    names = [f for f, _, _ in students]
    refs = {f: list(ks) for f, _, ks in students}
    first = {f: phs for f, phs, _ in students}
    faces = {}
    for k, ph in enumerate(photo_ids):
        faces.setdefault(int(ph), []).append(k)
    owner = {}                       # rosto -> aluno
    photos = {n: set() for n in names}

    def score(k, n):
        s = np.sort(X[refs[n]] @ X[k])[::-1]
        return float(s[:3].mean())   # media dos 3 mais parecidos: um erro nao estraga

    def give(k, n):
        owner[k] = n
        refs[n].append(k)
        photos[n].add(int(photo_ids[k]))

    # 1. sequencia depois de cada ficha
    for n in names:
        for p in first[n]:
            i, misses, blank = p + 1, 0, []
            while i < n_photos and i not in cards and misses < 2:
                ks = [k for k in faces.get(i, []) if k not in owner]
                if not faces.get(i):
                    blank.append(i)
                elif ks:
                    k = max(ks, key=lambda k: score(k, n))
                    other = max([score(k, m) for m in names if m != n] or [-1.0])
                    if score(k, n) >= SEQ_MATCH and score(k, n) >= other - SEQ_SLACK \
                            and n not in [owner.get(j) for j in faces[i]]:
                        give(k, n)
                        misses = 0
                        photos[n].update(b for b in blank if b < i)
                        blank = []
                    else:
                        misses += 1
                else:
                    misses += 1
                i += 1

    # 2. rostos que sobraram (fotos de festa, fora de ordem...)
    for _round in range(2):
        changed = False
        for k in range(len(X)):
            if k in owner or scores[k] < SURE_FACE * 0.9 or len(names) == 0:
                continue
            sc = sorted(((score(k, n), n) for n in names), reverse=True)
            best, n = sc[0]
            second = sc[1][0] if len(sc) > 1 else -1.0
            ph = int(photo_ids[k])
            taken = n in [owner.get(j) for j in faces[ph]]
            if best >= FREE_MATCH and best - second >= FREE_MARGIN and not taken:
                give(k, n)
                changed = True
        if not changed:
            break
    return {n: sorted(photos[n] - set(cards)) for n in names}


# ---------------------------------------------------------------------------
# Fichas de identificacao (foto do aluno segurando a ficha com nome e codigo)
# ---------------------------------------------------------------------------

CARD_LABELS = {"nome", "aluno", "aluna", "codigo", "código", "cod", "cód", "id",
               "curso", "turma", "matricula", "matrícula", "n", "no", "nº", "numero", "número"}

CARD_SKIP = {"formatura", "formandos", "colegio", "colégio", "escola", "turma", "curso",
             "universidade", "faculdade", "gala", "eventos", "ficha", "identificacao",
             "identificação"}

# Leitor de letra de mao (PP-OCRv6). Vai dentro do .exe novo; quem tem o .exe
# antigo baixa uma vez para a pasta "atualizacao".
CARD_JUNK = {"dados", "contrato", "eventos", "calaeventos", "galaeventos", "formaturas",
             "gala", "nascimento", "lei", "responsavel", "cadastro", "ficha"}

HAND_MODEL = "PP-OCRv6_rec_small.onnx"
HAND_URL = "https://github.com/Luci0Camarg0/Testegit/releases/download/modelos/" + HAND_MODEL

_ocr = None


def hand_model(log=print, download=True):
    dl = os.path.join(os.path.dirname(data_dir()), "atualizacao", "modelos")
    for d in (os.path.join(resource_dir(), "models"), os.path.join(app_dir(), "models"), dl):
        p = os.path.join(d, HAND_MODEL)
        if os.path.isfile(p) and os.path.getsize(p) > 1000000:
            return p
    if not download:
        return None
    try:
        log("Baixando o leitor de letra de mão (21 MB, só desta vez)...")
        data = _get(HAND_URL, timeout=180)
        if len(data) < 1000000:
            return None
        os.makedirs(dl, exist_ok=True)
        p = os.path.join(dl, HAND_MODEL)
        with open(p + ".tmp", "wb") as f:
            f.write(data)
        os.replace(p + ".tmp", p)
        return p
    except Exception:
        return None


def get_ocr(log=print):
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        rec = hand_model(log)
        try:
            _ocr = RapidOCR(rec_model_path=rec) if rec else RapidOCR()
        except Exception:
            _ocr = RapidOCR()
    return _ocr


def parse_card(lines):
    """
    Separa nome e codigo do texto lido na ficha.
    Codigo: a maior sequencia de numeros (3 ou mais digitos).
    Nome: a linha mais longa feita de letras, sem rotulos como "Nome:".
    """
    code, name, best_c = "", "", -99
    for t in lines:
        low = t.lower()
        labeled = any(l in low for l in ("cod", "cód", "id", "matr", "nº", "num", "núm"))
        for d in re.findall(r"\d[\d\-./]*\d", t.replace(" ", "")):
            if sum(c.isdigit() for c in d) < 3:
                continue
            score = len(d) + (10 if labeled else 0)
            if re.fullmatch(r"(19|20)\d\d", d):     # parece ano (formatura 2026)
                score -= 8
            if score > best_c and score > 0:
                best_c, code = score, d.replace("/", "-")
    best = 0
    for t in lines:
        words = re.findall(r"[^\W\d_]+", t)
        if any(w.lower() in CARD_SKIP for w in words):   # cabecalho da ficha
            continue
        words = [w for w in words if w.lower() not in CARD_LABELS]
        letters = sum(len(w) for w in words)
        digits = sum(c.isdigit() for c in t)
        if len(words) == 0 or digits > letters:
            continue
        score = letters + 5 * (len(words) >= 2)
        if score > best:
            best, name = score, " ".join(words)
    return name.strip().lower(), code


_ACCENTS = str.maketrans("áàâãäåéèêëíìîïóòôõöúùûüçñýÿāēīōū",
                         "aaaaaaeeeeiiiiooooouuuucnyyaeiou")


def plain(text):
    """minusculas, sem acento, so letras e espacos."""
    text = text.lower().translate(_ACCENTS)
    return " ".join(re.findall(r"[a-z]+", text))


def folder_name_for(name, code):
    """nome_do_aluno_codigo (ex.: alicia_ferreira_guimaraes_0101)."""
    base = "_".join(plain(name).split()) or "aluno"
    return "%s_%s" % (base, code) if code else base


def _edit(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def read_card(img):
    """Le o texto da foto da ficha. Retorna (nome, codigo, linhas lidas)."""
    h, w = img.shape[:2]
    k = min(1.0, 1600.0 / max(h, w))
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img
    res, _ = get_ocr()(small)
    lines = [r[1] for r in (res or []) if r[2] >= 0.5]
    name, code = parse_card(lines)
    return name, code, lines


def card_region(img, box):
    """Recorte abaixo do rosto, onde o aluno segura a ficha."""
    h, w = img.shape[:2]
    x, y, fw, fh = box
    x0, x1 = int(max(0, x - 2.5 * fw)), int(min(w, x + 3.5 * fw))
    y0, y1 = int(max(0, y + 0.8 * fh)), int(min(h, y + 7 * fh))
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None
    return img[y0:y1, x0:x1]


def find_card_box(region):
    """Acha o papel branco da ficha no recorte. Retorna x0, y0, x1, y1 ou None."""
    h, w = region.shape[:2]
    k = 400.0 / max(h, w)
    small = cv2.resize(region, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 55)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    # a ficha fica na frente do aluno: so conta o branco que passa pelo meio
    # do recorte (parede branca dos lados nao e ficha)
    mid0, mid1 = 0.35 * small.shape[1], 0.65 * small.shape[1]
    cs = [q for q in cs if cv2.boundingRect(q)[0] < mid1 and
          cv2.boundingRect(q)[0] + cv2.boundingRect(q)[2] > mid0]
    if not cs:
        return None
    cnt = max(cs, key=cv2.contourArea)
    area = cv2.contourArea(cnt)          # contorno cheio: o texto da ficha nao conta
    x, y, bw, bh = cv2.boundingRect(cnt)
    # sem papel branco grande = nao e foto de ficha (pula a leitura, que e lenta)
    if area < 0.04 * small.shape[0] * small.shape[1] or area < 0.35 * bw * bh:
        return None
    pad = 0.03 * max(bw, bh)
    return (int(max(0, (x - pad) / k)), int(max(0, (y - pad) / k)),
            int(min(w, (x + bw + pad) / k)), int(min(h, (y + bh + pad) / k)))


def _box(r):
    return np.array(r[0], np.float32)


# nomes e sobrenomes comuns: ajudam a corrigir a letra de mao ("ferveira" -> "ferreira")
NAMES = set("""
alice alicia amanda ana beatriz bianca bruna camila carolina cecilia clara dafne
daniela debora eduarda elisa emanuelly emilly ester fernanda gabriela gabrielly
giovana giovanna helena heloisa isabel isabela isabella isadora jamile joana julia
juliana lara larissa laura lavinia leticia livia lorena luana luiza manuela marcela
maria mariana marina melissa milena mirela natalia nicole olivia paula pietra rafaela
raissa rebeca sabrina sara sarah sofia sophia stella stephany tais thais valentina
vitoria yasmin yasmim agatha allana ana alana ayla brenda caroline catarina eloa
emanuele esther evelyn evellyn flavia geovana giulia ingrid isis jessica kamila
karina kauany kelly kemilly lais lethicia luna maite maisa mel nathalia nayara
pamela priscila rayssa samara samira tainara talita vanessa vivian
arthur artur bernardo bruno caio carlos cauan caua daniel davi david diego eduardo
enzo erick felipe fernando gabriel guilherme gustavo heitor henrique igor isaac
joao jorge jose juan kaique kaio kaua kaue leandro leonardo lorenzo lucas luan luca
luis luiz marcelo marcos matheus mateus miguel murilo nicolas otavio paulo pedro
rafael renan ricardo rodrigo samuel thiago tiago vinicius vitor victor wesley yago
yuri breno benjamin anthony andre alexandre antonio augusto benicio calebe cristian
emanuel enrico fabio francisco gael hugo ian joaquim kevin levi lorenzo mauricio
nathan noah raul ryan theo thomas valentim wallace william
silva santos oliveira souza sousa rodrigues ferreira alves pereira lima gomes costa
ribeiro martins carvalho almeida lopes soares fernandes vieira barbosa rocha dias
nascimento andrade moreira nunes marques machado mendes freitas cardoso ramos
goncalves santana teixeira araujo pinto correia moura cavalcanti batista campos
monteiro castro melo miranda reis barros duarte guimaraes figueiredo azevedo
borges brito cunha farias fonseca franco garcia leite lourenco macedo magalhaes
matos medeiros morais neves pacheco peixoto prado queiroz rezende sales sampaio
siqueira tavares toledo vasconcelos xavier camargo candido baptista bastos bueno
caetano coelho cruz dantas domingues esteves estevam fabri galvao gimenes
antonella aurora liz luisa mariah mirella maya heloise ana lis melina ana clarice
cecilia benicio bento otto ravi lucca vicente kaleb henry apollo matteo mathias
pietro joaquim davi gael raul lorenzo enzo valentim antony theodoro bryan
mendonca modesto barros bairos zanetti rizzo
junior filho neto sobrinho
""".split())


def best_name(reads, vocab):
    """
    Junta varias leituras do mesmo nome escrito a mao: para cada palavra escolhe
    a forma que mais combina com as leituras, com os nomes comuns e com as
    outras palavras da ficha (nome dos pais, e-mail).
    """
    lists = [r.split() for r in reads if r.split()]
    if not lists:
        return ""
    counts = {}
    for l in lists:
        counts[len(l)] = counts.get(len(l), 0) + 1
    n = max(counts, key=lambda k: (counts[k], k))
    rows = [l for l in lists if len(l) == n]
    out = []
    for i in range(n):
        ev = [l[i] for l in rows]
        med = min(ev, key=lambda c: sum(_edit(c, e) for e in ev))

        def near(w):
            lim = 0.45 if len(med) >= 5 else 0.34
            return abs(len(w) - len(med)) <= 2 and _edit(w, med) <= max(1, int(lim * len(med)))
        cands = set(ev) | {v for v in vocab if len(v) >= 4 and near(v)} | \
            {v for v in NAMES if near(v)}

        def score(c):
            s = sum(max(0.0, 1 - _edit(c, e) / float(max(len(c), len(e)))) for e in ev)
            return s + (1.5 if c in vocab else 0) + (2 if c in NAMES else 0)
        out.append(max(sorted(cands), key=score))
    return " ".join(out)


def _name_read(text, need_label=False):
    """Texto lido no campo do nome -> palavras do nome (sem o rotulo e sem "Serie")."""
    low = plain(text) if need_label else text.lower()
    if any(w in plain(text) for w in ("facul", "colegio", "cidade", "bairro", "endereco")):
        return ""                    # pegou outra linha da ficha
    for key in ("formando", "ormando", "mando", "ando", "ndo"):
        if key in low:
            text = (plain(text) if need_label else text)[low.find(key) + len(key):]
            break
    else:
        if need_label:
            return ""
    words = []
    for w in plain(text).split():
        if w.endswith("serie") and len(w) > 5:
            w = w[:-5]
        if w in ("serie", "n", "no") or len(w) < 2:
            continue
        words.append(w)
    return " ".join(words)


GALA_LABEL = re.compile(r"formand|ormand|rmando|mando|ando:|ndo:")
GALA_MARK = re.compile(r"gala|formaturas|faculdade|instagram|chinelo")


def _gala_code(img, res, bottom):
    """
    Numero escrito grande no canto de cima da ficha, acima de `bottom` (ele
    desce ate perto da linha do nome). A leitura da ficha inteira vale mais; o
    recorte em tamanhos menores ajuda quando o tracado e grosso.
    """
    ocr = get_ocr()
    W = img.shape[1]
    zone = img[0:int(max(10, bottom)), int(0.4 * W):W]
    found = [(r, 1.0, 3.0) for r in res
             if _box(r).mean(0)[1] < bottom and _box(r)[:, 0].min() > 0.4 * W]
    if zone.size:
        for sc in (0.3, 0.45, 0.6, 1.0):
            z = cv2.resize(zone, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) if sc != 1 else zone
            found += [(r, 1.0 / sc, 1.0) for r in (ocr(z)[0] or [])]
    votes = {}
    for r, k, wt in found:
        txt = r[1].replace(" ", "")
        dig = sum(ch.isdigit() for ch in txt)
        if r[2] >= 0.6 and dig >= 2 and dig >= 0.8 * len(txt):
            d = re.sub(r"\D", "", txt)
            size = float(np.ptp(_box(r)[:, 1])) * k
            v = votes.get(d, (0.0, 0.0))
            votes[d] = (v[0] + wt * r[2], max(v[1], size))
    # o mais lido ganha; empate: o mais completo ("243" ganha de "24")
    code = max(votes, key=lambda d: (round(votes[d][0], 1), len(d), votes[d][1])) if votes else ""
    return code


def _label_line(res, lab):
    """Texto do rotulo do nome + caixas lidas logo depois dele, na mesma linha."""
    b = _box(lab)
    end = (b[1] + b[2]) / 2           # meio da borda direita do rotulo
    hl = max(4.0, float(b[2][1] - b[1][1]))
    nxt = []
    for r in res:
        rb = _box(r)
        start = (rb[0] + rb[3]) / 2
        if r is not lab and abs(start[1] - end[1]) < 0.4 * hl and \
                end[0] - 2 * hl <= start[0] <= end[0] + 3 * hl:
            nxt.append((float(start[0]), r[1]))
    return " ".join([lab[1]] + [t for _, t in sorted(nxt)])


def read_gala_card(img, res):
    """
    Ficha da Gala Eventos: nome escrito em "Nome/Formando" e o numero grande
    do canto de cima. Retorna (nome, codigo) ou None se nao for esse modelo.
    """
    lab = [r for r in res if GALA_LABEL.search(r[1].lower())]
    fac = [r for r in res if "faculdade" in r[1].lower() or "colegio" in plain(r[1])]
    if not lab:
        if not any(GALA_MARK.search(plain(r[1])) for r in res):
            return None
        bottom = float(_box(fac[0])[:, 1].max()) if fac else 0.35 * img.shape[0]
        code = _gala_code(img, res, bottom)
        if not fac:
            return "", code
        # a linha do nome nao foi achada: le de novo so a faixa abaixo de
        # "Faculdade/Colegio", maior. Sem nome legivel fica so o numero.
        fb = _box(fac[0])
        y = float(fb.mean(0)[1])
        fh = float(np.ptp(fb[:, 1]))
        band = img[int(y):int(y + 1.6 * fh)]
        if band.shape[0] < 8:
            return "", code
        band = cv2.resize(band, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        rs = [r for r in (get_ocr()(band)[0] or []) if r[2] >= 0.5]
        lab = [r for r in rs if GALA_LABEL.search(r[1].lower())]
        name = _name_read(_label_line(rs, lab[0])) if lab else ""
        vocab = {w for r in res for w in plain(r[1]).split() if len(w) >= 4}
        return (best_name([name], vocab) if name else ""), code
    lab = lab[0]
    b = _box(lab)
    c = b.mean(0)
    h = float(b[:, 1].max() - b[:, 1].min())
    sp = float(abs(c[1] - _box(fac[0]).mean(0)[1])) if fac else 1.3 * h
    code = _gala_code(img, res, float(c[1] - 0.4 * h))
    ocr = get_ocr()

    # nome: varias leituras da linha "Nome/Formando" (desentortada), com e sem
    # folga para cima (a letra de mao sobe da linha)
    reads = [_name_read(_label_line(res, lab))]
    ang = float(np.degrees(np.arctan2(b[1][1] - b[0][1], b[1][0] - b[0][0])))
    rot = cv2.getRotationMatrix2D((float(c[0]), float(c[1])), ang, 1.0)
    img_r = cv2.warpAffine(img, rot, (img.shape[1], img.shape[0]), borderValue=(255, 255, 255))
    rb = cv2.transform(b[None], rot)[0]
    left = float(rb[:, 0].min())
    right = float(img.shape[1])
    for r in res:
        rb2 = cv2.transform(_box(r)[None], rot)[0]
        if (("n°" in r[1] or "nº" in r[1]) and rb2[:, 0].min() > left + 2 * h
                and abs(rb2[:, 1].mean() - c[1]) < 0.6 * sp):
            right = min(right, float(rb2[:, 0].min()))
    for up, down in ((0.8, 0.3), (0.65, 0.35)):
        band = img_r[int(max(0, c[1] - up * sp)):int(c[1] + down * sp),
                     int(max(0, left - 5)):int(right)]
        if band.shape[0] < 8 or band.shape[1] < 20:
            continue
        for sc in (1, 2):
            im = cv2.resize(band, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC) \
                if sc > 1 else band
            rr, _ = ocr(im, use_det=False, use_cls=False)
            if rr and rr[0][1] >= 0.5:
                reads.append(_name_read(rr[0][0], need_label=True))
    vocab = set()
    for r in res:
        if r is not lab:
            vocab.update(w for w in plain(r[1]).split() if len(w) >= 4)
    return best_name(reads, vocab), code


def read_card_photo(img, face_box):
    """
    Le a ficha que o aluno segura abaixo do rosto. Retorna (nome, codigo, ficha
    da Gala Eventos?).
    """
    region = card_region(img, face_box)
    if region is None:
        return "", "", False
    cb = find_card_box(region)
    if cb is None:
        return "", "", False
    card = region[cb[1]:cb[3], cb[0]:cb[2]]
    hh, ww = card.shape[:2]
    k = min(1.0, 1600.0 / max(hh, ww))
    if k < 1:
        card = cv2.resize(card, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    res, _ = get_ocr()(card)
    res = [r for r in (res or []) if r[2] >= 0.5]
    gala = read_gala_card(card, res)
    if gala is not None:
        return gala[0], gala[1], True
    name, code = parse_card([r[1] for r in res])
    return name, code, False


def find_cards(images, photo_ids, scores, boxes, log=print,
               progress=lambda done, total, text=None: None):
    """
    Acha, no meio das fotos da festa, as fotos de ficha: poucas pessoas e,
    logo abaixo do maior rosto, um texto com nome e codigo. Retorna
    {foto: (nome, codigo, rosto do aluno)}.
    """
    sure = {}
    for k, ph in enumerate(photo_ids):
        if scores[k] >= SURE_FACE:
            sure.setdefault(int(ph), []).append(k)
    cands = sorted(ph for ph, ks in sure.items() if len(ks) <= 3)
    cards = {}
    if cands:
        get_ocr(log)
    for n, ph in enumerate(cands):
        progress(n + 1, len(cands), "Procurando fichas...")
        ks = sure[ph]
        k = max(ks, key=lambda k: boxes[k][2] * boxes[k][3])     # o aluno: maior rosto
        if len(ks) > 1 and sorted(boxes[j][2] * boxes[j][3] for j in ks)[-2] > \
                0.6 * boxes[k][2] * boxes[k][3]:
            continue            # dois rostos do mesmo tamanho: foto de grupo, nao ficha
        img = read_image(images[ph])
        if img is None:
            continue
        try:
            name, code, gala = read_card_photo(img, boxes[k])
        except Exception as e:
            log("Leitor de fichas falhou: %s" % e)
            break
        words = plain(name).split()
        if len(words) > 6 or any(w in CARD_JUNK for w in words):
            name = ""               # pegou o texto impresso da ficha, nao o nome
        # na ficha da Gala Eventos, sem numero legivel a pasta fica so com o
        # nome, e sem nome legivel fica so com o numero
        if (code and (gala or len(name.replace(" ", "")) >= 3)) or \
                (gala and len(name.split()) >= 2 and len(name.replace(" ", "")) >= 6):
            cards[ph] = (name, code, k)
            log("Ficha: %s -> %s" % (os.path.basename(images[ph]), folder_name_for(name, code)))
    return cards


# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------

def process_folder(src, engine, log=print, progress=lambda done, total, text=None: None,
                   out_root=None, report=None):
    """
    Processa uma pasta de fotos e cria festa_N. Se no meio das fotos houver
    fotos de ficha (aluno segurando nome e codigo), cria uma pasta para cada
    aluno ("maria eduarda_4821") e ignora quem nao tem ficha (pais,
    convidados). Sem fichas, agrupa por pessoa em aluno_1, aluno_2...
    Retorna o caminho criado.
    """
    out_root = out_root or data_dir()
    images = list_images(src)
    if not images:
        raise RuntimeError("Nenhuma foto encontrada nessa pasta.")

    embs, photo_ids, scores, boxes = scan_faces(images, engine, log, progress)
    if not len(embs):
        raise RuntimeError("Nenhum rosto encontrado nas fotos.")

    log("Procurando fotos de ficha...")
    cards = find_cards(images, photo_ids, scores, boxes, log, progress)

    if cards:
        log("Separando os alunos das %d ficha(s)..." % len(cards))
        found = assign_by_cards(embs, photo_ids, scores, cards, len(images))
        people = [(n, ph) for n, ph in found.items() if ph]
        missing = [n for n, ph in found.items() if not ph]
        if report is not None:
            report["fichas"] = len(found)
            report["missing"] = missing
        if missing:
            log("Alunos sem fotos além da ficha: " + ", ".join(missing))
        if not people:
            raise RuntimeError("Achei %d ficha(s), mas nenhum desses alunos aparece nas "
                               "outras fotos." % len(found))
    else:
        log("Agrupando %d rostos..." % len(embs))
        groups = cluster_faces(embs, photo_ids)
        # grupo formado so por deteccoes duvidosas = provavelmente nao e um rosto
        groups = [g for g in groups if max(scores[k] for k in g) >= SURE_FACE]
        if not groups:
            raise RuntimeError("Nenhum rosto encontrado nas fotos.")
        # mais fotos primeiro (aluno_1 = quem mais aparece)
        phs = sorted([sorted({int(photo_ids[k]) for k in g}) for g in groups],
                     key=lambda ph: (-len(ph), ph[0]))
        people = [("aluno_%d" % i, ph) for i, ph in enumerate(phs, 1)]

    event = os.path.join(out_root, next_numbered_name(out_root, "festa"))
    os.makedirs(event)
    for folder, ph in people:
        d = os.path.join(event, folder)
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
    log("Pronto! %d pasta(s) criadas em %s" % (len(people), os.path.basename(event)))
    return event


# ---------------------------------------------------------------------------
# Atualizacao automatica
# ---------------------------------------------------------------------------

def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache",
                                               "User-Agent": "ReconhecimentoFacial"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check_update():
    """
    Ve se existe versao nova. Retorna None, ("codigo", versao) quando o codigo
    novo ja foi baixado (vale na proxima vez que abrir) ou ("completa", versao)
    quando a mudanca precisa do .exe novo.
    """
    runtime = int(os.environ.get("RF_RUNTIME", "0"))
    if not runtime:             # rodando direto do .py, sem o .exe
        return None
    info = json.loads(_get(UPDATE_BASE + "versao.json").decode("utf-8"))
    remote = int(info["versao"])
    if remote <= VERSAO:
        return None
    if int(info.get("runtime", 1)) > runtime:
        return ("completa", remote)
    dest_dir = os.path.join(os.path.dirname(data_dir()), "atualizacao")
    dest = os.path.join(dest_dir, "reconhecimento.py")
    try:
        with open(dest, encoding="utf-8") as f:
            m = re.search(r"^VERSAO\s*=\s*(\d+)", f.read(), re.M)
        if m and int(m.group(1)) >= remote:
            return ("codigo", remote)        # ja baixado, falta reabrir
    except OSError:
        pass
    try:
        with open(dest + ".com_erro", encoding="utf-8") as f:
            m = re.search(r"^VERSAO\s*=\s*(\d+)", f.read(), re.M)
        if m and int(m.group(1)) >= remote:
            return None                      # essa versao ja deu erro aqui
    except OSError:
        pass
    code = _get(UPDATE_BASE + "reconhecimento.py", timeout=30).decode("utf-8")
    m = re.search(r"^VERSAO\s*=\s*(\d+)", code, re.M)
    if not m or int(m.group(1)) != remote:
        return None                          # arquivo ainda nao atualizado no servidor
    compile(code, "reconhecimento.py", "exec")   # nao salva codigo quebrado
    os.makedirs(dest_dir, exist_ok=True)
    with open(dest + ".tmp", "w", encoding="utf-8") as f:
        f.write(code)
    os.replace(dest + ".tmp", dest)
    return ("codigo", remote)


def restart_program(args=()):
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
        # sem isso o .exe novo usa a pasta temporaria deste, que e apagada
        # quando este fecha, e abre com erro (traceback)
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for k in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE",
                  "_PYI_PARENT_PROCESS_LEVEL", "_PYI_SPLASH_IPC"):
            env.pop(k, None)
    else:
        cmd = [sys.executable, os.path.abspath(sys.argv[0])]
    subprocess.Popen(cmd + list(args), env=env)


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
YELLOW = "#ffd600"
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
    win.title("%s  —  versão %d" % (APP_NAME, VERSAO))
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
    back_btn.configure(fg=YELLOW, activeforeground=YELLOW, disabledforeground="#857000")
    back_btn.pack(side="left", padx=(10, 0))
    open_btn = make_button(top, "Abrir no Explorer", None)
    open_btn.pack(side="right")

    tip = tk.Label(win, text="Dica: junte às fotos da festa as fotos de cada aluno segurando "
                   "a ficha. As pastas saem com o nome e o código do aluno.",
                   bg=BG, fg=FG_DIM, font=("Segoe UI", 10), padx=12, anchor="w",
                   justify="left")
    tip.pack(fill="x", pady=(0, 8))
    tip.bind("<Configure>", lambda e: tip.configure(wraplength=max(200, e.width - 24)))

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
    status_row = tk.Frame(bottom, bg=BG)
    status_row.pack(fill="x", pady=(6, 0))
    tk.Label(status_row, textvariable=status_var, bg=BG, fg=FG_DIM, font=("Segoe UI", 10),
             anchor="w").pack(side="left")
    update_lbl = tk.Label(status_row, text="", bg=BG, fg=ACCENT_HOVER,
                          font=("Segoe UI", 10, "bold underline"), cursor="hand2")

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

    def busy(on):
        state["busy"] = on
        add_btn.configure(state="disabled" if on else "normal")
        if on:
            prog["value"] = 0

    # --- atualizacao ---------------------------------------------------------
    def update_job():
        try:
            msgs.put(("update", check_update()))
        except Exception:
            pass                    # sem internet: tenta de novo na proxima vez

    def show_update(res):
        if not res:
            return
        kind, ver = res
        if kind == "codigo":
            update_lbl.configure(text="Versão %d pronta. Clique para reiniciar e usar." % ver)

            def go(_e=None):
                if state["busy"]:
                    messagebox.showinfo(APP_NAME, "Espere terminar o processamento.",
                                        parent=win)
                    return
                restart_program()
                win.destroy()
        else:
            update_lbl.configure(text="Versão %d disponível: clique para baixar o "
                                      "programa novo." % ver)

            def go(_e=None):
                import webbrowser
                webbrowser.open(FULL_DOWNLOAD)
        update_lbl.bind("<Button-1>", go)
        update_lbl.pack(side="right")

    # --- processamento ------------------------------------------------------
    def worker(folder):
        def log(m):
            msgs.put(("status", m))
        try:
            if state["engine"] is None:
                log("Carregando modelos de reconhecimento...")
                state["engine"] = FaceEngine(log)
            report = {}
            ev = process_folder(folder, state["engine"], log,
                                lambda d, t, txt=None: msgs.put(("prog", d, t, txt)),
                                root_dir, report=report)
            msgs.put(("done", ev, report))
        except Exception as e:  # mostra qualquer erro ao usuario
            msgs.put(("error", str(e)))

    def add_folder():
        if state["busy"]:
            return
        folder = filedialog.askdirectory(title="Escolha a pasta com as fotos da festa")
        if not folder:
            return
        busy(True)
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
                    status_var.set("%s %d de %d" % (m[3] or "Analisando fotos...", m[1], m[2]))
                elif m[0] == "update":
                    show_update(m[1])
                elif m[0] in ("done", "error"):
                    busy(False)
                    if m[0] == "done":
                        n = len(subdirs(m[1]))
                        rep = m[2]
                        if "fichas" in rep:
                            text = ("%s criada: %d ficha(s), %d aluno(s) com fotos."
                                    % (os.path.basename(m[1]), rep["fichas"], n))
                            if rep["missing"]:
                                text += "\n\nNão apareceram em outras fotos:\n" + \
                                        "\n".join(rep["missing"][:30])
                        else:
                            text = "%s criada com %d pessoa(s)." % (os.path.basename(m[1]), n)
                        status_var.set("Pronto! " + text.split("\n")[0])
                        state["current"] = m[1]
                        state["sel"] = None
                        search_var.set("")
                        refresh()
                        messagebox.showinfo(APP_NAME, text)
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
    threading.Thread(target=update_job, daemon=True).start()
    search.focus_set()
    win.mainloop()


def run_cli(folder):
    """Uso sem interface: reconhecimento.exe C:\\caminho\\fotos"""
    engine = FaceEngine()
    ev = process_folder(folder, engine)
    print(ev)


def self_test():
    """Usado no build: confere se o .exe abre os modelos e o leitor de fichas."""
    out = os.path.join(app_dir(), "autoteste.txt")
    try:
        engine = FaceEngine()
        img = np.full((200, 600, 3), 255, np.uint8)
        cv2.putText(img, "MARIA 4821", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
        name, code, lines = read_card(img)
        assert engine.detect(img).shape[1] == 15
        msg = "ok v%d %s %s mao=%s" % (VERSAO, name, code,
                                         "sim" if hand_model(download=False) else "nao")
    except Exception as e:
        msg = "erro %r" % e
    with open(out, "w", encoding="utf-8") as f:
        f.write(msg)


def main(argv):
    if argv and argv[0] == "--autoteste":
        self_test()
    elif argv and argv[0] == "--autoteste-reinicio":
        restart_program(["--autoteste"])    # usado no build: testa o reiniciar
    elif argv and os.path.isdir(argv[0]):
        run_cli(argv[0])
    else:
        run_gui()


if __name__ == "__main__":
    main(sys.argv[1:])
