package com.galeria.app

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer

/** Toca as músicas do celular numa fila, como no Spotify. */
class MusicPlayer(context: Context) {
    private val exo = ExoPlayer.Builder(context).build()
    private var queue: List<Song> = emptyList()

    var current by mutableStateOf<Song?>(null)
        private set
    var isPlaying by mutableStateOf(false)
        private set
    var shuffle by mutableStateOf(false)
        private set

    init {
        exo.addListener(object : Player.Listener {
            override fun onIsPlayingChanged(playing: Boolean) { isPlaying = playing }
            override fun onMediaItemTransition(item: MediaItem?, reason: Int) {
                current = queue.getOrNull(exo.currentMediaItemIndex)
            }
        })
    }

    fun play(songs: List<Song>, start: Int) {
        queue = songs
        exo.setMediaItems(songs.map { MediaItem.fromUri(it.uri) }, start, 0)
        exo.prepare()
        exo.play()
        current = songs.getOrNull(start)
    }

    fun toggle() = if (exo.isPlaying) exo.pause() else exo.play()
    fun next() = exo.seekToNextMediaItem()
    fun previous() = exo.seekToPreviousMediaItem()
    fun toggleShuffle() { shuffle = !shuffle; exo.shuffleModeEnabled = shuffle }
    fun release() = exo.release()
}
