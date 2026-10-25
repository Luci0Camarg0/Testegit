extends Node3D
## Cena principal: prepara os controles, cria a mira na tela
## e coloca o jogador em cima do terreno.
## (O céu, o sol e a lua ficam no nó DiaNoite, desde a Etapa 3.)

const Controles = preload("res://scripts/core/controles.gd")

@onready var terreno = $Terrain
@onready var jogador = $Player


func _ready() -> void:
	Controles.registrar()
	_criar_mira()
	_posicionar_jogador()


func _criar_mira() -> void:
	var camada := CanvasLayer.new()
	var ponto := ColorRect.new()
	ponto.color = Color(1, 1, 1, 0.8)
	ponto.size = Vector2(4, 4)
	ponto.set_anchors_preset(Control.PRESET_CENTER)
	ponto.position -= ponto.size / 2.0
	ponto.mouse_filter = Control.MOUSE_FILTER_IGNORE
	camada.add_child(ponto)
	add_child(camada)


func _posicionar_jogador() -> void:
	var posicao: Vector3 = terreno.ponto_inicial()
	jogador.global_position = posicao
	jogador.ponto_de_renascer = posicao
