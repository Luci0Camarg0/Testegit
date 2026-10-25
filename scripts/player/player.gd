extends CharacterBody3D
## Controle do jogador em primeira pessoa:
## andar (WASD), correr (Shift), pular (Espaço) e olhar com o mouse.

@export var velocidade_andar: float = 5.0
@export var velocidade_correr: float = 8.5
@export var forca_pulo: float = 7.0
@export var multiplicador_gravidade: float = 2.0   # maior = pulo mais rápido e "pesado"
@export var multiplicador_queda: float = 1.4       # cai mais rápido do que sobe (pulo mais firme)
@export var aceleracao: float = 10.0
@export var sensibilidade_mouse: float = 0.0025   # depois virá do menu Configurações

var gravidade: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var ponto_de_renascer := Vector3.ZERO
var tempo_balanco := 0.0

@onready var cabeca: Node3D = $Head
@onready var camera: Camera3D = $Head/Camera3D
@onready var bracos: Node3D = $Head/Camera3D/Arms


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED   # esconde e "prende" o mouse


func _unhandled_input(event: InputEvent) -> void:
	# Olhar ao redor com o mouse
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * sensibilidade_mouse)          # corpo gira para os lados
		cabeca.rotate_x(-event.relative.y * sensibilidade_mouse)   # cabeça olha para cima/baixo
		cabeca.rotation.x = clampf(cabeca.rotation.x, deg_to_rad(-89), deg_to_rad(89))

	# ESC solta o mouse; clicar na janela prende de novo
	if event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _physics_process(delta: float) -> void:
	# 1. Gravidade (mais forte na descida, para o pulo não parecer "flutuante")
	if not is_on_floor():
		var forca := gravidade * multiplicador_gravidade
		if velocity.y < 0:
			forca *= multiplicador_queda
		velocity.y -= forca * delta

	# 2. Pulo
	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = forca_pulo

	# 3. Direção que o jogador quer andar (relativa para onde ele está olhando)
	var entrada := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direcao := (transform.basis * Vector3(entrada.x, 0, entrada.y)).normalized()
	var correndo := Input.is_action_pressed("sprint") and entrada.y < 0   # só corre para frente
	var velocidade_alvo := velocidade_correr if correndo else velocidade_andar

	# 4. Acelera e freia suavemente (no ar o controle é menor)
	var controle := aceleracao if is_on_floor() else aceleracao * 0.3
	velocity.x = lerpf(velocity.x, direcao.x * velocidade_alvo, clampf(controle * delta, 0, 1))
	velocity.z = lerpf(velocity.z, direcao.z * velocidade_alvo, clampf(controle * delta, 0, 1))

	move_and_slide()

	_balancar_camera(delta)

	# Caiu para fora do mapa? Volta ao ponto inicial.
	if global_position.y < -30.0:
		renascer()


## "Head bob": a câmera sobe e desce levemente ao andar, como passos.
func _balancar_camera(delta: float) -> void:
	var velocidade_chao := Vector2(velocity.x, velocity.z).length()
	var movendo := is_on_floor() and velocidade_chao > 0.5
	if movendo:
		tempo_balanco += delta * velocidade_chao * 1.8
	var intensidade := clampf(velocidade_chao / velocidade_correr, 0, 1) if movendo else 0.0
	var alvo := Vector3(cos(tempo_balanco * 0.5) * 0.04, sin(tempo_balanco) * 0.05, 0) * intensidade
	camera.position = camera.position.lerp(alvo, clampf(10.0 * delta, 0, 1))
	bracos.definir_movimento(intensidade, tempo_balanco)


func renascer() -> void:
	global_position = ponto_de_renascer
	velocity = Vector3.ZERO
