package com.galeria.app

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.PlaylistAdd
import androidx.compose.material.icons.filled.QueueMusic
import androidx.compose.material.icons.filled.Shuffle
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun MusicScreen(store: Store, player: MusicPlayer) {
    val context = LocalContext.current
    val songs by produceState(emptyList<Song>()) {
        value = withContext(Dispatchers.IO) { loadSongs(context) }
    }
    var playlists by remember { mutableStateOf(store.loadPlaylists()) }
    fun update(list: List<Playlist>) { playlists = list; store.savePlaylists(list) }

    var filter by remember { mutableStateOf(0) } // 0 músicas, 1 playlists, 2 artistas
    var openPlaylistId by remember { mutableStateOf<Long?>(null) }
    var addingSong by remember { mutableStateOf<Song?>(null) }
    var creating by remember { mutableStateOf(false) }

    val openPlaylist = playlists.find { it.id == openPlaylistId }
    if (openPlaylist != null) {
        BackHandler { openPlaylistId = null }
        val byId = songs.associateBy { it.id }
        val items = openPlaylist.songIds.mapNotNull { byId[it] }
        Column(Modifier.fillMaxSize()) {
            Text(openPlaylist.name, fontSize = 28.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(16.dp))
            Row(Modifier.padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("${items.size} músicas", color = Color.Gray, modifier = Modifier.weight(1f))
                IconButton(onClick = { update(playlists - openPlaylist); openPlaylistId = null }) {
                    Icon(Icons.Filled.Delete, "Apagar playlist")
                }
                IconButton(
                    onClick = { if (items.isNotEmpty()) player.play(items, 0) },
                    modifier = Modifier.clip(RoundedCornerShape(50)).background(SpotifyGreen),
                ) { Icon(Icons.Filled.PlayArrow, "Tocar", tint = Color.Black) }
            }
            if (items.isEmpty()) Text(
                "Vazia. Na aba Músicas, toque no + de uma música para adicionar aqui.",
                color = Color.Gray, modifier = Modifier.padding(16.dp),
            )
            LazyColumn {
                itemsIndexed(items) { i, song ->
                    SongRow(song, onClick = { player.play(items, i) }) {
                        IconButton(onClick = {
                            update(playlists.map { if (it.id == openPlaylist.id) it.copy(songIds = it.songIds - song.id) else it })
                        }) { Icon(Icons.Filled.Delete, "Remover") }
                    }
                }
            }
        }
        return
    }

    Column(Modifier.fillMaxSize()) {
        Text("Sua Biblioteca", fontSize = 24.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(16.dp))
        Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Músicas", "Playlists", "Artistas").forEachIndexed { i, label ->
                FilterChip(selected = filter == i, onClick = { filter = i }, label = { Text(label) })
            }
        }
        when (filter) {
            0 -> {
                if (songs.isEmpty()) Text(
                    "Nenhuma música encontrada nos arquivos do celular.",
                    color = Color.Gray, modifier = Modifier.padding(16.dp),
                )
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = { if (songs.isNotEmpty()) { if (!player.shuffle) player.toggleShuffle(); player.play(songs, 0) } }) {
                        Icon(Icons.Filled.Shuffle, null); Spacer(Modifier.width(4.dp)); Text("Aleatório")
                    }
                }
                LazyColumn {
                    itemsIndexed(songs, key = { _, s -> s.id }) { i, song ->
                        SongRow(song, onClick = { player.play(songs, i) }) {
                            IconButton(onClick = { addingSong = song }) { Icon(Icons.Filled.PlaylistAdd, "Adicionar à playlist") }
                        }
                    }
                }
            }
            1 -> LazyColumn {
                item {
                    Row(
                        Modifier.fillMaxWidth().clickable { creating = true }.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Filled.Add, null, tint = SpotifyGreen)
                        Spacer(Modifier.width(12.dp))
                        Text("Criar playlist", color = SpotifyGreen, fontWeight = FontWeight.Bold)
                    }
                }
                items(playlists, key = { it.id }) { p ->
                    Row(
                        Modifier.fillMaxWidth().clickable { openPlaylistId = p.id }.padding(16.dp, 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(
                            Modifier.size(48.dp).clip(RoundedCornerShape(4.dp)).background(MaterialTheme.colorScheme.surfaceVariant),
                            contentAlignment = Alignment.Center,
                        ) { Icon(Icons.Filled.QueueMusic, null) }
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(p.name, fontWeight = FontWeight.SemiBold)
                            Text("Playlist • ${p.songIds.size} músicas", color = Color.Gray, fontSize = 13.sp)
                        }
                    }
                }
            }
            else -> {
                val byArtist = remember(songs) { songs.groupBy { it.artist }.toSortedMap() }
                LazyColumn {
                    byArtist.forEach { (artist, list) ->
                        item {
                            Text(artist, fontWeight = FontWeight.Bold, modifier = Modifier.padding(16.dp, 12.dp, 16.dp, 4.dp))
                        }
                        itemsIndexed(list) { i, song -> SongRow(song, onClick = { player.play(list, i) }) {} }
                    }
                }
            }
        }
    }

    if (creating) NameDialog("Nova playlist", onDismiss = { creating = false }) { name ->
        update(playlists + Playlist(System.currentTimeMillis(), name, emptyList()))
        creating = false
    }

    addingSong?.let { song ->
        AlertDialog(
            onDismissRequest = { addingSong = null },
            title = { Text("Adicionar \"${song.title}\" a…") },
            text = {
                Column {
                    if (playlists.isEmpty()) Text("Você ainda não tem playlists.")
                    playlists.forEach { p ->
                        Text(
                            p.name,
                            modifier = Modifier.fillMaxWidth().clickable {
                                if (song.id !in p.songIds) {
                                    update(playlists.map { if (it.id == p.id) it.copy(songIds = it.songIds + song.id) else it })
                                }
                                addingSong = null
                            }.padding(vertical = 12.dp),
                        )
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { creating = true }) { Text("Nova playlist") }
            },
            dismissButton = { TextButton(onClick = { addingSong = null }) { Text("Cancelar") } },
        )
    }
}

@Composable
fun SongRow(song: Song, onClick: () -> Unit, trailing: @Composable () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp, 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AlbumArt(song, 48)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(song.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(song.artist, color = Color.Gray, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        trailing()
    }
}

@Composable
fun AlbumArt(song: Song, sizeDp: Int) {
    Box(
        Modifier.size(sizeDp.dp).clip(RoundedCornerShape(4.dp)).background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        Icon(Icons.Filled.MusicNote, null, tint = Color.Gray)
        AsyncImage(song.albumArt, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
    }
}

@Composable
fun MiniPlayer(player: MusicPlayer) {
    val song = player.current ?: return
    Row(
        Modifier.fillMaxWidth().padding(8.dp, 4.dp).clip(RoundedCornerShape(8.dp))
            .background(Color(0xFF3A2A2A)).padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AlbumArt(song, 40)
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(song.title, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(song.artist, maxLines = 1, color = Color.LightGray, fontSize = 12.sp)
        }
        IconButton(onClick = player::toggleShuffle) {
            Icon(Icons.Filled.Shuffle, "Aleatório", tint = if (player.shuffle) SpotifyGreen else Color.White)
        }
        IconButton(onClick = player::previous) { Icon(Icons.Filled.SkipPrevious, "Anterior") }
        IconButton(onClick = player::toggle) {
            Icon(if (player.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow, "Tocar/pausar")
        }
        IconButton(onClick = player::next) { Icon(Icons.Filled.SkipNext, "Próxima") }
    }
}

@Composable
fun NameDialog(title: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var text by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { OutlinedTextField(text, { text = it }, singleLine = true, placeholder = { Text("Nome") }) },
        confirmButton = { TextButton(onClick = { if (text.isNotBlank()) onConfirm(text.trim()) }) { Text("Criar") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}
