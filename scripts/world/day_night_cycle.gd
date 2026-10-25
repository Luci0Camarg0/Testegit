extends Node3D
## Etapa 3: ciclo de dia e noite.
## Gira o sol e a lua, muda as cores do céu, da luz e da neblina suavemente,
## mostra um relógio na tela e avisa quando amanhece e anoitece.

signal amanheceu      # as próximas etapas usam isso (animais de dia, criaturas à noite)
signal anoiteceu

@export var duracao_dia_minutos: float = 20.0   # quanto dura um dia inteiro (24 h no jogo)
@export var hora: float = 8.0                   # hora atual (0 a 24). Começa de manhã.
@export var velocidade_acelerada: float = 60.0  # segurando T, o tempo passa 60x mais rápido

var dia: int = 1
var era_noite := false

# Cores do céu: dia, pôr do sol e noite
const TOPO_DIA := Color(0.30, 0.58, 0.95)
const HORIZONTE_DIA := Color(0.72, 0.87, 1.0)
const TOPO_NOITE := Color(0.02, 0.03, 0.09)
const HORIZONTE_NOITE := Color(0.07, 0.10, 0.20)
const HORIZONTE_POR_DO_SOL := Color(1.0, 0.55, 0.30)
const LUZ_DIA := Color(1.0, 0.96, 0.88)
const LUZ_POR_DO_SOL := Color(1.0, 0.60, 0.35)

var sol: DirectionalLight3D
var lua: DirectionalLight3D
var ambiente: Environment
var material_ceu: ShaderMaterial
var relogio: Label


func _ready() -> void:
	_criar_ceu()
	_criar_luzes()
	_criar_relogio()
	era_noite = e_noite()
	_atualizar_visual()


func _process(delta: float) -> void:
	var velocidade := 1.0
	if InputMap.has_action("acelerar_tempo") and Input.is_action_pressed("acelerar_tempo"):
		velocidade = velocidade_acelerada
	# 24 horas do jogo passam em "duracao_dia_minutos" minutos reais
	hora += delta * velocidade * 24.0 / (duracao_dia_minutos * 60.0)
	if hora >= 24.0:
		hora -= 24.0
		dia += 1

	# Avisa quando muda de dia para noite (ou o contrário)
	var agora_noite := e_noite()
	if agora_noite != era_noite:
		era_noite = agora_noite
		if agora_noite:
			anoiteceu.emit()
		else:
			amanheceu.emit()

	_atualizar_visual()


func e_noite() -> bool:
	return hora < 5.5 or hora >= 19.0


func _atualizar_visual() -> void:
	# O sol dá uma volta completa em 24 h: nasce às 6 h, fica no alto ao meio-dia, se põe às 18 h.
	var angulo := (hora - 6.0) / 24.0 * TAU
	sol.rotation = Vector3(-angulo, deg_to_rad(-35), 0)
	lua.rotation = Vector3(-angulo + PI, deg_to_rad(-35), 0)

	var direcao_sol := sol.global_transform.basis.z    # aponta do chão para o sol
	var altura_sol := direcao_sol.y                    # 1 = meio-dia, 0 = horizonte, -1 = meia-noite

	var claridade := smoothstep(-0.15, 0.25, altura_sol)                  # 0 = noite, 1 = dia
	var por_do_sol := 1.0 - smoothstep(0.0, 0.3, absf(altura_sol - 0.02))  # 1 perto do horizonte

	var topo := TOPO_NOITE.lerp(TOPO_DIA, claridade)
	var horizonte := HORIZONTE_NOITE.lerp(HORIZONTE_DIA, claridade).lerp(HORIZONTE_POR_DO_SOL, por_do_sol * 0.7)

	material_ceu.set_shader_parameter("cor_topo", topo)
	material_ceu.set_shader_parameter("cor_horizonte", horizonte)
	material_ceu.set_shader_parameter("direcao_sol", direcao_sol)
	material_ceu.set_shader_parameter("direcao_lua", lua.global_transform.basis.z)
	material_ceu.set_shader_parameter("estrelas", 1.0 - smoothstep(-0.3, 0.0, altura_sol))

	# Sol: forte de dia, alaranjado no fim da tarde, apagado à noite
	sol.light_energy = 0.32 * smoothstep(-0.05, 0.2, altura_sol)
	sol.light_color = LUZ_DIA.lerp(LUZ_POR_DO_SOL, por_do_sol)
	sol.visible = sol.light_energy > 0.001            # luz apagada não gasta nada

	# Lua: luz fraca e azulada, sem sombra (mais leve)
	lua.light_energy = 0.07 * (1.0 - smoothstep(-0.2, 0.0, altura_sol))
	lua.visible = lua.light_energy > 0.001

	ambiente.ambient_light_color = Color(0.25, 0.32, 0.55).lerp(Color(0.62, 0.70, 0.85), claridade)
	ambiente.ambient_light_energy = lerpf(0.22, 0.3, claridade)
	ambiente.fog_light_color = horizonte

	relogio.text = "Dia %d   %02d:%02d" % [dia, int(hora), int(fmod(hora, 1.0) * 60.0)]


func _criar_ceu() -> void:
	material_ceu = ShaderMaterial.new()
	material_ceu.shader = load("res://assets/materials/ceu.gdshader")
	var ceu := Sky.new()
	ceu.sky_material = material_ceu

	ambiente = Environment.new()
	ambiente.background_mode = Environment.BG_SKY
	ambiente.sky = ceu
	ambiente.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	ambiente.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	# Neblina: esconde o fim do mapa e deixa o visual mais suave
	ambiente.fog_enabled = true
	ambiente.fog_density = 0.003
	ambiente.fog_sky_affect = 0.0

	var mundo := WorldEnvironment.new()
	mundo.name = "Ambiente"
	mundo.environment = ambiente
	add_child(mundo)


func _criar_luzes() -> void:
	sol = DirectionalLight3D.new()
	sol.name = "Sol"
	sol.shadow_enabled = true
	sol.directional_shadow_max_distance = 60.0   # sombras só perto: bem mais leve
	add_child(sol)

	lua = DirectionalLight3D.new()
	lua.name = "Lua"
	lua.light_color = Color(0.65, 0.75, 1.0)
	lua.shadow_enabled = false
	add_child(lua)


func _criar_relogio() -> void:
	var camada := CanvasLayer.new()
	relogio = Label.new()
	relogio.add_theme_font_size_override("font_size", 22)
	relogio.add_theme_color_override("font_color", Color.WHITE)
	relogio.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	relogio.add_theme_constant_override("outline_size", 6)
	relogio.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	relogio.position = Vector2(-190, 16)
	camada.add_child(relogio)
	add_child(camada)
