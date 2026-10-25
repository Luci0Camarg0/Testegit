shader_type sky;
// Céu do jogo: degradê, sol, lua e estrelas. Leve, sem nenhuma imagem.
// As cores e direções são trocadas o tempo todo pelo script do dia e noite.

uniform vec3 cor_topo : source_color = vec3(0.30, 0.58, 0.95);
uniform vec3 cor_horizonte : source_color = vec3(0.72, 0.87, 1.0);
uniform vec3 cor_sol : source_color = vec3(1.0, 0.95, 0.80);
uniform vec3 direcao_sol = vec3(0.0, 1.0, 0.0);   // para onde olhar para ver o sol
uniform vec3 direcao_lua = vec3(0.0, -1.0, 0.0);
uniform float estrelas : hint_range(0.0, 1.0) = 0.0;   // 0 = dia, 1 = noite cheia de estrelas

float aleatorio(vec3 p) {
	p = fract(p * 0.3183099 + 0.1);
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

void sky() {
	vec3 olhar = EYEDIR;
	float altura = max(olhar.y, 0.0);
	vec3 cor = mix(cor_horizonte, cor_topo, smoothstep(0.0, 0.5, altura));

	// Sol: um disco + um brilho em volta
	float sol = dot(olhar, normalize(direcao_sol));
	cor += cor_sol * smoothstep(0.9985, 0.9990, sol);
	cor += cor_sol * pow(max(sol, 0.0), 10.0) * 0.25;

	// Lua: disco branco-azulado
	float lua = dot(olhar, normalize(direcao_lua));
	cor += vec3(0.85, 0.90, 1.0) * smoothstep(0.9990, 0.9994, lua);

	// Estrelas: pontinhos quadrados (combina com o low poly), só acima do horizonte
	if (estrelas > 0.0) {
		float sorteio = aleatorio(floor(olhar * 140.0));
		cor += vec3(step(0.988, sorteio)) * estrelas * smoothstep(0.0, 0.15, altura);
	}
	COLOR = cor;
}
