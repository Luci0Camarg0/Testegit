extends CanvasLayer
## Etapa 4: a interface na tela. Barras grandes de vida, fome e sede,
## a dica da tecla E, mensagens rápidas e a tela de "Você morreu".

@export var caminho_status: NodePath = ^"../Status"

var status
var barras := {}
var dica: Label
var mensagem: Label
var tempo_mensagem := 0.0
var tela_morte: ColorRect


func _ready() -> void:
	status = get_node(caminho_status)
	_criar_barras()
	_criar_textos()
	_criar_tela_morte()
	status.aviso.connect(_mostrar_mensagem)
	status.morreu.connect(func(): tela_morte.visible = true)
	status.renasceu.connect(func(): tela_morte.visible = false)


func _process(delta: float) -> void:
	barras.vida.value = status.vida
	barras.fome.value = status.fome
	barras.sede.value = status.sede

	match "" if status.morto else status.o_que_tem_perto():
		"agua":
			dica.text = "[E] Beber água"
		"frutinhas":
			dica.text = "[E] Comer frutinhas"
		_:
			dica.text = ""

	tempo_mensagem -= delta
	mensagem.modulate.a = clampf(tempo_mensagem, 0.0, 1.0)   # some devagar


func _mostrar_mensagem(texto: String) -> void:
	mensagem.text = texto
	tempo_mensagem = 2.5


func _criar_barras() -> void:
	var caixa := VBoxContainer.new()
	caixa.add_theme_constant_override("separation", 8)
	# Presa no canto de baixo à esquerda (mesmo se a janela mudar de tamanho), crescendo para cima
	caixa.anchor_top = 1.0
	caixa.anchor_bottom = 1.0
	caixa.offset_left = 24
	caixa.offset_bottom = -24
	caixa.grow_vertical = Control.GROW_DIRECTION_BEGIN
	add_child(caixa)

	for info in [["vida", "Vida", Color(0.90, 0.25, 0.25)], ["fome", "Fome", Color(0.95, 0.60, 0.20)], ["sede", "Sede", Color(0.25, 0.60, 0.95)]]:
		var linha := HBoxContainer.new()
		linha.add_theme_constant_override("separation", 10)
		var nome := Label.new()
		nome.text = info[1]
		nome.custom_minimum_size = Vector2(56, 0)
		_contorno(nome, 20)
		linha.add_child(nome)

		var barra := ProgressBar.new()
		barra.custom_minimum_size = Vector2(260, 24)
		barra.max_value = 100.0
		barra.show_percentage = false
		var fundo := StyleBoxFlat.new()
		fundo.bg_color = Color(0, 0, 0, 0.45)
		fundo.set_corner_radius_all(4)
		var cheio := StyleBoxFlat.new()
		cheio.bg_color = info[2]
		cheio.set_corner_radius_all(4)
		barra.add_theme_stylebox_override("background", fundo)
		barra.add_theme_stylebox_override("fill", cheio)
		linha.add_child(barra)
		caixa.add_child(linha)
		barras[info[0]] = barra


func _criar_textos() -> void:
	dica = Label.new()
	dica.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_contorno(dica, 22)
	dica.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	dica.position += Vector2(-150, 60)
	dica.custom_minimum_size = Vector2(300, 0)
	add_child(dica)

	mensagem = Label.new()
	mensagem.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_contorno(mensagem, 22)
	mensagem.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	mensagem.position += Vector2(-250, 70)
	mensagem.custom_minimum_size = Vector2(500, 0)
	add_child(mensagem)


func _criar_tela_morte() -> void:
	tela_morte = ColorRect.new()
	tela_morte.color = Color(0.35, 0.0, 0.0, 0.6)
	tela_morte.set_anchors_preset(Control.PRESET_FULL_RECT)
	tela_morte.visible = false
	var texto := Label.new()
	texto.text = "VOCÊ MORREU\n\nAperte Enter para renascer"
	texto.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	texto.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	texto.set_anchors_preset(Control.PRESET_FULL_RECT)
	_contorno(texto, 36)
	tela_morte.add_child(texto)
	add_child(tela_morte)


func _contorno(rotulo: Label, tamanho: int) -> void:
	rotulo.add_theme_font_size_override("font_size", tamanho)
	rotulo.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	rotulo.add_theme_constant_override("outline_size", 6)
