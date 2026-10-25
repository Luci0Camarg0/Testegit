extends Node
## Etapa 4: vida, fome e sede do jogador.
## Fome e sede caem com o tempo (mais rápido correndo). Sem comida ou água,
## a vida cai. Bem alimentado, a vida volta aos poucos.
## Tecla E: beber água (perto do rio ou do mar) e comer frutinhas (perto de um arbusto).

signal morreu
signal renasceu
signal aviso(texto: String)   # mensagens rápidas na tela, ex.: "+25 sede"

const MAXIMO := 100.0

@export var minutos_para_ficar_com_fome: float = 25.0   # de cheio a vazio
@export var minutos_para_ficar_com_sede: float = 15.0
@export var dano_por_segundo_sem_comida: float = 0.5
@export var cura_por_segundo: float = 0.5
@export var distancia_para_interagir: float = 2.5

var vida := MAXIMO
var fome := MAXIMO      # 100 = satisfeito, 0 = morrendo de fome
var sede := MAXIMO
var morto := false

@onready var jogador: CharacterBody3D = get_parent()


func _process(delta: float) -> void:
	if morto:
		return
	var gasto := 2.0 if jogador.esta_correndo() else 1.0   # correr cansa mais
	fome = maxf(fome - delta * gasto * MAXIMO / (minutos_para_ficar_com_fome * 60.0), 0.0)
	sede = maxf(sede - delta * gasto * MAXIMO / (minutos_para_ficar_com_sede * 60.0), 0.0)

	if fome <= 0.0 or sede <= 0.0:
		receber_dano(dano_por_segundo_sem_comida * delta)
	elif fome > 50.0 and sede > 50.0:
		vida = minf(vida + cura_por_segundo * delta, MAXIMO)


func _unhandled_input(event: InputEvent) -> void:
	if morto:
		if event.is_action_pressed("renascer"):
			renascer()
		return
	if event.is_action_pressed("interagir"):
		match o_que_tem_perto():
			"agua":
				sede = minf(sede + 25.0, MAXIMO)
				aviso.emit("Você bebeu água  (+25 sede)")
			"frutinhas":
				fome = minf(fome + 15.0, MAXIMO)
				aviso.emit("Você comeu frutinhas  (+15 fome)")


## Diz o que dá para usar com a tecla E agora: "agua", "frutinhas" ou "".
func o_que_tem_perto() -> String:
	var cena := jogador.get_parent()   # a cena principal (Main)
	var terreno = cena.get_node_or_null("Terrain")
	var vegetacao = cena.get_node_or_null("Vegetation")
	var pe := jogador.global_position
	if terreno:
		# Olha o chão em 8 direções em volta do jogador: algum ponto está debaixo d'água?
		for i in 8:
			var direcao := Vector2.from_angle(i * TAU / 8.0) * 1.8
			if terreno.obter_altura(pe.x + direcao.x, pe.z + direcao.y) < terreno.nivel_agua \
					and pe.y < terreno.nivel_agua + 2.0:
				return "agua"
	if vegetacao and vegetacao.arbusto_perto(pe, distancia_para_interagir):
		return "frutinhas"
	return ""


func receber_dano(quantidade: float) -> void:
	if morto:
		return
	vida = maxf(vida - quantidade, 0.0)
	if vida <= 0.0:
		morto = true
		morreu.emit()


func renascer() -> void:
	vida = MAXIMO
	fome = 60.0
	sede = 60.0
	morto = false
	jogador.renascer()
	renasceu.emit()
