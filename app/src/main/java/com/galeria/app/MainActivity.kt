package com.galeria.app

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Photo
import androidx.compose.material.icons.filled.StickyNote2
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import coil.Coil
import coil.ImageLoader
import coil.decode.VideoFrameDecoder

val SpotifyGreen = Color(0xFF1DB954)

class MainActivity : ComponentActivity() {
    private lateinit var player: MusicPlayer

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Coil.setImageLoader(ImageLoader.Builder(this).components { add(VideoFrameDecoder.Factory()) }.build())
        player = MusicPlayer(this)
        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = SpotifyGreen,
                    background = Color(0xFF121212),
                    surface = Color(0xFF181818),
                    surfaceVariant = Color(0xFF282828),
                ),
            ) { App(player) }
        }
    }

    override fun onDestroy() {
        player.release()
        super.onDestroy()
    }
}

private fun mediaPermissions(): Array<String> =
    if (Build.VERSION.SDK_INT >= 33) arrayOf(
        Manifest.permission.READ_MEDIA_IMAGES,
        Manifest.permission.READ_MEDIA_VIDEO,
        Manifest.permission.READ_MEDIA_AUDIO,
    ) else arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)

@Composable
fun App(player: MusicPlayer) {
    val context = LocalContext.current
    val store = remember { Store(context) }
    var granted by remember { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        granted = it.values.any { ok -> ok }
    }
    LaunchedEffect(Unit) { launcher.launch(mediaPermissions()) }

    var tab by rememberSaveable { mutableIntStateOf(0) }
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            Column {
                MiniPlayer(player)
                NavigationBar(containerColor = Color.Black) {
                    NavigationBarItem(tab == 0, { tab = 0 }, { Icon(Icons.Filled.Photo, null) }, label = { Text("Fotos") })
                    NavigationBarItem(tab == 1, { tab = 1 }, { Icon(Icons.Filled.MusicNote, null) }, label = { Text("Músicas") })
                    NavigationBarItem(tab == 2, { tab = 2 }, { Icon(Icons.Filled.StickyNote2, null) }, label = { Text("Notas") })
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when {
                tab == 2 -> NotesScreen(store)
                !granted -> Column(Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Preciso de acesso às suas fotos e músicas")
                    Button(onClick = { launcher.launch(mediaPermissions()) }, modifier = Modifier.padding(top = 12.dp)) {
                        Text("Permitir acesso")
                    }
                }
                tab == 0 -> PhotosScreen()
                else -> MusicScreen(store, player)
            }
        }
    }
}
