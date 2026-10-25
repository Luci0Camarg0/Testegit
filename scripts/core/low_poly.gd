extends RefCounted
## Funções de ajuda para criar coisas no estilo low poly (facetado).
## Para usar em outro script, coloque no topo dele:
##     const LowPoly = preload("res://scripts/core/low_poly.gd")
## (Não usamos "class_name" porque ele não funciona bem com as atualizações automáticas.)


## Recebe uma malha simples (caixa, cilindro, esfera...) e devolve a mesma forma
## com cada triângulo "chapado", sem suavização. É isso que dá o visual facetado.
static func facetar(malha: PrimitiveMesh) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	adicionar_forma(st, malha, Color.WHITE)
	return st.commit()


## Junta várias formas coloridas em um único modelo (ex.: tronco + copa = árvore).
## Cada parte é [forma, cor, posição, escala]. Um modelo só = desenho bem mais leve.
static func modelo(partes: Array) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for parte in partes:
		var escala: Vector3 = parte[3] if parte.size() > 3 else Vector3.ONE
		var t := Transform3D(Basis.from_scale(escala), parte[2])
		adicionar_forma(st, parte[0], parte[1], t)
	return st.commit()


## Copia os triângulos de uma forma simples para o SurfaceTool, já movida/escalada e pintada.
static func adicionar_forma(st: SurfaceTool, malha: PrimitiveMesh, cor: Color, t := Transform3D.IDENTITY) -> void:
	var dados := malha.get_mesh_arrays()
	var vertices: PackedVector3Array = dados[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = dados[Mesh.ARRAY_INDEX]
	for i in range(0, indices.size(), 3):
		adicionar_triangulo(st, t * vertices[indices[i]], t * vertices[indices[i + 1]], t * vertices[indices[i + 2]], cor)


## Adiciona um triângulo com uma única normal (a direção para onde a face "olha").
## Na Godot, a frente do triângulo é o lado em que os vértices aparecem no sentido horário.
static func adicionar_triangulo(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, cor := Color.WHITE) -> void:
	var normal := (c - a).cross(b - a).normalized()
	for v in [a, b, c]:
		st.set_color(cor)
		st.set_normal(normal)
		st.add_vertex(v)


## Material de cor sólida e fosca, como no estilo da imagem de referência.
static func material(cor: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = cor
	mat.roughness = 1.0
	return mat


## Material que usa as cores pintadas em cada triângulo (para modelos e terreno).
static func material_colorido() -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.roughness = 1.0
	return mat


## Cria uma peça pronta: forma facetada + cor + posição.
static func peca(malha: PrimitiveMesh, cor: Color, posicao := Vector3.ZERO, rotacao_graus := Vector3.ZERO) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = facetar(malha)
	mi.material_override = material(cor)
	mi.position = posicao
	mi.rotation_degrees = rotacao_graus
	return mi
