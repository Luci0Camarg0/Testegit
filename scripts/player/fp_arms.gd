extends Node3D
## Monta os braços e mãos em primeira pessoa usando formas low poly simples,
## no estilo da imagem de referência: jaqueta militar verde-oliva, luvas sem dedos
## e pele clara. Também faz os braços balançarem ao andar e ao mexer o mouse.

const LowPoly = preload("res://scripts/core/low_poly.gd")
const COR_MANGA := Color(0.36, 0.44, 0.24)    # verde-oliva militar
const COR_PUNHO := Color(0.27, 0.33, 0.18)    # verde mais escuro (punho dobrado)
const COR_LUVA := Color(0.20, 0.18, 0.17)     # luva escura
const COR_PELE := Color(0.95, 0.80, 0.68)     # pele clara

var posicao_base := Vector3.ZERO
var balanco_mouse := Vector2.ZERO
var intensidade_passos := 0.0
var tempo_passos := 0.0


func _ready() -> void:
	add_child(_criar_braco(1.0))    # braço direito
	add_child(_criar_braco(-1.0))   # braço esquerdo
	posicao_base = position


## lado = 1 para a direita, -1 para a esquerda (espelha o braço).
func _criar_braco(lado: float) -> Node3D:
	var braco := Node3D.new()
	braco.name = "BracoDireito" if lado > 0 else "BracoEsquerdo"
	braco.position = Vector3(0.24 * lado, -0.26, -0.18)
	braco.rotation_degrees = Vector3(12, 14 * lado, 0)

	# Manga (cilindro de 6 lados = facetado)
	var manga := CylinderMesh.new()
	manga.top_radius = 0.055
	manga.bottom_radius = 0.07
	manga.height = 0.42
	manga.radial_segments = 6
	manga.rings = 1
	braco.add_child(LowPoly.peca(manga, COR_MANGA, Vector3(0, 0, 0.05), Vector3(-90, 0, 0)))

	# Punho dobrado da manga
	var punho := CylinderMesh.new()
	punho.top_radius = 0.064
	punho.bottom_radius = 0.064
	punho.height = 0.06
	punho.radial_segments = 6
	punho.rings = 1
	braco.add_child(LowPoly.peca(punho, COR_PUNHO, Vector3(0, 0, -0.15), Vector3(-90, 0, 0)))

	# Pulso (pele)
	var pulso := BoxMesh.new()
	pulso.size = Vector3(0.075, 0.06, 0.06)
	braco.add_child(LowPoly.peca(pulso, COR_PELE, Vector3(0, 0, -0.19)))

	# Palma com luva sem dedos
	var palma := BoxMesh.new()
	palma.size = Vector3(0.095, 0.05, 0.09)
	braco.add_child(LowPoly.peca(palma, COR_LUVA, Vector3(0, 0, -0.255)))

	# Dedos (pele, um bloco só, levemente dobrados para baixo)
	var dedos := BoxMesh.new()
	dedos.size = Vector3(0.09, 0.04, 0.07)
	braco.add_child(LowPoly.peca(dedos, COR_PELE, Vector3(0, -0.008, -0.33), Vector3(-15, 0, 0)))

	# Polegar, do lado de dentro da mão
	var polegar := BoxMesh.new()
	polegar.size = Vector3(0.03, 0.035, 0.07)
	braco.add_child(LowPoly.peca(polegar, COR_PELE, Vector3(-0.055 * lado, 0.005, -0.27), Vector3(0, 25 * lado, 0)))

	# Os braços não precisam fazer sombra (mais leve e evita sombras estranhas)
	for parte in braco.get_children():
		parte.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return braco


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		balanco_mouse += event.relative * 0.0004


## Chamado pelo jogador a cada quadro de física.
func definir_movimento(intensidade: float, tempo: float) -> void:
	intensidade_passos = intensidade
	tempo_passos = tempo


func _process(delta: float) -> void:
	# O balanço do mouse volta devagar para zero (sensação de "peso")
	balanco_mouse = balanco_mouse.limit_length(0.04).lerp(Vector2.ZERO, clampf(8.0 * delta, 0, 1))
	var passos := Vector3(
		sin(tempo_passos * 0.5) * 0.02,
		-absf(cos(tempo_passos * 0.5)) * 0.025,
		0) * intensidade_passos
	var alvo := posicao_base + Vector3(-balanco_mouse.x, balanco_mouse.y, 0) + passos
	position = position.lerp(alvo, clampf(12.0 * delta, 0, 1))
