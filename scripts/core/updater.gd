extends Control
## Atualizador automático. É a primeira tela que abre.
## 1. Pergunta ao servidor (GitHub) qual é a versão mais nova do jogo.
## 2. Se for mais nova que a instalada, baixa só o pacote do jogo (.pck, poucos KB).
## 3. Carrega o pacote e abre o jogo. Sem internet, abre a última versão baixada.

## Versão que vem dentro do .exe. Aumente a cada .exe novo.
const VERSAO_EMBUTIDA := 3

## Endereço da pasta de atualizações no GitHub (ramo "sobrevivencia-lowpoly" do repositório Testegit).
const URL_PADRAO := "https://raw.githubusercontent.com/Luci0Camarg0/Testegit/sobrevivencia-lowpoly/atualizacoes/"

const PASTA := "user://atualizacoes/"
const ARQUIVO_INSTALADA := "user://atualizacoes/instalada.json"
const CENA_JOGO := "res://scenes/main/main.tscn"
const TEMPO_LIMITE := 6.0   # segundos esperando o servidor antes de desistir

var url_base := URL_PADRAO
var http: HTTPRequest
var texto: Label
var barra: ProgressBar
var baixando := {}


func _ready() -> void:
	# Para testes: dá para trocar o endereço com a variável de ambiente ATUALIZADOR_URL
	if OS.get_environment("ATUALIZADOR_URL") != "":
		url_base = OS.get_environment("ATUALIZADOR_URL")
	_criar_tela()
	DirAccess.make_dir_recursive_absolute(PASTA)
	http = HTTPRequest.new()
	http.timeout = TEMPO_LIMITE
	add_child(http)
	_verificar()


func _verificar() -> void:
	texto.text = "Procurando atualizações..."
	http.request_completed.connect(_recebeu_versao, CONNECT_ONE_SHOT)
	if http.request(url_base + "versao.json?t=%d" % Time.get_unix_time_from_system()) != OK:
		_iniciar_jogo("Sem conexão. Abrindo a versão instalada.")


func _recebeu_versao(resultado: int, codigo: int, _cabecalhos, corpo: PackedByteArray) -> void:
	if resultado != HTTPRequest.RESULT_SUCCESS or codigo != 200:
		_iniciar_jogo("Sem conexão com o servidor. Abrindo a versão instalada.")
		return
	var info = JSON.parse_string(corpo.get_string_from_utf8())
	if typeof(info) != TYPE_DICTIONARY or not info.has("versao") or not info.has("arquivo"):
		_iniciar_jogo("Resposta estranha do servidor. Abrindo a versão instalada.")
		return
	if int(info.versao) <= versao_instalada():
		_iniciar_jogo("O jogo já está atualizado.")
		return

	# Tem versão nova: baixa o pacote para a pasta de atualizações
	baixando = info
	texto.text = "Baixando a versão %d...\n%s" % [int(info.versao), info.get("notas", "")]
	barra.visible = true
	http.timeout = 0   # download pode demorar mais
	http.download_file = PASTA + str(info.arquivo) + ".parcial"
	http.request_completed.connect(_terminou_download, CONNECT_ONE_SHOT)
	http.request(url_base + str(info.arquivo))


func _terminou_download(resultado: int, codigo: int, _cabecalhos, _corpo) -> void:
	var parcial := PASTA + str(baixando.arquivo) + ".parcial"
	if resultado != HTTPRequest.RESULT_SUCCESS or codigo != 200:
		DirAccess.remove_absolute(parcial)
		_iniciar_jogo("O download falhou. Abrindo a versão instalada.")
		return
	# Só troca a versão depois que o arquivo chegou inteiro
	var antiga := _ler_instalada()
	DirAccess.rename_absolute(parcial, PASTA + str(baixando.arquivo))
	var arquivo := FileAccess.open(ARQUIVO_INSTALADA, FileAccess.WRITE)
	arquivo.store_string(JSON.stringify({"versao": int(baixando.versao), "arquivo": str(baixando.arquivo)}))
	arquivo.close()
	if antiga.has("arquivo") and str(antiga.arquivo) != str(baixando.arquivo):
		DirAccess.remove_absolute(PASTA + str(antiga.arquivo))   # apaga o pacote velho
	_iniciar_jogo("Atualizado para a versão %d!" % int(baixando.versao))


func _process(_delta: float) -> void:
	if barra and barra.visible and http.get_body_size() > 0:
		barra.value = 100.0 * http.get_downloaded_bytes() / http.get_body_size()


func versao_instalada() -> int:
	return maxi(VERSAO_EMBUTIDA, int(_ler_instalada().get("versao", 0)))


func _ler_instalada() -> Dictionary:
	if not FileAccess.file_exists(ARQUIVO_INSTALADA):
		return {}
	var info = JSON.parse_string(FileAccess.get_file_as_string(ARQUIVO_INSTALADA))
	return info if typeof(info) == TYPE_DICTIONARY else {}


func _iniciar_jogo(mensagem: String) -> void:
	print(mensagem)
	texto.text = mensagem
	# Se existe um pacote baixado mais novo que o .exe, carrega por cima do jogo embutido
	var instalada := _ler_instalada()
	if int(instalada.get("versao", 0)) > VERSAO_EMBUTIDA and FileAccess.file_exists(PASTA + str(instalada.arquivo)):
		if ProjectSettings.load_resource_pack(PASTA + str(instalada.arquivo), true):
			print("Usando a versão baixada ", instalada.versao)
		else:
			print("Pacote baixado com problema; usando a versão do .exe")
	await get_tree().create_timer(0.6).timeout   # dá tempo de ler a mensagem
	get_tree().change_scene_to_file(CENA_JOGO)


func _criar_tela() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	var fundo := ColorRect.new()
	fundo.color = Color(0.13, 0.32, 0.22)
	fundo.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(fundo)

	var caixa := VBoxContainer.new()
	caixa.set_anchors_preset(Control.PRESET_CENTER)
	caixa.custom_minimum_size = Vector2(520, 0)
	caixa.position = Vector2(-260, -60)
	caixa.add_theme_constant_override("separation", 16)
	add_child(caixa)

	var titulo := Label.new()
	titulo.text = "SOBREVIVÊNCIA LOW POLY"
	titulo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	titulo.add_theme_font_size_override("font_size", 34)
	caixa.add_child(titulo)

	texto = Label.new()
	texto.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	texto.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	texto.add_theme_font_size_override("font_size", 18)
	caixa.add_child(texto)

	barra = ProgressBar.new()
	barra.custom_minimum_size = Vector2(0, 22)
	barra.visible = false
	caixa.add_child(barra)
