extends Node3D
## Espalha árvores, pinheiros, pedras e arbustos pela ilha, de acordo com o bioma.
## Para ficar leve, objetos iguais são desenhados juntos (MultiMesh), o mapa é
## dividido em blocos, e cada bloco some quando está longe do jogador.

const LowPoly = preload("res://scripts/core/low_poly.gd")
const Bioma = preload("res://scripts/world/terrain_generator.gd").Bioma

@export var tentativas: int = 40000          # quantos pontos sorteados (mais = mais denso)
@export var tamanho_bloco: float = 60.0      # tamanho de cada bloco do mapa, em metros

const COR_TRONCO := Color(0.47, 0.31, 0.19)
const COR_FOLHA := Color(0.36, 0.70, 0.25)
const COR_FOLHA_CLARA := Color(0.52, 0.80, 0.30)
const COR_PINHEIRO := Color(0.17, 0.47, 0.27)
const COR_PEDRA := Color(0.62, 0.60, 0.58)
const COR_ARBUSTO := Color(0.30, 0.62, 0.22)

@onready var terreno = get_node("../Terrain")

# Cada tipo: o modelo, a chance de aparecer em cada bioma, o tamanho,
# a distância em que ainda é desenhado e o formato da colisão.
var tipos := {}
var colisoes: StaticBody3D
var arbustos: Array[Vector3] = []   # onde tem frutinhas para comer (Etapa 4)


func _ready() -> void:
	tipos = {
		"arvore": {
			"modelo": _modelo_arvore(), "escala": Vector2(0.8, 1.3), "distancia": 230.0,
			"colisao": "tronco", "raio": 0.3,
			"chance": {Bioma.FLORESTA: 0.16, Bioma.PLANICIE: 0.015},
		},
		"pinheiro": {
			"modelo": _modelo_pinheiro(), "escala": Vector2(0.8, 1.5), "distancia": 230.0,
			"colisao": "tronco", "raio": 0.25,
			"chance": {Bioma.FLORESTA: 0.10, Bioma.MONTANHA: 0.05},
		},
		"pedra": {
			"modelo": _modelo_pedra(), "escala": Vector2(0.5, 1.8), "distancia": 200.0,
			"colisao": "pedra", "raio": 0.9,
			"chance": {Bioma.PLANICIE: 0.012, Bioma.FLORESTA: 0.01, Bioma.MONTANHA: 0.06, Bioma.PRAIA: 0.015},
		},
		"arbusto": {
			"modelo": _modelo_arbusto(), "escala": Vector2(0.7, 1.3), "distancia": 100.0,
			"colisao": "", "raio": 0.0,
			"chance": {Bioma.PLANICIE: 0.06, Bioma.FLORESTA: 0.08},
		},
	}
	colisoes = StaticBody3D.new()
	colisoes.name = "Colisoes"
	add_child(colisoes)
	espalhar()


func espalhar() -> void:
	var sorteio := RandomNumberGenerator.new()
	sorteio.seed = terreno.semente          # mesma semente = mesmas árvores no mesmo lugar
	var metade: float = terreno.quadrados_por_lado * terreno.tamanho_quadrado * 0.5
	var nascimento: Vector3 = terreno.ponto_inicial()

	# blocos[Vector2i(bx, bz)][nome_do_tipo] = lista de posições (Transform3D)
	var blocos := {}

	for i in tentativas:
		var x := sorteio.randf_range(-metade, metade)
		var z := sorteio.randf_range(-metade, metade)
		if Vector2(x - nascimento.x, z - nascimento.z).length() < 8.0:
			continue   # deixa livre o lugar onde o jogador nasce
		var bioma: Bioma = terreno.obter_bioma(x, z)
		if bioma == Bioma.AGUA:
			continue

		# Escolhe qual tipo nasce aqui (ou nenhum), conforme as chances do bioma
		var nome := _sortear_tipo(bioma, sorteio.randf())
		if nome == "":
			continue
		var altura: float = terreno.obter_altura(x, z)
		var limite := 1.6 if nome == "pedra" else 0.8   # pedras aceitam chão mais torto
		if _muito_inclinado(x, z, altura, limite):
			continue
		if altura > terreno.altura_maxima * 1.3:   # nada cresce na neve
			continue

		var tipo: Dictionary = tipos[nome]
		var escala := sorteio.randf_range(tipo.escala.x, tipo.escala.y)
		var tamanho := Vector3.ONE * escala
		if nome == "pedra":   # pedras achatadas e tortas, cada uma diferente
			tamanho *= Vector3(sorteio.randf_range(0.8, 1.4), sorteio.randf_range(0.5, 1.0), sorteio.randf_range(0.8, 1.3))
		var giro := Basis(Vector3.UP, sorteio.randf() * TAU)
		var posicao := Transform3D(giro.scaled(tamanho), Vector3(x, altura - 0.15, z))

		var chave := Vector2i(floori(x / tamanho_bloco), floori(z / tamanho_bloco))
		if not blocos.has(chave):
			blocos[chave] = {}
		if not blocos[chave].has(nome):
			blocos[chave][nome] = []
		blocos[chave][nome].append(posicao)
		if nome == "arbusto":
			arbustos.append(posicao.origin)

		_criar_colisao(tipo, posicao.origin, escala)

	for chave in blocos:
		for nome in blocos[chave]:
			_desenhar_bloco(chave, nome, blocos[chave][nome])


## Tem um arbusto com frutinhas a até "raio" metros deste ponto?
func arbusto_perto(ponto: Vector3, raio: float) -> bool:
	for arbusto in arbustos:
		if Vector2(arbusto.x - ponto.x, arbusto.z - ponto.z).length() < raio:
			return true
	return false


func _sortear_tipo(bioma: Bioma, valor: float) -> String:
	var soma := 0.0
	for nome in tipos:
		soma += tipos[nome].chance.get(bioma, 0.0)
		if valor < soma:
			return nome
	return ""


func _muito_inclinado(x: float, z: float, altura: float, limite: float) -> bool:
	var dx: float = terreno.obter_altura(x + 1.0, z) - altura
	var dz: float = terreno.obter_altura(x, z + 1.0) - altura
	return absf(dx) > limite or absf(dz) > limite


## Um MultiMesh desenha centenas de cópias do mesmo modelo de uma vez só.
func _desenhar_bloco(chave: Vector2i, nome: String, posicoes: Array) -> void:
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_colors = true
	multimesh.mesh = tipos[nome].modelo
	multimesh.instance_count = posicoes.size()
	for i in posicoes.size():
		multimesh.set_instance_transform(i, posicoes[i])
		# Cada cópia fica um pouquinho mais clara ou escura que a outra
		var tom := 0.85 + float(absi(hash(posicoes[i].origin)) % 30) / 100.0
		multimesh.set_instance_color(i, Color(tom, tom, tom))

	var desenho := MultiMeshInstance3D.new()
	desenho.name = "%s_%d_%d" % [nome, chave.x, chave.y]
	desenho.multimesh = multimesh
	desenho.material_override = LowPoly.material_colorido()
	desenho.visibility_range_end = tipos[nome].distancia   # some quando está longe
	if nome == "arbusto":
		desenho.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(desenho)


func _criar_colisao(tipo: Dictionary, posicao: Vector3, escala: float) -> void:
	if tipo.colisao == "":
		return   # arbustos: o jogador passa por dentro
	var forma := CollisionShape3D.new()
	if tipo.colisao == "tronco":
		var cilindro := CylinderShape3D.new()
		cilindro.radius = tipo.raio * escala
		cilindro.height = 3.0 * escala
		forma.shape = cilindro
		forma.position = posicao + Vector3(0, cilindro.height * 0.5, 0)
	else:
		var esfera := SphereShape3D.new()
		esfera.radius = tipo.raio * escala
		forma.shape = esfera
		forma.position = posicao + Vector3(0, esfera.radius * 0.3, 0)
	colisoes.add_child(forma)


# ---------- Modelos low poly (feitos só com formas simples) ----------

func _modelo_arvore() -> ArrayMesh:
	var tronco := _cilindro(0.18, 0.28, 2.2, 6)
	var copa := _esfera(1.5, 2.4, 7, 4)
	var copa_pequena := _esfera(0.95, 1.5, 6, 3)
	return LowPoly.modelo([
		[tronco, COR_TRONCO, Vector3(0, 1.1, 0)],
		[copa, COR_FOLHA, Vector3(0, 3.0, 0)],
		[copa_pequena, COR_FOLHA_CLARA, Vector3(0.6, 3.7, 0.3)],
	])


func _modelo_pinheiro() -> ArrayMesh:
	return LowPoly.modelo([
		[_cilindro(0.15, 0.22, 1.6, 6), COR_TRONCO, Vector3(0, 0.8, 0)],
		[_cilindro(0.0, 1.5, 2.0, 7), COR_PINHEIRO, Vector3(0, 2.2, 0)],
		[_cilindro(0.0, 1.15, 1.7, 7), COR_PINHEIRO.lightened(0.08), Vector3(0, 3.3, 0)],
		[_cilindro(0.0, 0.8, 1.4, 7), COR_PINHEIRO.lightened(0.16), Vector3(0, 4.3, 0)],
	])


func _modelo_pedra() -> ArrayMesh:
	return LowPoly.modelo([[_esfera(1.0, 1.4, 6, 3), COR_PEDRA, Vector3(0, 0.3, 0)]])


func _modelo_arbusto() -> ArrayMesh:
	return LowPoly.modelo([
		[_esfera(0.7, 1.0, 6, 3), COR_ARBUSTO, Vector3(0, 0.35, 0)],
		[_esfera(0.45, 0.7, 6, 3), COR_ARBUSTO.lightened(0.1), Vector3(0.4, 0.45, 0.2)],
	])


func _cilindro(raio_topo: float, raio_base: float, altura: float, lados: int) -> CylinderMesh:
	var c := CylinderMesh.new()
	c.top_radius = raio_topo
	c.bottom_radius = raio_base
	c.height = altura
	c.radial_segments = lados
	c.rings = 1
	return c


func _esfera(raio: float, altura: float, lados: int, aneis: int) -> SphereMesh:
	var e := SphereMesh.new()
	e.radius = raio
	e.height = altura
	e.radial_segments = lados
	e.rings = aneis
	return e
