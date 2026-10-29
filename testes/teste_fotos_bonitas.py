"""Testes da escolha das fotos bonitas (rodam sem fotos e sem modelos).

    python testes/teste_fotos_bonitas.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import reconhecimento as R   # noqa: E402

OK = dict(blinkL=0.05, blinkR=0.05, earL=0.32, earR=0.32, inL=0.1, inR=0.1, outL=0.1,
          outR=0.1, squintL=0.2, squintR=0.2, jaw=0.01, mouth=0.05, smileL=0.1,
          smileR=0.1, turn=0.0)


def face(**kw):
    q = dict(OK)
    q.update(kw)
    return q


CLOSED = face(blinkL=0.6, blinkR=0.6, earL=0.10, earR=0.10)
AWAY = face(outL=0.96, inR=0.96, turn=0.1)      # como a foto 2T1A9461 da pasta Manha
OPEN_MOUTH = face(jaw=0.6, mouth=0.5)


def mini(seed):
    m = np.random.RandomState(seed).rand(768).astype(np.float32)
    m -= m.mean()
    return m / np.linalg.norm(m)


def run(looks, people, owner, minis=None, cards=()):
    photo_ids = list(range(len(looks)))      # um rosto por foto
    return R.pick_good_photos(people, owner, photo_ids, looks, minis or {}, set(cards))


def test_problemas_do_rosto():
    assert R.look_problem(face()) == ""
    assert R.look_problem(CLOSED) == "olho fechado"
    assert R.look_problem(AWAY) == "olhando para o lado"
    assert R.look_problem(None) == ""            # rosto pequeno: nao julga
    # valores medidos em fotos reais das pastas de teste
    # 2T1A0043 (2 Ano A): sorriso de olho apertado, olho aberto -> fica
    assert R.look_problem(face(blinkL=0.34, blinkR=0.39, squintL=0.50, squintR=0.43)) == ""
    # 2T1A9462 (Manha): olhos fechados -> descarta
    assert R.look_problem(face(blinkL=0.49, blinkR=0.43, squintL=0.24, squintR=0.33)) == \
        "olho fechado"
    # 2T1A9541 (Manha): cabeca inclinada olhando para a camera -> fica
    assert R.look_problem(face(outL=0.1, inR=0.1, turn=0.09)) == ""
    # 2T1A9407 (Manha): cabeca virada, olhos voltados para a camera -> fica
    assert R.look_problem(face(outL=0.66, inR=0.66, inL=0.05, outR=0.05, turn=-0.22)) == ""
    # 2T1A9581 (Manha): olhando para o lado na foto da turma -> descarta
    assert R.look_problem(face(inL=0.73, outR=0.73, outL=0.05, inR=0.05, turn=-0.23)) == \
        "olhando para o lado"
    # pela iris (Manha): 2T1A9561 do Bento olhando para o lado -> descarta
    assert R.look_problem(face(outL=0.01, inL=0.36, outR=0.35, inR=0.02, turn=-0.09,
                               iris=-0.21)) == "olhando para o lado"
    # 2T1A9533 do Theo: cabeca virada, olhos na camera -> fica
    assert R.look_problem(face(iris=0.32, turn=-0.70, outL=0.96, inR=0.96, inL=0.0, outR=0.0)) == ""
    # 2T1A9436 da Alice: olhando para a camera -> fica
    assert R.look_problem(face(iris=0.14, turn=0.02)) == ""


def test_descarta_so_dentro_do_aluno():
    looks = [face(), CLOSED, face(), AWAY]
    people = [("maria_0101", [0, 1, 2, 3])]
    owner = {0: "maria_0101", 1: "maria_0101", 2: "maria_0101", 3: "maria_0101"}
    out = run(looks, people, owner)
    assert out == {"maria_0101": {1, 3}}, out


def test_sem_aluno_nunca_e_mexido():
    looks = [CLOSED, CLOSED]
    out = run(looks, [(R.LEFTOVER_FOLDER, [0, 1])], {})
    assert out == {}, out


def test_olha_o_rosto_do_proprio_aluno():
    # foto 0 tem dois rostos: o do joao (olho fechado) e o da ana (bem)
    looks = [CLOSED, face(), face()]
    photo_ids = [0, 0, 1]
    people = [("ana_1", [0, 1]), ("joao_2", [0])]
    owner = {0: "joao_2", 1: "ana_1", 2: "ana_1"}
    out = R.pick_good_photos(people, owner, photo_ids, looks, {}, set())
    assert out == {}, out      # ana fica com a foto; joao so tem ela (nao fica vazio)
    people = [("ana_1", [0, 1]), ("joao_2", [0, 1])]
    owner = {0: "joao_2", 1: "ana_1", 2: "joao_2"}
    out = R.pick_good_photos(people, owner, photo_ids, looks, {}, set())
    assert out == {"joao_2": {0}}, out


def test_ficha_nunca_e_descartada():
    looks = [CLOSED, face()]
    out = run(looks, [("aluno_2421", [0, 1])], {0: "aluno_2421", 1: "aluno_2421"}, cards=[0])
    assert out == {}, out


def test_pasta_nao_fica_vazia():
    looks = [CLOSED, face(blinkL=0.9, blinkR=0.9, earL=0.05, earR=0.05)]
    out = run(looks, [("aluno_1", [0, 1])], {0: "aluno_1", 1: "aluno_1"})
    assert out == {"aluno_1": {1}}, out          # fica a menos ruim


def test_boca_aberta_so_com_foto_igual():
    looks = [OPEN_MOUTH, face(), OPEN_MOUTH]
    m = mini(1)
    minis = {0: m, 1: m * 0.999 + mini(2) * 0.001, 2: mini(3)}
    for k in minis:
        minis[k] = minis[k] / np.linalg.norm(minis[k])
    owner = {0: "aluno_1", 1: "aluno_1", 2: "aluno_1"}
    out = run(looks, [("aluno_1", [0, 1, 2])], owner, minis)
    # 0 tem uma igual (1) de boca fechada: descarta; 2 nao tem: fica
    assert out == {"aluno_1": {0}}, out


def test_boca_aberta_longe_na_sequencia_fica():
    looks = [OPEN_MOUTH, face(), face(), face(), face(), face()]
    m = mini(1)
    minis = {i: m for i in range(6)}
    owner = {i: "aluno_1" for i in range(6)}
    out = run(looks, [("aluno_1", [0, 5])], owner, minis)
    assert out == {}, out


def test_olho_baixo_comparado_com_o_proprio_aluno():
    # como o Gerson (festa_2): olho normal 0.40; na 2T1A9842 olhando para baixo, 0.285
    looks = [face(earL=0.40, earR=0.41), face(earL=0.41, earR=0.40), face(earL=0.39, earR=0.40),
             face(earL=0.285, earR=0.285), face(earL=0.42, earR=0.41)]
    owner = {i: "gerson_2395" for i in range(5)}
    out = run(looks, [("gerson_2395", list(range(5)))], owner)
    assert out == {"gerson_2395": {3}}, out
    # sorrindo o olho fecha um pouco: fica
    looks[3] = face(earL=0.285, earR=0.285, smileL=0.8, smileR=0.8)
    assert run(looks, [("gerson_2395", list(range(5)))], owner) == {}
    # aluno de olho puxado em todas as fotos: nada sai
    looks = [face(earL=0.2, earR=0.2) for _ in range(5)]
    assert run(looks, [("aluno_1", list(range(5)))], owner_all("aluno_1", 5)) == {}


def owner_all(name, n):
    return {i: name for i in range(n)}


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            n += 1
            print("ok", name)
    print("%d testes ok" % n)
