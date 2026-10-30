package com.galeria.app

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.PushPin
import androidx.compose.material.icons.outlined.PushPin
import androidx.compose.material3.Card
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.TextStyle

@Composable
fun NotesScreen(store: Store) {
    var notes by remember { mutableStateOf(store.loadNotes()) }
    fun update(list: List<Note>) { notes = list; store.saveNotes(list) }
    var editing by remember { mutableStateOf<Note?>(null) }
    var query by remember { mutableStateOf("") }

    editing?.let { note ->
        NoteEditor(note, onClose = { edited ->
            val others = notes.filter { it.id != edited.id }
            update(if (edited.title.isBlank() && edited.body.isBlank()) others else others + edited)
            editing = null
        }, onDelete = {
            update(notes.filter { it.id != note.id }); editing = null
        })
        return
    }

    val shown = notes
        .filter { query.isBlank() || it.title.contains(query, true) || it.body.contains(query, true) }
        .sortedWith(compareByDescending<Note> { it.pinned }.thenByDescending { it.updatedAt })

    Box(Modifier.fillMaxSize()) {
        Column {
            Text("Notas", fontSize = 24.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(16.dp))
            OutlinedTextField(
                query, { query = it }, placeholder = { Text("Pesquisar notas") }, singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            )
            LazyColumn(Modifier.padding(top = 8.dp)) {
                items(shown, key = { it.id }) { note ->
                    Card(Modifier.fillMaxWidth().padding(16.dp, 6.dp).clickable { editing = note }) {
                        Column(Modifier.padding(14.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    note.title.ifBlank { "Sem título" }, fontWeight = FontWeight.Bold,
                                    modifier = Modifier.weight(1f),
                                )
                                if (note.pinned) Icon(Icons.Filled.PushPin, null, tint = SpotifyGreen)
                            }
                            Text(note.body, color = Color.Gray, maxLines = 3, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = { editing = Note(System.currentTimeMillis(), "", "", false, System.currentTimeMillis()) },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        ) { Icon(Icons.Filled.Add, "Nova nota") }
    }
}

@Composable
private fun NoteEditor(note: Note, onClose: (Note) -> Unit, onDelete: () -> Unit) {
    var title by remember { mutableStateOf(note.title) }
    var body by remember { mutableStateOf(note.body) }
    var pinned by remember { mutableStateOf(note.pinned) }
    fun close() = onClose(note.copy(title = title, body = body, pinned = pinned, updatedAt = System.currentTimeMillis()))
    BackHandler { close() }

    val colors = TextFieldDefaults.colors(
        focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent,
        focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent,
    )
    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { close() }) { Icon(Icons.Filled.ArrowBack, "Voltar") }
            Box(Modifier.weight(1f))
            IconButton(onClick = { pinned = !pinned }) {
                Icon(if (pinned) Icons.Filled.PushPin else Icons.Outlined.PushPin, "Fixar")
            }
            IconButton(onClick = onDelete) { Icon(Icons.Filled.Delete, "Apagar") }
        }
        TextField(
            title, { title = it }, placeholder = { Text("Título") }, colors = colors,
            textStyle = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color.White),
            modifier = Modifier.fillMaxWidth(),
        )
        TextField(
            body, { body = it }, placeholder = { Text("Escreva aqui…") }, colors = colors,
            modifier = Modifier.fillMaxSize(),
        )
    }
}
