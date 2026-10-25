extends StaticBody3D
## Gera um terreno low poly (uma ilha) usando "ruído": uma função matemática
## que cria morros e vales de aparência natural. A mesma semente (seed)
## sempre gera o mesmo mapa.
## Etapa 2: biomas (praia, planície, floresta, montanha) e rios.

const LowPoly = preload("res://scripts/core/low_poly.gd")
enum Bioma { AGUA, PRAIA, PLANICIE, FLORESTA, MONTANHA }

@export var semente: int = 1234
@export var quadrados_por_lado: int = 192   # mais = mapa maior (e mais pesado)
@export var tamanho_quadrado: float = 2.5   # em metros. Maior = mais "low poly"
@export var altura_maxima: float = 22.0
@export var nivel_agua: float = 0.0

# Cores vivas do terreno (mude à vontade!)
const COR_AREIA := Color(0.96, 0.86, 0.55)
const COR_GRAMA_PLANICIE := Color(0.58, 0.76, 0.30)   # verde-amarelado, campo aberto
const COR_GRAMA_FLORESTA := Color(0.26, 0.55, 0.23)   # verde escuro, sombra das árvores
const COR_PEDRA := Color(0.58, 0.53, 0.50)
const COR_NEVE := Color(0.96, 0.97, 1.0)
const COR_AGUA := Color(0.20, 0.60, 0.95, 0.75)

var ruido := FastNoiseLite.new()           # morros
var ruido_montanha := FastNoiseLite.new()  # onde ficam as regiões de montanha
var ruido_crista := FastNoiseLite.new()    # formato das cristas das montanhas
var ruido_umidade := FastNoiseLite.new()   # úmido = floresta, seco = planície
var ruido_rio := FastNoiseLite.new()       # caminho dos rios


func _ready() -> void:
	_preparar_ruidos()
	gerar()


func _preparar_ruidos() -> void:
	# Cada ruído usa uma semente diferente (derivada da principal)
	var lista := [ruido, ruido_montanha, ruido_crista, ruido_umidade, ruido_rio]
	var frequencias := [0.006, 0.0035, 0.012, 0.005, 0.0028]
	for i in lista.size():
		lista[i].seed = semente + i * 1000
		lista[i].noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
		lista[i].frequency = frequencias[i]
	ruido.fractal_octaves = 4
	ruido_crista.fractal_octaves = 3
	ruido_rio.fractal_octaves = 2


## Devolve a altura do chão em qualquer ponto (x, z). Usado também para
## posicionar o jogador, as árvores e (nas próximas etapas) os animais.
func obter_altura(x: float, z: float) -> float:
	# 1. Morros suaves
	var altura := (ruido.get_noise_2d(x, z) + 0.5) * altura_maxima * 0.5

	# 2. Montanhas: só nas regiões onde o "ruído de montanha" é alto
	var regiao := regiao_montanha(x, z)
	var crista := 1.0 - absf(ruido_crista.get_noise_2d(x, z))   # 1 no topo da crista
	altura += regiao * crista * crista * altura_maxima * 1.6

	# 3. Rios: onde o ruído do rio passa perto de zero, cava um vale até abaixo da água.
	#    Perto do rio o vale é suave (margens), no meio fica fundo (água).
	var vale := 1.0 - smoothstep(0.025, 0.11, absf(ruido_rio.get_noise_2d(x, z)))
	vale *= 1.0 - regiao     # rios não cortam as montanhas altas
	altura = lerpf(altura, nivel_agua - 1.5, vale)

	# 4. Afunda as bordas do mapa no mar, formando uma ilha com praia.
	var metade := quadrados_por_lado * tamanho_quadrado * 0.5
	var distancia := Vector2(x, z).length() / metade   # 0 no centro, 1 na borda
	var queda := smoothstep(0.65, 0.95, distancia)
	return lerpf(altura, nivel_agua - 10.0, queda)


## 0 = fora das montanhas, 1 = no meio de uma cordilheira.
func regiao_montanha(x: float, z: float) -> float:
	return smoothstep(0.1, 0.45, ruido_montanha.get_noise_2d(x, z))


## Diz qual é o bioma de um ponto. As árvores e os animais usam isso.
func obter_bioma(x: float, z: float) -> Bioma:
	var altura := obter_altura(x, z)
	if altura < nivel_agua + 0.3:
		return Bioma.AGUA
	if altura < nivel_agua + 1.5:
		return Bioma.PRAIA
	if regiao_montanha(x, z) > 0.5 or altura > altura_maxima * 0.9:
		return Bioma.MONTANHA
	if ruido_umidade.get_noise_2d(x, z) > -0.05:
		return Bioma.FLORESTA
	return Bioma.PLANICIE


## Procura um lugar plano na planície ou na floresta, perto do centro,
## andando em espiral. É onde o jogador nasce (as árvores evitam esse ponto).
func ponto_inicial() -> Vector3:
	for tentativa in 400:
		var angulo := tentativa * 0.5
		var raio := tentativa * 0.5
		var x := cos(angulo) * raio
		var z := sin(angulo) * raio
		var bioma := obter_bioma(x, z)
		if bioma != Bioma.PLANICIE and bioma != Bioma.FLORESTA:
			continue
		var altura := obter_altura(x, z)
		if absf(obter_altura(x + 2.0, z) - altura) > 0.6 or absf(obter_altura(x, z + 2.0) - altura) > 0.6:
			continue
		return Vector3(x, altura + 1.0, z)
	return Vector3(0, 40, 0)   # não achou: cai do céu no centro


func gerar() -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	var metade := quadrados_por_lado * tamanho_quadrado * 0.5
	for iz in quadrados_por_lado:
		for ix in quadrados_por_lado:
			var x0 := ix * tamanho_quadrado - metade
			var z0 := iz * tamanho_quadrado - metade
			var x1 := x0 + tamanho_quadrado
			var z1 := z0 + tamanho_quadrado
			# Os 4 cantos deste quadrado do chão
			var a := Vector3(x0, obter_altura(x0, z0), z0)
			var b := Vector3(x1, obter_altura(x1, z0), z0)
			var c := Vector3(x0, obter_altura(x0, z1), z1)
			var d := Vector3(x1, obter_altura(x1, z1), z1)
			# Cada quadrado vira 2 triângulos, cada um com sua cor
			LowPoly.adicionar_triangulo(st, a, b, c, _cor_do_triangulo(a, b, c))
			LowPoly.adicionar_triangulo(st, b, d, c, _cor_do_triangulo(b, d, c))

	var malha := st.commit()

	var visual := MeshInstance3D.new()
	visual.name = "Visual"
	visual.mesh = malha
	visual.material_override = LowPoly.material_colorido()
	add_child(visual)

	# Colisão: o formato exato do chão, para o jogador não atravessar.
	var colisao := CollisionShape3D.new()
	colisao.name = "Colisao"
	colisao.shape = malha.create_trimesh_shape()
	add_child(colisao)

	_criar_agua(3000.0)   # bem maior que a ilha: vira o mar até o horizonte


func _cor_do_triangulo(a: Vector3, b: Vector3, c: Vector3) -> Color:
	var centro := (a + b + c) / 3.0
	var normal := (c - a).cross(b - a).normalized()
	var inclinacao := 1.0 - normal.y      # 0 = plano, quanto maior mais íngreme

	var cor: Color
	if centro.y < nivel_agua + 1.2:
		cor = COR_AREIA
	elif centro.y > altura_maxima * 1.3:
		cor = COR_NEVE
	elif inclinacao > 0.28 or centro.y > altura_maxima * 0.9:
		cor = COR_PEDRA
	else:
		# Mistura suave entre a grama seca (planície) e a escura (floresta)
		var umidade := ruido_umidade.get_noise_2d(centro.x, centro.z)
		cor = COR_GRAMA_PLANICIE.lerp(COR_GRAMA_FLORESTA, smoothstep(-0.2, 0.1, umidade))

	# Pequena variação aleatória por triângulo: realça o visual facetado
	var variacao := (absi(hash(Vector2i(int(a.x * 10.0), int(a.z * 10.0 + c.x)))) % 100) / 100.0
	return cor.lightened(variacao * 0.06)


func _criar_agua(tamanho: float) -> void:
	var plano := PlaneMesh.new()
	plano.size = Vector2(tamanho, tamanho)
	var material := StandardMaterial3D.new()
	material.albedo_color = COR_AGUA
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.roughness = 0.2

	var agua := MeshInstance3D.new()
	agua.name = "Agua"
	agua.mesh = plano
	agua.material_override = material
	agua.position.y = nivel_agua
	agua.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(agua)
