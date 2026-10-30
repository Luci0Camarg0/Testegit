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
import hashlib
import traceback
import threading
import time
import queue
import subprocess
import urllib.request

import numpy as np
import cv2

APP_NAME = "Reconhecimento Facial"

# Atualizacao automatica: a cada mudanca no codigo, aumente VERSAO aqui e em
# versao.json. RUNTIME_NEEDED so aumenta quando o .exe inteiro precisa ser
# baixado de novo (biblioteca ou modelo novo); veja iniciar.py.
VERSAO = 21
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
LEFTOVER_FOLDER = "sem_aluno"   # fotos que nao foram para nenhum aluno
DISCARD_FOLDER = "fotos_descartadas"  # dentro do aluno: olho fechado, olhando para o lado...
NO_ID_FOLDER = "aluno_sem_id%d"  # aluno sem ficha legivel: separado so pelo rosto
DOUBT_SUFFIX = "_conferir"   # numero repetido em fichas de alunos diferentes
SAME_CARD_FACE = 0.65       # duas fichas com o mesmo numero: so junta se for o mesmo rosto
SEQ_MATCH = 0.62            # foto logo depois da ficha: o mesmo aluno fica acima disso
SEQ_WEAK = 0.40             # rosto de lado/borrado: so vai se o aluno aparecer de novo logo depois
SEQ_MARGIN = 0.10           # ...e tem que parecer claramente mais com ele do que com outro aluno
NEAR_MARGIN = 0.05          # foto sozinha colada nas fotos do aluno: basta parecer mais com ele
ALONE_MATCH = 0.55          # foto sozinha longe das fotos do aluno: tem que parecer com ele
ALONE_MARGIN = 0.20         # ...e muito mais do que com qualquer outro aluno
FREE_GROUP = 0.55           # fotos fora da sequencia: primeiro junta as da mesma pessoa
FREE_MATCH = 0.65           # ...e o grupo so vai para o aluno se parecer muito com ele
FREE_MARGIN = 0.15          # ...e bem mais do que com o segundo aluno mais parecido
NO_ID_SAME = 0.50           # fotos sem ficha: mesma pessoa para virar uma pasta aluno_sem_idN
MAX_PARALLEL = 2            # fila de pastas: quantas pastas sao processadas ao mesmo tempo


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


_festa_lock = threading.Lock()


def new_event_dir(parent, prefix="festa"):
    """Cria festa_N sem repetir, mesmo com duas pastas terminando juntas."""
    with _festa_lock:
        os.makedirs(parent, exist_ok=True)
        while True:
            d = os.path.join(parent, next_numbered_name(parent, prefix))
            try:
                os.makedirs(d)
                return d
            except FileExistsError:
                continue


class Cancelled(Exception):
    """A pessoa clicou em Cancelar na fila de pastas."""


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

def cluster_faces(embs, photo_ids, threshold=SAME_PERSON, merge=True):
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
    return merge_groups(X, groups, ids) if merge else groups


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


def scan_faces(images, engine, log=print, progress=lambda done, total, text=None: None,
               extra=None, card_reads=None):
    """
    Detecta e descreve todos os rostos. Retorna (embeddings, foto de cada
    rosto, confianca, caixa x,y,w,h de cada rosto). Com extra={} guarda tambem
    como cada rosto esta (olhos, boca, virado) e uma miniatura de cada foto,
    usados para separar as fotos bonitas. Com card_reads={} ja le a ficha de
    cada foto que pode ser ficha, com a foto ainda aberta (sem abrir de novo).
    """
    embs, photo_ids, scores, boxes = [], [], [], []
    looks = extra.setdefault("looks", []) if extra is not None else None
    minis = extra.setdefault("minis", {}) if extra is not None else None
    text = "Analisando fotos e fichas..." if card_reads is not None else "Analisando fotos..."
    if card_reads is not None:
        with _ocr_lock:
            get_ocr(log)
    total = len(images)
    for i, path in enumerate(images):
        img = read_image(path)
        if img is None:
            log("Não foi possível abrir: %s" % os.path.basename(path))
            progress(i + 1, total, text)
            continue
        first, kept = len(embs), 0
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
            if looks is not None:
                looks.append(face_look(img, f) if f[14] >= SURE_FACE else None)
            kept += 1
        if minis is not None:
            minis[i] = photo_mini(img)
        log("%s: %d rosto(s)" % (os.path.basename(path), kept))
        if card_reads is not None and not card_reads.get(None):
            ks = [k for k in range(first, len(embs)) if scores[k] >= SURE_FACE]
            read = _card_candidate(img, ks, {k: np.array(boxes[k], np.float32) for k in ks}, log)
            if read is not None:
                card_reads[i] = read
            if read == "erro":
                card_reads[None] = True     # leitor quebrou: nao tenta mais fichas
        progress(i + 1, total, text)
    return (np.array(embs, np.float32).reshape(-1, 128), np.array(photo_ids, int),
            np.array(scores), np.array(boxes, np.float32).reshape(-1, 4))


# ---------------------------------------------------------------------------
# Fotos bonitas (olhos abertos, olhando para a camera)
# ---------------------------------------------------------------------------
# Modelos do MediaPipe (Google, licenca Apache 2.0) convertidos para ONNX: 478
# pontos do rosto e, a partir deles, quanto cada olho esta fechado, a boca
# aberta e para onde os olhos olham. Vao dentro do .exe novo; quem tem o .exe
# antigo baixa uma vez (7 MB) para a pasta "atualizacao".
LOOK_MODELS = ("face_landmarks_detector.onnx", "face_blendshapes.onnx")
LOOK_MIN_PX = 70            # rosto menor que isso (foto de longe): nao da para julgar, fica
# indices dos 146 pontos que o modelo de expressoes usa (iguais aos do MediaPipe)
LOOK_POINTS = [0, 1, 4, 5, 6, 7, 8, 10, 13, 14, 17, 21, 33, 37, 39, 40, 46, 52, 53, 54, 55,
               58, 61, 63, 65, 66, 67, 70, 78, 80, 81, 82, 84, 87, 88, 91, 93, 95, 103, 105,
               107, 109, 127, 132, 133, 136, 144, 145, 146, 148, 149, 150, 152, 153, 154,
               155, 157, 158, 159, 160, 161, 162, 163, 168, 172, 173, 176, 178, 181, 185,
               191, 195, 197, 234, 246, 249, 251, 263, 267, 269, 270, 276, 282, 283, 284,
               285, 288, 291, 293, 295, 296, 297, 300, 308, 310, 311, 312, 314, 317, 318,
               321, 323, 324, 332, 334, 336, 338, 356, 361, 362, 365, 373, 374, 375, 377,
               378, 379, 380, 381, 382, 384, 385, 386, 387, 388, 389, 390, 397, 398, 400,
               402, 405, 409, 415, 454, 466, 468, 469, 470, 471, 472, 473, 474, 475, 476, 477]
LOOK_SHAPES = {"blinkL": 9, "blinkR": 10, "inL": 13, "inR": 14, "outL": 15, "outR": 16,
               "squintL": 19, "squintR": 20, "jaw": 25, "smileL": 44, "smileR": 45}

_look = {"models": None, "tried": False}
_look_lock = threading.Lock()


def look_models(log=print, download=True):
    """Os dois modelos (pontos e expressoes) ou None se nao tiver como usar."""
    with _look_lock:
        if _look["models"] is not None or _look["tried"]:
            return _look["models"]
        dl = os.path.join(os.path.dirname(data_dir()), "atualizacao", "modelos")
        paths = []
        for name in LOOK_MODELS:
            found = None
            for d in (os.path.join(resource_dir(), "assets"), os.path.join(app_dir(), "assets"),
                      os.path.join(resource_dir(), "models"), dl):
                p = os.path.join(d, name)
                if os.path.isfile(p) and os.path.getsize(p) > 100000:
                    found = p
                    break
            if found is None and download:
                try:
                    log("Baixando o detector de olhos fechados (só desta vez)...")
                    data = _get(UPDATE_BASE + "assets/" + name, timeout=120)
                    if len(data) > 100000:
                        os.makedirs(dl, exist_ok=True)
                        found = os.path.join(dl, name)
                        with open(found + ".tmp", "wb") as f:
                            f.write(data)
                        os.replace(found + ".tmp", found)
                except Exception:
                    found = None
            paths.append(found)
        if None in paths:
            if download:
                _look["tried"] = True
            return None
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            _look["models"] = [ort.InferenceSession(p, opts, providers=["CPUExecutionProvider"])
                               for p in paths]
        except Exception:
            _look["models"] = None
        _look["tried"] = True
        return _look["models"]


def face_look(img, f):
    """
    Como o rosto esta na foto: olhos (0 aberto .. 1 fechado), boca, para onde
    a cabeca e os olhos apontam. None se o rosto for pequeno demais ou sem
    modelo.
    """
    if f[2] < LOOK_MIN_PX:
        return None
    models = _look["models"] if _look["tried"] else look_models(download=False)
    if not models:
        return None
    x, y, w, h = [float(v) for v in f[:4]]
    reye, leye = f[4:6], f[6:8]
    ang = float(np.degrees(np.arctan2(leye[1] - reye[1], leye[0] - reye[0])))
    c = (x + w / 2, y + h / 2)
    M = cv2.getRotationMatrix2D(c, ang, 256.0 / (max(w, h) * 1.5))
    M[:, 2] += (128 - c[0], 128 - c[1])
    crop = cv2.warpAffine(img, M, (256, 256), flags=cv2.INTER_LINEAR)
    inp = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32)[None] / 255.0
    try:
        lm_model, bs_model = models
        P = lm_model.run(None, {lm_model.get_inputs()[0].name: inp})[0].reshape(478, 3)
        bs = bs_model.run(None, {bs_model.get_inputs()[0].name:
                                 P[LOOK_POINTS, :2][None].astype(np.float32)})[0].ravel()
    except Exception:
        return None

    def dist(a, b):
        return float(np.linalg.norm(P[a, :2] - P[b, :2])) + 1e-6
    out = {k: float(bs[i]) for k, i in LOOK_SHAPES.items()}
    # abertura dos olhos medida nos pontos (altura / largura de cada olho)
    out["earL"] = (dist(159, 145) + dist(158, 153) + dist(160, 144)) / 3 / dist(33, 133)
    out["earR"] = (dist(386, 374) + dist(385, 380) + dist(387, 373)) / 3 / dist(362, 263)
    out["mouth"] = dist(13, 14) / dist(61, 291)
    # cabeca virada: nariz em relacao ao meio das bochechas (-1 .. 1)
    mid = (P[234, 0] + P[454, 0]) / 2
    out["turn"] = float((P[1, 0] - mid) / (abs(P[454, 0] - P[234, 0]) / 2 + 1e-6))
    # onde a iris esta dentro de cada olho (0 = no meio; - esquerda, + direita
    # da foto), somando os dois olhos: mais preciso que as expressoes do modelo
    out["iris"] = float((P[468, 0] - P[33, 0]) / (P[133, 0] - P[33, 0] + 1e-6) +
                        (P[473, 0] - P[362, 0]) / (P[263, 0] - P[362, 0] + 1e-6) - 1)
    return out


def photo_mini(img):
    """Miniatura cinza da foto inteira: duas fotos quase iguais tem a mesma."""
    m = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (32, 24), interpolation=cv2.INTER_AREA)
    m = m.astype(np.float32).ravel()
    m -= m.mean()
    return m / (np.linalg.norm(m) + 1e-6)


# limites medidos nas fotos reais (estudio e festa, criancas e formandos)
# Medido em 650 rostos das pastas Manha, 1 Ano e 2 Ano A: olho fechado de verdade
# ficou acima de 0.45; sorriso de olho apertado chega a 0.39, mas com "apertado"
# alto. Olhando para o lado: |olhos + 2 x cabeca| acima de 0.6; olhando para a
# camera (mesmo de cabeca virada, os olhos compensam) ficou ate 0.31.
EYES_CLOSED_BLINK = 0.42    # quanto o modelo acha que os dois olhos estao fechados
EYES_CLOSED_SQUINT = 0.10   # ...e bem mais "fechado" do que "apertado" (sorriso)
LOOK_AWAY = 0.55            # direcao do olhar em relacao a camera
# Pela posicao da iris (601 rostos da Manha, conferidos um a um): olhando para a
# camera ficou ate 0.15 (2T1A9436 da Alice, 2T1A9576 do Leite); olhando para o lado
# a partir de 0.23 (2T1A9561 e 9562 do Bento, 2T1A9581 da Agatha), que passavam.
IRIS_AWAY = 0.20
IRIS_TURN = 0.4             # quanto a cabeca virada puxa a iris para o outro lado
MOUTH_OPEN_JAW = 0.35       # boca muito aberta
MOUTH_OPEN_RATIO = 0.35
SAME_SHOT = 0.92            # duas fotos seguidas quase iguais (mesma pose e fundo)
# Olho quase fechado / olhando para baixo: comparado com as outras fotos do proprio
# aluno (cada um tem o seu olho). 2T1A9842 do Gerson: 0.70 do normal dele; as
# outras fotos dele ficaram acima de 0.94. Sorrindo o olho fecha um pouco: nao conta.
OWN_EYES = 0.78
OWN_EYES_MIN_PHOTOS = 4     # precisa de fotos suficientes para saber o normal dele
OWN_EYES_SMILE = 0.30


def look_problem(q):
    """Motivo para descartar a foto pelo rosto do aluno, ou ''."""
    if q is None:
        return ""
    blink = (q["blinkL"] + q["blinkR"]) / 2
    squint = (q["squintL"] + q["squintR"]) / 2
    if blink >= EYES_CLOSED_BLINK and blink - squint >= EYES_CLOSED_SQUINT:
        return "olho fechado"
    # para onde olha: olhos dentro do rosto + quanto a cabeca esta virada
    # (cabeca virada com os olhos voltados para a camera da quase zero)
    eyes = ((q["outL"] + q["inR"]) - (q["inL"] + q["outR"])) / 2
    if abs(eyes + 2 * q["turn"]) >= LOOK_AWAY:
        return "olhando para o lado"
    # pela iris: cabeca virada para um lado e olhos para o outro = olhando a camera
    if "iris" in q and abs(q["iris"] + IRIS_TURN * q["turn"]) >= IRIS_AWAY:
        return "olhando para o lado"
    return ""


def mouth_open(q):
    return q is not None and (q["jaw"] >= MOUTH_OPEN_JAW or q["mouth"] >= MOUTH_OPEN_RATIO)


def pick_good_photos(people, owner, photo_ids, looks, minis, card_photos, reasons=None):
    """
    Escolhe, em cada pasta de aluno, as fotos que vao para fotos_descartadas:
    olho fechado ou olhando para o lado (olhando so o rosto daquele aluno), e
    boca muito aberta quando existe uma foto quase igual com a boca fechada.
    A separacao dos alunos nao muda. A foto da ficha nunca e descartada, e a
    pasta nunca fica sem nenhuma foto boa. Retorna {pasta: {fotos}}.
    """
    faces = {}
    for k, ph in enumerate(photo_ids):
        faces.setdefault(int(ph), []).append(k)
    out = {}
    for folder, ph in people:
        if folder == LEFTOVER_FOLDER:
            continue
        q = {}
        for p in ph:
            ks = [k for k in faces.get(p, []) if owner.get(k) == folder]
            q[p] = looks[ks[0]] if ks and ks[0] < len(looks) else None
        judged = [p for p in ph if p not in card_photos]
        bad = {p: look_problem(q[p]) for p in judged}
        bad = {p: r for p, r in bad.items() if r}
        ears = {p: (q[p]["earL"] + q[p]["earR"]) / 2 for p in ph if q[p] is not None}
        if len(ears) >= OWN_EYES_MIN_PHOTOS:
            normal = float(np.median(list(ears.values())))
            for p in judged:
                if p in bad or p not in ears:
                    continue
                smile = (q[p]["smileL"] + q[p]["smileR"]) / 2
                if ears[p] <= OWN_EYES * normal and smile < OWN_EYES_SMILE:
                    bad[p] = "olho quase fechado / olhando para baixo"
        for p in judged:
            if p in bad or not mouth_open(q[p]):
                continue
            for o in judged:
                if o != p and abs(o - p) <= 3 and o not in bad and q[o] is not None and \
                        not mouth_open(q[o]) and p in minis and o in minis and \
                        float(minis[p] @ minis[o]) >= SAME_SHOT:
                    bad[p] = "boca aberta (tem uma igual de boca fechada)"
                    break
        if judged and len(bad) == len(judged) and not set(ph) & set(card_photos):
            # todas ruins: a menos ruim fica, para a pasta nao ficar vazia
            keep = min(bad, key=lambda p: (q[p] or {}).get("blinkL", 0) +
                       (q[p] or {}).get("blinkR", 0))
            del bad[keep]
        if bad:
            out[folder] = set(bad)
            if reasons is not None:
                reasons[folder] = bad
    return out


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
            # mesmo numero e mesmo rosto = mesma ficha fotografada de novo. Mesmo
            # numero com outro rosto = numero lido errado: fica separado
            if code and code in cand["codes"] and \
                    float(np.max(X[cand["faces"]] @ X[k])) >= SAME_CARD_FACE:
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
    out, used, no_id = [], set(), 0
    for g in groups:
        g["code"] = max(sorted(set(g["codes"])), key=lambda c: (g["codes"].count(c), len(c))) \
            if g["codes"] else ""
    taken = [g["code"] for g in groups if g["code"]]
    for g in groups:
        code = g["code"]
        name = max(g["names"], key=_name_quality) if g["names"] else ""
        if name or code:
            folder = base = folder_name_for(name, code)
            if taken.count(code) > 1:
                # o mesmo numero em fichas de alunos diferentes: um foi lido
                # errado. Ficam separados e a pasta avisa para conferir
                folder = base = folder + DOUBT_SUFFIX
        else:
            no_id += 1
            folder = base = NO_ID_FOLDER % no_id
        n = 2
        while folder in used:           # mesmo nome lido em fichas diferentes
            folder = "%s_%d" % (base, n)
            n += 1
        used.add(folder)
        out.append((folder, g["photos"], g["faces"]))
    return out


def assign_by_cards(embs, photo_ids, scores, cards, n_photos, owners=None):
    """
    Separa as fotos pelos alunos das fichas, sem agrupar todo mundo antes.
    1. Sequencia: as fotos logo depois da ficha sao do mesmo aluno enquanto o
       rosto dele continuar aparecendo e for claramente ele (para na proxima
       ficha ou depois de 2 fotos sem ele). Fotos sem rosto (de costas) ou com
       o rosto de lado no meio da sequencia so vao se ele aparecer de novo.
    2. O resto: junta os rostos da mesma pessoa e o grupo inteiro vai para o
       aluno so se for claramente ele, comparando com a ficha e a sequencia
       (uma foto aceita nao serve de base para aceitar a proxima). Na duvida a
       foto fica de fora (vira aluno_sem_idN ou sem_aluno): um aluno na pasta
       de outro e pior que uma pasta a mais.
    3. Foto sozinha de um rosto (de lado, com sombra) colada nas fotos de um
       aluno ou muito mais parecida com ele do que com qualquer outro.
    cards: {foto: (nome, codigo, rosto)}. Retorna {pasta: [fotos]}. Em
    owners (se dado) fica de quem e cada rosto.
    """
    X = np.asarray(embs, np.float32)
    photo_ids = np.asarray(photo_ids)
    students = group_cards(X, cards)
    names = [f for f, _, _ in students]
    refs = {f: list(ks) for f, _, ks in students}
    first = {f: phs for f, phs, _ in students}
    faces = {}
    for k, ph in enumerate(photo_ids):
        faces.setdefault(int(ph), []).append(k)
    owner = {k: f for f, _, ks in students for k in ks}     # rosto -> aluno
    photos = {n: set() for n in names}

    def score(k, n, base=None):
        s = np.sort(X[(base or refs)[n]] @ X[k])[::-1]
        return float(s[:3].mean())   # media dos 3 mais parecidos: um erro nao estraga

    def give(k, n, ref=True):
        owner[k] = n
        if ref:
            refs[n].append(k)
        photos[n].add(int(photo_ids[k]))

    def other(k, n):
        return max([score(k, m) for m in names if m != n] or [-1.0])

    # 1. sequencia depois de cada ficha
    for n in names:
        for p in first[n]:
            i, misses, wait = p + 1, 0, []
            while i < n_photos and i not in cards and misses < 2:
                ks = [k for k in faces.get(i, []) if k not in owner]
                mine = n in [owner.get(j) for j in faces.get(i, [])]
                if not faces.get(i):
                    wait.append((i, None))
                elif ks and not mine:
                    k = max(ks, key=lambda k: score(k, n))
                    s, o = score(k, n), other(k, n)
                    if s >= SEQ_MATCH and s - o >= SEQ_MARGIN:
                        give(k, n)
                        misses = 0
                        for b, kb in wait:      # o que ficou esperando no meio vai junto
                            if kb is None:
                                photos[n].add(b)
                            elif kb not in owner:
                                give(kb, n, ref=False)
                        wait = []
                    else:
                        if s >= SEQ_WEAK and s - o >= SEQ_MARGIN:
                            wait.append((i, k))
                        misses += 1
                else:
                    misses += 1
                i += 1

    # 2. rostos que sobraram (fotos de festa, fora de ordem...)
    base = {n: list(refs[n]) for n in names}
    left = [k for k in range(len(X)) if k not in owner and scores[k] >= SURE_FACE * 0.9]
    alone = []
    if left and names:
        for g in cluster_faces(X[left], photo_ids[left], threshold=FREE_GROUP, merge=False):
            ks = [left[j] for j in g]
            if len(ks) == 1:
                alone.append(ks[0])
            sc = sorted(((float(np.mean([score(k, n, base) for k in ks])), n) for n in names),
                        reverse=True)
            best, n = sc[0]
            second = sc[1][0] if len(sc) > 1 else -1.0
            if best < FREE_MATCH or best - second < FREE_MARGIN:
                continue
            for k in ks:
                if score(k, n, base) >= SEQ_WEAK and \
                        n not in [owner.get(j) for j in faces[int(photo_ids[k])]]:
                    give(k, n, ref=False)

    # 3. foto sozinha (rosto de lado, careta, sombra): vai para o aluno se for
    # muito mais parecida com ele (comparando tambem com as fotos aceitas no
    # passo 2) ou, colada numa foto que ja e dele, se ainda parecer mais com
    # ele. Foto com outras fotos do mesmo rosto nao entra aqui: e outra pessoa
    # (ficha que nao deu para ver)
    sure_ph = {n: set(photos[n]) | set(first[n]) for n in names}
    wide = {n: [k for k in range(len(X)) if owner.get(k) == n and scores[k] >= SURE_FACE * 0.9]
            for n in names}
    for k in alone:
        if k in owner:
            continue
        ph = int(photo_ids[k])
        taken = [owner.get(j) for j in faces[ph]]
        near = {n for n in names if (ph - 1 in sure_ph[n] or ph + 1 in sure_ph[n])}
        sc = sorted(((score(k, n, base), n) for n in names), reverse=True)
        best, n = sc[0]
        second = sc[1][0] if len(sc) > 1 else -1.0
        wc = sorted(((score(k, m, wide), m) for m in names if wide[m]), reverse=True)
        if n in near and best >= SEQ_WEAK and best - second >= NEAR_MARGIN:
            pass
        elif wc and wc[0][0] >= ALONE_MATCH and \
                wc[0][0] - (wc[1][0] if len(wc) > 1 else -1.0) >= ALONE_MARGIN:
            n = wc[0][1]
        else:
            continue
        if n not in taken:
            give(k, n, ref=False)
    if owners is not None:
        owners.update(owner)
    # a foto da ficha vai so para a pasta do proprio aluno
    return {n: sorted((photos[n] - set(cards)) | set(first[n])) for n in names}


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
             "gala", "lei", "responsavel", "cadastro", "ficha"}
# texto impresso da ficha da Gala (nao e nome de ninguem)
PRINTED_WORDS = set("""
acima acordo adolescente alem aluno apenas bairro beca cadastral cadastro chinelo cidade
colegio compromete conhecimento crianca data dados empresa endereco estado evento eventos
faculdade formando formandos formatura formaturas foto imagem instagram mail nascimento
nome perfil responsavel serie termos telefone celular autorizo autorizacao estatuto
""".split())

HAND_MODEL = "PP-OCRv6_rec_small.onnx"
HAND_URL = "https://github.com/Luci0Camarg0/Testegit/releases/download/modelos/" + HAND_MODEL

_ocr = None
_ocr_lock = threading.RLock()   # o leitor de fichas e um so: uma pasta por vez usa


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


class _KeepProbs:
    """Guarda as probabilidades de cada letra da ultima leitura (para conferir
    o nome lido com o dicionario de nomes)."""
    def __init__(self, decode):
        self.decode = decode
        self.last = None

    def __call__(self, preds, *a, **k):
        self.last = preds
        return self.decode(preds, *a, **k)

    def __getattr__(self, name):
        return getattr(self.decode, name)


def get_ocr(log=print):
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        rec = hand_model(log)
        try:
            _ocr = RapidOCR(rec_model_path=rec) if rec else RapidOCR()
        except Exception:
            _ocr = RapidOCR()
        try:
            _ocr.text_rec.postprocess_op = _KeepProbs(_ocr.text_rec.postprocess_op)
        except Exception:
            pass
    return _ocr


def _last_probs():
    """Probabilidades (tempo x letra) da ultima leitura de uma linha so, ou None."""
    try:
        p = _ocr.text_rec.postprocess_op.last
        return p[0] if p is not None and len(p) == 1 else None
    except Exception:
        return None


_letter_ids = None


def _char_ids():
    """Letra sem acento/minuscula -> indices do leitor (a: a A á à ã â Á...)."""
    global _letter_ids
    if _letter_ids is None:
        chars = _ocr.text_rec.postprocess_op.character
        _letter_ids = {}
        for i, c in enumerate(chars):
            if i == 0:
                continue                         # 0 = "nada" (blank)
            key = " " if c == " " else plain(c)
            if len(key) == 1:
                _letter_ids.setdefault(key, []).append(i)
        _letter_ids = {k: np.array(v) for k, v in _letter_ids.items()}
    return _letter_ids


def _ctc_score(P, text):
    """
    Quanto a imagem combina com o texto (log da probabilidade CTC), sem ligar
    para maiuscula e acento. P: probabilidades (tempo x letra).
    """
    ids = _char_ids()
    labs = []
    for ch in text:
        key = " " if ch == " " else plain(ch)
        if len(key) != 1 or key not in ids:
            return -1e9
        labs.append(key)
    if not labs:
        return float(np.log(P[:, 0] + 1e-12).sum())
    emit = np.log(np.stack([P[:, ids[c]].sum(1) for c in labs], 1) + 1e-12)
    blank = np.log(P[:, 0] + 1e-12)
    L = len(labs)
    S = 2 * L + 1
    skip = np.zeros(S, bool)                     # pode pular o "nada" entre letras diferentes
    for j in range(1, L):
        skip[2 * j + 1] = labs[j] != labs[j - 1]
    a = np.full(S, -np.inf)
    a[0], a[1] = blank[0], emit[0, 0]
    em = np.empty(S)
    for t in range(1, len(P)):
        a1 = np.empty(S)
        a1[0], a1[1:] = -np.inf, a[:-1]
        a2 = np.full(S, -np.inf)
        a2[2:][skip[2:]] = a[:-2][skip[2:]]
        em[0::2] = blank[t]
        em[1::2] = emit[t]
        a = np.logaddexp(np.logaddexp(a, a1), a2) + em
    return float(np.logaddexp(a[-1], a[-2]))


NAME_BONUS = 5.0            # nome conhecido: aceita se a letra combinar quase tao bem quanto a lida


def _fix_with_names(text, P, vocab=()):
    """
    Linha lida "Nome/Formando: Austave S. Alonso" + probabilidades das letras:
    troca cada palavra do nome por um nome conhecido parecido (Gustavo) quando
    a imagem combina quase tao bem com ele quanto com o que foi lido.
    """
    if P is None:
        return text
    try:
        return _fix_names(text, P, vocab)
    except Exception:
        return text                     # na duvida fica a leitura original


def _fix_names(text, P, vocab):
    m = re.search(r"(?i)ando\s*:?|ande\s*:?", text)
    start = m.end() if m else 0
    e = re.search(r"(?i)s[eé]rie", text[start:])
    end = start + e.start() if e else len(text)
    pre, post = text[:start], text[end:]
    parts = []
    for p in re.findall(r"[^\W\d_]+|[\W\d_]+", text[start:end]):
        # escrito colado: "deJesus" -> "de" "Jesus"
        parts += (re.findall(r"[^\W\d_][^\W\d_A-ZÀ-Ý]*", p) or [p]) if p[0].isalpha() else [p]
    base = _ctc_score(P, text)
    if base < -1e8:
        return text
    known = NAMES | set(vocab)
    for i, w in enumerate(parts):
        lw = plain(w)
        if not w[0].isalpha() or len(lw) < 3 or lw in NAMES:
            continue
        lim = max(1, int(0.4 * len(lw) + 0.5))
        best, pick = base, w
        for c in sorted(known):
            if abs(len(c) - len(lw)) > 2 or _edit(c, lw) > lim:
                continue
            cw = c.capitalize() if w[0].isupper() else c
            sc = _ctc_score(P, pre + "".join(parts[:i] + [cw] + parts[i + 1:]) + post)
            sc += NAME_BONUS if c in NAMES else 0.7 * NAME_BONUS
            if sc > best:
                best, pick = sc, cw
        if pick is not w:
            parts[i] = pick
            base = _ctc_score(P, pre + "".join(parts) + post)
    return pre + "".join(parts) + post


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


def find_card_box(region, sat=55):
    """
    Acha o papel branco da ficha no recorte. Retorna x0, y0, x1, y1 ou None.
    sat: quanto de cor ainda conta como branco (menor = so o papel, sem a pele
    clara do pescoco e das maos grudada nele).
    """
    h, w = region.shape[:2]
    k = 400.0 / max(h, w)
    small = cv2.resize(region, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 2] > 150) & (hsv[:, :, 1] < sat)).astype(np.uint8) * 255
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
abner adriano adriel agnes alan alef alessandra alex alexia alicia aline allan alyssa amelia
analu anabela anderson andressa andrey angela angelo anna anne antonia antonio aquiles
arthur augusto aurelio barbara beatrice benedito benjamim betina bia brayan bryan
camilly carla carlos carmem cassio catarina cauã cesar charles chloe cibele cicero clarice
claudia claudio clovis cristiano cristina dalila damiao danilo dante davi davy denis
diana diogo douglas dulce edson eduarda elaine eliana elias elisa eloah eloisa emily
enzo erica erik estela estevao eva evandro ezequiel fabiana fabricio felipe felix flavio
francine frederico gabriela gael geovanna geovane gerson giane gilberto giovane giovani
giovanni giovanna gisele glaucia gregorio guilherme gustavo hadassa halley heitor helio
henzo hilda horacio iago icaro igor ines iris isaias isis israel italo ivan jade jamal
janaina jaqueline jean jefferson jenifer jeremias joaquim joel jonas jonathan jordana
josue juan juca julio kaike kaleo karen kauan kenzo laerte lais lana lavinia leila
leo leon leonor leticia levi lia liam lidia ligia lilian lina lis livia lohan lorena
lorenzo louise luan luana lucca lucia luciana luciano lucio luiza luna maira manoel
manuel marcio marco marcia margarida mari mariane marilia mario marisa marta martim
mateo matias maura mauro max maximo mayara micaela michel michele miguel milton mirela
moises monica nadia nair natan nathalia nelson nicolas nicolly nina noa noah norberto
olga oliver omar oscar otavio paola patricia patrick pablo paulo pedro penelope pietra
pietro poliana priscila rafaela ramon raquel raul rayane regina renata ricardo rita
roberta roberto rodrigo rogerio ronaldo rosa rosana ruan rubens ruth sabrina salvador
samuel sandra saulo sebastiao selena sergio silas silvia simone sofia stefany suelen
tadeu talia tamires tania tatiana teo teodoro thales thalita theo thiago tomas tulio
ursula vagner valentim valeria valter vanderlei vera vicente victoria vinicius violeta
virginia vitor vitoria viviane wagner walter wellington wendel willian yan yara yasmin
yohan yuri zara zoe
abreu acosta aguiar albuquerque alencar alonso alvarenga amaral amorim andrade antunes
aparecido aragao arantes arruda assis assuncao avila azevedo bandeira barreto barros
bastos batista becker belo bernardes bezerra bittencourt bonfim braga branco brandao
brito bueno cabral caldeira calixto camargo campos cardoso carneiro carrara carvalho
casagrande castilho castro cavalcante cavalcanti chagas chaves conceicao cordeiro correa
correia costa coutinho cruz cunha damasceno dias diniz domingos dorneles duarte duque
esteves evangelista falcao faria farias fernandes ferrari ferraz ferreira figueira
figueiredo fischer fontes fonseca franca franco freire freitas frota furtado galvao
gama garcia gaspar godoy goes gomes goncalves gouveia guerra guimaraes hoffmann honorio
jesus junqueira lacerda lago lara leal leao leite lemos lima linhares lins lisboa lobo
lopes louro lucena luz macedo machado maciel magalhaes maia malta mancini marangoni
marinho marques martins matias matos medeiros medina meireles melo mendes mendonca
menezes mesquita miranda modesto monteiro moraes morais moreira moreno mota moura muller
nascimento navarro neves nobre nogueira novaes nunes oliveira ornelas pacheco padilha
paes paiva palma pantoja paranhos pastor pedrosa peixoto pereira peres pimenta pimentel
pinheiro pinto pires portela porto prado prates queiroz quintana ramalho ramos rangel
rebelo rego reis resende rezende ribeiro ricci rios rocha rodrigues romano romero rosa
rossi sa sabino salgado sales salles sampaio sanches santana santiago santos saraiva
schmidt seixas serafim silveira simoes siqueira soares sobral souza tavares teixeira
teles toledo torres trindade valente valenca vargas vasconcelos vaz veiga velasco viana
vidal vieira vilela villa xavier zanforlin zanella
""".split())


def best_name(reads, vocab, weights=None):
    """
    Junta varias leituras do mesmo nome escrito a mao: para cada palavra escolhe
    a forma que mais combina com as leituras, com os nomes comuns e com as
    outras palavras da ficha (nome dos pais, e-mail). weights: quanto vale
    cada leitura (a do recorte justo da letra erra menos).
    """
    weights = weights or [1.0] * len(reads)
    lists = [(r.split(), wt) for r, wt in zip(reads, weights) if r.split()]
    if not lists:
        return ""
    # leitura bem mais curta que as outras pegou so um pedaco do nome
    size = sorted(len("".join(l)) for l, _ in lists)[len(lists) // 2]
    lists = [(l, wt * min(1.0, len("".join(l)) / float(size)) ** 2) for l, wt in lists]
    counts = {}
    for l, wt in lists:
        # leitura com nomes conhecidos vale mais na hora de contar as palavras
        counts[len(l)] = counts.get(len(l), 0) + wt * (1 + 0.5 * sum(w in NAMES for w in l))
    n = max(counts, key=lambda k: (counts[k], k))
    rows = [(l, wt) for l, wt in lists if len(l) == n]
    out = []
    for i in range(n):
        ev = [l[i] for l, _ in rows]
        evw = [wt for _, wt in rows]
        def near(w, e):
            lim = 0.45 if len(e) >= 5 else 0.34
            return abs(len(w) - len(e)) <= 2 and _edit(w, e) <= max(1, int(lim * len(e)))
        # nomes conhecidos perto de qualquer leitura boa (a pior leitura nao conta)
        good = [e for e, wt in zip(ev, evw) if len(e) >= 3 and wt >= 1.5] or ev
        cands = set(ev) | {v for v in vocab if len(v) >= 4 and any(near(v, e) for e in good)} | \
            {v for v in NAMES if any(near(v, e) for e in good)}

        def score(c):
            s = sum(wt * max(0.0, 1 - _edit(c, e) / float(max(len(c), len(e))))
                    for e, wt in zip(ev, evw))
            return s + (1.5 if c in vocab else 0) + (2 if c in NAMES else 0)
        out.append(max(sorted(cands), key=score))
    return " ".join(_split_glued(w) for w in out)


def _split_glued(word):
    """Nome escrito colado: "joaopedro" -> "joao pedro"."""
    if word in NAMES or len(word) < 6:
        return word
    for i in range(3, len(word) - 2):
        if word[:i] in NAMES and word[i:] in NAMES:
            return word[:i] + " " + word[i:]
    return word


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
        # "Serie: 2 ano A" vem depois do nome na mesma linha: para ali
        cut = next((i for i in range(len(w) - 3) if len(w) - i <= 6 and
                    _edit(w[i:], "serie") <= 1), None)
        if cut is not None:
            if cut >= 3:
                words.append(w[:cut])
            break
        if w in ("n", "no") or len(w) < 2:
            continue
        words.append(w)
    return " ".join(words)


GALA_LABEL = re.compile(r"formand|ormand|rmando|mando|ando:|ndo:")
GALA_MARK = re.compile(r"gala|formaturas|faculdade|instagram|chinelo")


CODE_RANGE = 60             # fichas da mesma festa tem numeros proximos (2412, 2413...)
DIGIT_LOOKALIKE = str.maketrans("CcOoDQIl|Zz", "00000011122")


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
        # a ficha esta de pe (o rosto esta de pe): sem o classificador de giro,
        # que as vezes le o numero de cabeca para baixo ("pohz" = 2400)
        for sc in (0.3, 0.45, 0.6, 1.0):
            z = cv2.resize(zone, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) if sc != 1 else zone
            found += [(r, 1.0 / sc, 1.0) for r in (ocr(z, use_cls=False)[0] or [])]
        # so a tinta grossa da caneta, sem o QR code e as letras impressas por tras
        gray = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        k = max(3, int(W / 200) | 1)
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        clean = cv2.cvtColor(255 - ink, cv2.COLOR_GRAY2BGR)
        for sc in (0.5, 1.0):
            z = cv2.resize(clean, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) if sc != 1 else clean
            found += [(r, 1.0 / sc, 2.0) for r in (ocr(z, use_cls=False)[0] or [])]
    votes = {}
    for r, k, wt in found:
        txt = r[1].replace(" ", "")
        if sum(ch.isdigit() for ch in txt) >= 2 and len(txt) >= 3:
            fixed = txt.translate(DIGIT_LOOKALIKE)     # "241C" -> "2410"
            if fixed != txt and fixed.isdigit():
                txt, wt = fixed, wt * 0.6
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
    return " ".join([lab[1]] + [r[1] for r in _label_items(res, lab)])


def _label_items(res, lab):
    """Caixas lidas logo depois do rotulo do nome, na mesma linha, em ordem."""
    b = _box(lab)
    end = (b[1] + b[2]) / 2           # meio da borda direita do rotulo
    hl = max(4.0, float(b[2][1] - b[1][1]))
    nxt = []
    for r in res:
        rb = _box(r)
        start = (rb[0] + rb[3]) / 2
        if r is not lab and abs(start[1] - end[1]) < 0.4 * hl and \
                end[0] - 2 * hl <= start[0] <= end[0] + 3 * hl:
            nxt.append((float(start[0]), id(r), r))
    return [r for _, _, r in sorted(nxt)]


def _ink_crop(band, base, gap=0):
    """
    Recorte justo da letra de mao numa faixa da ficha: tira as linhas impressas
    e fica so com a linha de escrita que passa pela altura `base` (a linha de
    cima, "Faculdade/Colegio", tambem pode estar escrita). None se nao achar.
    """
    if band.shape[0] < 10 or band.shape[1] < 20:
        return None
    g = band.min(2).astype(np.float32)          # caneta azul fica escura aqui
    paper = float(np.percentile(g, 75))
    # o recorte pode passar da borda da ficha (fundo escuro): corta ali
    col = (g > paper - 40).mean(0)
    off = np.convolve(col < 0.3, np.ones(10), "valid") >= 10
    if off.any():
        band, g = band[:, :int(np.argmax(off))], g[:, :int(np.argmax(off))]
        if band.shape[1] < 20:
            return None
    ink = (g < paper - max(25.0, 0.18 * paper)).astype(np.uint8)
    w = band.shape[1]
    lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(15, w // 6)), np.uint8))
    ink = ink & (1 - lines)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    rows = ink.sum(1).astype(np.float32)
    if rows.max() < 3:
        return None
    on = rows > max(1.0, 0.03 * rows.max())
    base = int(min(max(base, 0), len(on) - 1))
    # a linha de escrita mais perto da altura do rotulo
    cand = [y for y in range(len(on)) if on[y]]
    if not cand:
        return None
    y = min(cand, key=lambda r: abs(r - base))
    if abs(y - base) > 0.5 * band.shape[0]:
        return None
    a = b = y
    while a > 0 and on[a - 1]:
        a -= 1
    while b < len(on) - 1 and on[b + 1]:
        b += 1
    if a == 0 and gap and base - gap > 2:
        # encostou na escrita da linha de cima: corta onde tem menos tinta
        sm = np.convolve(rows, np.ones(3) / 3.0, "same")
        a = int(np.argmin(sm[:base - gap]))
    xs = np.nonzero(ink[a:b + 1].sum(0))[0]
    if len(xs) < 3 or b - a < 4:
        return None
    # o nome acaba num espaco grande (depois vem "n°:" ou a "Serie" impressos)
    gaps = np.nonzero(np.diff(xs) > 2.0 * (b - a))[0]
    if len(gaps):
        xs = xs[:gaps[0] + 1]
    m = int(0.25 * (b - a)) + 2
    return band[max(0, a - m):b + m + 1, max(0, int(xs[0]) - m):int(xs[-1]) + m + 1]


def _label_end_x(text, P, height):
    """
    Onde termina o rotulo "Nome/Formando:" na faixa lida, em pixels: cada
    passo das probabilidades do leitor cobre 8 pixels da imagem com 48 de
    altura. None se o rotulo nao foi lido.
    """
    m = re.search(r"(?i)(ando|ande|ndo)\s*:?", text)
    if not m:
        return None
    idx = P.argmax(1)
    steps, prev = [], 0
    for t, i in enumerate(idx):
        if i != prev and i != 0:
            steps.append(t)
        prev = i
    if len(steps) != len(text) or m.end() < 1:
        return None
    return int((steps[m.end() - 1] + 0.5) * 8 * height / 48.0)


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
    # palavras do resto da ficha (nome dos pais, e-mail) ajudam a acertar o
    # sobrenome; as da propria linha do nome nao contam (seria o mesmo erro)
    same = [lab] + _label_items(res, lab)
    vocab = set()
    for r in res:
        if not any(r is q for q in same):
            vocab.update(w for w in plain(r[1]).split() if len(w) >= 4 and w.isalpha())
    vocab -= CARD_JUNK | CARD_SKIP | PRINTED_WORDS
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
    seen = []                           # (faixa, texto lido, probabilidades)

    def band_reads(tall):
        out = []
        for up, down in ((0.8, 0.3), (0.65, 0.35)):
            top = up * (max(sp, 1.1 * h) if tall else sp)
            low = down * (max(sp, 1.1 * h) if tall else sp)
            band = img_r[int(max(0, c[1] - top)):int(c[1] + low),
                         int(max(0, left - 5)):int(right)]
            if band.shape[0] < 8 or band.shape[1] < 20:
                continue
            for sc in (1, 2):
                im = cv2.resize(band, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC) \
                    if sc > 1 else band
                rr, _ = ocr(im, use_det=False, use_cls=False)
                if rr and rr[0][1] >= 0.5:
                    P = _last_probs()
                    if sc == 1 and P is not None:
                        seen.append((band, rr[0][0], P))
                    txt = _fix_with_names(rr[0][0], P, vocab)
                    out.append(_name_read(txt, need_label=True))
        return out

    def tight_reads():
        # so a letra de mao, recortada bem justa: o leitor acerta muito mais a
        # caneta fraca (Laura, Lucas) do que na faixa inteira da linha. O fim
        # do rotulo "Nome/Formando:" sai da propria leitura da faixa
        out = []
        for band, txt, P in seen[:1]:
            x = _label_end_x(txt, P, band.shape[0])
            if x is None or x >= band.shape[1] - 10:
                continue
            y0 = int(max(0, c[1] - 0.95 * sp))
            y1 = int(c[1] + 0.45 * sp)
            x0 = int(max(0, left - 5)) + x
            crop = _ink_crop(img_r[y0:y1, x0:int(right)], int(c[1]) - y0, int(0.3 * sp))
            if crop is None:
                continue
            for sc in (1, 2):
                im = cv2.resize(crop, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC) \
                    if sc > 1 else crop
                rr, _ = ocr(im, use_det=False, use_cls=False)
                if rr and rr[0][1] >= 0.5:
                    t = _fix_with_names(rr[0][0], _last_probs(), vocab)
                    out.append(_name_read(re.split(r"(?i)s[eé]rie", t)[0]))
        return out

    def letters(rs):
        return sum(len(r.replace(" ", "")) for r in rs) / float(max(1, len(rs)))

    # a faixa cortada (linha muito junta da de cima) le so o fim do nome:
    # tenta uma faixa mais alta; se ainda vier curto, fica a leitura da linha
    first = len(reads[0].replace(" ", "")) if reads[0] else 0
    more = band_reads(False)
    if first >= 5 and letters(more) < 0.6 * first:
        more = band_reads(True)
        if letters(more) < 0.6 * first:
            more = []
    try:
        tight = tight_reads()
    except Exception:
        tight = []                      # recorte justo e so um reforco
    weights = [1.5] + [1.0] * len(more) + [2.0] * len(tight)
    return best_name(reads + more + tight, vocab, weights), code


def _big_number(res, card):
    """Numero grande (3+ digitos) lido com certeza na metade de cima da ficha."""
    best = ""
    for r in res:
        txt = r[1].replace(" ", "")
        fixed = txt.translate(DIGIT_LOOKALIKE)
        if fixed.isdigit() and len(fixed) >= 3 and sum(c.isdigit() for c in txt) >= 3 and \
                r[2] >= 0.9 and _box(r).mean(0)[1] < 0.5 * card.shape[0] and \
                len(fixed) >= len(best):
            best = fixed
    return best


def read_card_photo(img, face_box):
    """
    Le a ficha que o aluno segura abaixo do rosto. Retorna (nome, codigo, ficha
    da Gala Eventos?, numero grande lido mesmo sem achar o resto da ficha).
    """
    region = card_region(img, face_box)
    if region is None:
        return "", "", False, ""
    seen, first, number = [], None, ""
    # o recorte do papel branco as vezes pega junto a pele clara do pescoco e
    # das maos e a leitura falha: tenta de novo so com o branco mais puro
    for sat in (55, 38, 26):
        cb = find_card_box(region, sat)
        if cb is None or any(_iou(cb, o) > 0.85 for o in seen):
            continue
        seen.append(cb)
        card = region[cb[1]:cb[3], cb[0]:cb[2]]
        hh, ww = card.shape[:2]
        k = min(1.0, 1600.0 / max(hh, ww))
        if k < 1:
            card = cv2.resize(card, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        res, _ = get_ocr()(card)
        res = [r for r in (res or []) if r[2] >= 0.5]
        gala = read_gala_card(card, res)
        if gala is not None:
            return gala[0], gala[1], True, _big_number(res, card)
        number = number or _big_number(res, card)
        if first is None:
            first = parse_card([r[1] for r in res])
        if not number:
            break               # nada de ficha aqui: nao perde tempo lendo de novo
    if first is None:
        return "", "", False, ""
    return first[0], first[1], False, number


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / float(union or 1)


def _card_candidate(img, ks, boxes, log=print):
    """
    Le a ficha de uma foto, se ela pode ser foto de ficha: ate 3 rostos certos
    e o maior (o aluno) bem maior que os outros. Retorna (nome, codigo, ficha
    da Gala?, numero grande, rosto do aluno), None se nao e candidata, ou
    "erro" se o leitor de fichas falhou.
    """
    if not ks or len(ks) > 3:
        return None
    k = max(ks, key=lambda k: boxes[k][2] * boxes[k][3])     # o aluno: maior rosto
    if len(ks) > 1 and sorted(boxes[j][2] * boxes[j][3] for j in ks)[-2] > \
            0.6 * boxes[k][2] * boxes[k][3]:
        return None             # dois rostos do mesmo tamanho: foto de grupo, nao ficha
    try:
        with _ocr_lock:
            name, code, gala, number = read_card_photo(img, boxes[k])
    except Exception as e:
        log("Leitor de fichas falhou: %s" % e)
        return "erro"
    return name, code, gala, number, k


def find_cards(images, card_reads, log=print):
    """
    Acha, no meio das fotos da festa, as fotos de ficha: poucas pessoas e,
    logo abaixo do maior rosto, um texto com nome e codigo. Usa as leituras
    feitas por scan_faces (card_reads). Retorna {foto: (nome, codigo, rosto do aluno)}.
    """
    cards, maybe, gala_codes = {}, [], []
    for ph in sorted(p for p in card_reads if p is not None):
        read = card_reads[ph]
        if read == "erro":
            break
        name, code, gala, number, k = read
        words = plain(name).split()
        if len(words) > 6 or any(w in CARD_JUNK for w in words):
            name = ""               # pegou o texto impresso da ficha, nao o nome
        # na ficha da Gala Eventos, sem numero legivel a pasta fica so com o
        # nome, e sem nome legivel fica so com o numero
        if gala and not code and (len(name.split()) < 2 or len(name.replace(" ", "")) < 6):
            # e a ficha da Gala, mas nao deu para ler: vira aluno_sem_idN e as
            # fotos vao pelo rosto, para o aluno nao ir para sem_aluno
            cards[ph] = ("", "", k)
            log("Ficha: %s -> não deu para ler" % os.path.basename(images[ph]))
        elif (code and (gala or len(name.replace(" ", "")) >= 3)) or \
                (gala and len(name.split()) >= 2 and len(name.replace(" ", "")) >= 6):
            cards[ph] = (name, code, k)
            if gala and code.isdigit():
                gala_codes.append(code)
            log("Ficha: %s -> %s" % (os.path.basename(images[ph]), folder_name_for(name, code)))
        elif number:
            maybe.append((ph, name, number, k))
    # ficha desfocada ou com a pele grudada no papel: o texto impresso nao foi
    # lido, mas o numero grande sim. Se o numero e da mesma serie das fichas
    # da Gala desta pasta, e ficha (senao as fotos do aluno iam para outro)
    if gala_codes and maybe:
        size = max(set(map(len, gala_codes)), key=[len(c) for c in gala_codes].count)
        nums = [int(c) for c in gala_codes]
        for ph, name, number, k in maybe:
            if len(number) != size or min(abs(int(number) - c) for c in nums) > CODE_RANGE:
                continue
            words = plain(name).split()
            if len(words) < 2 or len(name.replace(" ", "")) < 6 or \
                    any(w in CARD_JUNK for w in words) or not name.replace(" ", "").isalpha():
                name = ""
            cards[ph] = (name, number, k)
            log("Ficha: %s -> %s (só deu para ler o número)"
                % (os.path.basename(images[ph]), folder_name_for(name, number)))
    return cards


# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------

def process_folder(src, engine, log=print, progress=lambda done, total, text=None: None,
                   out_root=None, report=None, cancel=None):
    """
    Processa uma pasta de fotos e cria festa_N. Se no meio das fotos houver
    fotos de ficha (aluno segurando nome e codigo), cria uma pasta para cada
    aluno ("maria eduarda_4821") e ignora quem nao tem ficha (pais,
    convidados). Sem fichas, agrupa por pessoa em aluno_1, aluno_2...
    Retorna o caminho criado.
    """
    out_root = out_root or data_dir()
    user_progress = progress

    def progress(done, total, text=None):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        user_progress(done, total, text)

    images = list_images(src)
    if not images:
        raise RuntimeError("Nenhuma foto encontrada nessa pasta.")

    extra = {}
    look_models(log)                 # detector de olhos fechados (baixa uma vez)
    card_reads = {}                  # fichas lidas junto com os rostos (abre cada foto uma vez)
    embs, photo_ids, scores, boxes = scan_faces(images, engine, log, progress, extra, card_reads)
    if not len(embs):
        raise RuntimeError("Nenhum rosto encontrado nas fotos.")

    cards = find_cards(images, card_reads, log)
    owner = {}                       # rosto -> pasta (para olhar so o rosto do aluno)

    if cards:
        log("Separando os alunos das %d ficha(s)..." % len(cards))
        found = assign_by_cards(embs, photo_ids, scores, cards, len(images), owner)
        people = [(n, ph) for n, ph in found.items() if ph]
        missing = [n for n, ph in found.items() if not set(ph) - set(cards)]
        if report is not None:
            report["fichas"] = len(found)
            report["missing"] = missing
        if missing:
            log("Alunos sem fotos além da ficha: " + ", ".join(missing))
    else:
        log("Agrupando %d rostos..." % len(embs))
        groups = cluster_faces(embs, photo_ids)
        # grupo formado so por deteccoes duvidosas = provavelmente nao e um rosto
        groups = [g for g in groups if max(scores[k] for k in g) >= SURE_FACE]
        if not groups:
            raise RuntimeError("Nenhum rosto encontrado nas fotos.")
        # mais fotos primeiro (aluno_1 = quem mais aparece)
        groups = sorted(groups, key=lambda g: (-len({int(photo_ids[k]) for k in g}),
                                               min(int(photo_ids[k]) for k in g)))
        people = []
        for i, g in enumerate(groups, 1):
            people.append(("aluno_%d" % i, sorted({int(photo_ids[k]) for k in g})))
            owner.update({k: "aluno_%d" % i for k in g})

    # fotos que nao foram para nenhum aluno (sem rosto, outras pessoas) nao se
    # perdem: vao para uma pasta separada
    placed = {p for _, ph in people for p in ph}
    rest = [p for p in range(len(images)) if p not in placed]
    if cards and rest:
        # quem sobrou e aparece em 2 fotos ou mais com o mesmo rosto ganha uma
        # pasta aluno_sem_idN (sem ficha legivel); o resto vai para sem_aluno
        ks = [k for k in range(len(embs))
              if int(photo_ids[k]) in set(rest) and scores[k] >= SURE_FACE]
        if ks:
            sub = cluster_faces(embs[ks], photo_ids[ks], threshold=NO_ID_SAME, merge=False)
            phs = sorted([sorted({int(photo_ids[ks[j]]) for j in grp}) for grp in sub],
                         key=lambda ph: ph[0])
            used = {f for f, _ in people}
            n = 1
            for ph in phs:
                if len(ph) < 2:
                    continue
                while NO_ID_FOLDER % n in used:
                    n += 1
                grp = next(g for g in sub if sorted({int(photo_ids[ks[j]]) for j in g}) == ph)
                owner.update({ks[j]: NO_ID_FOLDER % n for j in grp})
                people.append((NO_ID_FOLDER % n, ph))
                used.add(NO_ID_FOLDER % n)
                log("Sem ficha, separado pelo rosto: %s (%d fotos)" % (NO_ID_FOLDER % n, len(ph)))
            placed = {p for _, ph in people for p in ph}
            rest = [p for p in range(len(images)) if p not in placed]
    if rest:
        people.append((LEFTOVER_FOLDER, rest))

    # fotos bonitas: a separacao dos alunos nao muda; dentro da pasta de cada
    # aluno, foto com olho fechado / olhando para o lado (ou de boca aberta
    # tendo outra igual de boca fechada) vai para a subpasta fotos_descartadas
    discard, why = {}, {}
    if extra.get("looks") and any(v is not None for v in extra["looks"]):
        log("Escolhendo as fotos bonitas...")
        discard = pick_good_photos(people, owner, photo_ids, extra["looks"],
                                   extra.get("minis", {}), set(cards), why)
        for folder, items in why.items():
            for p, r in sorted(items.items()):
                log("Descartada: %s/%s (%s)" % (folder, os.path.basename(images[p]), r))
    if report is not None:
        report["descartadas"] = sum(len(v) for v in discard.values())

    if cancel is not None and cancel.is_set():
        raise Cancelled()
    event = new_event_dir(out_root)
    if report is not None:
        report["event"] = event
    copied = {}                      # foto de origem -> arquivos criados
    try:
        for folder, ph in people:
            d = os.path.join(event, folder)
            os.makedirs(d)
            used = set()
            bad = discard.get(folder, set())
            for p in ph:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                name = os.path.basename(images[p])
                base, ext = os.path.splitext(name)
                k = 2
                while name.lower() in used:     # fotos com mesmo nome em subpastas
                    name = "%s_%d%s" % (base, k, ext)
                    k += 1
                used.add(name.lower())
                if p in bad:
                    os.makedirs(os.path.join(d, DISCARD_FOLDER), exist_ok=True)
                    dst = os.path.join(d, DISCARD_FOLDER, name)
                else:
                    dst = os.path.join(d, name)
                shutil.copy2(images[p], dst)
                copied.setdefault(p, []).append(dst)
                if p in bad:
                    with open(os.path.join(d, DISCARD_FOLDER, "motivos.txt"), "a",
                              encoding="utf-8") as f:
                        f.write("%s: %s\n" % (name, why.get(folder, {}).get(p, "")))
    except BaseException:
        shutil.rmtree(event, ignore_errors=True)    # festa pela metade nao fica
        raise

    # conferencia: cada foto da pasta original tem que estar em alguma pasta
    ok = [p for p in range(len(images)) if any(os.path.isfile(f) for f in copied.get(p, ()))]
    if report is not None:
        report["total"] = len(images)
        report["placed"] = len(ok)
        report["multi"] = sum(len(v) > 1 for v in copied.values())
        report["leftover"] = len(rest)
        report["lost"] = [os.path.basename(images[p]) for p in range(len(images))
                          if p not in set(ok)]
    log("Pronto! %d pasta(s) criadas em %s" % (len(people), os.path.basename(event)))
    log("Conferência: %d de %d fotos nas pastas" % (len(ok), len(images)))
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

# Cores do tema (preto e vermelho)
BG = "#0b0b0d"
PANEL = "#17171a"
ROW_HOVER = "#211618"
ROW_SEL = "#6e1414"
ACCENT = "#c62828"
ACCENT_HOVER = "#e53935"
ACCENT_DARK = "#5c0f0f"
LINE = "#2a2a2e"
FG = "#ffffff"
YELLOW = "#ffd600"
FG_DIM = "#a8a8ad"
LOGO_OPACITY = 0.10         # logo de fundo bem suave para nao atrapalhar a leitura
ROW_H = 36
TARGET_H = 50               # altura de cada aluno na lista "Mover para"
TARGET_W = 300
HEADER_H = 64
SPLASH_SECONDS = 3.0        # abertura: logo da Gala no fundo preto


def mix(c1, c2, t):
    """Cor entre c1 e c2 (t de 0 a 1), usada nas animacoes."""
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def student_label(folder):
    """'alice_maranoaglle_2373' -> ('Alice Maranoaglle', '2373', '')."""
    parts = folder.split("_")
    tag = ""
    if len(parts) > 1 and parts[-1].lower() == "conferir":
        tag = "conferir"
        parts = parts[:-1]
    num = ""
    if len(parts) > 1 and parts[-1].isdigit():
        num = parts[-1]
        parts = parts[:-1]
    m = re.match(r"aluno_sem_id(\d*)$", "_".join(parts))
    if m:
        return ("Aluno sem id " + m.group(1)).strip(), "", tag
    words = [w for w in parts if w]
    small = {"da", "de", "do", "das", "dos", "e", "du", "di"}
    name = " ".join(w if (i and w.lower() in small) else w[:1].upper() + w[1:]
                    for i, w in enumerate(words))
    return (name or folder), num, tag


def initials(name):
    if name.startswith("Aluno sem id") or name == "Sem Aluno":
        return "?"
    ws = [w for w in name.split() if w[:1].isalnum() and w.lower() not in
          ("da", "de", "do", "das", "dos", "e", "du", "di")]
    if not ws:
        return "?"
    return (ws[0][0] + (ws[-1][0] if len(ws) > 1 else "")).upper()


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def gala_logo():
    """Logo da Gala em alta (texto claro para fundo preto). Vem dentro deste
    arquivo porque a atualizacao automatica so baixa o reconhecimento.py."""
    from PIL import Image
    import base64
    import io
    try:
        return Image.open(io.BytesIO(base64.b64decode(LOGO_GALA_PNG))).convert("RGBA")
    except Exception:
        pass
    try:
        return Image.open(os.path.join(resource_dir(), "assets", "logo.png")).convert("RGBA")
    except Exception:
        return None


def check_text(rep):
    """Texto da caixa de conferencia: soma das pastas x total da pasta original."""
    if "total" not in rep:
        return ""
    total, placed = rep["total"], rep["placed"]
    if rep["lost"]:
        return ("Atenção: %d de %d fotos foram adicionadas.\n\nFicaram de fora:\n%s"
                % (placed, total, "\n".join(rep["lost"][:20])))
    text = "Todas as %d fotos foram adicionadas.\nNenhuma ficou de fora." % total
    if rep["leftover"]:
        text += ("\n\n%d foto(s) sem aluno reconhecido estão na pasta %s."
                 % (rep["leftover"], LEFTOVER_FOLDER))
    if rep["multi"]:
        text += ("\n\n%d foto(s) com mais de um aluno foram para mais de uma pasta."
                 % rep["multi"])
    return text


THUMB_PX = 150              # tamanho das miniaturas da galeria


def photos_in(folder):
    """Fotos direto dentro da pasta (sem subpastas), em ordem natural."""
    try:
        names = [n for n in os.listdir(folder)
                 if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                 and os.path.isfile(os.path.join(folder, n))]
    except OSError:
        return []
    return [os.path.join(folder, n) for n in sorted(names, key=natural_key)]


def thumbs_dir():
    """Miniaturas guardadas ao lado da pasta Eventos (abrem na hora da 2a vez)."""
    d = os.path.join(os.path.dirname(data_dir()), "miniaturas")
    if not os.path.isdir(d):
        try:
            os.makedirs(d)
            if sys.platform.startswith("win"):
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(d, 2)    # pasta oculta
        except Exception:
            pass
    return d


def load_photo(path, max_side):
    """Abre a foto ja reduzida (rapido em JPG grande) e na posicao certa."""
    from PIL import Image, ImageOps
    im = Image.open(path)
    im.draft("RGB", (max_side, max_side))
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def make_thumb(path, size=THUMB_PX, cache=None):
    """Miniatura da foto. Usa a copia guardada se a foto nao mudou (vale
    tambem depois de mover a foto para outra pasta)."""
    from PIL import Image
    key = None
    if cache:
        st = os.stat(path)
        key = os.path.join(cache, hashlib.md5(("%s|%d|%d|%d" % (
            os.path.basename(path).lower(), st.st_size, int(st.st_mtime), size)
        ).encode("utf-8")).hexdigest() + ".jpg")
        if os.path.isfile(key):
            try:
                im = Image.open(key)
                im.load()
                return im
            except Exception:
                pass
    im = load_photo(path, size * 2)
    im.thumbnail((size, size), Image.LANCZOS)
    if key:
        try:
            im.save(key, quality=85)
        except OSError:
            pass
    return im


def free_path(folder, name):
    """Caminho em `folder` que ainda nao existe (foto.jpg, foto_2.jpg...)."""
    base, ext = os.path.splitext(name)
    dst, k = os.path.join(folder, name), 2
    while os.path.exists(dst):
        dst = os.path.join(folder, "%s_%d%s" % (base, k, ext))
        k += 1
    return dst


def move_photos(paths, dest):
    """Move fotos para outra pasta. Retorna ([(de, para)], [erros])."""
    done, errors = [], []
    for p in paths:
        try:
            if os.path.normcase(os.path.dirname(p)) == os.path.normcase(dest):
                continue
            dst = free_path(dest, os.path.basename(p))
            shutil.move(p, dst)
            done.append((p, dst))
        except OSError as e:
            errors.append("%s: %s" % (os.path.basename(p), e))
    return done, errors


def send_to_trash(paths):
    """Manda pastas/fotos para a Lixeira do Windows (da para recuperar).
    Retorna ([apagados], [erros])."""
    paths = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not paths:
        return [], []
    if sys.platform.startswith("win"):
        import ctypes       # sem ctypes.wintypes: os .exe antigos nao trazem

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
                        ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                        ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", ctypes.c_int),
                        ("hNameMappings", ctypes.c_void_p),
                        ("lpszProgressTitle", ctypes.c_wchar_p)]
        done, errors = [], []
        for p in paths:         # uma por vez: o erro de uma nao para as outras
            op = SHFILEOPSTRUCTW()
            op.wFunc = 3                                # FO_DELETE
            op.pFrom = p + "\0\0"
            op.fFlags = 0x40 | 0x10 | 0x04 | 0x400      # lixeira, sem perguntar, sem janelas
            r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if r == 0 and not op.fAnyOperationsAborted and not os.path.exists(p):
                done.append(p)
            else:
                errors.append("%s (código %d)" % (os.path.basename(p), r))
        return done, errors
    # fora do Windows: pasta "Lixeira" ao lado de Eventos
    trash = os.path.join(os.path.dirname(data_dir()), "Lixeira")
    os.makedirs(trash, exist_ok=True)
    done, errors = [], []
    for p in paths:
        try:
            shutil.move(p, free_path(trash, os.path.basename(p)))
            done.append(p)
        except OSError as e:
            errors.append("%s: %s" % (os.path.basename(p), e))
    return done, errors


def create_folder(parent, name):
    """Cria uma pasta. Retorna (caminho, None) ou (None, mensagem de erro)."""
    err = validate_new_name(parent, "", name)
    if err:
        return None, err
    path = os.path.join(parent, name.strip())
    try:
        os.makedirs(path)
    except OSError as e:
        return None, "Não foi possível criar a pasta:\n%s" % e
    return path, None


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


def error_file():
    return os.path.join(os.path.dirname(data_dir()), "erros.txt")


def log_error(text):
    """Guarda o erro em erros.txt (ao lado da pasta Eventos) para poder ser enviado."""
    try:
        with open(error_file(), "a", encoding="utf-8") as f:
            f.write("--- versao %d ---\n%s\n" % (VERSAO, text))
    except OSError:
        pass


def run_gui(test=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from PIL import Image, ImageTk

    root_dir = data_dir()
    state = {"current": None, "engine": None, "busy": False,
             "rows": [], "sel": None, "hover": None, "editor": None}
    msgs = queue.Queue()

    win = tk.Tk()

    def report_error(exc, val, tb):
        # erro num clique: avisa e continua, em vez de fechar o programa
        log_error("".join(traceback.format_exception(exc, val, tb)))
        if test:
            test_errors.append("%s: %s" % (exc.__name__, val))
            return
        try:
            messagebox.showerror(APP_NAME, "Ocorreu um erro:\n%s\n\nOs detalhes foram salvos em:"
                                 "\n%s" % (val, error_file()), parent=win)
        except Exception:
            pass
    test_errors = []
    win.report_callback_exception = report_error
    win.title("%s  —  versão %d" % (APP_NAME, VERSAO))
    win.geometry("820x640")
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

    pill_cache = {}

    def pill_image(w, h, fill, outline):
        # botao com as pontas redondas, desenhado 4x maior e reduzido (borda lisa)
        key = (w, h, fill, outline)
        if key not in pill_cache:
            # so numpy (os .exe antigos nao trazem PIL.ImageDraw nem tkinter.font)
            r = h / 2.0
            yy, xx = np.mgrid[0:h, 0:w] + 0.5
            cx = np.clip(xx, r, w - r)
            d = np.hypot(xx - cx, yy - r) - (r - 0.5)       # <0 dentro do botao
            inside = np.clip(0.5 - d, 0, 1)
            rgb = np.empty((h, w, 3), float)
            rgb[:] = [int(fill[i:i + 2], 16) for i in (1, 3, 5)]
            if outline:
                ring = np.clip(1.5 - np.abs(d + 0.5), 0, 1) * inside
                oc = np.array([int(outline[i:i + 2], 16) for i in (1, 3, 5)], float)
                rgb = rgb * (1 - ring[..., None]) + oc * ring[..., None]
            im = np.dstack([rgb, inside * 255]).astype(np.uint8)
            if len(pill_cache) > 300:
                pill_cache.clear()
            pill_cache[key] = ImageTk.PhotoImage(Image.fromarray(im, "RGBA"))
        return pill_cache[key]

    class PillButton(tk.Canvas):
        """Botao oval nas pontas, com a mesma cara do tk.Button usado antes."""

        def __init__(self, parent, text, cmd, primary):
            self._base = ACCENT if primary else PANEL
            self._hover = ACCENT_HOVER if primary else "#2a1a1c"
            self._edge = None if primary else "#2e2e33"
            self._font = font_b if primary else font
            self._opt = {"text": text, "command": cmd, "state": "normal", "fg": FG,
                         "disabledforeground": "#5a5a5e"}
            self._bg = self._base
            self._job = None
            w = int(parent.tk.call("font", "measure", self._font, text)) + 40
            h = int(parent.tk.call("font", "metrics", self._font, "-linespace")) + 18
            super().__init__(parent, width=w, height=h, bg=parent.cget("bg"),
                             highlightthickness=0, bd=0, cursor="hand2")
            self._pw, self._ph = w, h
            self.bind("<Enter>", lambda e: self._state() == "normal" and self._fade(self._hover))
            self.bind("<Leave>", lambda e: self._fade(self._base))
            self.bind("<ButtonRelease-1>", self._click)
            self._draw()

        def _state(self):
            return self._opt["state"]

        def _draw(self):
            self.delete("all")
            self.create_image(0, 0, anchor="nw",
                              image=pill_image(self._pw, self._ph, self._bg, self._edge))
            fg = (self._opt["fg"] if self._state() == "normal"
                  else self._opt["disabledforeground"])
            self.create_text(self._pw / 2, self._ph / 2, text=self._opt["text"], fill=fg,
                             font=self._font)

        def _fade(self, target, steps=8, k=1, start=None):
            if k == 1:
                if self._job:
                    self.after_cancel(self._job)
                start = self._bg
            self._bg = mix(start, target, ease_out(k / steps))
            self._draw()
            self._job = self.after(16, lambda: self._fade(target, steps, k + 1, start)) \
                if k < steps else None

        def _click(self, e):
            if (self._state() == "normal" and self._opt["command"]
                    and 0 <= e.x < self._pw and 0 <= e.y < self._ph):
                self._opt["command"]()

        def configure(self, cnf=None, **kw):
            mine = {k: kw.pop(k) for k in list(kw) if k in self._opt}
            kw.pop("activeforeground", None)
            if mine:
                self._opt.update(mine)
                if mine.get("state") == "disabled":
                    if self._job:
                        self.after_cancel(self._job)
                        self._job = None
                    self._bg = self._base
                self.configure(cursor="hand2" if self._state() == "normal" else "")
                self._draw()
            if cnf or kw:
                return super().configure(cnf, **kw)
        config = configure

        def cget(self, key):
            return self._opt[key] if key in self._opt else super().cget(key)

        def __getitem__(self, key):
            return self.cget(key)

        def invoke(self):
            if self._state() == "normal" and self._opt["command"]:
                return self._opt["command"]()

    def make_button(parent, text, cmd, primary=False):
        return PillButton(parent, text, cmd, primary)

    # --- cabecalho (logo pequena + titulo, faixa vermelha embaixo) ----------
    header = tk.Canvas(win, bg=BG, height=HEADER_H, highlightthickness=0, bd=0)
    header.pack(fill="x")
    head = {"img": None, "logo": None, "w": 0}
    logo_full = gala_logo()

    def draw_header(_e=None):
        w = max(header.winfo_width(), 200)
        if w == head["w"]:
            return
        head["w"] = w
        # fundo preto que esquenta para vermelho escuro na direita
        x = np.linspace(0, 1, w)[None, :, None]
        c0 = np.array([11, 11, 13], float)
        c1 = np.array([58, 10, 12], float)
        grad = c0 + (c1 - c0) * (x ** 2.2)
        grad = np.repeat(grad, HEADER_H, axis=0)
        grad[-2:, :, :] = (np.array([120, 16, 18]) + (np.array([229, 57, 53]) -
                                                      np.array([120, 16, 18])) * x[0])
        head["img"] = ImageTk.PhotoImage(Image.fromarray(grad.astype(np.uint8)))
        header.delete("all")
        header.create_image(0, 0, image=head["img"], anchor="nw")
        tx = 18
        if logo_full is not None:
            if head["logo"] is None:
                k = (HEADER_H - 20) / logo_full.height
                head["logo"] = ImageTk.PhotoImage(logo_full.resize(
                    (int(logo_full.width * k), HEADER_H - 20), Image.LANCZOS))
            header.create_image(18, HEADER_H / 2 - 1, image=head["logo"], anchor="w")
            tx = 18 + head["logo"].width() + 16
            header.create_line(tx - 8, 16, tx - 8, HEADER_H - 18, fill="#3a3a3e")
        header.create_text(tx, HEADER_H / 2 - 9, text=APP_NAME, anchor="w", fill=FG,
                           font=("Segoe UI", 14, "bold"))
        header.create_text(tx, HEADER_H / 2 + 12, anchor="w", fill=FG_DIM,
                           font=("Segoe UI", 9),
                           text="Separação de fotos por aluno  ·  versão %d" % VERSAO)
    header.bind("<Configure>", draw_header)

    # --- topo ---------------------------------------------------------------
    top = tk.Frame(win, bg=BG, padx=12, pady=12)
    top.pack(fill="x")
    add_btn = make_button(top, "+  Adicionar pasta de fotos", None, primary=True)
    add_btn.pack(side="left")
    back_btn = make_button(top, "‹  Voltar", None)
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
                      insertbackground=ACCENT_HOVER, relief="flat", highlightthickness=1,
                      highlightbackground=LINE, highlightcolor=ACCENT)
    search.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=6)
    where_var = tk.StringVar()
    tk.Label(win, textvariable=where_var, bg=BG, fg=FG, font=("Segoe UI", 12, "bold"),
             padx=12, pady=8, anchor="w").pack(fill="x")

    # --- lista (canvas com a logo no fundo) ---------------------------------
    mid = tk.Frame(win, bg=BG, padx=12)
    mid.pack(fill="both", expand=True)
    canvas = tk.Canvas(mid, bg=BG, highlightthickness=1, highlightbackground=LINE, bd=0,
                       yscrollincrement=ROW_H, height=120)   # cresce; deixa lugar para a fila
    sb = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview,
                       style="Dark.Vertical.TScrollbar")
    canvas.configure(yscrollcommand=lambda a, b: (sb.set(a, b), place_logo()))
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    # --- galeria (fotos de um aluno) -----------------------------------------
    gal = tk.Frame(win, bg=BG, padx=12)
    side = tk.Frame(gal, bg=BG)
    side.pack(side="left", fill="y", padx=(0, 10))
    side_head = tk.Frame(side, bg=BG)
    side_head.pack(fill="x")
    tk.Label(side_head, text="Mover para", bg=BG, fg=FG, font=font_b,
             anchor="w").pack(side="left")
    side_count = tk.Label(side_head, text="", bg=ACCENT_DARK, fg=FG,
                          font=("Segoe UI", 8, "bold"), padx=7)
    side_count.pack(side="left", padx=(8, 0))
    tk.Label(side, text="Arraste as fotos para o aluno certo.\nDois cliques abrem a pasta.",
             bg=BG, fg=FG_DIM, font=("Segoe UI", 9), justify="left", anchor="w").pack(fill="x")
    # lista de alunos desenhada (um cartao por aluno; fotos_descartadas so
    # aparece quando abre a pasta do aluno)
    tbox = tk.Frame(side, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
    tbox.pack(fill="both", expand=True, pady=(6, 0))
    targets = tk.Canvas(tbox, bg=PANEL, width=TARGET_W, highlightthickness=0, bd=0,
                        yscrollincrement=TARGET_H // 2)
    tsb = ttk.Scrollbar(tbox, orient="vertical", command=targets.yview,
                        style="Dark.Vertical.TScrollbar")
    targets.configure(yscrollcommand=tsb.set)
    tsb.pack(side="right", fill="y")
    targets.pack(side="left", fill="both", expand=True)
    tname_font = ("Segoe UI", 10, "bold")

    def text_w(txt):
        return int(win.tk.call("font", "measure", tname_font, txt))
    gcan = tk.Canvas(gal, bg=BG, highlightthickness=1, highlightbackground=LINE, bd=0,
                     yscrollincrement=40, height=120)
    gsb = ttk.Scrollbar(gal, orient="vertical", command=gcan.yview,
                        style="Dark.Vertical.TScrollbar")
    gcan.configure(yscrollcommand=gsb.set)
    gsb.pack(side="right", fill="y")
    gcan.pack(side="left", fill="both", expand=True)
    TILE_W, TILE_H, GAP = THUMB_PX + 12, THUMB_PX + 34, 10
    g = {"items": [], "sel": set(), "anchor": None, "hover": None, "press": None,
         "drag": None, "drop": None, "targets": [], "undo": [], "mode": "lista",
         "thover": None, "tdrop": None}
    thumbs = {}                     # foto -> miniatura pronta para a tela
    asked = set()
    thumb_q = queue.Queue()
    cache = thumbs_dir()

    # --- rodape -------------------------------------------------------------
    bottom = tk.Frame(win, bg=BG, padx=12, pady=10)
    bottom.pack(fill="x")
    prog = ttk.Progressbar(bottom, mode="determinate", style="Dark.Horizontal.TProgressbar")
    prog.pack(fill="x")
    status_var = tk.StringVar(value="Pronto. Clique em 'Adicionar pasta de fotos'.  "
                                    "Botão direito para renomear ou criar pasta.")
    status_row = tk.Frame(bottom, bg=BG)
    status_row.pack(fill="x", pady=(6, 0))
    tk.Label(status_row, textvariable=status_var, bg=BG, fg=FG_DIM, font=("Segoe UI", 10),
             anchor="w").pack(side="left")
    update_lbl = tk.Label(status_row, text="", bg=BG, fg=ACCENT_HOVER,
                          font=("Segoe UI", 10, "bold underline"), cursor="hand2")

    # --- logo ---------------------------------------------------------------
    logo_src = None
    try:
        logo_src = logo_full.copy()
        ch_r, ch_g, ch_b, ch_a = logo_src.split()
        ch_a = ch_a.point(lambda v: int(v * LOGO_OPACITY))
        logo_src = Image.merge("RGBA", (ch_r, ch_g, ch_b, ch_a))
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
        if in_gallery():
            cur = state["current"]
            where_var.set("Eventos  ›  " + os.path.relpath(cur, root_dir).replace(os.sep, "  ›  "))
            back_btn.configure(state="normal")
            show_mode("galeria")
            refresh_gallery()
            return
        show_mode("lista")
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
        anim["hl"].clear()
        if anim["where"] != cur:        # mudou de pasta: linhas entram deslizando
            anim["where"] = cur
            anim["enter_t"] = time.perf_counter()
            kick_anim()
        draw_rows()

    # animacoes da lista: cada linha acende devagar no mouse e as linhas
    # entram deslizando quando muda de pasta
    anim = {"hl": {}, "enter_t": None, "job": None, "where": object()}

    def anim_tick():
        anim["job"] = None
        moving = False
        for i in list(anim["hl"]):
            target = 1.0 if i == state["hover"] else 0.0
            v = anim["hl"][i] + (target - anim["hl"][i]) * 0.35
            if abs(v - target) < 0.03:
                v = target
            if v == 0.0:
                del anim["hl"][i]
            else:
                anim["hl"][i] = v
            moving = moving or v != target
        if anim["enter_t"] is not None:
            if time.perf_counter() - anim["enter_t"] > 0.45 + 0.035 * min(len(state["rows"]), 14):
                anim["enter_t"] = None
            else:
                moving = True
        draw_rows(animating=True)
        if moving:
            anim["job"] = win.after(16, anim_tick)

    def kick_anim():
        if anim["job"] is None:
            anim["job"] = win.after(16, anim_tick)

    def draw_rows(animating=False):
        if not animating and anim["job"] is not None:
            return                  # a animacao ja vai redesenhar
        canvas.delete("row")
        cw = max(canvas.winfo_width(), 200)
        col2 = int(cw * 0.66)
        canvas.create_text(18, ROW_H / 2, text="PASTA", anchor="w", fill=FG_DIM,
                           font=("Segoe UI", 9, "bold"), tags="row")
        canvas.create_text(col2, ROW_H / 2, text="CONTEÚDO", anchor="w", fill=FG_DIM,
                           font=("Segoe UI", 9, "bold"), tags="row")
        canvas.create_line(10, ROW_H - 1, cw - 10, ROW_H - 1, fill=LINE, tags="row")
        now = time.perf_counter()
        for i, (path, text, info, kind) in enumerate(state["rows"]):
            y = ROW_H * (i + 1) + 2
            dx, k = 0, 1.0
            if anim["enter_t"] is not None:
                k = ease_out((now - anim["enter_t"] - 0.035 * min(i, 14)) / 0.40)
                dx = int(36 * (1 - k))
            hl = anim["hl"].get(i, 0.0)
            if path == state["sel"]:
                canvas.create_rectangle(6 + dx, y + 1, cw - 6, y + ROW_H - 3,
                                        fill=mix(BG, ROW_SEL, k), outline="", tags="row")
                canvas.create_rectangle(6 + dx, y + 1, 10 + dx, y + ROW_H - 3,
                                        fill=mix(BG, ACCENT_HOVER, k), outline="", tags="row")
            elif hl > 0:
                canvas.create_rectangle(6 + dx, y + 1, cw - 6, y + ROW_H - 3,
                                        fill=mix(BG, ROW_HOVER, hl), outline="", tags="row")
                canvas.create_rectangle(6 + dx, y + 1, 9 + dx, y + ROW_H - 3,
                                        fill=mix(BG, ACCENT, hl), outline="", tags="row")
            draw_icon(24 + dx, y + ROW_H / 2 - 1, kind, k)
            canvas.create_text(46 + dx, y + ROW_H / 2 - 1, text=text, anchor="w",
                               fill=mix(BG, FG, k), font=font, tags="row")
            canvas.create_text(col2 + dx, y + ROW_H / 2 - 1, text=info, anchor="w",
                               fill=mix(BG, FG if path == state["sel"] else FG_DIM, k),
                               font=font, tags="row")
        if not state["rows"]:
            msg = ("Nenhuma pasta encontrada." if search_var.get().strip() else
                   "Nenhum evento ainda. Clique em 'Adicionar pasta de fotos'."
                   if state["current"] is None else "Este evento está vazio.")
            canvas.create_text(18, ROW_H * 1.6, text=msg, anchor="w", fill=FG_DIM,
                               font=font, tags="row")
        total_h = ROW_H * (len(state["rows"]) + 1) + 8
        canvas.configure(scrollregion=(0, 0, cw, max(total_h, canvas.winfo_height())))
        place_logo()

    def draw_icon(x, y, kind, k=1.0):
        # icones desenhados (emoji nao aparece direito em todo Windows)
        if kind == "festa":
            canvas.create_polygon(x - 9, y - 6, x - 3, y - 6, x - 1, y - 4, x + 9, y - 4,
                                  x + 9, y + 7, x - 9, y + 7, fill=mix(BG, ACCENT, k),
                                  outline="", tags="row")
        else:
            c = mix(BG, "#e6e6e8", k)
            canvas.create_oval(x - 4, y - 8, x + 4, y, fill=c, outline="", tags="row")
            canvas.create_arc(x - 8, y + 1, x + 8, y + 15, start=0, extent=180,
                              fill=c, outline="", tags="row")

    def row_at(event):
        i = int(canvas.canvasy(event.y) // ROW_H) - 1
        return i if 0 <= i < len(state["rows"]) else None

    # --- acoes --------------------------------------------------------------
    def enter(path):
        """Abre uma festa (lista de alunos) ou um aluno (galeria de fotos)."""
        if not os.path.isdir(path):
            return
        state["current"] = path
        state["sel"] = None
        g["sel"] = set()
        g["anchor"] = None
        while not thumb_q.empty():        # miniaturas da pasta anterior: nao precisa mais
            try:
                asked.discard(thumb_q.get_nowait())
            except queue.Empty:
                break
        search_var.set("")
        canvas.yview_moveto(0)
        gcan.yview_moveto(0)
        refresh()
        if in_gallery():
            status_var.set("Dois cliques numa foto para ver grande. Arraste as fotos para o "
                           "aluno certo na lista da esquerda.")

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
            if i is not None:
                anim["hl"].setdefault(i, 0.0)
            kick_anim()

    def on_leave(_e):
        if state["hover"] is not None:
            state["hover"] = None
            kick_anim()

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
        cur = state["current"]
        if cur is None:
            return
        parent = os.path.dirname(cur)
        state["current"] = None if os.path.normcase(parent) == os.path.normcase(root_dir) \
            else parent
        state["sel"] = cur
        g["sel"] = {cur}
        search_var.set("")
        refresh()

    def open_sel():
        if in_gallery():
            open_in_explorer(state["current"])
        else:
            open_in_explorer(state["sel"] or state["current"] or root_dir)

    # --- renomear -----------------------------------------------------------
    def cancel_edit(*_):
        ed = state.get("editor")
        if ed is not None:
            state["editor"] = None
            canvas.delete("editor")
            ed.destroy()

    def start_rename(path=None):
        if in_gallery():
            sel = [p for p, k in g["items"] if k == "pasta" and p in g["sel"]]
            if sel:
                rename_dialog(sel[0])
            return
        path = path or state["sel"]
        if not path or path in busy_paths():
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
        canvas.create_window(40, y + 3, window=ed, anchor="nw",
                             width=int(cw * 0.66) - 56, height=ROW_H - 8, tags="editor")
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
        menu.delete(0, "end")
        here = state["current"] or root_dir
        if i is not None:
            path = state["rows"][i][0]
            state["sel"] = path
            draw_rows()
            menu.add_command(label="Abrir", command=lambda: enter(path))
            menu.add_command(label="Abrir no Explorer", command=lambda: open_in_explorer(path))
            menu.add_separator()
            menu.add_command(label="Renomear        F2", command=lambda: start_rename(path))
            menu.add_command(label="Deletar           Del", command=lambda: delete_paths([path]))
            menu.add_separator()
        menu.add_command(label="Criar pasta", command=lambda: new_folder(here))
        if i is None:
            menu.add_command(label="Abrir no Explorer", command=lambda: open_in_explorer(here))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def busy(on):
        state["busy"] = on
        if not on:
            prog["value"] = 0

    # --- galeria ------------------------------------------------------------
    def in_gallery():
        cur = state["current"]
        return cur is not None and os.path.dirname(cur) != root_dir

    def show_mode(mode):
        if g["mode"] == mode:
            return
        g["mode"] = mode
        if mode == "galeria":
            mid.pack_forget()
            gal.pack(fill="both", expand=True, before=bottom)
        else:
            gal.pack_forget()
            mid.pack(fill="both", expand=True, before=bottom)

    def festa_of(path):
        while os.path.dirname(path) != root_dir and os.path.dirname(path) != path:
            path = os.path.dirname(path)
        return path

    def fill_targets():
        # so as pastas dos alunos (as subpastas, como fotos_descartadas, ficam
        # dentro do aluno e aparecem quando abre a pasta dele)
        cur = state["current"]
        festa = festa_of(cur)
        paths = [os.path.join(festa, a) for a in subdirs(festa)]
        g["targets"] = [p for p in paths if os.path.normcase(p) != os.path.normcase(cur)]
        g["tinfo"] = [student_label(os.path.basename(p)) + (len(photos_in(p)),)
                      for p in g["targets"]]
        g["thover"] = g["tdrop"] = None
        side_count.configure(text="%d aluno%s" % (len(g["targets"]),
                                                  "" if len(g["targets"]) == 1 else "s"))
        targets.yview_moveto(0)
        draw_targets()

    def draw_targets():
        targets.delete("all")
        tw = max(targets.winfo_width(), 120)
        for k, (name, num, tag, n) in enumerate(g.get("tinfo", [])):
            y = k * TARGET_H
            cy = y + TARGET_H / 2
            drop, hov = k == g["tdrop"], k == g["thover"]
            if drop:
                targets.create_rectangle(0, y + 2, tw, y + TARGET_H - 2, fill=ROW_SEL,
                                         outline="")
                targets.create_rectangle(0, y + 2, 4, y + TARGET_H - 2, fill=ACCENT_HOVER,
                                         outline="")
            elif hov:
                targets.create_rectangle(0, y + 2, tw, y + TARGET_H - 2, fill=ROW_HOVER,
                                         outline="")
                targets.create_rectangle(0, y + 2, 3, y + TARGET_H - 2, fill=ACCENT,
                                         outline="")
            # bolinha com as iniciais
            r = 16
            ax = 12 + r
            targets.create_oval(ax - r, cy - r, ax + r, cy + r,
                                fill=ACCENT if (drop or hov) else ACCENT_DARK,
                                outline=ACCENT_HOVER if drop else "")
            targets.create_text(ax, cy, text=initials(name), fill=FG,
                                font=("Segoe UI", 9, "bold"))
            # quantidade de fotos (pilula na direita)
            pill = "%d" % n
            pw = 10 + 7 * len(pill)
            px1 = tw - 10
            px0 = px1 - pw
            targets.create_rectangle(px0, cy - 10, px1, cy + 10,
                                     fill=ACCENT if drop else "#232327", outline="")
            targets.create_text((px0 + px1) / 2, cy, text=pill, fill=FG,
                                font=("Segoe UI", 9, "bold"))
            # nome e numero do aluno
            tx = ax + r + 10
            maxw = px0 - tx - 8
            shown = name
            if text_w(shown) > maxw:
                while len(shown) > 1 and text_w(shown + "…") > maxw:
                    shown = shown[:-1]
                shown = shown.rstrip() + "…"
            targets.create_text(tx, cy - 8, text=shown, anchor="w", fill=FG,
                                font=("Segoe UI", 10, "bold"))
            sub = ("nº " + num) if num else "sem ficha"
            sub += "  ·  %d foto%s" % (n, "" if n == 1 else "s")
            targets.create_text(tx, cy + 10, text=sub, anchor="w", fill=FG_DIM,
                                font=("Segoe UI", 8))
            if tag:
                targets.create_text(px0 - 6, cy + 10, text="CONFERIR", anchor="e",
                                    fill=YELLOW, font=("Segoe UI", 7, "bold"))
            if k < len(g["tinfo"]) - 1 and not (drop or hov):
                targets.create_line(ax + r + 10, y + TARGET_H - 1, tw - 10, y + TARGET_H - 1,
                                    fill=LINE)
        if not g.get("tinfo"):
            targets.create_text(14, 22, text="Nenhum outro aluno nesta festa.", anchor="w",
                                fill=FG_DIM, font=("Segoe UI", 9))
        h = TARGET_H * len(g.get("tinfo", []))
        targets.configure(scrollregion=(0, 0, tw, max(h, targets.winfo_height())))

    def target_index(y_root):
        y = targets.canvasy(y_root - targets.winfo_rooty())
        k = int(y // TARGET_H)
        return k if 0 <= k < len(g["targets"]) else None

    def set_tdrop(k):
        if k != g["tdrop"]:
            g["tdrop"] = k
            draw_targets()
        if k is not None:           # rola a lista para mostrar o aluno
            top, bot = targets.yview()
            h = TARGET_H * max(len(g["targets"]), 1)
            if k * TARGET_H < top * h:
                targets.yview_moveto(k * TARGET_H / h)
            elif (k + 1) * TARGET_H > bot * h:
                targets.yview_moveto(((k + 1) * TARGET_H - targets.winfo_height()) / h)

    def t_motion(e):
        k = target_index(e.y_root)
        if k != g["thover"]:
            g["thover"] = k
            draw_targets()

    def t_leave(_e=None):
        if g["thover"] is not None:
            g["thover"] = None
            draw_targets()

    def refresh_gallery():
        q = search_var.get().strip().lower()
        cur = state["current"]
        items = [(os.path.join(cur, d), "pasta") for d in subdirs(cur)] + \
                [(p, "foto") for p in photos_in(cur)]
        if q:
            items = [it for it in items if q in os.path.basename(it[0]).lower()]
        g["items"] = items
        g["sel"] &= {p for p, _ in items}
        g["hover"] = None
        fill_targets()
        draw_gallery()

    def cols():
        return max(1, (max(gcan.winfo_width(), 200) - GAP) // (TILE_W + GAP))

    def tile_xy(i):
        c = cols()
        return GAP + (i % c) * (TILE_W + GAP), GAP + (i // c) * (TILE_H + GAP)

    def tile_at(x, y):
        """Indice da miniatura no ponto (coordenadas do canvas) ou None."""
        c = cols()
        col, row = int((x - GAP) // (TILE_W + GAP)), int((y - GAP) // (TILE_H + GAP))
        if col < 0 or row < 0 or col >= c:
            return None
        i = row * c + col
        if i >= len(g["items"]):
            return None
        tx, ty = tile_xy(i)
        return i if tx <= x <= tx + TILE_W and ty <= y <= ty + TILE_H else None

    def short(name, n=22):
        return name if len(name) <= n else name[:n - 1] + "…"

    def draw_gallery():
        gcan.delete("all")
        items = g["items"]
        for i, (path, kind) in enumerate(items):
            x, y = tile_xy(i)
            sel = path in g["sel"]
            outline = ACCENT_HOVER if g["drop"] == path else \
                ("#666666" if i == g["hover"] else "")
            gcan.create_rectangle(x, y, x + TILE_W, y + TILE_H, fill=ROW_SEL if sel else PANEL,
                                  outline=outline, width=2)
            cx, cy = x + TILE_W / 2, y + 6 + THUMB_PX / 2
            if kind == "pasta":
                gcan.create_polygon(cx - 48, cy - 30, cx - 16, cy - 30, cx - 8, cy - 22,
                                    cx + 48, cy - 22, cx + 48, cy + 34, cx - 48, cy + 34,
                                    fill=ACCENT, outline="")
                gcan.create_text(cx, cy + 6, text="%d foto(s)" % len(photos_in(path)),
                                 fill=FG, font=("Segoe UI", 9, "bold"))
            elif path in thumbs:
                gcan.create_image(cx, cy, image=thumbs[path])
            else:
                gcan.create_text(cx, cy, text="carregando...", fill=FG_DIM,
                                 font=("Segoe UI", 9))
                ask_thumb(path)
            gcan.create_text(cx, y + TILE_H - 14, text=short(os.path.basename(path)),
                             fill=FG, font=("Segoe UI", 9))
        if not items:
            gcan.create_text(16, 24, anchor="w", fill=FG_DIM, font=font,
                             text="Nenhuma foto encontrada." if search_var.get().strip()
                             else "Esta pasta está vazia.")
        rows = (len(items) + cols() - 1) // cols()
        h = GAP + rows * (TILE_H + GAP)
        gcan.configure(scrollregion=(0, 0, gcan.winfo_width(), max(h, gcan.winfo_height())))

    redraw_pending = {"on": False}

    def redraw_soon():
        if not redraw_pending["on"]:
            redraw_pending["on"] = True

            def go():
                redraw_pending["on"] = False
                if g["mode"] == "galeria":
                    draw_gallery()
            win.after(60, go)

    def ask_thumb(path):
        if path not in asked:
            asked.add(path)
            thumb_q.put(path)

    def thumb_worker():
        while True:
            path = thumb_q.get()
            try:
                msgs.put(("thumb", path, make_thumb(path, THUMB_PX, cache)))
            except Exception:
                msgs.put(("thumb", path, None))

    for _ in range(2):
        threading.Thread(target=thumb_worker, daemon=True).start()

    def got_thumb(path, im):
        if im is None:
            g.setdefault("thumb_fail", []).append(path)
            from PIL import Image as _I
            im = _I.new("RGB", (THUMB_PX, THUMB_PX), "#333333")
        if len(thumbs) > 3000:
            thumbs.clear()
            asked.clear()
        thumbs[path] = ImageTk.PhotoImage(im)
        redraw_soon()

    def photo_items():
        return [p for p, k in g["items"] if k == "foto"]

    def g_select(i, ctrl=False, shift=False):
        path = g["items"][i][0]
        if ctrl:
            g["sel"] ^= {path}
        elif shift and g["anchor"] is not None and g["anchor"] < len(g["items"]):
            a, b = sorted((g["anchor"], i))
            g["sel"] = {p for p, _ in g["items"][a:b + 1]}
        else:
            g["sel"] = {path}
        if not shift:
            g["anchor"] = i

    def g_press(e):
        gcan.focus_set()
        x, y = gcan.canvasx(e.x), gcan.canvasy(e.y)
        i = tile_at(x, y)
        ctrl, shift = bool(e.state & 0x0004), bool(e.state & 0x0001)
        g["press"] = (e.x, e.y, i, ctrl or shift)
        if i is None:
            if not (ctrl or shift):
                g["sel"] = set()
        elif ctrl or shift or g["items"][i][0] not in g["sel"]:
            g_select(i, ctrl, shift)
        draw_gallery()

    def drop_target(xr, yr):
        w = win.winfo_containing(xr, yr)
        if w is targets and g["targets"]:
            k = target_index(yr)
            if k is not None:
                return g["targets"][k], k
        elif w is gcan:
            i = tile_at(gcan.canvasx(xr - gcan.winfo_rootx()),
                        gcan.canvasy(yr - gcan.winfo_rooty()))
            if i is not None and g["items"][i][1] == "pasta":
                return g["items"][i][0], None
        return None, None

    def g_motion(e):
        pr = g["press"]
        if pr is None:
            return
        if g["drag"] is None:
            if pr[2] is None or abs(e.x - pr[0]) + abs(e.y - pr[1]) < 8:
                return
            paths = [p for p in photo_items() if p in g["sel"]]
            if not paths:
                return
            ind = tk.Toplevel(win)
            ind.overrideredirect(True)
            try:
                ind.attributes("-topmost", True)
            except tk.TclError:
                pass
            tk.Label(ind, text="  Mover %d foto(s)  " % len(paths), bg=ACCENT, fg=FG,
                     font=font_b, pady=4).pack()
            g["drag"] = (paths, ind)
            gcan.configure(cursor="fleur")
        ind = g["drag"][1]
        ind.geometry("+%d+%d" % (e.x_root + 14, e.y_root + 10))
        target, k = drop_target(e.x_root, e.y_root)
        set_tdrop(k)
        if target != g["drop"]:
            g["drop"] = target
            draw_gallery()
        # rola a galeria quando arrasta perto da borda
        if e.y < 20:
            gcan.yview_scroll(-1, "units")
        elif e.y > gcan.winfo_height() - 20:
            gcan.yview_scroll(1, "units")

    def g_release(e):
        pr, drag = g["press"], g["drag"]
        g["press"] = None
        if drag is None:
            if pr and pr[2] is not None and not pr[3]:
                g_select(pr[2])         # clique simples numa foto ja marcada
                draw_gallery()
            return
        g["drag"] = None
        drag[1].destroy()
        gcan.configure(cursor="")
        target, _k = drop_target(e.x_root, e.y_root)
        g["drop"] = None
        set_tdrop(None)
        if target:
            do_move(drag[0], target)
        else:
            draw_gallery()

    def do_move(paths, dest):
        done, errors = move_photos(paths, dest)
        if done:
            g["undo"] = done
            status_var.set("%d foto(s) movida(s) para \"%s\".  Ctrl+Z desfaz."
                           % (len(done), os.path.basename(dest)))
        g["sel"] = set()
        refresh()
        if errors:
            messagebox.showerror(APP_NAME, "Não foi possível mover:\n" +
                                 "\n".join(errors[:10]), parent=win)
        return done

    def delete_paths(paths, ask=True, parent=None):
        """Manda pastas/fotos para a Lixeira, depois de confirmar."""
        paths = [p for p in dict.fromkeys(paths) if p and os.path.exists(p)]
        if not paths:
            return []
        busy_now = [os.path.normcase(b) for b in busy_paths()]
        if any(os.path.normcase(p) == b or os.path.normcase(p).startswith(b + os.sep)
               or b.startswith(os.path.normcase(p) + os.sep) for p in paths for b in busy_now):
            messagebox.showinfo(APP_NAME, "Essa pasta ainda está sendo processada. Espere "
                                "terminar para deletar.", parent=parent or win)
            return []
        if len(paths) == 1:
            p = paths[0]
            what = ("a pasta \"%s\" (%d foto(s))" % (os.path.basename(p), count_files(p))
                    if os.path.isdir(p) else "a foto \"%s\"" % os.path.basename(p))
        else:
            n_dirs = len([p for p in paths if os.path.isdir(p)])
            what = "%d item(ns)" % len(paths) if n_dirs else "%d fotos" % len(paths)
        if ask and not messagebox.askyesno(
                APP_NAME, "Deletar %s?\n\nVai para a Lixeira do Windows: se precisar, "
                "dá para recuperar de lá." % what, icon="warning", parent=parent or win):
            return []
        cancel_edit()
        done, errors = send_to_trash(paths)
        gone = {os.path.normcase(p) for p in done}
        g["sel"] = {p for p in g["sel"] if os.path.normcase(p) not in gone}
        if state["sel"] and os.path.normcase(state["sel"]) in gone:
            state["sel"] = None
        cur = state["current"]
        while cur is not None and not os.path.isdir(cur):      # a pasta aberta foi junto
            parent = os.path.dirname(cur)
            cur = None if os.path.normcase(parent) == os.path.normcase(root_dir) else parent
        state["current"] = cur
        if done:
            status_var.set("%s para a Lixeira." % (
                "\"%s\" foi" % os.path.basename(done[0]) if len(done) == 1
                else "%d itens foram" % len(done)))
        refresh()
        if errors:
            messagebox.showerror(APP_NAME, "Não foi possível deletar:\n" + "\n".join(errors[:10]) +
                                 "\n\nFeche as fotos ou janelas abertas dessa pasta e tente "
                                 "de novo.", parent=parent or win)
        return done

    def gallery_selection():
        return [p for p, _ in g["items"] if p in g["sel"]]

    def undo_move(_e=None):
        if not g["undo"]:
            return
        back = [(dst, os.path.dirname(src)) for src, dst in g["undo"]]
        g["undo"] = []
        n = 0
        for dst, folder in back:
            try:
                shutil.move(dst, free_path(folder, os.path.basename(dst)))
                n += 1
            except OSError:
                pass
        status_var.set("Desfeito: %d foto(s) voltaram para o lugar." % n)
        refresh()

    def move_menu(parent_menu, paths):
        sub = tk.Menu(parent_menu, tearoff=0, bg=PANEL, fg=FG, activebackground=ACCENT,
                      activeforeground=FG, bd=0, font=font)
        festa = festa_of(state["current"])
        for p in g["targets"]:
            sub.add_command(label=os.path.relpath(p, festa).replace(os.sep, " / "),
                            command=lambda p=p: do_move(paths, p))
        sub.add_separator()
        sub.add_command(label="Nova pasta de aluno...",
                        command=lambda: new_folder(festa, then_move=paths))
        return sub

    def g_double(e):
        i = tile_at(gcan.canvasx(e.x), gcan.canvasy(e.y))
        if i is not None:
            open_item(i)

    def open_item(i):
        path, kind = g["items"][i]
        if kind == "pasta":
            enter(path)
        else:
            ph = photo_items()
            open_viewer(ph, ph.index(path))

    def g_right(e):
        gcan.focus_set()
        i = tile_at(gcan.canvasx(e.x), gcan.canvasy(e.y))
        menu.delete(0, "end")
        cur = state["current"]
        if i is not None:
            path, kind = g["items"][i]
            if path not in g["sel"]:
                g_select(i)
                draw_gallery()
            if kind == "foto":
                paths = [p for p in photo_items() if p in g["sel"]]
                menu.add_command(label="Ver foto", command=lambda: open_item(i))
                menu.add_cascade(label="Mover %d foto(s) para" % len(paths),
                                 menu=move_menu(menu, paths))
                menu.add_command(label="Mostrar no Explorer",
                                 command=lambda: show_in_explorer(path))
            else:
                menu.add_command(label="Abrir pasta", command=lambda: enter(path))
                menu.add_command(label="Renomear        F2",
                                 command=lambda: rename_dialog(path))
            sel = gallery_selection()
            menu.add_command(label=("Deletar           Del" if len(sel) == 1 else
                                    "Deletar %d itens     Del" % len(sel)),
                             command=lambda: delete_paths(sel))
            menu.add_separator()
        menu.add_command(label="Criar pasta aqui dentro", command=lambda: new_folder(cur))
        menu.add_command(label="Criar pasta de aluno na festa",
                         command=lambda: new_folder(festa_of(cur)))
        menu.add_command(label="Abrir no Explorer", command=lambda: open_in_explorer(cur))
        if g["undo"]:
            menu.add_separator()
            menu.add_command(label="Desfazer última mudança     Ctrl+Z", command=undo_move)
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def g_key_move(step):
        n = len(g["items"])
        if not n:
            return
        cur = [i for i, (p, _) in enumerate(g["items"]) if p in g["sel"]]
        i = max(0, min(n - 1, (cur[-1] + step) if cur else 0))
        g_select(i)
        x, y = tile_xy(i)
        top, bot = gcan.canvasy(0), gcan.canvasy(gcan.winfo_height())
        total = float(gcan.bbox("all")[3]) if gcan.bbox("all") else 1.0
        if y < top or y + TILE_H > bot:
            gcan.yview_moveto(max(0.0, (y - GAP) / max(total, 1.0)))
        draw_gallery()

    def g_enter(_e=None):
        sel = [i for i, (p, _) in enumerate(g["items"]) if p in g["sel"]]
        if sel:
            open_item(sel[0])

    def g_select_all(_e=None):
        g["sel"] = set(photo_items())
        draw_gallery()
        return "break"

    def target_double(e):
        k = target_index(e.y_root)
        if k is not None:
            enter(g["targets"][k])

    def show_in_explorer(path):
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            open_in_explorer(os.path.dirname(path))

    # --- nome de pasta (criar / renomear na galeria) ------------------------
    def ask_name(title, initial):
        d = tk.Toplevel(win)
        d.title(title)
        d.configure(bg=BG, padx=16, pady=14)
        d.transient(win)
        d.resizable(False, False)
        tk.Label(d, text=title, bg=BG, fg=FG, font=font_b, anchor="w").pack(fill="x")
        ent = tk.Entry(d, font=font, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                       highlightthickness=1, highlightbackground=ACCENT,
                       highlightcolor=ACCENT, width=36)
        ent.pack(fill="x", pady=(8, 12), ipady=5)
        ent.insert(0, initial)
        ent.select_range(0, "end")
        out = {"v": None}
        row = tk.Frame(d, bg=BG)
        row.pack(fill="x")

        def ok(_e=None):
            out["v"] = ent.get().strip()
            d.destroy()
        make_button(row, "OK", ok, primary=True).pack(side="right")
        make_button(row, "Cancelar", d.destroy).pack(side="right", padx=(0, 8))
        ent.bind("<Return>", ok)
        ent.bind("<KP_Enter>", ok)
        d.bind("<Escape>", lambda e: d.destroy())
        d.update_idletasks()
        d.geometry("+%d+%d" % (win.winfo_rootx() + (win.winfo_width() - d.winfo_width()) // 2,
                               win.winfo_rooty() + 120))
        ent.focus_set()
        try:
            d.grab_set()
        except tk.TclError:
            pass
        win.wait_window(d)
        return out["v"]

    def new_folder(parent, then_move=None):
        name = "nova_pasta"
        while True:
            name = ask_name("Nome da nova pasta", name)
            if not name:
                return
            path, err = create_folder(parent, name)
            if not err:
                break
            messagebox.showerror(APP_NAME, err, parent=win)
        status_var.set("Pasta \"%s\" criada." % name)
        if then_move:
            do_move(then_move, path)
        else:
            if not in_gallery():
                state["sel"] = path
            refresh()

    def rename_dialog(path):
        old = os.path.basename(path)
        new = old
        while True:
            new = ask_name("Novo nome da pasta", new)
            if not new or new == old:
                return
            err = validate_new_name(os.path.dirname(path), old, new)
            if not err:
                break
            messagebox.showerror(APP_NAME, err, parent=win)
        try:
            os.rename(path, os.path.join(os.path.dirname(path), new))
        except OSError as ex:
            messagebox.showerror(APP_NAME, "Não foi possível renomear:\n%s\n\nFeche as "
                                 "fotos abertas dessa pasta e tente de novo." % ex, parent=win)
            return
        status_var.set("\"%s\" renomeada para \"%s\"." % (old, new))
        refresh()

    # --- ver a foto grande ---------------------------------------------------
    def open_viewer(paths, idx):
        v = tk.Toplevel(win)
        v.configure(bg="#000000")
        v.geometry("%dx%d+20+20" % (min(1100, v.winfo_screenwidth() - 60),
                                     min(780, v.winfo_screenheight() - 100)))
        try:
            v.state("zoomed")
        except tk.TclError:
            pass
        try:
            v.iconbitmap(os.path.join(resource_dir(), "assets", "icone.ico"))
        except Exception:
            pass
        vbar = tk.Frame(v, bg=BG, padx=10, pady=8)
        vbar.pack(side="bottom", fill="x")
        vc = tk.Canvas(v, bg="#000000", highlightthickness=0)
        vc.pack(fill="both", expand=True)
        vs = {"paths": list(paths), "i": idx, "src": None, "for": None, "img": None,
              "job": None}
        side_max = max(v.winfo_screenwidth(), v.winfo_screenheight())

        def show(_e=None):
            if not vs["paths"]:
                v.destroy()
                return
            path = vs["paths"][vs["i"]]
            if vs["for"] != path:
                try:
                    vs["src"] = load_photo(path, side_max)
                except Exception:
                    vs["src"] = None
                vs["for"] = path
            vc.delete("all")
            w, h = max(vc.winfo_width(), 50), max(vc.winfo_height(), 50)
            if vs["src"] is not None:
                im = vs["src"].copy()
                im.thumbnail((w, h), Image.LANCZOS)
                vs["img"] = ImageTk.PhotoImage(im)
                vc.create_image(w / 2, h / 2, image=vs["img"])
            else:
                vc.create_text(w / 2, h / 2, text="Não foi possível abrir a foto.", fill=FG,
                               font=font)
            name = os.path.basename(path)
            info.configure(text="%s      %d de %d" % (name, vs["i"] + 1, len(vs["paths"])))
            v.title("%s  —  %s" % (name, os.path.basename(os.path.dirname(path))))

        def later(_e=None):
            if vs["job"]:
                v.after_cancel(vs["job"])
            vs["job"] = v.after(80, show)

        def step(k):
            if vs["paths"]:
                vs["i"] = (vs["i"] + k) % len(vs["paths"])
                show()

        def move_here(dest):
            path = vs["paths"][vs["i"]]
            if do_move([path], dest):
                vs["paths"].pop(vs["i"])
                if not vs["paths"]:
                    v.destroy()
                    return
                vs["i"] = min(vs["i"], len(vs["paths"]) - 1)
                show()

        def delete_here(_e=None):
            path = vs["paths"][vs["i"]]
            if delete_paths([path], parent=v):
                vs["paths"].pop(vs["i"])
                if not vs["paths"]:
                    v.destroy()
                    return
                vs["i"] = min(vs["i"], len(vs["paths"]) - 1)
                show()
            v.focus_set()

        def move_popup():
            m = tk.Menu(v, tearoff=0, bg=PANEL, fg=FG, activebackground=ACCENT,
                        activeforeground=FG, bd=0, font=font)
            festa = festa_of(state["current"])
            for p in g["targets"]:
                m.add_command(label=os.path.relpath(p, festa).replace(os.sep, " / "),
                              command=lambda p=p: move_here(p))
            try:
                m.tk_popup(move_b.winfo_rootx(), move_b.winfo_rooty() - 10)
            finally:
                m.grab_release()

        make_button(vbar, "‹  Anterior", lambda: step(-1)).pack(side="left")
        make_button(vbar, "Próxima  ›", lambda: step(1)).pack(side="left", padx=(8, 0))
        info = tk.Label(vbar, text="", bg=BG, fg=FG, font=font)
        info.pack(side="left", padx=16)
        make_button(vbar, "Fechar", v.destroy).pack(side="right")
        move_b = make_button(vbar, "Mover para...", move_popup, primary=True)
        move_b.pack(side="right", padx=(0, 8))
        make_button(vbar, "Deletar", delete_here).pack(side="right", padx=(0, 8))
        v.bind("<Delete>", delete_here)
        vc.bind("<Configure>", later)
        v.bind("<Left>", lambda e: step(-1))
        v.bind("<Right>", lambda e: step(1))
        v.bind("<Escape>", lambda e: v.destroy())
        vc.bind("<Button-1>", lambda e: step(1 if e.x > vc.winfo_width() / 2 else -1))
        vc.bind("<MouseWheel>", lambda e: step(-1 if e.delta > 0 else 1))
        v.focus_set()
        show()

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

    # --- processamento (fila de pastas) --------------------------------------
    # Cada pasta escolhida entra na fila e vira um evento (festa_N). Duas pastas
    # sao processadas ao mesmo tempo; as outras esperam. Erro numa pasta nao
    # para as outras.
    jobs = []                       # na ordem em que foram escolhidas
    engines = []                    # motores de rosto livres (um por pasta rodando)
    engines_lock = threading.Lock()
    finished = []                   # terminaram desde a ultima caixa de resumo
    jobs_box = tk.Frame(bottom, bg=BG)
    jobs_head = tk.Frame(jobs_box, bg=BG)
    jobs_head.pack(fill="x")
    jobs_title = tk.Label(jobs_head, text="", bg=BG, fg=FG, font=font_b, anchor="w")
    jobs_title.pack(side="left")
    clear_btn = tk.Label(jobs_head, text="Limpar concluídas", bg=BG, fg=ACCENT_HOVER,
                         font=("Segoe UI", 9, "underline"), cursor="hand2")
    jobs_rows = tk.Frame(jobs_box, bg=BG)
    jobs_rows.pack(fill="x", pady=(4, 6))
    JOB_TEXT = {"espera": "Esperando na fila", "rodando": "Começando...",
                "pronto": "Pronto", "erro": "Erro", "cancelado": "Cancelado"}
    JOB_COLOR = {"espera": FG_DIM, "rodando": FG, "pronto": "#66bb6a", "erro": ACCENT_HOVER,
                 "cancelado": FG_DIM}

    def running():
        return [j for j in jobs if j["state"] in ("espera", "rodando")]

    def busy_paths():
        return {j["live"].get("event") for j in jobs if j["state"] == "rodando"} - {None}

    def get_engine(log):
        with engines_lock:
            if engines:
                return engines.pop()
        log("Carregando modelos de reconhecimento...")
        return FaceEngine(log)      # cada pasta rodando tem o seu (nao e seguro dividir)

    def worker(job):
        jid = job["id"]

        def log(m):
            msgs.put(("status", jid, m))
        engine = None
        try:
            engine = get_engine(log)
            report = job["live"]
            ev = process_folder(job["folder"], engine, log,
                                lambda d, t, txt=None: msgs.put(("prog", jid, d, t, txt)),
                                root_dir, report=report, cancel=job["cancel"])
            msgs.put(("done", jid, ev, report))
        except Cancelled:
            msgs.put(("cancelado", jid))
        except Exception as e:  # mostra qualquer erro ao usuario
            if not isinstance(e, RuntimeError):     # RuntimeError = aviso nosso
                log_error("Pasta %s:\n%s" % (job["folder"], traceback.format_exc()))
            msgs.put(("error", jid, str(e) or type(e).__name__))
        finally:
            if engine is not None:
                with engines_lock:
                    engines.append(engine)

    def start_jobs():
        active = [j for j in jobs if j["state"] == "rodando"]
        for j in jobs:
            if len(active) >= MAX_PARALLEL:
                break
            if j["state"] == "espera":
                j["state"] = "rodando"
                j["text"] = JOB_TEXT["rodando"]
                active.append(j)
                threading.Thread(target=worker, args=(j,), daemon=True).start()
        busy(bool(running()))
        draw_jobs()

    def cancel_job(j):
        if j["state"] == "espera":
            j["state"] = "cancelado"
            j["text"] = "Cancelado (não começou)"
            finished.append(j)
            start_jobs()
            if not running():
                show_summary()
        elif j["state"] == "rodando":
            j["cancel"].set()
            j["text"] = "Cancelando..."
            draw_jobs()

    def open_job(j):
        if j.get("event") and os.path.isdir(j["event"]):
            enter(j["event"])

    def clear_jobs(_e=None):
        jobs[:] = [j for j in jobs if j["state"] in ("espera", "rodando")]
        draw_jobs()

    def draw_jobs():
        for w in jobs_rows.winfo_children():
            w.destroy()
        if not jobs:
            jobs_box.pack_forget()
            return
        if not jobs_box.winfo_ismapped():
            jobs_box.pack(fill="x", before=prog)
        n_run = len([j for j in jobs if j["state"] == "rodando"])
        n_wait = len([j for j in jobs if j["state"] == "espera"])
        title = "Fila de pastas"
        if n_run or n_wait:
            title += ":  %d processando, %d esperando" % (n_run, n_wait)
        jobs_title.configure(text=title)
        if len(running()) < len(jobs):
            clear_btn.pack(side="right")
        else:
            clear_btn.pack_forget()
        shown = [j for j in jobs if j["state"] == "rodando"] + \
            [j for j in jobs if j["state"] == "espera"] + \
            [j for j in jobs if j["state"] not in ("rodando", "espera")][::-1]
        extra_n = max(0, len(shown) - 5)
        shown = sorted(shown[:5], key=jobs.index)
        if extra_n:
            tk.Label(jobs_rows, text="... e mais %d pasta(s)" % extra_n, bg=BG, fg=FG_DIM,
                     font=("Segoe UI", 9), anchor="w").pack(side="bottom", fill="x")
        for j in shown:
            row = tk.Frame(jobs_rows, bg=PANEL, padx=8, pady=4)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=short(os.path.basename(j["folder"]) or j["folder"], 26),
                     width=26, anchor="w", bg=PANEL, fg=FG,
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            if j["state"] == "rodando":
                bar = ttk.Progressbar(row, mode="determinate", length=140,
                                      style="Dark.Horizontal.TProgressbar",
                                      maximum=max(1, j["total"]), value=j["done"])
                bar.pack(side="left", padx=(0, 8))
                j["bar"] = bar
            lbl = tk.Label(row, text=j["text"], anchor="w", bg=PANEL,
                           fg=JOB_COLOR[j["state"]], font=("Segoe UI", 9))
            lbl.pack(side="left", fill="x", expand=True)
            j["label"] = lbl
            if j["state"] in ("espera", "rodando"):
                b = tk.Label(row, text="Cancelar", bg=PANEL, fg=YELLOW, cursor="hand2",
                             font=("Segoe UI", 9, "underline"))
                b.bind("<Button-1>", lambda e, j=j: cancel_job(j))
                b.pack(side="right")
            elif j["state"] == "pronto":
                b = tk.Label(row, text="Abrir", bg=PANEL, fg=YELLOW, cursor="hand2",
                             font=("Segoe UI", 9, "underline"))
                b.bind("<Button-1>", lambda e, j=j: open_job(j))
                b.pack(side="right")

    def job_by_id(jid):
        for j in jobs:
            if j["id"] == jid:
                return j
        return None

    def add_job(folder):
        folder = os.path.normpath(folder)
        if any(os.path.normcase(j["folder"]) == os.path.normcase(folder)
               for j in running()):
            if not test:
                messagebox.showinfo(APP_NAME, "Essa pasta já está na fila.", parent=win)
            return None
        state["job_n"] = state.get("job_n", 0) + 1
        j = {"id": state["job_n"], "folder": folder, "state": "espera",
             "text": JOB_TEXT["espera"], "cancel": threading.Event(), "done": 0, "total": 1, "live": {}}
        jobs.append(j)
        start_jobs()
        return j

    def add_folder():
        folder = filedialog.askdirectory(title="Escolha a pasta com as fotos da festa "
                                               "(pode escolher outra depois, ela entra na fila)")
        if not folder:
            return
        add_job(folder)

    def result_text(j):
        rep, ev = j["report"], j["event"]
        n = len([d for d in subdirs(ev) if os.path.basename(d) != LEFTOVER_FOLDER])
        if "fichas" in rep:
            text = ("%s criada: %d ficha(s), %d aluno(s) com fotos."
                    % (os.path.basename(ev), rep["fichas"], n))
        else:
            text = "%s criada com %d pessoa(s)." % (os.path.basename(ev), n)
        if rep.get("descartadas"):
            text += (" %d foto(s) com olho fechado ou olhando para o lado foram para "
                     "%s, dentro da pasta de cada aluno." % (rep["descartadas"], DISCARD_FOLDER))
        return text

    def show_summary():
        """Quando a fila termina: uma caixa com o resultado de cada pasta."""
        done = list(finished)
        finished[:] = []
        if not done:
            return
        if test:
            state["summary"] = [(j["folder"], j["state"]) for j in done]
            return
        ok = [j for j in done if j["state"] == "pronto"]
        if len(done) == 1 and ok:
            j = ok[0]
            state["current"] = j["event"]
            state["sel"] = None
            search_var.set("")
            refresh()
            text = result_text(j)
            if j["report"].get("missing"):
                text += "\n\nNão apareceram em outras fotos:\n" + \
                        "\n".join(j["report"]["missing"][:30])
            messagebox.showinfo(APP_NAME, text)
            check = check_text(j["report"])
            if check:
                (messagebox.showinfo if not j["report"].get("lost") else
                 messagebox.showwarning)("Conferência das fotos", check)
            return
        refresh()
        parts, warn = [], False
        for j in done:
            name = os.path.basename(j["folder"]) or j["folder"]
            if j["state"] == "pronto":
                parts.append("%s:\n%s\n%s" % (name, result_text(j), check_text(j["report"])))
                warn = warn or bool(j["report"].get("lost"))
            elif j["state"] == "erro":
                parts.append("%s:\nErro: %s" % (name, j["error"]))
                warn = True
            else:
                parts.append("%s:\nCancelada." % name)
        (messagebox.showwarning if warn else messagebox.showinfo)(
            "Fila de pastas: %d pasta(s) terminadas" % len(done), "\n\n".join(parts))

    def poll():
        try:
            while True:
                m = msgs.get_nowait()
                if m[0] == "status":
                    j = job_by_id(m[1])
                    if j is not None and j["state"] == "rodando" and not j["cancel"].is_set():
                        j["text"] = m[2]
                        if j.get("label"):
                            j["label"].configure(text=m[2])
                    status_var.set(m[2])
                elif m[0] == "prog":
                    j = job_by_id(m[1])
                    if j is not None and j["state"] == "rodando":
                        j["done"], j["total"] = m[2], m[3]
                        if not j["cancel"].is_set():
                            j["text"] = "%s %d de %d" % (m[4] or "Analisando fotos...", m[2], m[3])
                        if j.get("label"):
                            j["label"].configure(text=j["text"])
                        if j.get("bar"):
                            j["bar"].configure(maximum=max(1, m[3]), value=m[2])
                    act = [x for x in jobs if x["state"] == "rodando"]
                    prog["maximum"] = 100
                    prog["value"] = 100.0 * sum(x["done"] / max(1, x["total"]) for x in act) \
                        / max(1, len(act))
                    status_var.set(j["text"] if j is not None else "")
                elif m[0] == "update":
                    show_update(m[1])
                elif m[0] == "thumb":
                    got_thumb(m[1], m[2])
                elif m[0] in ("done", "error", "cancelado"):
                    j = job_by_id(m[1])
                    if j is None:
                        continue
                    if m[0] == "done":
                        j["state"], j["event"], j["report"] = "pronto", m[2], m[3]
                        j["text"] = result_text(j).split(" criada")[0] + " criada. " + \
                            (check_text(m[3]).split("\n")[0] if check_text(m[3]) else "")
                        if m[3].get("descartadas"):
                            j["text"] += "  %d descartada(s)." % m[3]["descartadas"]
                    elif m[0] == "error":
                        j["state"], j["error"] = "erro", m[2]
                        j["text"] = "Erro: " + m[2]
                    else:
                        j["state"], j["text"] = "cancelado", "Cancelado"
                    finished.append(j)
                    start_jobs()
                    if not in_gallery():
                        refresh()
                    if not running():
                        status_var.set("Fila terminada.")
                        show_summary()
        except queue.Empty:
            pass
        win.after(100, poll)

    add_btn.configure(command=add_folder)
    clear_btn.bind("<Button-1>", clear_jobs)

    def on_close():
        if running() and not messagebox.askyesno(
                APP_NAME, "Ainda há pastas na fila sendo processadas.\n"
                "Fechar mesmo assim? As que não terminaram não serão salvas.", parent=win):
            return
        for j in running():
            j["cancel"].set()
            ev = j["live"].get("event")
            if ev:
                shutil.rmtree(ev, ignore_errors=True)
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", on_close)
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
    gcan.bind("<Configure>", lambda e: g["mode"] == "galeria" and draw_gallery())
    gcan.bind("<ButtonPress-1>", g_press)
    gcan.bind("<B1-Motion>", g_motion)
    gcan.bind("<ButtonRelease-1>", g_release)
    gcan.bind("<Double-1>", g_double)
    gcan.bind("<Button-3>", g_right)
    gcan.bind("<MouseWheel>",
              lambda e: gcan.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1),
                                          "units"))
    gcan.bind("<Button-4>", lambda e: gcan.yview_scroll(-1, "units"))
    gcan.bind("<Button-5>", lambda e: gcan.yview_scroll(1, "units"))
    gcan.bind("<Left>", lambda e: g_key_move(-1))
    gcan.bind("<Right>", lambda e: g_key_move(1))
    gcan.bind("<Up>", lambda e: g_key_move(-cols()))
    gcan.bind("<Down>", lambda e: g_key_move(cols()))
    gcan.bind("<Return>", g_enter)
    gcan.bind("<BackSpace>", lambda e: go_back())
    gcan.bind("<Control-a>", g_select_all)
    gcan.bind("<Control-A>", g_select_all)
    win.bind("<Control-z>", undo_move)
    win.bind("<Control-Z>", undo_move)
    targets.bind("<Double-1>", target_double)
    targets.bind("<Motion>", t_motion)
    targets.bind("<Leave>", t_leave)
    targets.bind("<Configure>", lambda e: g["mode"] == "galeria" and draw_targets())
    targets.bind("<MouseWheel>",
                 lambda e: targets.yview_scroll(int(-e.delta / 120) or
                                                (-1 if e.delta > 0 else 1), "units"))
    targets.bind("<Button-4>", lambda e: targets.yview_scroll(-1, "units"))
    targets.bind("<Button-5>", lambda e: targets.yview_scroll(1, "units"))
    canvas.bind("<Up>", lambda e: move_sel(-1))
    canvas.bind("<Down>", lambda e: move_sel(1))
    canvas.bind("<Return>", lambda e: state["sel"] and enter(state["sel"]))
    canvas.bind("<BackSpace>", lambda e: go_back())
    canvas.bind("<Delete>", lambda e: state["sel"] and delete_paths([state["sel"]]))
    gcan.bind("<Delete>", lambda e: delete_paths(gallery_selection()))
    win.bind("<F2>", lambda e: start_rename())
    search.bind("<Down>", lambda e: (canvas.focus_set(), move_sel(1)))
    search_var.trace_add("write", refresh)

    # --- abertura: logo da Gala no fundo preto, depois a tela se abre -------
    def show_splash():
        if logo_full is None:
            return
        halves = [tk.Canvas(win, bg="#000000", highlightthickness=0, bd=0, cursor="arrow")
                  for _ in range(2)]
        sp = {"t0": None, "key": None, "img": None, "base": None, "bsize": None}

        def logo_frame(w, h, scale, alpha):
            side = min(w * 0.46, h * 0.40 * logo_full.width / logo_full.height)
            size = (max(1, int(side)), max(1, int(side * logo_full.height / logo_full.width)))
            if sp["bsize"] != size:     # logo ja montada no preto, no tamanho da janela
                bg = Image.new("RGBA", size, (0, 0, 0, 255))
                bg.alpha_composite(logo_full.resize(size, Image.LANCZOS))
                sp["base"], sp["bsize"] = bg.convert("RGB"), size
            key = (size, round(scale, 3), round(alpha, 2))
            if key != sp["key"]:
                im = sp["base"]
                if abs(scale - 1) > 0.002:
                    im = im.resize((max(1, int(size[0] * scale)), max(1, int(size[1] * scale))),
                                   Image.BILINEAR)
                arr = (np.asarray(im, np.float32) * alpha).astype(np.uint8)
                sp["img"], sp["key"] = ImageTk.PhotoImage(Image.fromarray(arr)), key
            return sp["img"], size

        def frame():
            if sp["t0"] is None:
                sp["t0"] = time.perf_counter()
            t = time.perf_counter() - sp["t0"]
            w, h = max(win.winfo_width(), 200), max(win.winfo_height(), 200)
            T = SPLASH_SECONDS
            fade_in = ease_out(t / 0.9)
            fade_out = ease_in_out((t - (T - 0.55)) / 0.55)
            alpha = fade_in * (1 - fade_out)
            scale = 0.90 + 0.10 * fade_in + 0.05 * fade_out
            img, size = logo_frame(w, h, scale, alpha)
            load = ease_in_out((t - 0.35) / (T - 1.0))
            open_k = ease_in_out((t - T) / 0.65)       # cortina abrindo
            cy = h * 0.46
            if open_k > 0 and not sp.get("aberto"):
                sp["aberto"] = True
                anim["where"] = object()        # linhas entram deslizando
                refresh()
            for n, c in enumerate(halves):
                top = n == 0
                hh = h // 2 if top else h - h // 2
                dy = -int(open_k * hh) if top else h // 2 + int(open_k * hh)
                c.place(x=0, y=dy, width=w, height=hh)
                c.tk.call("raise", c._w)
                c.delete("all")
                oy = 0 if top else -(h // 2)        # mesma cena nas duas metades
                c.create_image(w / 2, cy + oy, image=img)
                bw = min(260, w * 0.3)
                by = cy + size[1] * 0.5 + 46 + oy
                bar_a = min(fade_in, 1 - fade_out)
                if bar_a > 0.01:
                    c.create_rectangle(w / 2 - bw / 2, by, w / 2 + bw / 2, by + 3,
                                       fill=mix("#000000", "#2a2a2e", bar_a), outline="")
                    c.create_rectangle(w / 2 - bw / 2, by, w / 2 - bw / 2 + bw * load, by + 3,
                                       fill=mix("#000000", ACCENT_HOVER, bar_a), outline="")
                    c.create_text(w / 2, by + 22, text="Carregando...",
                                  fill=mix("#000000", "#8a8a90", bar_a),
                                  font=("Segoe UI", 10))
                if open_k > 0:          # brilho vermelho na emenda da cortina
                    glow = mix("#000000", ACCENT_HOVER, 1 - open_k * 0.6)
                    if top:
                        c.create_rectangle(0, hh - 2, w, hh, fill=glow, outline="")
                    else:
                        c.create_rectangle(0, 0, w, 2, fill=glow, outline="")
            if open_k < 1:
                win.after(15, frame)
            else:
                for c in halves:
                    c.destroy()
                search.focus_set()
        frame()

    refresh()
    poll()
    if not test:
        show_splash()
    if test:
        api = {"win": win, "enter": enter, "go_back": go_back, "g": g, "thumbs": thumbs,
               "open_viewer": open_viewer, "do_move": do_move, "undo": undo_move,
               "photo_items": photo_items, "state": state, "errors": test_errors,
               "create": new_folder, "add_job": add_job, "jobs": jobs,
               "cancel_job": cancel_job, "delete": delete_paths, "draw_targets": draw_targets}
        win.after(500, lambda: test(api))
    else:
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
        # conferencia do nome com o dicionario (usa as probabilidades do leitor)
        get_ocr()(img[60:140, 0:330], use_det=False, use_cls=False)
        P = _last_probs()
        fixed = _fix_names("MARIA", P, ()) if P is not None else "sem"
        msg = "ok v%d %s %s mao=%s nomes=%s" % (VERSAO, name, code,
                                                "sim" if hand_model(download=False) else "nao",
                                                fixed)
    except Exception as e:
        msg = "erro %r" % e
    with open(out, "w", encoding="utf-8") as f:
        f.write(msg)


def gui_self_test():
    """Usado no build: abre a janela, a galeria, a foto grande, move e desfaz."""
    out = os.path.join(app_dir(), "autoteste_janela.txt")
    root = data_dir()
    festa = os.path.join(root, "festa_autoteste")
    shutil.rmtree(festa, ignore_errors=True)
    fila = os.path.join(app_dir(), "fila_autoteste")
    shutil.rmtree(fila, ignore_errors=True)
    for i in range(3):              # pastas sem rosto: cada uma tem que dar erro sozinha
        os.makedirs(os.path.join(fila, "pasta_%d" % i))
        for k in range(2):
            cv2.imwrite(os.path.join(fila, "pasta_%d" % i, "f%d.jpg" % k),
                        np.full((300, 400, 3), 60 * k + 40 * i, np.uint8))
    for a in ("aluno_a", "aluno_b"):
        os.makedirs(os.path.join(festa, a))
        for i in range(4):
            img = np.full((900, 600, 3), (40 * i, 120, 200), np.uint8)
            cv2.circle(img, (300, 300), 120, (220, 200, 180), -1)
            cv2.imwrite(os.path.join(festa, a, "foto_%d.jpg" % i), img)
    os.makedirs(os.path.join(festa, "aluno_b", DISCARD_FOLDER))
    result = {"msg": "erro: nao terminou"}

    def script(api):
        win, g = api["win"], api["g"]
        steps = []
        a, b = os.path.join(festa, "aluno_a"), os.path.join(festa, "aluno_b")

        def check(cond, what):
            if not cond:
                api["errors"].append("falhou: " + what)

        def s1():
            api["enter"](festa)
            api["enter"](a)
            check(len(api["photo_items"]()) == 4, "galeria com 4 fotos")
            check(g["targets"] == [b], "lista mover para so com alunos (%s)" % g["targets"])

        def s2():
            check(len(api["thumbs"]) >= 4, "miniaturas (%d)" % len(api["thumbs"]))
            check(not g.get("thumb_fail"), "miniaturas com erro")
            api["open_viewer"](api["photo_items"](), 1)

        def s3():
            for w in win.winfo_children():
                if w.winfo_class() == "Toplevel":
                    w.destroy()
            moved = api["do_move"](api["photo_items"]()[:2], b)
            check(len(moved) == 2 and len(photos_in(b)) == 6, "mover 2 fotos")
            api["undo"]()
            check(len(photos_in(a)) == 4, "desfazer")
            gone = api["delete"]([photos_in(a)[0]], ask=False)
            check(len(gone) == 1 and len(photos_in(a)) == 3, "deletar foto")
            lixo = os.path.join(festa, "pasta_para_deletar")
            os.makedirs(lixo)
            gone = api["delete"]([lixo], ask=False)
            check(len(gone) == 1 and not os.path.exists(lixo), "deletar pasta")
            api["go_back"]()
            api["go_back"]()
            for i in range(3):
                api["add_job"](os.path.join(fila, "pasta_%d" % i))
            sts = [j["state"] for j in api["jobs"]]
            check(sts == ["rodando", "rodando", "espera"], "fila 2 por vez (%s)" % sts)
            api["cancel_job"](api["jobs"][2])
            check(api["jobs"][2]["state"] == "cancelado", "cancelar na fila")

        def s3b():
            sts = [j["state"] for j in api["jobs"]]
            check(sts == ["erro", "erro", "cancelado"], "fila terminou (%s)" % sts)
            check(len(api["state"].get("summary") or []) == 3, "resumo da fila")

        def s4():
            errs = api["errors"]
            result["msg"] = ("ok janela v%d" % VERSAO) if not errs else \
                "erro: " + " | ".join(errs)
            win.destroy()
        steps = [s1, s2, s3, s3b, s4]

        def run(i=0):
            try:
                steps[i]()
            except Exception as e:
                log_error(traceback.format_exc())
                api["errors"].append("%s: %s" % (type(e).__name__, e))
                if i < len(steps) - 1:
                    i = len(steps) - 2
            if i + 1 < len(steps):
                win.after(4000 if i == 0 else 20000 if steps[i] is s3 else 1500,
                          lambda: run(i + 1))
        run()

    try:
        run_gui(test=script)
    except Exception:
        result["msg"] = "erro: " + traceback.format_exc()
    shutil.rmtree(festa, ignore_errors=True)
    shutil.rmtree(fila, ignore_errors=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(result["msg"])


def main(argv):
    if argv and argv[0] == "--autoteste":
        self_test()
    elif argv and argv[0] == "--autoteste-janela":
        gui_self_test()
    elif argv and argv[0] == "--autoteste-reinicio":
        restart_program(["--autoteste"])    # usado no build: testa o reiniciar
    elif argv and os.path.isdir(argv[0]):
        run_cli(argv[0])
    else:
        try:
            run_gui()
        except Exception:
            log_error(traceback.format_exc())
            raise


# Logo da Gala Eventos (PNG em base64), usada na abertura e no cabecalho
LOGO_GALA_PNG = (
    "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"
    "xajto5vOPnvJLcXSu5tEr6rCbZfFiuZrC3K2DzqGYhWeGLTCTUFEB8NWSSKimRdEBICs7+mROcPDAgBLN2w4ZuvxOaDre3p0"
    "zvCwLG1r8/V9wE70+S1ZAKwLtLNvX9y+cOGlKdDh7rsjIIk7z7t07I89EXfVpJimG88bGhqoG7pMRERERLM5LNbfVgG6Kuut"
    "mvItf/xDngdsXCQiIpq2eBInIiI6RlYB2svNQCeOs2eQiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiI"
    "iIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiI"
    "iIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiI"
    "iIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiKYX4SYgoqlw9wOWFyLi3EpE"
    "RNOzDGc5TsRASEQ0sfKgABSAi0ic4t+EvFwxETFuRSKiExoANS+T41TCXn25n5fjDIhEDIRENFuDoIikE+5vAlACEOorDABS"
    "ABURKU8SDsFKBRFRQ5ThSV6GF/JyXOrK8SqAsfrGv/x5hGU4EQMhEc2OCoQAkPpePXd/BIBHAbgAwCUAlgBYCODMPBAir0jc"
    "DWArgNsA3ARgE4BbRWRgkkoK2HNIRHT0y29kozm87v5WABcD6ALwSAAXAlgM4BwArXVPsRvAdgCbAfwWwG8AbBSRWw50jiAi"
    "BkIimjmViTChVbgHwB8CuCwPhPW25RWG3wGoAJgLoBPApQCKdY/bDGAjgPUAviwig3XPn4BDSomIjkYQDPU9ge5eAPBUAM8B"
    "8BhkDXpz6v6sH8DNAO5FNrrjJADdeXAs1D1uR17WfxPAF0Tk3tr5AuwxJCIimllhMP/Z5O4r3P2n7l7xfaru/j13f527L3H3"
    "llpPX33Ac/eT3f3Z7v55d7/fH2q3u3/d3V/k7mfUv/ZUJjkgIqKHBsFJyuFHu/u/uPvmvNyut8Hd3+Dui929eWK56+5Fdz/N"
    "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"
    "hrPRY7FxvMzbvPnlnUrmd4bhvY0iGYKaKL1dUf9Iym4dhvWBOlWF2RV3Tc198prIE6dN1I0aqjNuKtmK9QreMXXq2zP1TXfX"
    "BfJZCupCkj1af+Vt7Wvfe8SqVXnWPl9bwqhYmzSI+rfbZ+ZOOg4oDHWa3EKjX80Dircf3PzurAq+1UMd1imV7QrDjky++yOL"
    "E9ZFVYP4bMWut3Ws/U0P9Vu7Qn1dRiB1SjKautCldVgn6pIGrf/vrlzuk8tnzaoXQC8G9DUtLdnhphgSEE29f+hWUEv4EIQW"
    "ZsxF3++Nuw/Qy/fff2wRvJRCKBHVo7le57tuBHrL7Y9ELFq8WN7X3t5NheuKUX0ylbaWIajrRN6EMPwAAC4ZAF1o6NR903tV"
    "YwQFCATqy0uA4Klh0p7Alka+e+r0U7Mil+/WYUHASPWpHAoAM1BX1inJEpBdOiySvMEYItQIvsw1APSg85dd5C4VMWWm7LMO"
    "IAgVP3RNC7JP7aMtKMLyNK/yJDMKuZ5sdmq1+35WCxNbWwUAAgRvHhMEY4GwZ7gJx4uwWOZVwNcEBEXfcmpHx6v3trZmZAQa"
    "YDTCsrx0z4dyKoap0rsECGTxYv1/s6bOAHhoCHYPgPnU9c5bS1brfb5GghWso8KCaz+3I9Q/aBJRBItp9DBSEDCrNLSkyQ3c"
    "U6FZZ7J14bBPs7BFZi5cu3YLMuriXQyXNEZeXWpTgTRdLoLYNB4IxjcG6rvTcrnf3ZHLzTO1svRC46EbzLNrK4gKwFsPPviQ"
    "u5qn/SyjgtsChROLIELylbwUr3h7x7ov0sjWteK3Lp1I1FKISuRNqiA3LZ8yrdU6vobC+Gx7LC4G9F3NzVc2ZIKfFkGKkkyR"
    "+lUdFi4748UX2xcm9MJV1WIU1irxjvb2dWd0rHtXPuQVeXJNUxBkAQQ7w7AAUVOyor4r+cKfbm9ufvfySbMmfritrWA9jbbE"
    "+FALaz9uaclA1KGFiPFLCRc7xORM3NfPMZ9uwo+C0fudmRV1VJdpEkbKDWdt2bJ7H0h41wAQZrM/RYe6eAAARKFJREFU7dZ6"
    "i4rWM613HDUEmrxiWfN+4+ebfJ1+SWxa11XYV0h1kTobqFOacrmv2pALc5CHgg7FKoNLJk2aqBV/SJF6OvkalVrSAOil0w84"
    "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"
    "nvYh2urXmuxjfLZfRpI3Ao3vo/u8pyAjsJcncQ/mA8H8KVP2ywbBWAKNIdCQDXRQ0EEQSJGiVKhDVQyAbqVUV7Gue/fWZybv"
    "+DDaCkn04sr5i/rfUm6f4pNpuo/Ve97IPMbDw8PDw8PDw2OYY2EUaix+Jfad/VwCBNe0tGTvbW3td7rZEiB4pKUle28rBtyg"
    "3aPKWq5fAg8PDw8Pj+oITYvw+oJpHh4eHvsSXK/eIvQ2T49jPsBF5v8XDX/Pn4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eH"
    "h4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eH"
    "h4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eH"
    "h4eHh4eHh4eHh4fH4EL8Enh4lAbJQTsnIsIhnmOpuXKox1mrPRpJ8xnMsaaNw6/X8OEZtZxvuXkM9F21fv4biWeMpLX395aH"
    "h1cIPTw8htdlGgCgiIR9/NtMf/5umK+FMh8NQA9X4YGkDMbYBus91RAIvaDnMcQ8g4Zn6JEy9pF6ZkjaNQ/7OgeSgZF7Q88z"
    "PDy8Qujh0ecLqNYX/WAKtlYRFJGi829ZAPsBGA3gTQAmAGgwPKITwFYA2wDsAvCqHae5nDHUglAtBByj9A6ZkDcchLYk2jd7"
    "zuEkUKWt1WCc3X1ZQS6xrjXnVyNRaTEKB4czzdl1HWlnw/AdcY2QJMcAGANgLIADzdcMgDyA3ebees3cWzvc+Rr+7hVDDw+v"
    "EHp4lBeESc4D8HcAehB502oBbS6xNSLy+VoJQnFBnuRYAKcBOA7AWwDMATCtxCNCAC8AeBzAQwAeFJE/DZXw7ezRsQA+3889"
    "IoACgJ0AXgKwHsAaAE+IyPahmBvJ0QCuBnCwWXM3LKoA4FMAXq6FQO54PTSAzxrayJt/A4CiMRTcLSLXkAyGwkvshIqNBfAN"
    "AONia2XptQHATSLyq0H0rE4E8B1zpgdtSczXLIBvi8hD/d0b51xdCeDtZs9VtfiV8/w55txmzTPFmYsYQf5zIrK9WnvnKEM5"
    "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"
    "6Loyf/82pzx7WmuDr9Vi7Cn79o4ybTu+Hac56601//8d83uFlP3QJF91yqyrBMXs6hItL2yuUtXo3mkf8t6UNgfVbCfCEs/e"
    "TfLEQdzrA0k+lTJnu39X1no8Jcb5/VjLhCR6vNmZTyV84++dVg86pZ3FH2rRZsOhs6+XOWNPl3nOTNPORZdoFfIb90zVgobM"
    "+uxv2kiwiu0zKoXlsddUmR8IybHm3niW5CVuFEuMtqTERzl7/ukUPmK/bzd3mvjWEx4eEbyH0OMNrwgaC+Qo9Hqf4lZsay21"
    "1UGHzQVivQmIrNO3Iqq2Vkw429aaOw/AvST/FcC15Tw+xoMyH5GV/BTzz2mWaYtPiMi6ahdUMALIm1P2YE/JfiMU1CEq4OP+"
    "XETkbpI3mjmlhbx+hOQvRWRVtZtJJ+C4lH+36/u6AiOxcK3fALgSUcPmpGbSAuBjIvI6b60NOS6xpkCUw1i1ZuG2ZQTJKQC+"
    "lnDe3P26D1GricZ+vpuIKg/GvV7W29GEKJT6IXPGaxUabN97MJKbo7ve4WcGm8c4dHE/gI+XoEcN4CIA/0vyMyZUPe2ZkxCF"
    "lX/cPX8pv/5V40msVaPwoxJ4lIuVhmfEPV6CyOP3AskfAPhCAo1Y7+klJM82+bm1mIdtM/EFRGHHSQ3oBcAWRIW8iuh7JWxB"
    "VJxsGoB34vWeYkujR5IcLSK7BjpXx+v5CfS23rkRwO9IXo8oZ397H847SF6EqJE9kV4P4P5qjN/Dw8PDYx9SCM3X48o0Te4m"
    "+XZ7iQ2zOVir6Ckku1Ks8UywKj9D8j9J/i3JU0keSfIokqeTfD/Jn5im6CzhybFrZD0cX6r2Gjl71Eyyp8QeaZKXO8pj/DnW"
    "s3G406Q6zWvxv/bdtbAgO2O5pYS1v0DycHcN4s8wn98l7I/dj2+W2g+S9U4z6qSG9C9U0yNu84NI/iqFpuyerCM5sQrv+2LK"
    "e6y34xe1PtPO+bwkZSyuZ32GSx+DxD8sLU4hubZM83ZLIxtJXkPycpInkJxrGodfbvjGhjKe3jB+zmrE18c5HrW0df9s2prH"
    "PHPryvCMP5nccqlyfp3dn9NKRIHYf7uqCu+bSfLlBL5k5/0aySMHem6ctc0Zj531TrvvbCd5rbmjDjde9rGGb9WRbDB7PIXk"
    "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"
    "23sAAAAASUVORK5CYII="
)


if __name__ == "__main__":
    main(sys.argv[1:])

