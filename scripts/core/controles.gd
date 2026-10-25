extends RefCounted
## Cria os controles do jogo por código.
## Assim, quando uma atualização trouxer um controle novo, ele já funciona
## sem precisar baixar o .exe de novo.

const TECLAS := {
	"move_forward": KEY_W,
	"move_back": KEY_S,
	"move_left": KEY_A,
	"move_right": KEY_D,
	"jump": KEY_SPACE,
	"sprint": KEY_SHIFT,
	"acelerar_tempo": KEY_T,   # segure T para o tempo passar rápido (para testar o dia e a noite)
}


static func registrar() -> void:
	for acao in TECLAS:
		if InputMap.has_action(acao):
			continue
		InputMap.add_action(acao)
		var tecla := InputEventKey.new()
		tecla.physical_keycode = TECLAS[acao]
		InputMap.action_add_event(acao, tecla)
