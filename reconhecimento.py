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
import queue
import subprocess
import urllib.request

import numpy as np
import cv2

APP_NAME = "Reconhecimento Facial"

# Atualizacao automatica: a cada mudanca no codigo, aumente VERSAO aqui e em
# versao.json. RUNTIME_NEEDED so aumenta quando o .exe inteiro precisa ser
# baixado de novo (biblioteca ou modelo novo); veja iniciar.py.
VERSAO = 16
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


def assign_by_cards(embs, photo_ids, scores, cards, n_photos):
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
    cards: {foto: (nome, codigo, rosto)}. Retorna {pasta: [fotos]}.
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
    cards, maybe, gala_codes = {}, [], []
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
            name, code, gala, number = read_card_photo(img, boxes[k])
        except Exception as e:
            log("Leitor de fichas falhou: %s" % e)
            break
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
        phs = sorted([sorted({int(photo_ids[k]) for k in g}) for g in groups],
                     key=lambda ph: (-len(ph), ph[0]))
        people = [("aluno_%d" % i, ph) for i, ph in enumerate(phs, 1)]

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
                people.append((NO_ID_FOLDER % n, ph))
                used.add(NO_ID_FOLDER % n)
                log("Sem ficha, separado pelo rosto: %s (%d fotos)" % (NO_ID_FOLDER % n, len(ph)))
            placed = {p for _, ph in people for p in ph}
            rest = [p for p in range(len(images)) if p not in placed]
    if rest:
        people.append((LEFTOVER_FOLDER, rest))

    event = os.path.join(out_root, next_numbered_name(out_root, "festa"))
    os.makedirs(event)
    copied = {}                      # foto de origem -> arquivos criados
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
            dst = os.path.join(d, name)
            shutil.copy2(images[p], dst)
            copied.setdefault(p, []).append(dst)

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

    # --- galeria (fotos de um aluno) -----------------------------------------
    gal = tk.Frame(win, bg=BG, padx=12)
    side = tk.Frame(gal, bg=BG)
    side.pack(side="left", fill="y", padx=(0, 10))
    tk.Label(side, text="Mover para:", bg=BG, fg=FG, font=font_b, anchor="w").pack(fill="x")
    tk.Label(side, text="Arraste as fotos para o aluno\ncerto. Dois cliques abrem.",
             bg=BG, fg=FG_DIM, font=("Segoe UI", 9), justify="left", anchor="w").pack(fill="x")
    targets = tk.Listbox(side, bg=PANEL, fg=FG, font=("Segoe UI", 10), width=30, relief="flat",
                         highlightthickness=1, highlightbackground="#2a2a2a",
                         highlightcolor="#2a2a2a", selectbackground=ACCENT,
                         selectforeground=FG, activestyle="none", exportselection=False)
    targets.pack(fill="both", expand=True, pady=(6, 0))
    gcan = tk.Canvas(gal, bg=BG, highlightthickness=1, highlightbackground="#2a2a2a", bd=0,
                     yscrollincrement=40)
    gsb = ttk.Scrollbar(gal, orient="vertical", command=gcan.yview,
                        style="Dark.Vertical.TScrollbar")
    gcan.configure(yscrollcommand=gsb.set)
    gsb.pack(side="right", fill="y")
    gcan.pack(side="left", fill="both", expand=True)
    TILE_W, TILE_H, GAP = THUMB_PX + 12, THUMB_PX + 34, 10
    g = {"items": [], "sel": set(), "anchor": None, "hover": None, "press": None,
         "drag": None, "drop": None, "targets": [], "undo": [], "mode": "lista"}
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
        logo_src = Image.open(os.path.join(resource_dir(), "assets", "logo.png")).convert("RGBA")
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
            ed.destroy()

    def start_rename(path=None):
        if in_gallery():
            sel = [p for p, k in g["items"] if k == "pasta" and p in g["sel"]]
            if sel:
                rename_dialog(sel[0])
            return
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
        menu.add_command(label="Criar pasta", command=lambda: new_folder(here))
        if i is None:
            menu.add_command(label="Abrir no Explorer", command=lambda: open_in_explorer(here))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def busy(on):
        state["busy"] = on
        add_btn.configure(state="disabled" if on else "normal")
        if on:
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
        cur = state["current"]
        festa = festa_of(cur)
        paths = []
        for a in subdirs(festa):
            pa = os.path.join(festa, a)
            paths.append(pa)
            paths += [os.path.join(pa, b) for b in subdirs(pa)]
        g["targets"] = [p for p in paths if os.path.normcase(p) != os.path.normcase(cur)]
        targets.delete(0, "end")
        for p in g["targets"]:
            rel = os.path.relpath(p, festa).replace(os.sep, " / ")
            targets.insert("end", "%s  (%d)" % (rel, len(photos_in(p))))

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
            k = targets.nearest(yr - targets.winfo_rooty())
            bb = targets.bbox(k)
            if bb and bb[1] <= yr - targets.winfo_rooty() <= bb[1] + bb[3]:
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
        targets.selection_clear(0, "end")
        if k is not None:
            targets.selection_set(k)
            targets.see(k)
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
        targets.selection_clear(0, "end")
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
        k = targets.nearest(e.y)
        if 0 <= k < len(g["targets"]):
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
        if state["busy"] and parent == root_dir:
            return
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
                elif m[0] == "thumb":
                    got_thumb(m[1], m[2])
                elif m[0] in ("done", "error"):
                    busy(False)
                    if m[0] == "done":
                        n = len([d for d in subdirs(m[1])
                                 if os.path.basename(d) != LEFTOVER_FOLDER])
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
                        check = check_text(rep)
                        state["current"] = m[1]
                        state["sel"] = None
                        search_var.set("")
                        refresh()
                        messagebox.showinfo(APP_NAME, text)
                        if check:
                            (messagebox.showinfo if not rep.get("lost") else
                             messagebox.showwarning)("Conferência das fotos", check)
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
    canvas.bind("<Up>", lambda e: move_sel(-1))
    canvas.bind("<Down>", lambda e: move_sel(1))
    canvas.bind("<Return>", lambda e: state["sel"] and enter(state["sel"]))
    canvas.bind("<BackSpace>", lambda e: go_back())
    win.bind("<F2>", lambda e: start_rename())
    search.bind("<Down>", lambda e: (canvas.focus_set(), move_sel(1)))
    search_var.trace_add("write", refresh)

    refresh()
    poll()
    if test:
        api = {"win": win, "enter": enter, "go_back": go_back, "g": g, "thumbs": thumbs,
               "open_viewer": open_viewer, "do_move": do_move, "undo": undo_move,
               "photo_items": photo_items, "state": state, "errors": test_errors,
               "create": new_folder}
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
    for a in ("aluno_a", "aluno_b"):
        os.makedirs(os.path.join(festa, a))
        for i in range(4):
            img = np.full((900, 600, 3), (40 * i, 120, 200), np.uint8)
            cv2.circle(img, (300, 300), 120, (220, 200, 180), -1)
            cv2.imwrite(os.path.join(festa, a, "foto_%d.jpg" % i), img)
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
            api["go_back"]()
            api["go_back"]()

        def s4():
            errs = api["errors"]
            result["msg"] = ("ok janela v%d" % VERSAO) if not errs else \
                "erro: " + " | ".join(errs)
            win.destroy()
        steps = [s1, s2, s3, s4]

        def run(i=0):
            try:
                steps[i]()
            except Exception as e:
                log_error(traceback.format_exc())
                api["errors"].append("%s: %s" % (type(e).__name__, e))
                if i < len(steps) - 1:
                    i = len(steps) - 2
            if i + 1 < len(steps):
                win.after(4000 if i == 0 else 1500, lambda: run(i + 1))
        run()

    try:
        run_gui(test=script)
    except Exception:
        result["msg"] = "erro: " + traceback.format_exc()
    shutil.rmtree(festa, ignore_errors=True)
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


if __name__ == "__main__":
    main(sys.argv[1:])
