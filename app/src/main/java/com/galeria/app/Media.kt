package com.galeria.app

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.provider.MediaStore

data class Photo(val id: Long, val uri: Uri, val isVideo: Boolean, val dateTaken: Long)

data class Song(
    val id: Long,
    val uri: Uri,
    val title: String,
    val artist: String,
    val album: String,
    val albumArt: Uri,
    val durationMs: Long,
)

/** Lê fotos e vídeos do celular, mais recentes primeiro. */
fun loadPhotos(context: Context): List<Photo> {
    val collection = MediaStore.Files.getContentUri("external")
    val projection = arrayOf(
        MediaStore.Files.FileColumns._ID,
        MediaStore.Files.FileColumns.MEDIA_TYPE,
        MediaStore.Files.FileColumns.DATE_ADDED,
    )
    val selection = "${MediaStore.Files.FileColumns.MEDIA_TYPE} IN (" +
        "${MediaStore.Files.FileColumns.MEDIA_TYPE_IMAGE}, ${MediaStore.Files.FileColumns.MEDIA_TYPE_VIDEO})"
    val result = mutableListOf<Photo>()
    context.contentResolver.query(
        collection, projection, selection, null,
        "${MediaStore.Files.FileColumns.DATE_ADDED} DESC",
    )?.use { c ->
        val idCol = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns._ID)
        val typeCol = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns.MEDIA_TYPE)
        val dateCol = c.getColumnIndexOrThrow(MediaStore.Files.FileColumns.DATE_ADDED)
        while (c.moveToNext()) {
            val id = c.getLong(idCol)
            val isVideo = c.getInt(typeCol) == MediaStore.Files.FileColumns.MEDIA_TYPE_VIDEO
            val base = if (isVideo) MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            else MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            result += Photo(id, ContentUris.withAppendedId(base, id), isVideo, c.getLong(dateCol) * 1000)
        }
    }
    return result
}

/** Lê as músicas salvas nos arquivos do celular (MP3, M4A, etc). */
fun loadSongs(context: Context): List<Song> {
    val projection = arrayOf(
        MediaStore.Audio.Media._ID,
        MediaStore.Audio.Media.TITLE,
        MediaStore.Audio.Media.ARTIST,
        MediaStore.Audio.Media.ALBUM,
        MediaStore.Audio.Media.ALBUM_ID,
        MediaStore.Audio.Media.DURATION,
    )
    val result = mutableListOf<Song>()
    context.contentResolver.query(
        MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, projection,
        "${MediaStore.Audio.Media.IS_MUSIC} != 0", null,
        "${MediaStore.Audio.Media.TITLE} COLLATE NOCASE ASC",
    )?.use { c ->
        val idCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
        val titleCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.TITLE)
        val artistCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.ARTIST)
        val albumCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM)
        val albumIdCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM_ID)
        val durCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
        while (c.moveToNext()) {
            val id = c.getLong(idCol)
            result += Song(
                id = id,
                uri = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, id),
                title = c.getString(titleCol) ?: "Sem título",
                artist = c.getString(artistCol)?.takeIf { it != "<unknown>" } ?: "Artista desconhecido",
                album = c.getString(albumCol) ?: "",
                albumArt = ContentUris.withAppendedId(
                    Uri.parse("content://media/external/audio/albumart"), c.getLong(albumIdCol),
                ),
                durationMs = c.getLong(durCol),
            )
        }
    }
    return result
}
