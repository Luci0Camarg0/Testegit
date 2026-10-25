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
VERSAO = 6
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


def scan_faces(images, engine, log=print, progress=lambda done, total: None):
    """Detecta e descreve todos os rostos. Retorna (embeddings, foto de cada rosto, confianca)."""
    embs, photo_ids, scores = [], [], []
    total = len(images)
    for i, path in enumerate(images):
        img = read_image(path)
        if img is None:
            log("Não foi possível abrir: %s" % os.path.basename(path))
            progress(i + 1, total)
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
            kept += 1
        log("%s: %d rosto(s)" % (os.path.basename(path), kept))
        progress(i + 1, total)
    return np.array(embs, np.float32).reshape(-1, 128), np.array(photo_ids, int), np.array(scores)


# ---------------------------------------------------------------------------
# Cadastro de alunos
# ---------------------------------------------------------------------------

def load_roster(roster_dir, engine, log=print):
    """
    Le a pasta de cadastro. Cada foto vira um aluno com o nome do arquivo
    (Maria Silva.jpg), ou cada subpasta vira um aluno com todas as fotos dela
    (Maria Silva/foto1.jpg, foto2.jpg...). Retorna {nome: [embeddings]}.
    """
    entries = []
    for n in sorted(os.listdir(roster_dir), key=natural_key):
        p = os.path.join(roster_dir, n)
        if os.path.isdir(p):
            entries += [(n, f) for f in list_images(p)]
        elif os.path.splitext(n)[1].lower() in IMAGE_EXTS:
            entries.append((os.path.splitext(n)[0].strip(), p))
    roster, missing = {}, []
    for name, path in entries:
        img = read_image(path)
        faces = engine.detect(img) if img is not None else []
        faces = [f for f in faces if f[14] >= SURE_FACE]
        if not len(faces):
            missing.append(os.path.basename(path))
            continue
        # a foto de cadastro deve ter so o aluno: fica o maior rosto
        f = max(faces, key=lambda f: f[2] * f[3])
        roster.setdefault(name, []).append(engine.embed(img, f))
    for m in missing:
        log("Cadastro: nenhum rosto claro em %s (ignorada)" % m)
    if not roster:
        raise RuntimeError("Nenhum rosto encontrado nas fotos do cadastro.")
    log("Cadastro: %d aluno(s)" % len(roster))
    return {k: np.array(v, np.float32) for k, v in roster.items()}, missing


def match_roster(embs, photo_ids, groups, roster):
    """
    Liga cada grupo de rostos (mesma pessoa) ao aluno cadastrado mais
    parecido. A decisao e pela media de todas as fotos do grupo, e nao foto a
    foto: um pai ou irmao parecido pode bater com o aluno numa foto isolada,
    mas nao na media. Grupos que nao parecem com nenhum aluno (pais,
    convidados) ficam de fora. Retorna {nome do aluno: [fotos]}.
    """
    names = list(roster)
    X = np.asarray(embs, np.float32)
    found = {n: set() for n in names}
    for g in groups:
        avg = [float((X[g] @ roster[n].T).max(1).mean()) for n in names]
        j = int(np.argmax(avg))
        if avg[j] >= MATCH_STUDENT:
            found[names[j]].update(int(photo_ids[k]) for k in g)
    return {n: sorted(ph) for n, ph in found.items()}


# ---------------------------------------------------------------------------
# Fichas de identificacao (foto do aluno segurando a ficha com nome e codigo)
# ---------------------------------------------------------------------------

CARD_LABELS = {"nome", "aluno", "aluna", "codigo", "código", "cod", "cód", "id",
               "curso", "turma", "matricula", "matrícula", "n", "no", "nº", "numero", "número"}

CARD_SKIP = {"formatura", "formandos", "colegio", "colégio", "escola", "turma", "curso",
             "universidade", "faculdade", "gala", "eventos", "ficha", "identificacao",
             "identificação"}

_ocr = None


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
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


def folder_name_for(name, code):
    base = re.sub(r"[%s]" % re.escape(INVALID_CHARS), "", name).strip() or "sem_nome"
    return "%s_%s" % (base, code) if code else base


def read_card(img):
    """Le o texto da foto da ficha. Retorna (nome, codigo, linhas lidas)."""
    h, w = img.shape[:2]
    k = min(1.0, 1600.0 / max(h, w))
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img
    res, _ = get_ocr()(small)
    lines = [r[1] for r in (res or []) if r[2] >= 0.5]
    name, code = parse_card(lines)
    return name, code, lines


def scan_cards(card_dir, engine, log=print, progress=lambda done, total: None):
    """
    Para cada foto de ficha: le nome e codigo e guarda o rosto do aluno.
    Retorna lista de dicts {arquivo, nome, codigo, rosto (miniatura BGR) ou None}.
    """
    items = []
    files = list_images(card_dir)
    for i, path in enumerate(files):
        item = {"file": path, "name": "", "code": "", "thumb": None, "lines": []}
        img = read_image(path)
        if img is not None:
            faces = [f for f in engine.detect(img) if f[14] >= SURE_FACE]
            if faces:
                f = max(faces, key=lambda f: f[2] * f[3])
                item["thumb"] = engine.recognizer.alignCrop(img, f)
            try:
                item["name"], item["code"], item["lines"] = read_card(img)
            except Exception as e:  # sem OCR o usuario ainda pode digitar
                log("Não consegui ler a ficha de %s: %s" % (os.path.basename(path), e))
        log("%s: %s" % (os.path.basename(path),
                        folder_name_for(item["name"], item["code"]) if item["name"] or
                        item["code"] else "nome não lido"))
        items.append(item)
        progress(i + 1, len(files))
    return items


def save_roster_from_cards(items, roster_dir):
    """Cria a pasta de cadastro: uma copia de cada foto de ficha com o nome do aluno."""
    os.makedirs(roster_dir, exist_ok=True)
    used = {}
    for it in items:
        base = it["folder"]
        sub = os.path.join(roster_dir, base)
        os.makedirs(sub, exist_ok=True)       # subpasta: o mesmo aluno pode ter varias fichas
        n = used.get(base, 0) + 1
        used[base] = n
        ext = os.path.splitext(it["file"])[1]
        shutil.copy2(it["file"], os.path.join(sub, "ficha_%d%s" % (n, ext)))
    return roster_dir


# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------

def process_folder(src, engine, log=print, progress=lambda done, total: None,
                   out_root=None, roster_dir=None, report=None):
    """
    Processa uma pasta de fotos e cria festa_N. Sem cadastro, agrupa por
    pessoa em aluno_1, aluno_2...; com cadastro, cria uma pasta com o nome de
    cada aluno e ignora quem nao esta cadastrado. Retorna o caminho criado.
    """
    out_root = out_root or data_dir()
    images = list_images(src)
    if not images:
        raise RuntimeError("Nenhuma foto encontrada nessa pasta.")
    roster = load_roster(roster_dir, engine, log)[0] if roster_dir else None

    embs, photo_ids, scores = scan_faces(images, engine, log, progress)
    if not len(embs):
        raise RuntimeError("Nenhum rosto encontrado nas fotos.")

    log("Agrupando %d rostos..." % len(embs))
    groups = cluster_faces(embs, photo_ids)
    # grupo formado so por deteccoes duvidosas = provavelmente nao e um rosto
    groups = [g for g in groups if max(scores[k] for k in g) >= SURE_FACE]
    if not groups:
        raise RuntimeError("Nenhum rosto encontrado nas fotos.")

    if roster:
        log("Procurando os %d aluno(s) cadastrados..." % len(roster))
        found = match_roster(embs, photo_ids, groups, roster)
        people = [(n, ph) for n, ph in found.items() if ph]
        missing = [n for n, ph in found.items() if not ph]
        if report is not None:
            report["roster"] = len(roster)
            report["missing"] = missing
        if missing:
            log("Alunos não encontrados nas fotos: " + ", ".join(missing))
        if not people:
            raise RuntimeError("Nenhum aluno do cadastro foi encontrado nessas fotos.")
    else:
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


def restart_program():
    subprocess.Popen([sys.executable] + ([] if getattr(sys, "frozen", False)
                                         else [os.path.abspath(sys.argv[0])]))


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


def settings_path():
    return os.path.join(os.path.dirname(data_dir()), "config.json")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(cfg):
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def count_roster(roster_dir):
    """Quantos alunos a pasta de cadastro tem (fotos soltas + subpastas)."""
    try:
        return sum(1 for n in os.listdir(roster_dir)
                   if os.path.isdir(os.path.join(roster_dir, n)) or
                   os.path.splitext(n)[1].lower() in IMAGE_EXTS)
    except OSError:
        return 0


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
    back_btn.pack(side="left", padx=(10, 0))
    roster_btn = make_button(top, "Cadastro de alunos", None)
    roster_btn.pack(side="left", padx=(10, 0))
    open_btn = make_button(top, "Abrir no Explorer", None)
    open_btn.pack(side="right")

    cfg = load_settings()
    if cfg.get("roster_dir") and not os.path.isdir(cfg["roster_dir"]):
        cfg.pop("roster_dir")
    roster_bar = tk.Frame(win, bg=BG, padx=12)
    roster_bar.pack(fill="x", pady=(0, 8))
    roster_var = tk.StringVar()
    tk.Label(roster_bar, textvariable=roster_var, bg=BG, fg=FG_DIM,
             font=("Segoe UI", 10), anchor="w").pack(side="left")
    roster_clear = tk.Label(roster_bar, text="remover cadastro", bg=BG, fg=ACCENT_HOVER,
                            font=("Segoe UI", 10, "underline"), cursor="hand2")

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

    # --- cadastro de alunos ------------------------------------------------
    def show_roster():
        rd = cfg.get("roster_dir")
        if rd:
            roster_var.set("Cadastro: pasta \"%s\" com %d aluno(s). Só esses alunos serão "
                           "separados, com o nome de cada um." % (os.path.basename(rd),
                                                                   count_roster(rd)))
            roster_clear.pack(side="left", padx=(10, 0))
        else:
            roster_var.set("Sem cadastro: todas as pessoas serão separadas em "
                           "aluno_1, aluno_2...")
            roster_clear.pack_forget()

    def roster_menu():
        if state["busy"]:
            return
        m = tk.Menu(win, tearoff=0, bg=PANEL, fg=FG, activebackground=ACCENT,
                    activeforeground=FG, bd=0, font=font)
        m.add_command(label="Fotos das fichas (lê nome e código da ficha)",
                      command=import_cards)
        m.add_command(label="Pasta com uma foto de cada aluno, já com o nome",
                      command=choose_roster)
        x, y = roster_btn.winfo_rootx(), roster_btn.winfo_rooty() + roster_btn.winfo_height()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def busy(on):
        state["busy"] = on
        for b in (add_btn, roster_btn):
            b.configure(state="disabled" if on else "normal")
        if on:
            prog["value"] = 0

    def import_cards():
        d = filedialog.askdirectory(title="Pasta com as fotos dos alunos segurando a ficha")
        if not d:
            return
        if not list_images(d):
            messagebox.showerror(APP_NAME, "Essa pasta não tem fotos.", parent=win)
            return
        busy(True)

        def job():
            def log(m):
                msgs.put(("status", m))
            try:
                if state["engine"] is None:
                    log("Carregando modelos de reconhecimento...")
                    state["engine"] = FaceEngine(log)
                log("Carregando leitor de texto...")
                get_ocr()
                items = scan_cards(d, state["engine"], log,
                                   lambda a, t: msgs.put(("prog", a, t)))
                msgs.put(("cards", d, items))
            except Exception as e:
                msgs.put(("error", str(e)))
        threading.Thread(target=job, daemon=True).start()

    def review_cards(card_dir, items):
        """Janela para conferir/corrigir o nome lido de cada ficha antes de salvar."""
        top = tk.Toplevel(win, bg=BG)
        top.title("Conferir fichas")
        top.geometry("760x620")
        top.transient(win)
        top.grab_set()
        tk.Label(top, text="Confira o nome de cada aluno. Clique no nome para corrigir.",
                 bg=BG, fg=FG, font=font_b, padx=12, pady=10, anchor="w").pack(fill="x")
        tk.Label(top, text="Formato: nome_codigo  (ex.: maria eduarda_4821). Desmarque as "
                 "fotos que não devem entrar.", bg=BG, fg=FG_DIM, font=("Segoe UI", 10),
                 padx=12, anchor="w").pack(fill="x")
        body = tk.Frame(top, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        cv = tk.Canvas(body, bg=BG, highlightthickness=0)
        sc = ttk.Scrollbar(body, orient="vertical", command=cv.yview,
                           style="Dark.Vertical.TScrollbar")
        inner = tk.Frame(cv, bg=BG)
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window(0, 0, window=inner, anchor="nw", tags="inner")
        cv.bind("<Configure>", lambda e: cv.itemconfigure("inner", width=e.width))
        cv.configure(yscrollcommand=sc.set)
        cv.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))

        rows, thumbs = [], []
        top.thumbs = thumbs     # mantem as miniaturas vivas enquanto a janela existir
        for it in items:
            r = tk.Frame(inner, bg=PANEL, padx=8, pady=6)
            r.pack(fill="x", pady=3)
            var_on = tk.BooleanVar(value=it["thumb"] is not None)
            tk.Checkbutton(r, variable=var_on, bg=PANEL, activebackground=PANEL,
                           selectcolor=BG, fg=FG).pack(side="left")
            if it["thumb"] is not None:
                rgb = cv2.cvtColor(cv2.resize(it["thumb"], (64, 64)), cv2.COLOR_BGR2RGB)
                ph = ImageTk.PhotoImage(Image.fromarray(rgb))
                thumbs.append(ph)
                tk.Label(r, image=ph, bg=PANEL).pack(side="left", padx=(0, 10))
            else:
                tk.Label(r, text="sem\nrosto", width=8, height=3, bg="#3a1414", fg=FG,
                         font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
            col = tk.Frame(r, bg=PANEL)
            col.pack(side="left", fill="x", expand=True)
            var_name = tk.StringVar(value=folder_name_for(it["name"], it["code"])
                                    if it["name"] or it["code"] else "")
            e = tk.Entry(col, textvariable=var_name, font=font, bg="#2b2b2b", fg=FG,
                         insertbackground=FG, relief="flat", highlightthickness=1,
                         highlightbackground=ACCENT if not var_name.get() else "#333333",
                         highlightcolor=ACCENT)
            e.pack(fill="x", ipady=4)
            info = os.path.basename(it["file"])
            if it["lines"]:
                info += "   •   lido: " + " | ".join(it["lines"])[:90]
            tk.Label(col, text=info, bg=PANEL, fg=FG_DIM, font=("Segoe UI", 9),
                     anchor="w").pack(fill="x")
            rows.append((it, var_on, var_name))

        bar2 = tk.Frame(top, bg=BG, padx=12, pady=10)
        bar2.pack(fill="x")

        def save():
            chosen = []
            for it, on, nm in rows:
                if not on.get():
                    continue
                name = nm.get().strip()
                err = None if name else "Falta o nome de %s." % os.path.basename(it["file"])
                if name and (any(c in name for c in INVALID_CHARS) or name.endswith(".")):
                    err = "O nome \"%s\" tem caracteres que o Windows não aceita." % name
                if err:
                    messagebox.showerror(APP_NAME, err, parent=top)
                    return
                it["folder"] = name
                chosen.append(it)
            if not chosen:
                messagebox.showerror(APP_NAME, "Nenhuma ficha marcada.", parent=top)
                return
            base = os.path.join(os.path.dirname(root_dir), "Cadastros")
            dest = os.path.join(base, next_numbered_name(base, "cadastro"))
            try:
                save_roster_from_cards(chosen, dest)
            except OSError as ex:
                messagebox.showerror(APP_NAME, "Não foi possível salvar: %s" % ex, parent=top)
                return
            cfg["roster_dir"] = dest
            save_settings(cfg)
            show_roster()
            status_var.set("Cadastro salvo com %d aluno(s)." % count_roster(dest))
            close()

        def close():
            cv.unbind_all("<MouseWheel>")
            top.destroy()

        make_button(bar2, "Salvar cadastro", save, primary=True).pack(side="right")
        make_button(bar2, "Cancelar", close).pack(side="right", padx=(0, 10))
        top.protocol("WM_DELETE_WINDOW", close)

    def choose_roster():
        if state["busy"]:
            return
        messagebox.showinfo(APP_NAME, "Escolha a pasta de cadastro.\n\n"
                            "Dentro dela coloque uma foto de cada aluno, com o nome do "
                            "aluno no arquivo (ex.: Maria Silva.jpg). A foto deve mostrar "
                            "só o aluno, de frente.\n\nSe tiver mais de uma foto do mesmo "
                            "aluno, crie uma subpasta com o nome dele e coloque as fotos "
                            "dentro.", parent=win)
        d = filedialog.askdirectory(title="Pasta com uma foto de cada aluno",
                                    initialdir=cfg.get("roster_dir") or None)
        if not d:
            return
        if count_roster(d) == 0:
            messagebox.showerror(APP_NAME, "Essa pasta não tem fotos de alunos.", parent=win)
            return
        cfg["roster_dir"] = d
        save_settings(cfg)
        show_roster()

    def clear_roster(_e=None):
        if state["busy"]:
            return
        cfg.pop("roster_dir", None)
        save_settings(cfg)
        show_roster()

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
                                lambda d, t: msgs.put(("prog", d, t)), root_dir,
                                roster_dir=cfg.get("roster_dir"), report=report)
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
                    status_var.set("Analisando fotos... %d de %d" % (m[1], m[2]))
                elif m[0] == "update":
                    show_update(m[1])
                elif m[0] == "cards":
                    busy(False)
                    status_var.set("Fichas lidas. Confira os nomes.")
                    review_cards(m[1], m[2])
                elif m[0] in ("done", "error"):
                    busy(False)
                    if m[0] == "done":
                        n = len(subdirs(m[1]))
                        rep = m[2]
                        if "roster" in rep:
                            text = ("%s criada: %d de %d aluno(s) encontrados."
                                    % (os.path.basename(m[1]), n, rep["roster"]))
                            if rep["missing"]:
                                text += "\n\nNão apareceram nas fotos:\n" + \
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
    roster_btn.configure(command=roster_menu)
    roster_clear.bind("<Button-1>", clear_roster)
    show_roster()
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
    ev = process_folder(folder, engine,
                        progress=lambda d, t: None)
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
        msg = "ok v%d %s %s" % (VERSAO, name, code)
    except Exception as e:
        msg = "erro %r" % e
    with open(out, "w", encoding="utf-8") as f:
        f.write(msg)


def main(argv):
    if argv and argv[0] == "--autoteste":
        self_test()
    elif argv and os.path.isdir(argv[0]):
        run_cli(argv[0])
    else:
        run_gui()


if __name__ == "__main__":
    main(sys.argv[1:])
